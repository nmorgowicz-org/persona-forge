"""Kitten TTS 2 engine pack provisioner (Phase C4).

Builds ``<packs_root>/kitten2``: a private virtualenv with ``kittenml`` and the right torch build,
the model weights in ``hf/``, and a ``manifest.json`` marking it as provisioned. The install runs
as one background job with step-by-step progress, because a real install (packages plus about
2.4 GB of weights) outlives a web request.

Nothing here imports torch or kittenml; the work happens in the pack's own interpreter.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from persona_forge import accelerator_manifest, engine_packs, install_check

ENGINE_ID = "kitten2"
PACK_VERSION = "1"
KITTENML_VERSION = "0.9.6"
# Windows needs Triton for fast mode; Linux gets it with torch. Installing it is harmless without
# a compiler: the worker falls back to standard mode and says why.
TRITON_WINDOWS = "triton-windows==3.8.0.post29"
PACK_PYTHON = "3.12"  # the version every benchmark ran on
STEP_TAIL_CHARS = 600


# Run inside the pack. Fails when the installed torch has no kernels for this GPU, which import
# checks cannot see: such a build loads fine and breaks on the first synthesis.
_CHECK_SCRIPT = (
    "import kittenml, torch\n"
    "assert torch.cuda.is_available(), 'torch cannot see the GPU'\n"
    "major, minor = torch.cuda.get_device_capability(0)\n"
    "arch = f'sm_{major}{minor}'\n"
    "archs = torch.cuda.get_arch_list()\n"
    "assert arch in archs or f'compute_{major}{minor}' in archs, "
    "f'torch {torch.__version__} has no kernels for {arch} (has {archs})'\n"
)


class UnsupportedMachine(RuntimeError):
    """Kitten TTS 2 cannot run here; the message says what would be needed."""


@dataclass(frozen=True)
class Target:
    kind: str  # "mlx" | "cuda"
    pin: accelerator_manifest.AcceleratorPin | None = None

    @property
    def runtime(self) -> str:
        return "python-mlx" if self.kind == "mlx" else "python-cuda"


def _nvidia_smi(args: Sequence[str]) -> str | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", *args], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


_CUDA_BANNER = re.compile(r"CUDA\s+(?:UMD\s+)?Version:\s*(\d+)")


def parse_cuda_major(banner: str | None, driver_version: str | None = None) -> int | None:
    """Driver CUDA major from the ``nvidia-smi`` banner, else inferred from the driver version.

    Newer drivers print ``CUDA UMD Version: 13.4`` where older ones printed ``CUDA Version:``.
    The fallback maps the driver release to the CUDA generation it ships with.
    """
    if banner:
        match = _CUDA_BANNER.search(banner)
        if match:
            return int(match.group(1))
    if driver_version:
        try:
            release = int(driver_version.strip().split(".")[0])
        except ValueError:
            return None
        if release >= 580:
            return 13
        if release >= 525:
            return 12
    return None


def _cuda_facts() -> tuple[tuple[int, int] | None, int | None]:
    """(compute capability, driver CUDA major) from nvidia-smi, or Nones."""
    capability: tuple[int, int] | None = None
    cap_text = _nvidia_smi(["--query-gpu=compute_cap", "--format=csv,noheader"])
    if cap_text and cap_text.strip():
        first = cap_text.strip().splitlines()[0].strip()
        try:
            left, _, right = first.partition(".")
            capability = (int(left), int(right or 0))
        except ValueError:
            capability = None
    driver = _nvidia_smi(["--query-gpu=driver_version", "--format=csv,noheader"])
    driver_version = driver.strip().splitlines()[0] if driver and driver.strip() else None
    return capability, parse_cuda_major(_nvidia_smi([]), driver_version)


def detect_target(
    platform: str | None = None,
    machine: str | None = None,
    cuda_facts: Callable[[], tuple[tuple[int, int] | None, int | None]] = _cuda_facts,
) -> Target:
    import platform as py_platform

    platform = platform or sys.platform
    machine = machine or py_platform.machine()
    if platform == "darwin":
        if machine in ("arm64", "aarch64"):
            return Target("mlx")
        raise UnsupportedMachine(
            "Kitten TTS 2 needs an Apple silicon Mac; Intel Macs are not supported."
        )
    capability, major = cuda_facts()
    if capability is None:
        raise UnsupportedMachine(
            "Kitten TTS 2 needs an NVIDIA GPU (or an Apple silicon Mac). "
            "No NVIDIA GPU was found, and CPU-only runs are too slow to use."
        )
    pin = accelerator_manifest.select_cuda_pin(capability, major)
    if capability >= (10, 0) and pin.extra == "cuda12":
        # The cu126 wheels carry no Blackwell kernels, so the install would "work" and then fail
        # on first use. Refuse now with the reason instead.
        raise UnsupportedMachine(
            "This GPU (compute capability "
            f"{capability[0]}.{capability[1]}) needs the CUDA 13 runtime, but the NVIDIA driver "
            "could not be confirmed as CUDA 13 capable. Update the NVIDIA driver and try again."
        )
    return Target("cuda", pin)


def torch_requirements(target: Target) -> tuple[list[str], str | None]:
    """Torch packages and the index they must come from (None means PyPI)."""
    if target.kind == "mlx" or target.pin is None:
        return [], None
    pin = target.pin
    return [f"torch=={pin.torch_version}", f"torchaudio=={pin.torchaudio_version}"], pin.index_url


def package_requirements(target: Target, platform: str | None = None) -> list[str]:
    platform = platform or sys.platform
    if target.kind == "mlx":
        return [f"kittenml[mlx]=={KITTENML_VERSION}"]
    requirements = [f"kittenml=={KITTENML_VERSION}"]
    if platform == "win32":
        requirements.append(TRITON_WINDOWS)
    return requirements


def build_manifest(target: Target, platform: str | None = None) -> dict[str, Any]:
    torch_pkgs, torch_index = torch_requirements(target)
    return {
        "id": ENGINE_ID,
        "engine_id": ENGINE_ID,
        "version": PACK_VERSION,
        "label": "Kitten TTS 2",
        "description": "Cloning and 115 built-in voices. Runs in its own private environment.",
        "runtime": target.runtime,
        "provisioner": ENGINE_ID,
        "requirements": [*torch_pkgs, *package_requirements(target, platform)],
        "torch_index": torch_index,
        "artifacts": [],
    }


# -- paths -------------------------------------------------------------------------------------


def pack_dir(root: Path | None = None) -> Path:
    return (root or engine_packs.packs_root()) / ENGINE_ID


def venv_python(directory: Path, platform: str | None = None) -> Path:
    platform = platform or sys.platform
    return directory / "venv" / ("Scripts/python.exe" if platform == "win32" else "bin/python")


def weights_dir(directory: Path) -> Path:
    return directory / "hf"


# -- command running ---------------------------------------------------------------------------


class StepFailed(RuntimeError):
    pass


def run_command(command: Sequence[str], env: dict[str, str] | None = None) -> None:
    """Run one install command; raise StepFailed with the tail of its output on failure."""
    merged = {**os.environ, **(env or {})}
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            env=merged,
            check=False,
        )
    except OSError as exc:
        raise StepFailed(f"could not run {Path(command[0]).name}: {exc}") from exc
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise StepFailed(output[-STEP_TAIL_CHARS:] or f"exit code {result.returncode}")


def prefetch_weights(python: Path, directory: Path) -> None:
    """Load the model once in the pack interpreter so every weight lands in ``hf/``."""
    from persona_forge import kitten2_worker
    from persona_forge.pack_process import PackProcess, PackProcessError

    hf = weights_dir(directory)
    hf.mkdir(parents=True, exist_ok=True)
    process = PackProcess(
        [str(python), str(Path(kitten2_worker.__file__).resolve())],
        env={"HF_HOME": str(hf)},
        request_timeout=3600,
    )
    try:
        process.start()
        process.request({"op": "load", "cache_dir": str(hf), "warmup": False}, timeout=3600)
    except PackProcessError as exc:
        raise StepFailed(str(exc)) from exc
    finally:
        process.close()


def speed_check_spec(directory: Path, python: Path) -> install_check.SpeedCheckSpec:
    """The worker command and load request the engine adapter uses, for the install speed check.

    ``warmup`` is False so the check sends the compile-heavy first call itself, as the adapter's
    "warming" state does, and keeps it out of the timing.
    """
    from persona_forge import kitten2_worker

    weights = weights_dir(directory)
    return install_check.SpeedCheckSpec(
        command=(str(python), str(Path(kitten2_worker.__file__).resolve())),
        env={"HF_HOME": str(weights), "HF_HUB_OFFLINE": "1"},
        load_request={"op": "load", "warmup": False, "cache_dir": str(weights)},
    )


def find_uv() -> str | None:
    override = os.environ.get("ENGINE_PACKS_UV")
    if override and Path(override).is_file():
        return override
    return shutil.which("uv")


# -- job state ---------------------------------------------------------------------------------


@dataclass
class Job:
    state: str = "idle"  # idle | running | done | error
    step: str = ""
    step_index: int = 0
    step_count: int = 0
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "step": self.step,
            "step_index": self.step_index,
            "step_count": self.step_count,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


_job = Job()
_job_lock = threading.Lock()


def job_status() -> dict[str, Any]:
    with _job_lock:
        return _job.as_dict()


def _set(**changes: Any) -> None:
    with _job_lock:
        for key, value in changes.items():
            setattr(_job, key, value)


def install(
    root: Path | None = None,
    *,
    detect: Callable[[], Target] = detect_target,
    runner: Callable[..., None] = run_command,
    prefetch: Callable[[Path, Path], None] = prefetch_weights,
    uv: str | None = None,
    platform: str | None = None,
    measure: Callable[[install_check.SpeedCheckSpec], dict[str, Any]] | None = None,
) -> None:
    """Provision the pack synchronously. Failures leave the directory so a retry resumes."""
    platform = platform or sys.platform
    uv = uv if uv is not None else find_uv()
    directory = pack_dir(root)
    python = venv_python(directory, platform)
    try:
        target = detect()
    except UnsupportedMachine as exc:
        _set(state="error", error=str(exc), finished_at=time.time())
        return
    torch_pkgs, torch_index = torch_requirements(target)
    packages = package_requirements(target, platform)

    def make_venv() -> None:
        if python.is_file():
            return
        if uv:
            runner([uv, "venv", str(directory / "venv"), "--python", PACK_PYTHON])
        else:
            runner([sys.executable, "-m", "venv", str(directory / "venv")])

    def pip(*args: str) -> list[str]:
        if uv:
            return [uv, "pip", "install", "--python", str(python), *args]
        return [str(python), "-m", "pip", "install", *args]

    steps: list[tuple[str, Callable[[], None]]] = [
        ("Preparing the engine folder", lambda: _write_manifest(directory, target, platform)),
        ("Creating a private Python environment", make_venv),
    ]
    if torch_pkgs and torch_index:
        steps.append(
            (
                "Installing the GPU runtime (large download)",
                lambda: runner(pip("--index-url", torch_index, *torch_pkgs)),
            )
        )
    steps += [
        ("Installing Kitten TTS 2", lambda: runner(pip(*packages))),
        ("Downloading the voice models (about 2.4 GB)", lambda: prefetch(python, directory)),
        (
            "Checking the install",
            lambda: runner([str(python), "-c", _CHECK_SCRIPT if target.kind == "cuda" else "import kittenml"]),
        ),
        (
            "Measuring speed",
            lambda: install_check.check_and_record(directory, speed_check_spec(directory, python), measure),
        ),
        ("Finishing", lambda: _publish(directory)),
    ]
    _set(step_count=len(steps), step_index=0, error=None)
    for index, (label, action) in enumerate(steps, start=1):
        _set(step=label, step_index=index)
        try:
            action()
        except (StepFailed, OSError) as exc:
            _set(state="error", error=f"{label} failed: {exc}", finished_at=time.time())
            return
    _set(state="done", step="Installed", finished_at=time.time())


def _write_manifest(directory: Path, target: Target, platform: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / engine_packs.MANIFEST_FILENAME).write_text(
        json.dumps(build_manifest(target, platform), indent=2), encoding="utf-8"
    )


def _publish(directory: Path) -> None:
    manifest = engine_packs.load_manifest(directory)
    engine_packs._write_verification_stamp(directory, manifest.manifest_sha256)


def start_install(root: Path | None = None, **kwargs: Any) -> bool:
    """Start the install in the background. Returns False when one is already running."""
    with _job_lock:
        if _job.state == "running":
            return False
        _job.state = "running"
        _job.step = "Starting"
        _job.step_index = 0
        _job.step_count = 0
        _job.error = None
        _job.started_at = time.time()
        _job.finished_at = None
    threading.Thread(
        target=install, args=(root,), kwargs=kwargs, name="kitten2-install", daemon=True
    ).start()
    return True


def reset_job() -> None:
    """Forget the last job (used by tests)."""
    with _job_lock:
        _job.__dict__.update(Job().__dict__)

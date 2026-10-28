"""Phonon 31M engine pack provisioner.

Builds ``<packs_root>/phonon-31m``: a private virtualenv with the ``ptts`` wheel (a native
runtime, no torch, no GPU, no compiler), the model and the English voice catalog prefetched into
``hf/``, and a ``manifest.json`` marking it as provisioned. Small enough to install in well under
a minute, but run as the same background job as Kitten 2 so the UI treats both alike.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from persona_forge import engine_packs, install_check, pack_logs
from persona_forge.kitten2_pack import (
    PACK_PYTHON,
    Job,
    StepFailed,
    find_uv,
    run_command,
    venv_python,
)

ENGINE_ID = "phonon-31m"
PACK_VERSION = "1"
# Seconds idle before the worker is stopped; written to the manifest as idle_unload_after.
IDLE_UNLOAD_AFTER_S = 600.0
PTTS_VERSION = "0.4.1"

# Run inside the pack with the network switched off: proves the prefetch is complete and that the
# prebuilt native library runs on this CPU (older x86 processors lack AVX2).
_CHECK_SCRIPT = (
    "import os; os.environ['HF_HUB_OFFLINE']='1'; import ptts; "
    "t=ptts.TTS(ptts.DEFAULT_MODEL, lang='en', quant='q8'); "
    "a=t.synth('Ready.'); assert len(a) > 1000, 'no audio produced'"
)
# Download every English catalog voice (they are a few kilobytes each) so serving never needs
# the network. Voices are fetched lazily on first use, so synthesise one word with each.
_PREFETCH_SCRIPT = (
    "import ptts; t=ptts.TTS(ptts.DEFAULT_MODEL, lang='en', quant='q8'); "
    "names=[v['name'] for v in ptts.catalog_voices() if v.get('language')=='en']; "
    "[t.synth('Hi.', voice=n) for n in names]; print(len(names))"
)


class _Job:
    """Module-level job state, separate from Kitten 2's so both can install at once."""

    def __init__(self) -> None:
        self.job = Job()
        self.lock = threading.Lock()


_state = _Job()


def job_status() -> dict[str, Any]:
    with _state.lock:
        return _state.job.as_dict()


def _set(**changes: Any) -> None:
    with _state.lock:
        for key, value in changes.items():
            setattr(_state.job, key, value)
    pack_logs.record_job_change(changes)


def reset_job() -> None:
    with _state.lock:
        _state.job = Job()


def pack_dir(root: Path | None = None) -> Path:
    return (root or engine_packs.packs_root()) / ENGINE_ID


def weights_dir(directory: Path) -> Path:
    return directory / "hf"


def speed_check_spec(directory: Path, python: Path) -> install_check.SpeedCheckSpec:
    """The worker command and load request the engine adapter uses, for the install speed check."""
    from persona_forge import phonon_worker

    return install_check.SpeedCheckSpec(
        command=(str(python), str(Path(phonon_worker.__file__).resolve())),
        env={"HF_HOME": str(weights_dir(directory)), "HF_HUB_OFFLINE": "1"},
        load_request={"op": "load"},
    )


def build_manifest() -> dict[str, Any]:
    return {
        "id": ENGINE_ID,
        "engine_id": ENGINE_ID,
        "version": PACK_VERSION,
        "label": "Phonon 31M",
        "description": "Very fast English voices on any CPU. Runs in its own private environment.",
        "runtime": "ptts-native-cpu",
        "provisioner": ENGINE_ID,
        "idle_unload_after": IDLE_UNLOAD_AFTER_S,
        "requirements": [f"ptts=={PTTS_VERSION}"],
        "artifacts": [],
    }


def explain_install_failure(label: str, raw: str) -> str:
    """Plain-language reason for a failed step, keeping the raw tail for support."""
    lowered = raw.lower()
    if "no matching distribution" in lowered or "no solution found" in lowered:
        return (
            f"{label} failed: Phonon's prebuilt package does not support this computer's "
            "processor or Python. On Intel and AMD it needs a CPU with AVX2 (about 2013 or "
            f"newer). Details: {raw[-300:]}"
        )
    return f"{label} failed: {raw}"


@pack_logs.logs_install(ENGINE_ID, lambda root: pack_dir(root))
def install(
    root: Path | None = None,
    *,
    runner: Callable[..., None] = run_command,
    uv: str | None = None,
    platform: str | None = None,
    measure: Callable[[install_check.SpeedCheckSpec], dict[str, Any]] | None = None,
) -> None:
    """Provision the pack synchronously. Failures leave the directory so a retry resumes."""
    platform = platform or sys.platform
    uv = uv if uv is not None else find_uv()
    directory = pack_dir(root)
    python = venv_python(directory, platform)
    hf = weights_dir(directory)

    def write_manifest() -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / engine_packs.MANIFEST_FILENAME).write_text(
            json.dumps(build_manifest(), indent=2), encoding="utf-8"
        )

    def make_venv() -> None:
        if python.is_file():
            return
        if uv:
            runner([uv, "venv", str(directory / "venv"), "--python", PACK_PYTHON])
        else:
            runner([sys.executable, "-m", "venv", str(directory / "venv")])

    def install_ptts() -> None:
        spec = f"ptts=={PTTS_VERSION}"
        if uv:
            runner([uv, "pip", "install", "--python", str(python), spec])
        else:
            runner([str(python), "-m", "pip", "install", spec])

    def prefetch() -> None:
        hf.mkdir(parents=True, exist_ok=True)
        runner([str(python), "-c", _PREFETCH_SCRIPT], env={"HF_HOME": str(hf)})

    def check() -> None:
        runner(
            [str(python), "-c", _CHECK_SCRIPT],
            env={"HF_HOME": str(hf), "HF_HUB_OFFLINE": "1"},
        )

    def speed() -> None:
        install_check.check_and_record(directory, speed_check_spec(directory, python), measure)

    def publish() -> None:
        manifest = engine_packs.load_manifest(directory)
        engine_packs._write_verification_stamp(directory, manifest.manifest_sha256)

    steps: list[tuple[str, Callable[[], None]]] = [
        ("Preparing the engine folder", write_manifest),
        ("Creating a private Python environment", make_venv),
        ("Installing Phonon", install_ptts),
        ("Downloading the voices (about 70 MB)", prefetch),
        ("Checking the install", check),
        ("Measuring speed", speed),
        ("Finishing", publish),
    ]
    _set(step_count=len(steps), step_index=0, error=None)
    for index, (label, action) in enumerate(steps, start=1):
        _set(step=label, step_index=index)
        try:
            action()
        except (StepFailed, OSError) as exc:
            _set(
                state="error",
                error=explain_install_failure(label, str(exc)),
                finished_at=time.time(),
            )
            return
    _set(state="done", step="Installed", finished_at=time.time())


def start_install(root: Path | None = None, **kwargs: Any) -> bool:
    """Start the install in the background. Returns False when one is already running."""
    with _state.lock:
        if _state.job.state == "running":
            return False
        _state.job = Job(state="running", step="Starting", started_at=time.time())
    threading.Thread(
        target=install, args=(root,), kwargs=kwargs, name="phonon-install", daemon=True
    ).start()
    return True

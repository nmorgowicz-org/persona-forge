"""Kokoro 82M engine pack provisioner.

Builds ``<packs_root>/kokoro``: a private virtualenv with ``kokoro-onnx`` (which bundles the
espeak-ng phonemizer library in its ``espeakng-loader`` wheel, so nothing is installed system-wide),
the int8 model and voice file downloaded from a pinned release with SHA-256 verification, and a
``manifest.json`` marking it as provisioned.

The int8 model is the default because it is both smaller (92 MB against 326 MB) and was the
faster of the two on the Intel host (RTF 0.64 against 0.70).
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from persona_forge import engine_packs
from persona_forge.kitten2_pack import (
    PACK_PYTHON,
    Job,
    StepFailed,
    find_uv,
    run_command,
    venv_python,
)

ENGINE_ID = "kokoro"
PACK_VERSION = "1"
KOKORO_ONNX_VERSION = "0.6.1"
RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
# (filename, size in bytes, sha256) for the files the worker loads.
MODEL_FILE = (
    "kokoro-v1.0.int8.onnx",
    92361271,
    "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb",
)
VOICES_FILE = (
    "voices-v1.0.bin",
    28214398,
    "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
)

# Run inside the pack: proves the bundled phonemizer library loads and the model synthesises, with
# no system espeak-ng on the path.
_CHECK_SCRIPT = (
    "import sys, numpy as np; sys.path.insert(0, sys.argv[1]); "
    "import kokoro_worker as w; k = w.KokoroWorker(); "
    "k.handle({'op':'load','model_path':sys.argv[2],'voices_path':sys.argv[3]}); "
    "r = k.handle({'op':'synthesize','text':'Ready.','preset':'af_heart'}); "
    "assert len(r['audio_b64']) > 1000, 'no audio produced'"
)


class _State:
    def __init__(self) -> None:
        self.job = Job()
        self.lock = threading.Lock()


_state = _State()


def job_status() -> dict[str, Any]:
    with _state.lock:
        return _state.job.as_dict()


def _set(**changes: Any) -> None:
    with _state.lock:
        for key, value in changes.items():
            setattr(_state.job, key, value)


def reset_job() -> None:
    with _state.lock:
        _state.job = Job()


def pack_dir(root: Path | None = None) -> Path:
    return (root or engine_packs.packs_root()) / ENGINE_ID


def models_dir(directory: Path) -> Path:
    return directory / "models"


def model_path(directory: Path) -> Path:
    return models_dir(directory) / MODEL_FILE[0]


def voices_path(directory: Path) -> Path:
    return models_dir(directory) / VOICES_FILE[0]


def build_manifest() -> dict[str, Any]:
    return {
        "id": ENGINE_ID,
        "engine_id": ENGINE_ID,
        "version": PACK_VERSION,
        "label": "Kokoro 82M",
        "description": "Multilingual preset voices on any CPU. Runs in its own private environment.",
        "runtime": "onnxruntime-cpu",
        "provisioner": ENGINE_ID,
        "requirements": [f"kokoro-onnx=={KOKORO_ONNX_VERSION}"],
        "artifacts": [],
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download_file(directory: Path, spec: tuple[str, int, str], base: str = RELEASE) -> None:
    """Fetch one pinned file. A file already present with the right hash is kept (resume)."""
    name, size, sha = spec
    target = models_dir(directory) / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.stat().st_size == size and _sha256(target) == sha:
        return
    partial = target.with_suffix(target.suffix + ".part")
    try:
        with urllib.request.urlopen(f"{base}/{name}", timeout=60) as response, partial.open("wb") as out:
            while block := response.read(1 << 20):
                out.write(block)
    except OSError as exc:
        raise StepFailed(f"could not download {name}: {exc}") from exc
    if partial.stat().st_size != size or _sha256(partial) != sha:
        partial.unlink(missing_ok=True)
        raise StepFailed(f"{name} did not match its pinned size and checksum")
    partial.replace(target)


def explain_install_failure(label: str, raw: str) -> str:
    lowered = raw.lower()
    if "could not download" in lowered or "urlopen" in lowered or "name or service" in lowered:
        return (
            f"{label} failed: could not reach github.com to download the voices. Check the "
            f"internet connection and choose Repair to try again. Details: {raw[-300:]}"
        )
    if "no matching distribution" in lowered or "no solution found" in lowered:
        return (
            f"{label} failed: no Kokoro package is available for this computer's Python or "
            f"processor. Details: {raw[-300:]}"
        )
    return f"{label} failed: {raw}"


def install(
    root: Path | None = None,
    *,
    runner: Callable[..., None] = run_command,
    downloader: Callable[[Path, tuple[str, int, str]], None] = download_file,
    uv: str | None = None,
    platform: str | None = None,
) -> None:
    """Provision the pack synchronously. Failures leave the directory so a retry resumes."""
    platform = platform or sys.platform
    uv = uv if uv is not None else find_uv()
    directory = pack_dir(root)
    python = venv_python(directory, platform)

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

    def install_package() -> None:
        spec = f"kokoro-onnx=={KOKORO_ONNX_VERSION}"
        if uv:
            runner([uv, "pip", "install", "--python", str(python), spec])
        else:
            runner([str(python), "-m", "pip", "install", spec])

    def fetch() -> None:
        downloader(directory, MODEL_FILE)
        downloader(directory, VOICES_FILE)

    def check() -> None:
        from persona_forge import kokoro_worker

        runner(
            [
                str(python),
                "-c",
                _CHECK_SCRIPT,
                str(Path(kokoro_worker.__file__).resolve().parent),
                str(model_path(directory)),
                str(voices_path(directory)),
            ]
        )

    def publish() -> None:
        manifest = engine_packs.load_manifest(directory)
        engine_packs._write_verification_stamp(directory, manifest.manifest_sha256)

    steps: list[tuple[str, Callable[[], None]]] = [
        ("Preparing the engine folder", write_manifest),
        ("Creating a private Python environment", make_venv),
        ("Installing Kokoro", install_package),
        ("Downloading the voices (about 120 MB)", fetch),
        ("Checking the install", check),
        ("Finishing", publish),
    ]
    _set(step_count=len(steps), step_index=0, error=None)
    for index, (label, action) in enumerate(steps, start=1):
        _set(step=label, step_index=index)
        try:
            action()
        except (StepFailed, OSError) as exc:
            _set(state="error", error=explain_install_failure(label, str(exc)), finished_at=time.time())
            return
    _set(state="done", step="Installed", finished_at=time.time())


def start_install(root: Path | None = None, **kwargs: Any) -> bool:
    """Start the install in the background. Returns False when one is already running."""
    with _state.lock:
        if _state.job.state == "running":
            return False
        _state.job = Job(state="running", step="Starting", started_at=time.time())
    threading.Thread(
        target=install, args=(root,), kwargs=kwargs, name="kokoro-install", daemon=True
    ).start()
    return True

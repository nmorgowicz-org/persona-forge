"""Pocket Lite engine pack provisioner.

Builds ``<packs_root>/pocket-lite``: the 18M-parameter Pocket-TTS checkpoint and its English voice
files downloaded into a private ``hf/`` folder, plus a ``manifest.json`` marking it as provisioned.

There is no virtualenv: the worker runs on the application's own interpreter, which already ships
``pocket-tts``. Weights are fetched at install and served offline afterwards.

The cloning weights live in the gated ``kyutai/pocket-tts`` repository, so the install needs a
Hugging Face token whose owner has accepted the terms. Nothing here accepts terms or asks for them
on anyone's behalf; the failure message says what to do.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from persona_forge import engine_packs, install_check
from persona_forge.kitten2_pack import Job, StepFailed, run_command
from persona_forge.pocket_lite_worker import ENGLISH_PRESETS, MODEL_NAME

ENGINE_ID = "pocket-lite"
PACK_VERSION = "1"
# Seconds idle before the worker is stopped; written to the manifest as idle_unload_after.
IDLE_UNLOAD_AFTER_S = 600.0

# Loads the checkpoint online (which downloads the cloning weights, tokenizer and fallback weights)
# and fetches every English preset voice. Refuses a model without cloning so a missing token or
# unaccepted terms fails here, not later.
_PREFETCH_SCRIPT = (
    "import sys; sys.path.insert(0, sys.argv[1]); "
    "import pocket_lite_worker as w; m = w._default_factory(); "
    "assert getattr(m, 'has_voice_cloning', True), 'no cloning weights'; "
    "[m.get_state_for_audio_prompt(n) for n in w.ENGLISH_PRESETS]"
)
# Runs offline: proves the cached files are enough to load and synthesise.
_CHECK_SCRIPT = (
    "import sys; sys.path.insert(0, sys.argv[1]); "
    "import pocket_lite_worker as w; k = w.PocketLiteWorker(); k.handle({'op':'load'}); "
    "r = k.handle({'op':'synthesize','text':'Ready.','preset':'alba'}); "
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


def weights_dir(directory: Path) -> Path:
    return directory / "hf"


def worker_env(directory: Path, *, offline: bool) -> dict[str, str]:
    env = {"HF_HOME": str(weights_dir(directory))}
    if offline:
        env["HF_HUB_OFFLINE"] = "1"
    return env


def speed_check_spec(directory: Path) -> install_check.SpeedCheckSpec:
    """The worker command and load request the engine adapter uses, for the install speed check."""
    from persona_forge import pocket_lite_worker

    env = worker_env(directory, offline=True)
    env["POCKET_TTS_MODEL_SOURCE"] = "auto"  # as the adapter: keep standard Pocket's settings out
    return install_check.SpeedCheckSpec(
        command=(sys.executable, str(Path(pocket_lite_worker.__file__).resolve())),
        env=env,
        load_request={"op": "load"},
    )


def pocket_tts_version() -> str:
    """The ``pocket-tts`` version the weights are fetched for. Each release pins its own revisions."""
    from importlib import metadata

    try:
        return metadata.version("pocket-tts")
    except metadata.PackageNotFoundError:
        return "unknown"


def build_manifest() -> dict[str, Any]:
    return {
        "id": ENGINE_ID,
        "engine_id": ENGINE_ID,
        "version": PACK_VERSION,
        "label": "Pocket Lite (18M)",
        "description": "A smaller, faster Pocket model that still clones. Runs in the app's Python.",
        "runtime": "python-cpu",
        "provisioner": ENGINE_ID,
        "idle_unload_after": IDLE_UNLOAD_AFTER_S,
        "requirements": [f"pocket-tts=={pocket_tts_version()}", f"checkpoint {MODEL_NAME}"],
        "artifacts": [],
    }


def _hf_token() -> str | None:
    """The user's own token, from the environment or their Hugging Face login, if any."""
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token:
        return token
    try:
        from huggingface_hub import get_token

        return get_token()
    except ImportError:
        return None


def explain_install_failure(label: str, raw: str) -> str:
    lowered = raw.lower()
    if "no cloning weights" in lowered or "401" in lowered or "403" in lowered or "gated" in lowered:
        return (
            f"{label} failed: Pocket Lite's cloning weights are in the gated kyutai/pocket-tts "
            "repository. Accept its terms on huggingface.co with your account, make sure a "
            "Hugging Face token is set (HF_TOKEN, or `huggingface-cli login`), then choose Repair."
        )
    if "name or service" in lowered or "connection" in lowered or "resolve" in lowered:
        return (
            f"{label} failed: could not reach huggingface.co. Check the internet connection and "
            f"choose Repair to try again. Details: {raw[-300:]}"
        )
    return f"{label} failed: {raw}"


def install(
    root: Path | None = None,
    *,
    runner: Callable[..., None] = run_command,
    token: str | None = None,
    measure: Callable[[install_check.SpeedCheckSpec], dict[str, Any]] | None = None,
) -> None:
    """Provision the pack synchronously. Failures leave the directory so a retry resumes."""
    directory = pack_dir(root)
    worker_dir = str(Path(__file__).resolve().parent)
    hf_token = token if token is not None else _hf_token()

    def write_manifest() -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / engine_packs.MANIFEST_FILENAME).write_text(
            json.dumps(build_manifest(), indent=2), encoding="utf-8"
        )

    def prefetch() -> None:
        weights_dir(directory).mkdir(parents=True, exist_ok=True)
        env = worker_env(directory, offline=False)
        if hf_token:
            env["HF_TOKEN"] = hf_token  # passed to the child only; never logged or stored
        runner([sys.executable, "-c", _PREFETCH_SCRIPT, worker_dir], env=env)

    def check() -> None:
        runner(
            [sys.executable, "-c", _CHECK_SCRIPT, worker_dir],
            env=worker_env(directory, offline=True),
        )

    def speed() -> None:
        install_check.check_and_record(directory, speed_check_spec(directory), measure)

    def publish() -> None:
        manifest = engine_packs.load_manifest(directory)
        engine_packs._write_verification_stamp(directory, manifest.manifest_sha256)

    steps: list[tuple[str, Callable[[], None]]] = [
        ("Preparing the engine folder", write_manifest),
        (f"Downloading the model and {len(ENGLISH_PRESETS)} voices (about 150 MB)", prefetch),
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
        target=install, args=(root,), kwargs=kwargs, name="pocket-lite-install", daemon=True
    ).start()
    return True

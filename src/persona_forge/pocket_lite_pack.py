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
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from persona_forge import engine_packs, hf_access, install_check, pack_logs
from persona_forge.kitten2_pack import Job, StepFailed, run_command
from persona_forge.pocket_lite_worker import ENGLISH_PRESETS, MODEL_NAME

ENGINE_ID = "pocket-lite"
PACK_VERSION = "1"
# The cloning weights are in a gated repository. The engine card reads this to show the token
# field and the link to accept the terms; nothing here accepts them.
HF_GATE = {"repo": "kyutai/pocket-tts", "url": "https://huggingface.co/kyutai/pocket-tts"}
# Seconds idle before the worker is stopped; written to the manifest as idle_unload_after.
IDLE_UNLOAD_AFTER_S = 600.0

# First asks Hugging Face whether this token may read the gated repository, so a missing token, a
# token it does not recognise (401) and unaccepted terms (403) are told apart exactly; the model
# load alone reports all three as "no cloning weights". Then loads the checkpoint online (which
# downloads the cloning weights, tokenizer and fallback weights) and fetches every English preset
# voice. Refuses a model without cloning so a problem fails here, not later. The preflight skips
# itself when the library lacks ``auth_check`` or the network is down; the load then reports.
_PREFETCH_SCRIPT = (
    "import os, sys; sys.path.insert(0, sys.argv[1])\n"
    "try:\n"
    "    from huggingface_hub import HfApi\n"
    "    from huggingface_hub.errors import GatedRepoError\n"
    "    try:\n"
    "        HfApi().auth_check('kyutai/pocket-tts', token=os.environ.get('HF_TOKEN') or None)\n"
    "    except GatedRepoError as e:\n"
    "        status = getattr(getattr(e, 'response', None), 'status_code', None)\n"
    "        print(f'PF_HF_GATE {status or 401}: Hugging Face refused access to kyutai/pocket-tts', file=sys.stderr)\n"
    "        sys.exit(3)\n"
    "    except Exception:\n"
    "        pass\n"
    "except ImportError:\n"
    "    pass\n"
    "import pocket_lite_worker as w; m = w._default_factory()\n"
    "assert getattr(m, 'has_voice_cloning', True), 'no cloning weights'\n"
    "[m.get_state_for_audio_prompt(n) for n in w.ENGLISH_PRESETS]\n"
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
    pack_logs.record_job_change(changes)


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
    """The token for the download: the one saved on the card, else the environment, else the
    user's own Hugging Face login."""
    return hf_access.resolve()[0]


def explain_install_failure(label: str, raw: str, *, token_present: bool = False) -> tuple[str, str | None, str | None]:
    """``(message, error_code, link)``; code and link are set for failures the user can fix."""
    failure = hf_access.classify(
        raw,
        token_present=token_present,
        label=label,
        repo=HF_GATE["repo"],
        repo_url=HF_GATE["url"],
    )
    if failure is not None:
        return failure.message, failure.code, failure.link
    return f"{label} failed: {raw}", None, None


@pack_logs.logs_install(ENGINE_ID, lambda root: pack_dir(root))
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
    pack_logs.add_secret(hf_token)  # the exact value is redacted from the log and any error

    def write_manifest() -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / engine_packs.MANIFEST_FILENAME).write_text(
            json.dumps(build_manifest(), indent=2), encoding="utf-8"
        )

    def prefetch() -> None:
        weights_dir(directory).mkdir(parents=True, exist_ok=True)
        env = worker_env(directory, offline=False)
        if hf_token:
            # Passed to this one child process only: never put in os.environ, logged or stored here.
            env["HF_TOKEN"] = hf_token
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
    _set(step_count=len(steps), step_index=0, error=None, error_code=None, error_link=None)
    for index, (label, action) in enumerate(steps, start=1):
        _set(step=label, step_index=index)
        try:
            action()
        except (StepFailed, OSError) as exc:
            message, code, link = explain_install_failure(
                label, pack_logs.redact(str(exc), [hf_token or ""]), token_present=bool(hf_token)
            )
            _set(
                state="error",
                error=pack_logs.redact(message, [hf_token or ""]),
                error_code=code,
                error_link=link,
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
        target=install, args=(root,), kwargs=kwargs, name="pocket-lite-install", daemon=True
    ).start()
    return True

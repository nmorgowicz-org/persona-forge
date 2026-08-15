"""Runs the real persona_forge Flask app with the model layer faked out via FakeModelRuntime.

For Playwright E2E and Tier 3 API integration tests. No model weights, no OpenVINO, no Docker.

Uses tests/fixtures/fake_runtime.py as the single source of truth for the fake model module,
then layers UI-specific behaviors (delays, OmniVoice, error profiles) on top.

Usage:
    PERSONA_FORGE_TEST_PORT=8319 \\
    TEST_PROFILE= \\
    python tests/ui/fixtures/fake_model_server.py

TEST_PROFILE options:
    (empty)             Normal: healthy service, 200-600ms generate delay.
    error_on_generate   /generate returns 500 (for error banner tests).
    busy                swap_in_progress=True (busy UX tests).
    slow_async          Async jobs take 3-5 seconds (for cancel UX).
"""

from __future__ import annotations

import json
import logging
import os
import random
import secrets
import sys
import tempfile
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

_SAMPLE_RATE = 24000
_MAX_SEED = 2**32


def _setup_pythonpath():
    repo_root = Path(__file__).resolve().parents[3]
    for candidate in (
        repo_root,
        repo_root / "src",
        repo_root / "src" / "export",
    ):
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


def _read_test_profile() -> str:
    return (os.getenv("TEST_PROFILE") or "").strip().lower()


def _install_fake_runtime():
    from tests.fixtures.fake_runtime import FakeModelRuntime  # noqa: E402

    profile = _read_test_profile()

    generate_delay_ms = random.randint(200, 600)
    generate_should_fail = profile == "error_on_generate"
    swap_in_progress = profile == "busy"
    slow_async = profile == "slow_async"

    rt = FakeModelRuntime(
        initial_service_started=True,
        model_loaded=True,
        generate_delay_ms=generate_delay_ms,
        generate_should_fail=generate_should_fail,
        swap_in_progress=swap_in_progress,
    )
    rt.install()
    rt._slow_async = slow_async
    return rt


def _patch_generate_for_slow_async(rt):
    if not rt._slow_async:
        return

    original_run_generate = _get_module_attr("persona_forge.model", "_run_generate")

    def _wrapped(text, language, **kwargs):
        if kwargs.get("job_id"):
            time.sleep(random.uniform(3, 5))
        return original_run_generate(text, language, **kwargs)

    _set_module_attr("persona_forge.model", "_run_generate", _wrapped)


def _get_module_attr(module_name, attr):
    return getattr(sys.modules.get(module_name), attr)


def _set_module_attr(module_name, attr, value):
    setattr(sys.modules.get(module_name), attr, value)


def _patch_omnivoice_run_job(app_module):
    def fake_run_omnivoice_job(
        segments,
        instruct,
        language,
        candidates_per_segment,
        seed,
        num_step=None,
        durations=None,
        speed=None,
        guidance_scale=None,
        diverse_candidates=False,
        postprocess_output=None,
        min_match_score=None,
        on_candidate_complete=None,
        cancel_event=None,
    ):
        time.sleep(0.15)
 
        for seg_idx, text in enumerate(segments):
            if cancel_event is not None and cancel_event.is_set():
                break
            for cand_idx in range(candidates_per_segment):
                if cancel_event is not None and cancel_event.is_set():
                    break
                wav = np.zeros(int(_SAMPLE_RATE * 0.3), dtype=np.float32)
                candidate = (
                    wav,
                    _SAMPLE_RATE,
                    False,
                    None,
                    text,
                    0.9,
                )
                if on_candidate_complete is not None:
                    on_candidate_complete(seg_idx, cand_idx, text, candidate)
                time.sleep(0.03)
 
    app_module.omnivoice_engine.run_omnivoice_job = fake_run_omnivoice_job
    app_module.omnivoice_engine.swap_in_progress = lambda: False
    app_module.omnivoice_engine.mark_swap_pending = lambda: None

def _patch_save_voice(app_module, rt):
    """Route app-level voice library calls to the in-memory fake library."""
    fake_library = rt.voice_library
    app_module.voice_library.save_voice = fake_library.save_voice
    app_module.voice_library.get_voice = fake_library.get_voice
    app_module.voice_library.get_voice_wav_bytes = fake_library.get_voice_wav_bytes
    app_module.voice_library.update_voice = fake_library.update_voice
    app_module.voice_library.delete_voice = fake_library.delete_voice
    app_module.voice_library.list_voices = fake_library.list_voices
    app_module.voice_library.duplicate_voice = fake_library.duplicate_voice
    app_module.voice_library.set_default_variant = fake_library.set_default_variant


def _seed_fake_voice_library(rt):
    """Load the capture-data voice fixtures into the in-memory fake library."""
    fixtures_dir = Path(__file__).resolve().parent / "capture-data" / "voices"
    if not fixtures_dir.is_dir():
        return
    metas = []
    for entry in sorted(fixtures_dir.iterdir()):
        meta_path = entry / "meta.json"
        if not meta_path.is_file():
            continue
        try:
            metas.append(json.loads(meta_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    rt.voice_library.seed(metas)



def _install_fake_voice_design(app_module):
    def _fake_run_voice_design_request(description, sample_text, language, seed=None):
        time.sleep(random.uniform(0.2, 0.5))
        resolved_seed = seed if seed is not None else secrets.randbelow(_MAX_SEED)
        return np.zeros(int(_SAMPLE_RATE * 0.5), dtype=np.float32), _SAMPLE_RATE, resolved_seed

    app_module.voice_design.run_voice_design_request = _fake_run_voice_design_request
    app_module.voice_design.swap_in_progress = lambda: False


def main() -> None:
    _setup_pythonpath()

    port = int(os.getenv("PERSONA_FORGE_TEST_PORT", "8319"))
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    # Ensure library dirs before importing app (uses segment_library which defaults to /segments).
    os.environ.setdefault("VOICE_LIBRARY_DIR", tempfile.mkdtemp(prefix="persona-forge-e2e-voices-"))
    os.environ.setdefault("SEGMENT_LIBRARY_DIR", tempfile.mkdtemp(prefix="persona-forge-e2e-segments-"))

    rt = _install_fake_runtime()
    _patch_generate_for_slow_async(rt)

    from persona_forge import app as app_module  # noqa: E402

    _install_fake_voice_design(app_module)
    _patch_omnivoice_run_job(app_module)
    _patch_save_voice(app_module, rt)
    _seed_fake_voice_library(rt)

    from werkzeug.serving import make_server  # noqa: E402

    shutdown_event = threading.Event()

    app_module._shutdown_hook = shutdown_event.set

    server = make_server("127.0.0.1", port, app_module.app, threaded=True)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    print(f"[fake_model_server] listening on http://127.0.0.1:{port}", flush=True)
    print(f"[fake_model_server] TEST_PROFILE={_read_test_profile()}", flush=True)
    print(f"[fake_model_server] voice library: {os.environ['VOICE_LIBRARY_DIR']}", flush=True)

    # Block main thread; external health check is handled by CI / test harness.
    while not shutdown_event.is_set():
        shutdown_event.wait(timeout=1)


def start_server(port: int = 18318, frontend_enabled: bool = False):
    """Start the fake_model_server in a daemon thread and return (base_url, stop_fn).

    Intended for Tier 3 API integration tests and Playwright E2E.
    """
    _setup_pythonpath()
    lib_dir = tempfile.mkdtemp(prefix="persona-forge-e2e-voices-")
    seg_dir = tempfile.mkdtemp(prefix="persona-forge-e2e-segments-")
    os.environ.setdefault("VOICE_LIBRARY_DIR", lib_dir)
    os.environ.setdefault("SEGMENT_LIBRARY_DIR", seg_dir)

    rt = _install_fake_runtime()
    _patch_generate_for_slow_async(rt)

    from persona_forge import app as app_module  # noqa: E402
    from werkzeug.serving import make_server  # noqa: E402

    _install_fake_voice_design(app_module)
    _patch_omnivoice_run_job(app_module)
    _patch_save_voice(app_module, rt)
    _seed_fake_voice_library(rt)

    shutdown_event = threading.Event()
    app_module._shutdown_hook = shutdown_event.set

    server = make_server("127.0.0.1", port, app_module.app, threaded=True)
    actual_port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    import urllib.request

    base_url = f"http://127.0.0.1:{actual_port}"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.1)
    else:
        raise RuntimeError("fake_model_server did not become reachable within 10 seconds")

    def stop_fn():
        try:
            urllib.request.urlopen(f"{base_url}/_shutdown", timeout=2)
        except Exception:
            pass
        shutdown_event.wait(timeout=5)
        server.shutdown()

    return base_url, stop_fn


if __name__ == "__main__":
    import traceback, sys as _sys

    try:
        main()
    except Exception:
        traceback.print_exc(file=_sys.stderr)
        _sys.exit(1)

"""Runs the real qwen3_tts Flask app with the model layer faked out.

For local UI/UX review and E2E/screenshot testing (see docs/dev/resolved/E2E_AND_SCREENSHOTTING.md
§3.1). No model weights are loaded, no OpenVINO, no Docker required — this is a plain Python
process that works the same on any machine/architecture.

Reuses the exact fake-module substitution pattern already reviewed and in use for
tests/test_app_api.py: qwen3_tts.model is replaced in sys.modules *before* qwen3_tts.app is
imported, so nothing in app.py or model.py needs to change or know a fake is in use.
voice_library is used for real (it's pure filesystem code with no model dependency) pointed at a
throwaway temp directory, so /voices and /voice_design round-trip through real save/list/get/
delete logic instead of a second, divergent fake. Only voice_design.run_voice_design_request is
faked, since the real one requires a loaded VoiceDesign checkpoint.

Usage:
    QWEN3_TTS_TEST_PORT=8319 \
    FRONTEND_DIST_DIR=../../frontend/dist \
    python tests/ui/fixtures/fake_model_server.py
"""

from __future__ import annotations

import logging
import os
import secrets
import sys
import tempfile
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor

import numpy as np

_SAMPLE_RATE = 24000
_MAX_SEED = 2**32


def _install_fake_model_module() -> None:
    fake_model = types.ModuleType("qwen3_tts.model")
    fake_model.model = object()
    fake_model.voice_clone_prompt = object()
    fake_model._service_started = True
    fake_model.ov_runtime = types.SimpleNamespace(
        vocoder_runtime=types.SimpleNamespace(enabled=True, sample_rate=_SAMPLE_RATE)
    )
    fake_model.executor = ThreadPoolExecutor(max_workers=1)
    fake_model.health_state = lambda: {
        "status": "ok",
        "backend": "fake-e2e",
        "model_loaded": True,
        "service_started": True,
    }
    fake_model._apply_optional_seed = lambda seed: None
    fake_model.register_foreign_engine = lambda is_loaded, unload: None
    fake_model.resolve_seed = lambda seed_value: (
        seed_value if seed_value is not None else secrets.randbelow(_MAX_SEED)
    )

    # Runtime control panel (§8.8) — deterministic in-memory state, no reload ever actually
    # happens (there's no model to reload), but the shape matches the real endpoint so the
    # Runtime page can be exercised end to end.
    _runtime_state = {
        "reconfig_in_progress": False,
        "live": {
            "TTS_BACKEND": "openvino",
            "IDLE_UNLOAD_SECONDS": 0,
            "SILENCE_TRIM": True,
            "SILENCE_TRIM_THRESH": 0.01,
            "SILENCE_TRIM_PAD_MS": 30,
            "OV_DYNAMIC_QUANT_GROUP_SIZE": 32,
        },
        "read_only": {
            "mounts": {"model_cache": "ro", "ov_data": "rw", "voice_library": "rw"},
            "ref_audio_path_set": True,
            "hf_token_set": False,
            "device": "CPU",
            "torch_dtype": "float32",
        },
        "not_live": {
            "TTS_MAX_SPEECH_SECONDS": "64",
            "MODEL_SIZE": "1.7B",
            "compression": "int4_asym",
            "reason": "Baked into the OpenVINO IR at export time; requires re-export (see docs/HOW_TO_RUN.md).",
        },
    }

    def _runtime_config_state():
        return _runtime_state

    def _apply_runtime_config(updates):
        unknown = set(updates) - set(_runtime_state["live"])
        if unknown:
            raise ValueError(f"Not a live-adjustable key: {sorted(unknown)}")
        _runtime_state["live"].update(updates)
        return _runtime_state

    fake_model.reconfig_in_progress = lambda: _runtime_state["reconfig_in_progress"]
    fake_model.runtime_config_state = _runtime_config_state
    fake_model.apply_runtime_config = _apply_runtime_config

    def _run_generate(text, language, **kwargs):
        # Now returns (wav, sr, job_id) for consistency with real model.py.
        return np.zeros(int(_SAMPLE_RATE * 0.5), dtype=np.float32), _SAMPLE_RATE, "fake-job-" + str(int(time.time() * 1000))

    def _run_generate_with_streaming(text, language, on_chunk, **kwargs):
        chunk = np.zeros(_SAMPLE_RATE // 4, dtype=np.float32)
        on_chunk(chunk)
        return chunk, _SAMPLE_RATE, chunk, {
            "elapsed_seconds": 0.05,
            "reference_frames": 0,
            "decode_boundaries": [len(chunk)],
        }

    fake_model._run_generate = _run_generate
    fake_model._run_generate_with_streaming = _run_generate_with_streaming

    # Async job helpers (used by /generate/async, /generate/progress, /generate/cancel)
    fake_model._active_jobs = {}
    fake_model._active_jobs_lock = threading.Lock()

    def _fake_create_job(text, seed=None):
        job_id = "fake-job-" + str(int(time.time() * 1000))
        class _FakeJob:
            def __init__(self):
                self.job_id = job_id
                self.status = "running"
                self.frames_generated = 0
                self.reference_frames = 0
                self.text_length = len(text)
                self.message = None
                self.wav = np.zeros(int(_SAMPLE_RATE * 0.5), dtype=np.float32)
                self.sr = _SAMPLE_RATE
                self.seed = seed
                self.error = None
                self.started_at = time.monotonic()
                self.cancel_event = threading.Event()
        job = _FakeJob()
        fake_model._active_jobs[job_id] = job
        return job

    def _fake_get_job_progress(job_id):
        job = fake_model._active_jobs.get(job_id)
        if job is None:
            return None
        elapsed = time.monotonic() - job.started_at
        return {
            "job_id": job_id,
            "status": job.status,
            "frames_generated": job.frames_generated,
            "expected_total_frames": 60,
            "progress_pct": min(100.0, (job.frames_generated / 60) * 100),
            "elapsed_seconds": round(elapsed, 1),
            "eta_seconds": None,
            "message": job.message,
        }

    def _fake_cancel_job(job_id):
        job = fake_model._active_jobs.get(job_id)
        if job is None or job.status != "running":
            return False
        job.status = "cancelled"
        job.message = "Cancelled by user."
        job.cancel_event.set()
        return True

    def _fake_cleanup_job(job_id):
        fake_model._active_jobs.pop(job_id, None)

    fake_model._create_job = _fake_create_job
    fake_model.get_job_progress = _fake_get_job_progress
    fake_model.cancel_job = _fake_cancel_job
    fake_model._cleanup_job = _fake_cleanup_job

    sys.modules["qwen3_tts.model"] = fake_model


def _install_fake_voice_design(app_module) -> None:
    def _fake_run_voice_design_request(description, sample_text, language, seed=None):
        time.sleep(0.05)
        resolved_seed = seed if seed is not None else secrets.randbelow(_MAX_SEED)
        return np.zeros(int(_SAMPLE_RATE * 0.5), dtype=np.float32), _SAMPLE_RATE, resolved_seed

    app_module.voice_design.run_voice_design_request = _fake_run_voice_design_request
    app_module.voice_design.swap_in_progress = lambda: False


def main() -> None:
    port = int(os.getenv("QWEN3_TTS_TEST_PORT", "8319"))

    # Werkzeug logs every request at INFO ("GET /health HTTP/1.1" 200 -), which drowns out
    # Playwright's own pass/fail lines with no signal. Unhandled exceptions still log via ERROR,
    # so a 500 (a real test failure) stays visible; only the noisy per-request access log is cut.
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    # Real voice_library, but scoped to a throwaway directory so E2E runs never touch (or
    # depend on) a real deployment's saved voices. Must be set before qwen3_tts.voice_library
    # is imported (transitively, via qwen3_tts.app) since it reads the env var at import time.
    os.environ.setdefault("VOICE_LIBRARY_DIR", tempfile.mkdtemp(prefix="qwen3-tts-e2e-voices-"))

    _install_fake_model_module()

    # PYTHONPATH must include src/ (and src/export/ isn't needed here). Import happens after
    # the fake model module is installed so qwen3_tts.app / voice_design / voice_library all
    # pick up the fake qwen3_tts.model.
    from qwen3_tts import app as app_module  # noqa: E402

    _install_fake_voice_design(app_module)

    print(f"[fake_model_server] listening on http://127.0.0.1:{port}", flush=True)
    print(f"[fake_model_server] voice library: {os.environ['VOICE_LIBRARY_DIR']}", flush=True)
    app_module.app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()

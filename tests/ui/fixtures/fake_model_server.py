"""Runs the real qwen3_tts Flask app with the model layer faked out.

For local UI/UX review and E2E/screenshot testing (see docs/plans/20260702-e2e_and_screenshotting.md
§3.1). No model weights are loaded, no OpenVINO, no Docker required — this is a plain Python
process that works the same on any machine/architecture.

Reuses the exact fake-module substitution pattern already reviewed and in use for
tests/test_app_api.py: qwen3_tts.model is replaced in sys.modules *before* qwen3_tts.app is
imported, so nothing in app.py or model.py needs to change or know a fake is in use.

Usage:
    VOICE_LIBRARY_DIR=$(mktemp -d) \
    FRONTEND_DIST_DIR=../../frontend/dist \
    QWEN3_TTS_TEST_PORT=8319 \
    python tests/ui/fixtures/fake_model_server.py
"""

from __future__ import annotations

import os
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor

import numpy as np

_SAMPLE_RATE = 24000


def _install_fake_model_module() -> None:
    fake_model = types.ModuleType("qwen3_tts.model")
    fake_model.model = object()
    fake_model.voice_clone_prompt = object()
    fake_model._service_started = True
    fake_model.ov_runtime = types.SimpleNamespace(
        vocoder_runtime=types.SimpleNamespace(enabled=True, sample_rate=_SAMPLE_RATE)
    )
    fake_model.executor = ThreadPoolExecutor(max_workers=1)
    fake_model.health_state = lambda: {"status": "ok", "backend": "fake-e2e"}
    fake_model._apply_optional_seed = lambda seed: None

    def _run_generate(text, language, **kwargs):
        return np.zeros(int(_SAMPLE_RATE * 0.5), dtype=np.float32), _SAMPLE_RATE

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
    sys.modules["qwen3_tts.model"] = fake_model


def _install_fake_voice_design(app_module) -> None:
    def _fake_run_voice_design_request(description: str, sample_text: str, language: str):
        time.sleep(0.05)
        return np.zeros(int(_SAMPLE_RATE * 0.5), dtype=np.float32), _SAMPLE_RATE

    app_module.voice_design.run_voice_design_request = _fake_run_voice_design_request


def main() -> None:
    port = int(os.getenv("QWEN3_TTS_TEST_PORT", "8319"))

    _install_fake_model_module()

    # PYTHONPATH must include src/ (and src/export/ isn't needed here). Import happens after
    # the fake model module is installed so qwen3_tts.app / voice_design / voice_library all
    # pick up the fake qwen3_tts.model.
    from qwen3_tts import app as app_module  # noqa: E402

    _install_fake_voice_design(app_module)

    print(f"[fake_model_server] listening on http://127.0.0.1:{port}", flush=True)
    app_module.app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()

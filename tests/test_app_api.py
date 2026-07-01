from __future__ import annotations

import sys
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import numpy as np


fake_model = types.ModuleType("qwen3_tts.model")
fake_model.model = object()
fake_model.voice_clone_prompt = object()
fake_model._service_started = True
fake_model.ov_runtime = types.SimpleNamespace(
    vocoder_runtime=types.SimpleNamespace(enabled=True, sample_rate=24000)
)
fake_model.executor = ThreadPoolExecutor(max_workers=1)
fake_model.health_state = lambda: {"status": "ok", "backend": "openvino"}
fake_model._run_generate = lambda text, language: (np.zeros(240, dtype=np.float32), 24000)
fake_model._apply_optional_seed = lambda seed: None


def _stream(text, language, on_chunk, **kwargs):
    chunk = np.asarray([0.25, -0.25], dtype=np.float32)
    on_chunk(chunk)
    return chunk, 24000, chunk, {
        "elapsed_seconds": 0.1,
        "reference_frames": 0,
        "decode_boundaries": [2],
    }


fake_model._run_generate_with_streaming = _stream
sys.modules["qwen3_tts.model"] = fake_model

from qwen3_tts import app as app_module  # noqa: E402


class AppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = app_module.app.test_client()

    def test_health_reports_direct_model_state(self) -> None:
        result = self.client.get("/health")

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()["status"], "ok")
        self.assertNotIn("worker", result.get_json())

    def test_generate_returns_encoded_audio(self) -> None:
        with patch.object(app_module, "_encode", return_value=(b"audio", "audio/mpeg")):
            result = self.client.post("/generate", json={"text": "hello"})

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data, b"audio")
        self.assertEqual(result.content_type, "audio/mpeg")

    def test_generate_rejects_missing_text(self) -> None:
        result = self.client.post("/generate", json={"language": "English"})

        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.get_json()["error"], "text is required")

    def test_openai_speech_accepts_ignored_schema_fields(self) -> None:
        with patch.object(app_module, "_encode", return_value=(b"ID3audio", "audio/mpeg")):
            result = self.client.post(
                "/v1/audio/speech",
                json={"input": "hello", "model": "tts-1", "voice": "alloy"},
            )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data, b"ID3audio")

    def test_openai_speech_rejects_missing_input_with_openai_envelope(self) -> None:
        result = self.client.post("/v1/audio/speech", json={"model": "tts-1"})

        self.assertEqual(result.status_code, 400)
        error = result.get_json()["error"]
        self.assertEqual(error["message"], "'input' is required")
        self.assertEqual(error["type"], "invalid_request_error")
        self.assertIsNone(error["code"])

    def test_stream_returns_pcm_and_contract_headers(self) -> None:
        result = self.client.post("/generate/stream", json={"text": "hello"})

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data, np.asarray([0.25, -0.25], dtype="<f4").tobytes())
        self.assertEqual(result.headers["X-Audio-Format"], "f32le")
        self.assertEqual(result.headers["X-Audio-Sample-Rate"], "24000")
        self.assertEqual(result.headers["X-Audio-Channels"], "1")

    def test_stream_requires_openvino_vocoder(self) -> None:
        fake_model.ov_runtime.vocoder_runtime.enabled = False
        try:
            result = self.client.post("/generate/stream", json={"text": "hello"})
        finally:
            fake_model.ov_runtime.vocoder_runtime.enabled = True

        self.assertEqual(result.status_code, 503)


if __name__ == "__main__":
    unittest.main()

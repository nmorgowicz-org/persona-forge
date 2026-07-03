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
fake_model.reconfig_in_progress = lambda: False
fake_model.runtime_config_state = lambda: {"reconfig_in_progress": False, "live": {}}
fake_model.apply_runtime_config = lambda updates: {"reconfig_in_progress": False, "live": updates}
fake_model._run_generate = lambda text, language, **kwargs: (np.zeros(240, dtype=np.float32), 24000)
fake_model._apply_optional_seed = lambda seed: None
fake_model.resolve_seed = lambda seed_value: seed_value if seed_value is not None else 12345


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

    def test_generate_passes_voice_id_through_to_run_generate(self) -> None:
        seen = {}

        def fake_run_generate(text, language, **kwargs):
            seen.update(kwargs)
            return np.zeros(240, dtype=np.float32), 24000

        with patch.object(app_module.model, "_run_generate", fake_run_generate), patch.object(
            app_module, "_encode", return_value=(b"audio", "audio/mpeg")
        ):
            result = self.client.post("/generate", json={"text": "hello", "voice_id": "vd_abc"})

        self.assertEqual(result.status_code, 200)
        self.assertEqual(seen.get("voice_id"), "vd_abc")

    def test_generate_omits_voice_id_when_not_supplied(self) -> None:
        seen = {}

        def fake_run_generate(text, language, **kwargs):
            seen.update(kwargs)
            return np.zeros(240, dtype=np.float32), 24000

        with patch.object(app_module.model, "_run_generate", fake_run_generate), patch.object(
            app_module, "_encode", return_value=(b"audio", "audio/mpeg")
        ):
            result = self.client.post("/generate", json={"text": "hello"})

        self.assertEqual(result.status_code, 200)
        self.assertIsNone(seen.get("voice_id"))

    def test_voice_design_returns_voice_id_and_audio(self) -> None:
        def fake_run_voice_design_request(description, sample_text, language, seed):
            return np.zeros(240, dtype=np.float32), 24000, seed or 999

        with patch.object(
            app_module.voice_design, "run_voice_design_request", fake_run_voice_design_request
        ), patch.object(
            app_module.voice_library,
            "save_voice",
            lambda wav_bytes, **kw: {"voice_id": "vd_new123456"},
        ):
            result = self.client.post(
                "/voice_design",
                json={"description": "a calm narrator", "sample_text": "hello there"},
            )

        self.assertEqual(result.status_code, 200)
        body = result.get_json()
        self.assertEqual(body["voice_id"], "vd_new123456")
        self.assertEqual(body["sample_rate"], 24000)
        self.assertEqual(body["seed"], 999)
        self.assertIn("audio_base64", body)

    def test_voice_design_honors_explicit_seed(self) -> None:
        seen: dict[str, object] = {}

        def fake_run_voice_design_request(description, sample_text, language, seed):
            seen["seed"] = seed
            return np.zeros(240, dtype=np.float32), 24000, seed

        with patch.object(
            app_module.voice_design, "run_voice_design_request", fake_run_voice_design_request
        ), patch.object(
            app_module.voice_library,
            "save_voice",
            lambda wav_bytes, **kw: {"voice_id": "vd_new123456"},
        ):
            result = self.client.post(
                "/voice_design",
                json={
                    "description": "a calm narrator",
                    "sample_text": "hello there",
                    "seed": 42,
                },
            )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(seen["seed"], 42)
        self.assertEqual(result.get_json()["seed"], 42)

    def test_voice_design_rejects_non_integer_seed(self) -> None:
        result = self.client.post(
            "/voice_design",
            json={"description": "a calm narrator", "sample_text": "hello there", "seed": "abc"},
        )

        self.assertEqual(result.status_code, 400)

    def test_voice_design_rejects_missing_description(self) -> None:
        result = self.client.post("/voice_design", json={"sample_text": "hello there"})

        self.assertEqual(result.status_code, 400)

    def test_voice_design_rejects_missing_sample_text(self) -> None:
        result = self.client.post("/voice_design", json={"description": "a calm narrator"})

        self.assertEqual(result.status_code, 400)

    def test_voice_design_rejects_too_long_sample_text(self) -> None:
        long_text = " ".join(["word"] * 100)

        result = self.client.post(
            "/voice_design", json={"description": "a calm narrator", "sample_text": long_text}
        )

        self.assertEqual(result.status_code, 400)

    def test_voice_design_returns_503_when_swap_already_in_progress(self) -> None:
        app_module.voice_design._swap_in_progress = True
        try:
            result = self.client.post(
                "/voice_design",
                json={"description": "a calm narrator", "sample_text": "hello there"},
            )
        finally:
            app_module.voice_design._swap_in_progress = False

        self.assertEqual(result.status_code, 503)

    def test_generate_queues_through_voice_design_swap(self) -> None:
        app_module.voice_design._swap_in_progress = True
        try:
            result = self.client.get("/health")
            # /generate queues on model.executor instead of 503ing during a swap, so a
            # request submitted mid-swap still completes once its turn comes up.
            generate_result = self.client.post("/generate", json={"text": "hello"})
        finally:
            app_module.voice_design._swap_in_progress = False

        # /health reports raw model state regardless of swap; /generate is not gated by
        # swap_in_progress (see _generation_ready in app.py).
        self.assertEqual(result.status_code, 200)
        self.assertEqual(generate_result.status_code, 200)

    def test_omnivoice_audition_returns_candidates_with_ids(self) -> None:
        def fake_run_omnivoice_job(segments, instruct, language, candidates_per_segment, seed):
            return [
                [(np.zeros(240, dtype=np.float32), 24000) for _ in range(candidates_per_segment)]
                for _ in segments
            ]

        with patch.object(
            app_module.omnivoice_engine, "run_omnivoice_job", fake_run_omnivoice_job
        ), patch.object(app_module, "_encode", return_value=(b"audio", "audio/wav")):
            result = self.client.post(
                "/omnivoice/audition",
                json={
                    "segments": ["G'day, how are you?", "Fancy a barbie later on?"],
                    "instruct": "female, young adult, moderate pitch, australian accent",
                    "candidates_per_segment": 2,
                },
            )

        self.assertEqual(result.status_code, 200)
        body = result.get_json()
        self.assertEqual(len(body["segments"]), 2)
        self.assertEqual(len(body["segments"][0]["candidates"]), 2)
        candidate_ids = [c["candidate_id"] for seg in body["segments"] for c in seg["candidates"]]
        self.assertEqual(len(candidate_ids), len(set(candidate_ids)))
        self.assertIn("audio_base64", body["segments"][0]["candidates"][0])

    def test_omnivoice_audition_rejects_missing_segments(self) -> None:
        result = self.client.post(
            "/omnivoice/audition", json={"instruct": "female, young adult, moderate pitch"}
        )

        self.assertEqual(result.status_code, 400)

    def test_omnivoice_audition_rejects_missing_instruct(self) -> None:
        result = self.client.post("/omnivoice/audition", json={"segments": ["hello"]})

        self.assertEqual(result.status_code, 400)

    def test_omnivoice_audition_returns_503_when_swap_already_in_progress(self) -> None:
        app_module.omnivoice_engine._swap_in_progress = True
        try:
            result = self.client.post(
                "/omnivoice/audition",
                json={"segments": ["hello"], "instruct": "female, young adult"},
            )
        finally:
            app_module.omnivoice_engine._swap_in_progress = False

        self.assertEqual(result.status_code, 503)

    def test_omnivoice_stitch_combines_selected_candidates(self) -> None:
        def fake_run_omnivoice_job(segments, instruct, language, candidates_per_segment, seed):
            return [[(np.zeros(240, dtype=np.float32), 24000)] for _ in segments]

        with patch.object(
            app_module.omnivoice_engine, "run_omnivoice_job", fake_run_omnivoice_job
        ), patch.object(app_module, "_encode", return_value=(b"raw", "audio/wav")):
            audition = self.client.post(
                "/omnivoice/audition",
                json={"segments": ["hello", "world"], "instruct": "female, young adult"},
            )
        candidate_ids = [
            c["candidate_id"]
            for seg in audition.get_json()["segments"]
            for c in seg["candidates"]
        ]

        with patch.object(
            app_module.omnivoice_engine,
            "stitch_selected",
            lambda selected: (np.zeros(480, dtype=np.float32), 24000),
        ), patch.object(app_module, "_encode", return_value=(b"stitched", "audio/wav")):
            result = self.client.post("/omnivoice/stitch", json={"selections": candidate_ids})

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data, b"stitched")

    def test_omnivoice_stitch_rejects_unknown_candidate_id(self) -> None:
        result = self.client.post("/omnivoice/stitch", json={"selections": ["not-a-real-id"]})

        self.assertEqual(result.status_code, 400)

    def test_omnivoice_stitch_rejects_missing_selections(self) -> None:
        result = self.client.post("/omnivoice/stitch", json={})

        self.assertEqual(result.status_code, 400)

    def _seed_omnivoice_candidate(self) -> str:
        def fake_run_omnivoice_job(segments, instruct, language, candidates_per_segment, seed):
            return [[(np.zeros(240, dtype=np.float32), 24000)] for _ in segments]

        with patch.object(
            app_module.omnivoice_engine, "run_omnivoice_job", fake_run_omnivoice_job
        ), patch.object(app_module, "_encode", return_value=(b"raw", "audio/wav")):
            audition = self.client.post(
                "/omnivoice/audition",
                json={"segments": ["G'day"], "instruct": "female, young adult, high pitch"},
            )
        return audition.get_json()["segments"][0]["candidates"][0]["candidate_id"]

    def test_omnivoice_save_persists_to_voice_library(self) -> None:
        candidate_id = self._seed_omnivoice_candidate()
        saved_kwargs: dict[str, object] = {}

        def fake_save_voice(wav_bytes, **kwargs):
            saved_kwargs.update(kwargs)
            return {"voice_id": "ov_new123456"}

        with patch.object(
            app_module.omnivoice_engine,
            "stitch_selected",
            lambda selected: (np.zeros(480, dtype=np.float32), 24000),
        ), patch.object(app_module, "_encode", return_value=(b"stitched", "audio/wav")), patch.object(
            app_module.voice_library, "save_voice", fake_save_voice
        ):
            result = self.client.post(
                "/omnivoice/save",
                json={
                    "selections": [candidate_id],
                    "instruct": "female, young adult, high pitch, australian accent",
                    "segments": ["G'day"],
                    "accent_id": "au",
                },
            )

        self.assertEqual(result.status_code, 200)
        body = result.get_json()
        self.assertEqual(body["voice_id"], "ov_new123456")
        self.assertEqual(saved_kwargs["selections"]["engine"], "omnivoice")
        self.assertEqual(saved_kwargs["selections"]["accent_id"], "au")

    def test_omnivoice_save_rejects_missing_instruct(self) -> None:
        candidate_id = self._seed_omnivoice_candidate()

        result = self.client.post(
            "/omnivoice/save", json={"selections": [candidate_id], "segments": ["G'day"]}
        )

        self.assertEqual(result.status_code, 400)

    def test_omnivoice_save_rejects_unknown_candidate_id(self) -> None:
        result = self.client.post(
            "/omnivoice/save",
            json={"selections": ["nope"], "instruct": "female", "segments": ["G'day"]},
        )

        self.assertEqual(result.status_code, 400)

    def test_voices_list_returns_library_contents(self) -> None:
        with patch.object(
            app_module.voice_library,
            "list_voices",
            lambda: [{"voice_id": "vd_abc123456789"}],
        ):
            result = self.client.get("/voices")

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()["voices"], [{"voice_id": "vd_abc123456789"}])

    def test_voices_get_returns_metadata_and_audio(self) -> None:
        with patch.object(
            app_module.voice_library,
            "get_voice",
            lambda voice_id: {"voice_id": voice_id, "wav_path": "/voices/x/reference.wav"},
        ), patch.object(
            app_module.voice_library, "get_voice_wav_bytes", lambda voice_id: b"wavdata"
        ):
            result = self.client.get("/voices/vd_abc123456789")

        self.assertEqual(result.status_code, 200)
        body = result.get_json()
        self.assertEqual(body["voice_id"], "vd_abc123456789")
        self.assertNotIn("wav_path", body)
        self.assertIn("audio_base64", body)

    def test_voices_get_returns_404_for_unknown_voice(self) -> None:
        with patch.object(app_module.voice_library, "get_voice", lambda voice_id: None):
            result = self.client.get("/voices/vd_doesnotexist")

        self.assertEqual(result.status_code, 404)

    def test_voices_delete_returns_200_when_deleted(self) -> None:
        with patch.object(app_module.voice_library, "delete_voice", lambda voice_id: True):
            result = self.client.delete("/voices/vd_abc123456789")

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()["deleted"], "vd_abc123456789")

    def test_voices_delete_returns_404_for_unknown_voice(self) -> None:
        with patch.object(app_module.voice_library, "delete_voice", lambda voice_id: False):
            result = self.client.delete("/voices/vd_doesnotexist")

        self.assertEqual(result.status_code, 404)

    def test_runtime_config_get_returns_state(self) -> None:
        with patch.object(
            app_module.model,
            "runtime_config_state",
            lambda: {"reconfig_in_progress": False, "live": {"TTS_BACKEND": "openvino"}},
        ):
            result = self.client.get("/runtime/config")

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()["live"]["TTS_BACKEND"], "openvino")

    def test_runtime_config_post_applies_update(self) -> None:
        with patch.object(
            app_module.model,
            "apply_runtime_config",
            lambda updates: {"reconfig_in_progress": False, "live": updates},
        ):
            result = self.client.post("/runtime/config", json={"IDLE_UNLOAD_SECONDS": 60})

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()["live"]["IDLE_UNLOAD_SECONDS"], 60)

    def test_runtime_config_post_returns_400_on_invalid_key(self) -> None:
        def _raise(updates):
            raise ValueError("Not a live-adjustable key: ['NOT_A_KEY']")

        with patch.object(app_module.model, "apply_runtime_config", _raise):
            result = self.client.post("/runtime/config", json={"NOT_A_KEY": 1})

        self.assertEqual(result.status_code, 400)

    def test_runtime_config_post_returns_503_during_swap(self) -> None:
        with patch.object(app_module.voice_design, "swap_in_progress", lambda: True):
            result = self.client.post("/runtime/config", json={"IDLE_UNLOAD_SECONDS": 60})

        self.assertEqual(result.status_code, 503)


if __name__ == "__main__":
    unittest.main()

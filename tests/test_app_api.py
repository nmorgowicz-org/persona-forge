from __future__ import annotations

import io
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf


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

# _run_generate now returns (wav, sr, job_id)
_fake_job_counter = 0

def _fake_run_generate(text, language, **kwargs):
    global _fake_job_counter
    _fake_job_counter += 1
    job_id = f"fake-job-{_fake_job_counter}"
    return np.zeros(240, dtype=np.float32), 24000, job_id

fake_model._run_generate = _fake_run_generate

fake_model._apply_optional_seed = lambda seed: None
fake_model.resolve_seed = lambda seed_value: seed_value if seed_value is not None else 12345
fake_model._touch_last_request = lambda: None
fake_model.force_unload = lambda: None
fake_model.unload_foreign_models = lambda: None
fake_model.register_foreign_engine = lambda is_loaded, unload: None

# Async job helpers (for /generate/async, /generate/progress, /generate/cancel)
fake_model._active_jobs = {}
fake_model._active_jobs_lock = threading.Lock()

def _fake_create_job(text, seed=None):
    global _fake_job_counter
    _fake_job_counter += 1
    job_id = f"fake-job-{_fake_job_counter}"
    class _FakeJob:
        job_id = job_id
        status = "running"
        frames_generated = 0
        reference_frames = 0
        text_length = len(text)
        message = None
        wav = np.zeros(240, dtype=np.float32)
        sr = 24000
        seed = seed
        error = None
        started_at = time.monotonic()
        cancel_event = threading.Event()
    fake_model._active_jobs[job_id] = _FakeJob()
    return fake_model._active_jobs[job_id]

fake_model._create_job = _fake_create_job

def _fake_get_job_progress(job_id):
    job = fake_model._active_jobs.get(job_id)
    if job is None:
        return None
    elapsed = time.monotonic() - job.started_at
    frames = job.frames_generated
    return {
        "job_id": job_id,
        "status": job.status,
        "frames_generated": frames,
        "expected_total_frames": 60,
        "progress_pct": min(100.0, (frames / 60) * 100),
        "elapsed_seconds": round(elapsed, 1),
        "eta_seconds": None,
        "message": job.message,
    }

fake_model.get_job_progress = _fake_get_job_progress

def _fake_cancel_job(job_id):
    job = fake_model._active_jobs.get(job_id)
    if job is None or job.status != "running":
        return False
    job.status = "cancelled"
    job.message = "Cancelled by user."
    job.cancel_event.set()
    return True

fake_model.cancel_job = _fake_cancel_job

def _fake_cleanup_job(job_id):
    fake_model._active_jobs.pop(job_id, None)

fake_model._cleanup_job = _fake_cleanup_job


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
            return np.zeros(240, dtype=np.float32), 24000, "fake-job-1"

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
            return np.zeros(240, dtype=np.float32), 24000, "fake-job-1"

        with patch.object(app_module.model, "_run_generate", fake_run_generate), patch.object(
            app_module, "_encode", return_value=(b"audio", "audio/mpeg")
        ):
            result = self.client.post("/generate", json={"text": "hello"})

        self.assertEqual(result.status_code, 200)
        self.assertIsNone(seen.get("voice_id"))

    def test_voice_design_returns_preview_id_and_audio(self) -> None:
        def fake_run_voice_design_request(description, sample_text, language, seed):
            return np.zeros(240, dtype=np.float32), 24000, seed or 999

        with patch.object(
            app_module.voice_design, "run_voice_design_request", fake_run_voice_design_request
        ), patch.object(app_module, "_encode", return_value=(b"audio", "audio/wav")):
            result = self.client.post(
                "/voice_design",
                json={"description": "a calm narrator", "sample_text": "hello there"},
            )

        self.assertEqual(result.status_code, 200)
        body = result.get_json()
        self.assertIn("preview_id", body)
        self.assertTrue(len(body["preview_id"]) > 8)
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
        ), patch.object(app_module, "_encode", return_value=(b"audio", "audio/wav")):
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
        def fake_run_omnivoice_job(segments, instruct, language, candidates_per_segment, seed,
                                   num_step=None, durations=None, speed=None, guidance_scale=None,
                                   diverse_candidates=False, postprocess_output=None,
                                   min_match_score=None, on_candidate_complete=None):
            for seg_idx, text in enumerate(segments):
                for cand_idx in range(candidates_per_segment):
                    wav = np.zeros(240, dtype=np.float32)
                    candidate = (wav, 24000, False, "ok", "", None)
                    if on_candidate_complete is not None:
                        on_candidate_complete(seg_idx, cand_idx, text, candidate)

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
        self.assertIn("job_id", body)
        self.assertEqual(body["total_segments"], 2)

        # Poll until job is completed
        job_id = body["job_id"]
        import time
        for _ in range(100):
            time.sleep(0.01)
            prog = self.client.get(f"/omnivoice/audition/progress?job_id={job_id}")
            if prog.status_code == 200 and prog.get_json().get("status") == "completed":
                break

        prog_body = prog.get_json()
        self.assertEqual(prog_body["status"], "completed")
        segments = prog_body["segments_completed"]
        self.assertEqual(len(segments), 2)
        self.assertEqual(len(segments[0]["candidates"]), 2)
        candidate_ids = [c["candidate_id"] for seg in segments for c in seg["candidates"]]
        self.assertEqual(len(candidate_ids), len(set(candidate_ids)))
        self.assertIn("audio_base64", segments[0]["candidates"][0])

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
        import time
        def fake_run_omnivoice_job(segments, instruct, language, candidates_per_segment, seed,
                                   num_step=None, durations=None, speed=None, guidance_scale=None,
                                   diverse_candidates=False, postprocess_output=None,
                                   min_match_score=None, on_candidate_complete=None):
            for seg_idx, text in enumerate(segments):
                for cand_idx in range(candidates_per_segment):
                    wav = np.zeros(240, dtype=np.float32)
                    candidate = (wav, 24000, False, "ok", "", None)
                    if on_candidate_complete is not None:
                        on_candidate_complete(seg_idx, cand_idx, text, candidate)

        with patch.object(
            app_module.omnivoice_engine, "run_omnivoice_job", fake_run_omnivoice_job
        ), patch.object(app_module, "_encode", return_value=(b"raw", "audio/wav")):
            audition = self.client.post(
                "/omnivoice/audition",
                json={"segments": ["hello", "world"], "instruct": "female, young adult"},
            )

        job_id = audition.get_json()["job_id"]
        for _ in range(100):
            time.sleep(0.01)
            prog = self.client.get(f"/omnivoice/audition/progress?job_id={job_id}")
            if prog.status_code == 200 and prog.get_json().get("status") == "completed":
                break
        segments_completed = prog.get_json()["segments_completed"]
        candidate_ids = [
            c["candidate_id"]
            for seg in segments_completed
            for c in seg["candidates"]
        ]

        with patch.object(
            app_module.omnivoice_engine,
            "stitch_selected",
            lambda selected, **kw: (np.zeros(480, dtype=np.float32), 24000),
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
        import time
        def fake_run_omnivoice_job(segments, instruct, language, candidates_per_segment, seed,
                                   num_step=None, durations=None, speed=None, guidance_scale=None,
                                   diverse_candidates=False, postprocess_output=None,
                                   min_match_score=None, on_candidate_complete=None):
            for seg_idx, text in enumerate(segments):
                for cand_idx in range(candidates_per_segment):
                    wav = np.zeros(240, dtype=np.float32)
                    candidate = (wav, 24000, False, "ok", "", None)
                    if on_candidate_complete is not None:
                        on_candidate_complete(seg_idx, cand_idx, text, candidate)

        with patch.object(
            app_module.omnivoice_engine, "run_omnivoice_job", fake_run_omnivoice_job
        ), patch.object(app_module, "_encode", return_value=(b"raw", "audio/wav")):
            audition = self.client.post(
                "/omnivoice/audition",
                json={"segments": ["G'day"], "instruct": "female, young adult, high pitch"},
            )

        job_id = audition.get_json()["job_id"]
        for _ in range(100):
            time.sleep(0.01)
            prog = self.client.get(f"/omnivoice/audition/progress?job_id={job_id}")
            if prog.status_code == 200 and prog.get_json().get("status") == "completed":
                break
        segments_completed = prog.get_json()["segments_completed"]
        return segments_completed[0]["candidates"][0]["candidate_id"]

    def test_omnivoice_save_persists_to_voice_library(self) -> None:
        candidate_id = self._seed_omnivoice_candidate()
        saved_kwargs: dict[str, object] = {}

        def fake_save_voice(wav_bytes, **kwargs):
            saved_kwargs.update(kwargs)
            return {"voice_id": "ov_new123456"}

        with patch.object(
            app_module.omnivoice_engine,
            "stitch_selected",
            lambda selected, **kw: (np.zeros(480, dtype=np.float32), 24000),
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

    def test_omnivoice_progress_returns_engine_state(self) -> None:
        with patch.object(
            app_module.omnivoice_engine,
            "get_progress",
            lambda: {"phase": "generating", "total": 4, "completed": 1},
        ):
            result = self.client.get("/omnivoice/progress")

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()["phase"], "generating")

    def test_omnivoice_segments_lock_in_persists_and_lists(self) -> None:
        candidate_id = self._seed_omnivoice_candidate()
        tmpdir = tempfile.mkdtemp()
        try:
            with patch.object(app_module.segment_library, "SEGMENT_LIBRARY_DIR", Path(tmpdir)):
                create = self.client.post(
                    "/omnivoice/segments",
                    json={
                        "candidate_id": candidate_id,
                        "text": "G'day",
                        "instruct": "female, young adult, high pitch, australian accent",
                        "accent_id": "au",
                    },
                )
                self.assertEqual(create.status_code, 200)
                body = create.get_json()
                self.assertIn("segment_id", body)
                self.assertEqual(body["tags"], ["female", "young adult", "high pitch", "australian accent"])
                self.assertIn("audio_base64", body)

                listing = self.client.get("/omnivoice/segments")
                self.assertEqual(listing.status_code, 200)
                segment_ids = [s["segment_id"] for s in listing.get_json()["segments"]]
                self.assertIn(body["segment_id"], segment_ids)

                delete = self.client.delete(f"/omnivoice/segments/{body['segment_id']}")
                self.assertEqual(delete.status_code, 200)
                delete_again = self.client.delete(f"/omnivoice/segments/{body['segment_id']}")
                self.assertEqual(delete_again.status_code, 404)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_omnivoice_segments_lock_in_rejects_unknown_candidate(self) -> None:
        result = self.client.post(
            "/omnivoice/segments",
            json={"candidate_id": "nope", "text": "hi", "instruct": "female"},
        )

        self.assertEqual(result.status_code, 400)

    def test_omnivoice_stitch_accepts_segment_ids_from_library(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            with patch.object(app_module.segment_library, "SEGMENT_LIBRARY_DIR", Path(tmpdir)):
                buf = io.BytesIO()
                sf.write(buf, np.zeros(240, dtype=np.float32), 24000, format="WAV")
                meta = app_module.segment_library.save_segment(
                    buf.getvalue(),
                    text="G'day",
                    instruct="female, young adult",
                    engine="omnivoice",
                    sample_rate=24000,
                )
                with patch.object(
                    app_module.omnivoice_engine,
                    "stitch_selected",
                    lambda selected, **kw: (np.zeros(480, dtype=np.float32), 24000),
                ), patch.object(app_module, "_encode", return_value=(b"stitched", "audio/wav")):
                    result = self.client.post(
                        "/omnivoice/stitch", json={"segment_ids": [meta["segment_id"]]}
                    )

            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.data, b"stitched")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_omnivoice_stitch_rejects_unknown_segment_id(self) -> None:
        result = self.client.post("/omnivoice/stitch", json={"segment_ids": ["seg_deadbeef0000"]})

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

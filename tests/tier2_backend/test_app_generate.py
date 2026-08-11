"""Test /generate, /v1/audio/speech, and /generate/stream."""

import pytest


@pytest.mark.integration
class TestGenerate:

    def test_generate_success_wav(self, client):
        resp = client.post(
            "/generate",
            json={"text": "hello", "response_format": "wav"},
        )
        assert resp.status_code == 200
        assert "audio/wav" in resp.content_type

    def test_generate_success_mp3(self, client):
        resp = client.post(
            "/generate",
            json={"text": "hello", "response_format": "mp3"},
        )
        assert resp.status_code == 200
        assert "audio/mpeg" in resp.content_type

    def test_generate_includes_seed_header(self, client):
        resp = client.post(
            "/generate",
            json={"text": "hello", "seed": 42},
        )
        assert resp.status_code == 200
        assert "X-Seed" in resp.headers

    def test_generate_missing_text(self, client):
        resp = client.post("/generate", json={"language": "English"})
        assert resp.status_code == 400
        assert "text is required" in resp.get_json()["error"]

    def test_generate_invalid_format(self, client):
        resp = client.post(
            "/generate",
            json={"text": "hello", "response_format": "flac"},
        )
        assert resp.status_code == 400

    def test_generate_too_long_capacity_exceeded(self, client, rt):
        orig = rt.generate_should_fail
        rt.generate_should_fail = True
        try:
            resp = client.post(
                "/generate",
                json={"text": "x " * 5000},
            )
            assert resp.status_code in (422, 500)
        finally:
            rt.generate_should_fail = orig

    def test_generate_voice_id_passed_through(self, client, rt):
        resp = client.post(
            "/generate",
            json={"text": "hello", "voice_id": "vd_aabbccddeeff"},
        )
        assert resp.status_code == 200
        assert any(
            c["kwargs"].get("voice_id") == "vd_aabbccddeeff"
            for c in rt.generate_calls
        )

    def test_generate_prosody_repair_is_explicit_and_reported(self, client, rt):
        unflagged = client.post("/generate", json={"text": "First. Second."})
        flagged = client.post(
            "/generate",
            json={"text": "First. Second.", "prosody_repair": True},
        )

        assert unflagged.status_code == 200
        assert unflagged.headers["X-Prosody-Repair-Outcome"] == "not_requested"
        assert flagged.status_code == 200
        assert flagged.headers["X-Prosody-Repair-Outcome"] == "unnecessary"
        assert flagged.headers["X-Prosody-Repair-Budget-Seconds"] == "5.0"
        assert rt.generate_calls[-2]["kwargs"]["prosody_repair"] is False
        assert rt.generate_calls[-1]["kwargs"]["prosody_repair"] is True

    def test_generate_rejects_non_boolean_prosody_repair(self, client):
        resp = client.post(
            "/generate",
            json={"text": "hello", "prosody_repair": "true"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "prosody_repair must be a boolean"

    def test_generate_with_metrics_passes_repair_and_returns_metadata(self, client, rt):
        resp = client.post(
            "/generate/with_metrics",
            json={"text": "First. Second.", "prosody_repair": True},
        )
        assert resp.status_code == 200
        assert rt.generate_calls[-1]["kwargs"]["prosody_repair"] is True
        assert resp.get_json()["prosody_repair"]["outcome"] == "unnecessary"


@pytest.mark.integration
class TestOpenaiCompat:

    def test_v1_audio_speech_basic(self, client):
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "hello", "model": "tts-1", "voice": "alloy"},
        )
        assert resp.status_code == 200
        assert "audio" in resp.content_type

    def test_v1_audio_speech_missing_input(self, client):
        resp = client.post(
            "/v1/audio/speech",
            json={"model": "tts-1"},
        )
        assert resp.status_code == 400
        err = resp.get_json()["error"]
        assert "input" in err["message"].lower()
        assert err["type"] == "invalid_request_error"

    def test_v1_audio_speech_ignored_fields(self, client):
        resp = client.post(
            "/v1/audio/speech",
            json={
                "input": "hi",
                "model": "custom",
                "voice": "x",
                "response_format": "wav",
            },
        )
        assert resp.status_code == 200
        assert "audio/wav" in resp.content_type

    def test_v1_audio_speech_passes_and_reports_prosody_repair(self, client, rt):
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "First. Second.", "prosody_repair": True},
        )
        assert resp.status_code == 200
        assert rt.generate_calls[-1]["kwargs"]["prosody_repair"] is True
        assert resp.headers["X-Prosody-Repair-Outcome"] == "unnecessary"


@pytest.mark.integration
class TestStream:

    def test_stream_basic(self, client):
        resp = client.post(
            "/generate/stream",
            json={"text": "hello"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("X-Audio-Format") == "f32le"
        assert resp.headers.get("X-Audio-Sample-Rate") == "24000"

    def test_stream_requires_vocoder(self, client, rt):
        orig = rt.stream_vocoder_enabled
        rt.stream_vocoder_enabled = False
        rt.ov_runtime.vocoder_runtime.enabled = False
        try:
            resp = client.post(
                "/generate/stream",
                json={"text": "hello"},
            )
            # /generate/stream checks vocoder; without it it should refuse.
            assert resp.status_code in (503, 500)
        finally:
            rt.stream_vocoder_enabled = orig
            rt.ov_runtime.vocoder_runtime.enabled = orig

    def test_stream_rejects_complete_file_prosody_repair(self, client):
        resp = client.post(
            "/generate/stream",
            json={"text": "hello", "prosody_repair": True},
        )
        assert resp.status_code == 400
        assert "not supported" in resp.get_json()["error"]

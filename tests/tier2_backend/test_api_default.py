"""API default endpoints (Phase A1): preset + persistence contract."""

from __future__ import annotations

import pytest

from persona_forge import voice_library


@pytest.fixture(autouse=True)
def isolated_api_default(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_library, "VOICE_LIBRARY_DIR", tmp_path)
    monkeypatch.setattr(voice_library, "ACTIVE_DEFAULT_FILE", tmp_path / ".active_default")
    monkeypatch.setattr(voice_library, "API_DEFAULT_FILE", tmp_path / ".api_default.json")


def test_api_default_starts_unset(client):
    response = client.get("/api-default")

    assert response.status_code == 200
    assert response.get_json() == {"default": None}


def test_preset_can_be_api_default(client, rt, monkeypatch):
    monkeypatch.setattr(rt, "TTS_BACKEND", "pocket_tts")

    response = client.put("/api-default", json={"voice": "pocket:vera"})

    assert response.status_code == 200
    record = response.get_json()["default"]
    assert record["voice"] == "pocket:vera"
    assert record["kind"] == "preset"
    assert record["engine"] == "pocket_tts"
    # Presets have no library record, so the legacy mirror must stay empty.
    assert voice_library.get_active_default_voice_id() is None

    persisted = client.get("/api-default").get_json()["default"]
    assert persisted["voice"] == "pocket:vera"
    assert persisted["display_name"]


def test_preset_rejected_for_non_pocket_backend(client, rt, monkeypatch):
    monkeypatch.setattr(rt, "TTS_BACKEND", "openvino")

    response = client.put("/api-default", json={"voice": "pocket:vera"})

    assert response.status_code == 409
    assert "TTS_BACKEND" in response.get_json()["error"]


def test_unknown_preset_is_rejected(client, rt, monkeypatch):
    monkeypatch.setattr(rt, "TTS_BACKEND", "pocket_tts")

    response = client.put("/api-default", json={"voice": "pocket:not-a-real-voice"})

    assert response.status_code == 404
    assert voice_library.get_api_default() is None


def test_audio_speech_applies_preset_default(client, rt, monkeypatch):
    monkeypatch.setattr(rt, "TTS_BACKEND", "pocket_tts")
    client.put("/api-default", json={"voice": "pocket:vera"})
    captured: dict[str, object] = {}

    def fake_generate(_text, _language, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after capture")

    monkeypatch.setattr(rt, "_run_generate", fake_generate)

    response = client.post(
        "/v1/audio/speech",
        json={"input": "hello", "response_format": "mp3"},
    )

    # The fake raises so the request fails, but only after the no-voice request was
    # resolved to the persisted preset instead of the runtime reference.
    assert response.status_code == 500
    assert captured["voice_id"] == "pocket:vera"


def test_explicit_voice_wins_over_default(client, rt, monkeypatch):
    monkeypatch.setattr(rt, "TTS_BACKEND", "pocket_tts")
    client.put("/api-default", json={"voice": "pocket:vera"})
    captured: dict[str, object] = {}

    def fake_generate(_text, _language, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after capture")

    monkeypatch.setattr(rt, "_run_generate", fake_generate)

    response = client.post(
        "/v1/audio/speech",
        json={"input": "hello", "voice_id": "pocket:jane", "response_format": "mp3"},
    )

    assert response.status_code == 500
    assert captured["voice_id"] == "pocket:jane"

"""Engine registry and OpenAI discovery endpoints (Phase C1)."""

from __future__ import annotations

from persona_forge import speech_engines, voice_library


def test_registry_describes_pocket():
    engines = [engine.as_dict() for engine in speech_engines.list_engines()]

    assert [engine["id"] for engine in engines] == ["pocket-tts"]
    capabilities = engines[0]["capabilities"]
    assert capabilities["clone"] is True
    assert capabilities["presets"] is True
    assert capabilities["streaming"] == "frame"


def test_model_aliases_resolve_to_the_active_engine():
    for name in (None, "", "persona-forge", "persona_forge", "pocket", "pocket_tts"):
        engine, recognized = speech_engines.resolve_model(name, "pocket_tts")
        assert recognized is True
        assert engine is not None and engine.id == "pocket-tts"


def test_unknown_model_falls_back_to_active_but_is_flagged():
    engine, recognized = speech_engines.resolve_model("kokoro-82m", "pocket_tts")

    assert engine is not None and engine.id == "pocket-tts"
    assert recognized is False


def test_models_endpoint_is_openai_shaped(client):
    response = client.get("/v1/models")

    assert response.status_code == 200
    body = response.get_json()
    assert body["object"] == "list"
    entry = body["data"][0]
    assert entry["id"] == "pocket-tts"
    assert entry["object"] == "model"
    assert entry["owned_by"] == "local"
    assert entry["capabilities"]["presets"] is True


def test_voices_endpoint_lists_saved_and_presets(
    client, app_module, monkeypatch, tmp_path
):
    monkeypatch.setattr(voice_library, "VOICE_LIBRARY_DIR", tmp_path)
    monkeypatch.setattr(
        voice_library, "ACTIVE_DEFAULT_FILE", tmp_path / ".active_default"
    )
    monkeypatch.setattr(app_module.model, "TTS_BACKEND", "pocket_tts")
    saved = voice_library.save_voice(
        b"RIFF....", description="calm narrator", sample_text="hello", language="English"
    )

    response = client.get("/v1/audio/voices")

    assert response.status_code == 200
    entries = response.get_json()["data"]
    by_id = {entry["voice_id"]: entry for entry in entries}
    assert by_id[saved["voice_id"]]["kind"] == "library"
    assert by_id[saved["voice_id"]]["engine"] == "pocket-tts"
    assert by_id["pocket:vera"]["kind"] == "preset"
    assert by_id["pocket:vera"]["display_name"] == "Vera"
    assert all(entry["servable"] for entry in entries)


def test_speech_unknown_model_still_serves_and_is_flagged(client):
    response = client.post(
        "/v1/audio/speech", json={"input": "hello", "model": "not-an-engine"}
    )

    assert response.status_code == 200
    assert response.headers["X-Model-Recognized"] == "false"


def test_speech_accepts_persona_forge_alias(client, app_module, monkeypatch):
    captured: dict[str, object] = {}

    def fake_generate(_text, _language, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after capture")

    monkeypatch.setattr(app_module.model, "_run_generate", fake_generate)
    monkeypatch.setattr(app_module.model, "TTS_BACKEND", "pocket_tts")

    response = client.post(
        "/v1/audio/speech",
        json={"input": "hello", "model": "persona-forge", "response_format": "mp3"},
    )

    assert response.status_code == 500
    assert "Unknown model" not in response.get_data(as_text=True)
    assert captured["voice_id"] is None

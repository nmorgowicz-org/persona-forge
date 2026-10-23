"""Engine registry and OpenAI discovery endpoints (Phase C1)."""

from __future__ import annotations

import hashlib
import json

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


def test_registry_exposes_a_matching_adapter():
    engine = speech_engines.ENGINES["pocket-tts"]

    adapter = speech_engines.adapter_for(engine)

    assert adapter.id == "pocket-tts"
    assert isinstance(adapter, speech_engines.SpeechEngine)


def test_pocket_adapter_delegates_synthesis(app_module, monkeypatch):
    captured: dict[str, object] = {}

    def fake_generate(_text, _language, **kwargs):
        captured.update(kwargs)
        return object(), 24000, "job-1"

    monkeypatch.setattr(app_module.model, "_run_generate", fake_generate)

    wav, sample_rate, job_id = speech_engines.adapter_for(
        speech_engines.ENGINES["pocket-tts"]
    ).synthesize("hi", "English", voice_id="pocket:vera", seed_value=7)

    assert sample_rate == 24000
    assert job_id == "job-1"
    assert captured["voice_id"] == "pocket:vera"
    assert captured["seed_value"] == 7


def test_pocket_adapter_streams_pcm(monkeypatch):
    from types import SimpleNamespace

    import persona_forge

    def fake_stream(_text, _language, **kwargs):
        yield b"\x00\x00"

    monkeypatch.setattr(
        persona_forge,
        "model",
        SimpleNamespace(_run_generate_pocket_tts_stream=fake_stream),
        raising=False,
    )

    chunks = list(
        speech_engines.adapter_for(speech_engines.ENGINES["pocket-tts"]).stream_pcm(
            "hi", "English"
        )
    )

    assert chunks == [b"\x00\x00"]


def test_engines_endpoint_lists_builtin(client, app_module, monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))
    monkeypatch.setattr(app_module.model, "TTS_BACKEND", "pocket_tts")

    response = client.get("/engines")

    assert response.status_code == 200
    cards = {card["id"]: card for card in response.get_json()["engines"]}
    assert cards["pocket-tts"]["kind"] == "builtin"
    assert cards["pocket-tts"]["state"]["status"] == "built-in"
    assert cards["pocket-tts"]["active"] is True


def test_verify_builtin_engine(client, monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))

    response = client.post("/engines/pocket-tts/verify")

    assert response.status_code == 200
    assert response.get_json()["engine"]["state"]["verified"] is True


def test_verify_unknown_engine_is_404(client, monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))

    response = client.post("/engines/nope/verify")

    assert response.status_code == 404


def test_install_and_remove_pack_over_api(client, monkeypatch, tmp_path):
    data = b"blob"
    source = tmp_path / "source.bin"
    source.write_bytes(data)
    packs = tmp_path / "packs" / "demo"
    packs.mkdir(parents=True)
    (packs / "manifest.json").write_text(
        json.dumps(
            {
                "id": "demo",
                "engine_id": "demo-engine",
                "version": "1.0.0",
                "label": "Demo",
                "artifacts": [
                    {
                        "path": "model.bin",
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "size": len(data),
                        "source": source.as_uri(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path / "packs"))
    monkeypatch.setenv("ENGINE_PACKS_ALLOW_FILE_SOURCES", "1")

    installed = client.post("/engines/demo-engine/install")

    assert installed.status_code == 200
    assert installed.get_json()["state"]["status"] == "verified"
    cards = {card["id"]: card for card in client.get("/engines").get_json()["engines"]}
    assert cards["demo-engine"]["state"]["status"] == "verified"

    removed = client.post("/engines/demo-engine/remove")

    assert removed.status_code == 200
    assert removed.get_json() == {"removed": "demo-engine"}


def test_remove_builtin_engine_is_rejected(client, monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))

    response = client.post("/engines/pocket-tts/remove")

    assert response.status_code == 404


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

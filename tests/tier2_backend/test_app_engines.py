"""Engine registry and OpenAI discovery endpoints (Phase C1)."""

from __future__ import annotations

import hashlib
import json

from persona_forge import speech_engines, voice_library


def test_registry_describes_pocket_and_the_pack_only_kitten2():
    engines = [engine.as_dict() for engine in speech_engines.list_engines()]

    assert [engine["id"] for engine in engines] == ["pocket-tts", "kitten2"]
    assert [engine["pack_only"] for engine in engines] == [False, True]
    assert engines[1]["capabilities"]["clone"] is True
    assert engines[1]["capabilities"]["streaming"] == "none"
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


class _FakeWorker:
    """Stands in for PackProcess so the Kitten 2 adapter runs without a worker or weights."""

    instances: list["_FakeWorker"] = []

    def __init__(self, command, **_kwargs):
        self.command = command
        self.requests: list[dict] = []
        self.is_alive = True
        self.closed = False
        _FakeWorker.instances.append(self)

    def start(self):
        pass

    def request(self, payload, *, timeout=None):
        self.requests.append(dict(payload))
        return {"ok": True}

    def synthesize(self, payload):
        import io
        import wave

        self.requests.append({"op": "synthesize", **payload})
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(24000)
            handle.writeframes(b"\x00\x10" * 240)
        return buffer.getvalue()

    def close(self):
        self.closed = True


def _kitten_engine(monkeypatch, tmp_path):
    from persona_forge import kitten2_engine

    _FakeWorker.instances.clear()
    python = tmp_path / "python"
    python.write_text("")
    monkeypatch.setenv("KITTEN2_PYTHON", str(python))
    monkeypatch.setattr(kitten2_engine, "PackProcess", _FakeWorker)
    return kitten2_engine.Kitten2Engine(idle_unload_s=0)


def test_kitten2_adapter_serves_a_preset(monkeypatch, tmp_path):
    engine = _kitten_engine(monkeypatch, tmp_path)

    wav, rate, job = engine.synthesize("hi", "English", voice_id="kitten2:Luna", seed_value=5)

    assert rate == 24000 and job is None and len(wav) == 240
    worker = _FakeWorker.instances[0]
    assert worker.requests[0] == {"op": "load"}
    assert worker.requests[-1] == {"op": "synthesize", "text": "hi", "seed": 5, "preset": "Luna"}


def test_kitten2_adapter_prepares_a_saved_voice_once(monkeypatch, tmp_path):
    engine = _kitten_engine(monkeypatch, tmp_path)
    saved = voice_library.save_voice(
        b"RIFF....", description="x", sample_text="Some words.", language="English"
    )

    engine.synthesize("one", "English", voice_id=saved["voice_id"])
    engine.synthesize("two", "English", voice_id=saved["voice_id"])

    ops = [request["op"] for request in _FakeWorker.instances[0].requests]
    assert ops == ["load", "prepare", "synthesize", "synthesize"]
    prepare = _FakeWorker.instances[0].requests[1]
    assert prepare["reference_text"] == "Some words."
    assert _FakeWorker.instances[0].requests[-1]["voice_id"] == saved["voice_id"]


def test_kitten2_adapter_ignores_pocket_voices(monkeypatch, tmp_path):
    engine = _kitten_engine(monkeypatch, tmp_path)

    engine.synthesize("hi", "English", voice_id="pocket:vera")

    assert _FakeWorker.instances[0].requests[-1] == {"op": "synthesize", "text": "hi"}


def test_kitten2_adapter_unload_closes_the_worker(monkeypatch, tmp_path):
    engine = _kitten_engine(monkeypatch, tmp_path)
    engine.synthesize("hi", "English")

    engine.unload()
    engine.synthesize("again", "English")

    assert _FakeWorker.instances[0].closed is True
    assert len(_FakeWorker.instances) == 2


def test_kitten2_adapter_reports_a_missing_pack(monkeypatch, tmp_path):
    from persona_forge import kitten2_engine

    monkeypatch.delenv("KITTEN2_PYTHON", raising=False)
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))

    try:
        kitten2_engine.Kitten2Engine(idle_unload_s=0).synthesize("hi", "English")
    except kitten2_engine.EngineUnavailable as exc:
        assert "not installed" in str(exc)
    else:
        raise AssertionError("expected EngineUnavailable")


def test_speech_route_serves_kitten2_beside_pocket(client, app_module, monkeypatch, tmp_path):
    engine = _kitten_engine(monkeypatch, tmp_path)
    monkeypatch.setitem(speech_engines.ADAPTERS, "kitten2", engine)
    monkeypatch.setattr(app_module.model, "TTS_BACKEND", "pocket_tts")
    monkeypatch.setattr(app_module, "_generation_ready", lambda: True)
    monkeypatch.setattr(app_module.model, "_service_started", True, raising=False)

    response = client.post(
        "/v1/audio/speech",
        json={"model": "kitten2", "input": "hello", "voice": "Bruno", "response_format": "wav"},
    )

    assert response.status_code == 200
    assert response.headers["X-Model-Recognized"] == "true"
    assert _FakeWorker.instances[0].requests[-1]["preset"] == "Bruno"


def test_speech_route_returns_503_when_the_pack_is_missing(client, app_module, monkeypatch, tmp_path):
    monkeypatch.delenv("KITTEN2_PYTHON", raising=False)
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))
    monkeypatch.setattr(app_module.model, "TTS_BACKEND", "pocket_tts")
    monkeypatch.setattr(app_module, "_generation_ready", lambda: True)
    monkeypatch.setattr(app_module.model, "_service_started", True, raising=False)

    response = client.post("/v1/audio/speech", json={"model": "kitten2", "input": "hello"})

    assert response.status_code == 503
    assert "not installed" in response.get_json()["error"]["message"]


def test_models_endpoint_reports_kitten2_install_state(client, monkeypatch, tmp_path):
    monkeypatch.delenv("KITTEN2_PYTHON", raising=False)
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))

    entries = {item["id"]: item for item in client.get("/v1/models").get_json()["data"]}

    assert entries["kitten2"]["installed"] is False
    assert entries["kitten2"]["pack_only"] is True


def test_engines_endpoint_marks_kitten2_as_an_uninstalled_pack(client, app_module, monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))
    monkeypatch.setattr(app_module.model, "TTS_BACKEND", "pocket_tts")

    cards = {card["id"]: card for card in client.get("/engines").get_json()["engines"]}

    assert cards["kitten2"]["kind"] == "pack"
    assert cards["kitten2"]["state"]["status"] == "not-installed"
    assert cards["kitten2"]["state"]["verified"] is False


def test_speech_route_returns_400_for_an_unknown_kitten2_preset(client, app_module, monkeypatch, tmp_path):
    from persona_forge.pack_process import PackProcessError

    engine = _kitten_engine(monkeypatch, tmp_path)

    def reject(self, payload):
        raise PackProcessError("unknown preset 'Nobody'")

    monkeypatch.setattr(_FakeWorker, "synthesize", reject)
    monkeypatch.setitem(speech_engines.ADAPTERS, "kitten2", engine)
    monkeypatch.setattr(app_module.model, "TTS_BACKEND", "pocket_tts")
    monkeypatch.setattr(app_module, "_generation_ready", lambda: True)
    monkeypatch.setattr(app_module.model, "_service_started", True, raising=False)

    response = client.post(
        "/v1/audio/speech", json={"model": "kitten2", "input": "hi", "voice": "Nobody"}
    )

    assert response.status_code == 400
    assert "unknown preset" in response.get_json()["error"]["message"]

"""Engine registry and OpenAI discovery endpoints (Phase C1)."""

from __future__ import annotations

import hashlib
import json

import pytest

from persona_forge import speech_engines, voice_library


def test_registry_describes_pocket_and_the_pack_only_kitten2():
    engines = [engine.as_dict() for engine in speech_engines.list_engines()]

    assert [engine["id"] for engine in engines] == ["pocket-tts", "pocket-lite", "kitten2", "phonon-31m", "kokoro"]
    assert [engine["pack_only"] for engine in engines] == [False, True, True, True, True]
    kitten = engines[2]
    assert kitten["id"] == "kitten2"
    assert kitten["capabilities"]["clone"] is True
    assert kitten["capabilities"]["streaming"] == "none"
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
    engine, recognized = speech_engines.resolve_model("some-other-tts", "pocket_tts")

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
    client, rt, monkeypatch, tmp_path
):
    monkeypatch.setattr(voice_library, "VOICE_LIBRARY_DIR", tmp_path)
    monkeypatch.setattr(
        voice_library, "ACTIVE_DEFAULT_FILE", tmp_path / ".active_default"
    )
    monkeypatch.setattr(rt, "TTS_BACKEND", "pocket_tts")
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


def test_pocket_adapter_delegates_synthesis(rt, monkeypatch):
    captured: dict[str, object] = {}

    def fake_generate(_text, _language, **kwargs):
        captured.update(kwargs)
        return object(), 24000, "job-1"

    monkeypatch.setattr(rt, "_run_generate", fake_generate)

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


def test_engines_endpoint_lists_builtin(client, rt, monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))
    monkeypatch.setattr(rt, "TTS_BACKEND", "pocket_tts")

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


def test_speech_accepts_persona_forge_alias(client, rt, monkeypatch):
    captured: dict[str, object] = {}

    def fake_generate(_text, _language, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after capture")

    monkeypatch.setattr(rt, "_run_generate", fake_generate)
    monkeypatch.setattr(rt, "TTS_BACKEND", "pocket_tts")

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
    assert worker.requests[0] == {"op": "load", "warmup": False}  # warm-up is its own request
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


def test_speech_route_serves_kitten2_beside_pocket(client, app_module, rt, monkeypatch, tmp_path):
    engine = _kitten_engine(monkeypatch, tmp_path)
    monkeypatch.setitem(speech_engines.ADAPTERS, "kitten2", engine)
    monkeypatch.setattr(rt, "TTS_BACKEND", "pocket_tts")
    monkeypatch.setattr(app_module, "_generation_ready", lambda: True)
    monkeypatch.setattr(rt, "_service_started", True)

    response = client.post(
        "/v1/audio/speech",
        json={"model": "kitten2", "input": "hello", "voice": "Bruno", "response_format": "wav"},
    )

    assert response.status_code == 200
    assert response.headers["X-Model-Recognized"] == "true"
    assert _FakeWorker.instances[0].requests[-1]["preset"] == "Bruno"


def test_speech_route_returns_503_when_the_pack_is_missing(client, app_module, rt, monkeypatch, tmp_path):
    monkeypatch.delenv("KITTEN2_PYTHON", raising=False)
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))
    monkeypatch.setattr(rt, "TTS_BACKEND", "pocket_tts")
    monkeypatch.setattr(app_module, "_generation_ready", lambda: True)
    monkeypatch.setattr(rt, "_service_started", True)

    response = client.post("/v1/audio/speech", json={"model": "kitten2", "input": "hello"})

    assert response.status_code == 503
    assert "not installed" in response.get_json()["error"]["message"]


def test_models_endpoint_reports_kitten2_install_state(client, monkeypatch, tmp_path):
    monkeypatch.delenv("KITTEN2_PYTHON", raising=False)
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))

    entries = {item["id"]: item for item in client.get("/v1/models").get_json()["data"]}

    assert entries["kitten2"]["installed"] is False
    assert entries["kitten2"]["pack_only"] is True


def test_engines_endpoint_marks_kitten2_as_an_uninstalled_pack(client, rt, monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))
    monkeypatch.setattr(rt, "TTS_BACKEND", "pocket_tts")

    cards = {card["id"]: card for card in client.get("/engines").get_json()["engines"]}

    assert cards["kitten2"]["kind"] == "pack"
    assert cards["kitten2"]["state"]["status"] == "not-installed"
    assert cards["kitten2"]["state"]["verified"] is False


def test_speech_route_returns_400_for_an_unknown_kitten2_preset(client, app_module, rt, monkeypatch, tmp_path):
    from persona_forge.pack_process import PackProcessError

    engine = _kitten_engine(monkeypatch, tmp_path)

    def reject(self, payload):
        raise PackProcessError("unknown preset 'Nobody'")

    monkeypatch.setattr(_FakeWorker, "synthesize", reject)
    monkeypatch.setitem(speech_engines.ADAPTERS, "kitten2", engine)
    monkeypatch.setattr(rt, "TTS_BACKEND", "pocket_tts")
    monkeypatch.setattr(app_module, "_generation_ready", lambda: True)
    monkeypatch.setattr(rt, "_service_started", True)

    response = client.post(
        "/v1/audio/speech", json={"model": "kitten2", "input": "hi", "voice": "Nobody"}
    )

    assert response.status_code == 400
    assert "unknown preset" in response.get_json()["error"]["message"]


def test_install_route_starts_a_background_job_and_reports_progress(client, monkeypatch):
    from persona_forge import kitten2_pack

    kitten2_pack.reset_job()
    started = []
    monkeypatch.setattr(kitten2_pack, "start_install", lambda *a, **k: started.append(1) or True)
    monkeypatch.setattr(kitten2_pack, "job_status", lambda: {"state": "running", "step": "x"})

    response = client.post("/engines/kitten2/install")

    assert response.status_code == 202
    assert started == [1]
    assert client.get("/engines/kitten2/install").get_json()["job"]["state"] == "running"


def test_install_route_rejects_a_second_concurrent_install(client, monkeypatch):
    from persona_forge import kitten2_pack

    monkeypatch.setattr(kitten2_pack, "start_install", lambda *a, **k: False)

    assert client.post("/engines/kitten2/install").status_code == 409


def test_recheck_requires_an_installed_pack(client, monkeypatch, tmp_path):
    monkeypatch.delenv("KITTEN2_PYTHON", raising=False)
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))

    response = client.post("/engines/kitten2/recheck")

    assert response.status_code == 409
    assert "not installed" in response.get_json()["error"]


def test_recheck_reloads_the_worker_and_reports_status(client, monkeypatch, tmp_path):
    engine = _kitten_engine(monkeypatch, tmp_path)
    monkeypatch.setitem(speech_engines.ADAPTERS, "kitten2", engine)

    response = client.post("/engines/kitten2/recheck")

    assert response.status_code == 202
    for _ in range(100):
        if engine.status()["state"] != "loading":
            break
        import time

        time.sleep(0.02)
    assert engine.status()["state"] == "ready"
    assert len(_FakeWorker.instances) == 1


def test_engine_card_carries_install_job_and_load_status(client, monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))

    card = {c["id"]: c for c in client.get("/engines").get_json()["engines"]}["kitten2"]

    assert card["install_job"]["state"] in {"idle", "running", "done", "error"}
    assert card["load_status"]["state"] == "idle"


def test_kitten2_engine_module_imports_first_without_a_cycle():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", "import persona_forge.kitten2_engine as k; print(k.ENGINE_ID)"],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": "src"},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "kitten2"


def test_pocket_adapter_normalises_text_but_the_switch_turns_it_off(monkeypatch):
    from persona_forge import model

    seen = []

    class _Done:
        def result(self, timeout=None):
            return ("wav", 24000, None)

    monkeypatch.setattr(
        model.executor, "submit", lambda fn, text, *a, **k: seen.append(text) or _Done()
    )
    engine = speech_engines.ADAPTERS["pocket-tts"]

    engine.synthesize("Room 101", "English")
    monkeypatch.setenv("TTS_NORMALIZE_TEXT", "0")
    engine.synthesize("Room 101", "English")

    assert seen == ["Room one hundred one", "Room 101"]


def test_voice_catalog_lists_kitten_presets_from_the_installed_weights(client, monkeypatch, tmp_path):
    from persona_forge import kitten2_engine

    snapshot = tmp_path / "pack" / "hf" / "models--KittenML--kitten-tts-2" / "snapshots" / "abc" / "voices"
    snapshot.mkdir(parents=True)
    (snapshot / "voices.json").write_text('{"Bruno": {}, "Luna": {}}')
    monkeypatch.setattr(kitten2_engine, "pack_directory", lambda root=None: tmp_path / "pack")
    monkeypatch.setattr(kitten2_engine, "is_installed", lambda root=None: True)

    voices = client.get("/v1/audio/voices").get_json()["data"]

    ids = {v["voice_id"] for v in voices if v["engine"] == "kitten2"}
    assert ids == {"kitten2:Bruno", "kitten2:Luna"}


def test_voice_catalog_has_no_kitten_presets_when_not_installed(client, monkeypatch):
    from persona_forge import kitten2_engine

    monkeypatch.setattr(kitten2_engine, "is_installed", lambda root=None: False)

    voices = client.get("/v1/audio/voices").get_json()["data"]

    assert not [v for v in voices if v["engine"] == "kitten2"]


def test_phonon_is_listed_installable_and_has_voices(client, monkeypatch):
    from persona_forge import phonon_engine, phonon_pack

    monkeypatch.setattr(phonon_engine, "is_installed", lambda root=None: True)
    monkeypatch.setattr(phonon_engine, "list_presets", lambda root=None: ["Easton", "Zoey"])
    monkeypatch.setattr(phonon_pack, "start_install", lambda *a, **k: True)

    cards = {c["id"]: c for c in client.get("/engines").get_json()["engines"]}
    voices = client.get("/v1/audio/voices").get_json()["data"]
    models = {m["id"]: m for m in client.get("/v1/models").get_json()["data"]}
    installed = client.post("/engines/phonon-31m/install")

    assert cards["phonon-31m"]["install_job"]["state"] in {"idle", "running", "done", "error"}
    assert {v["voice_id"] for v in voices if v["engine"] == "phonon-31m"} == {
        "phonon:Easton", "phonon:Zoey",
    }
    assert models["phonon-31m"]["installed"] is True
    assert installed.status_code == 202


def test_voice_catalog_hides_non_english_unless_asked(client, monkeypatch):
    from persona_forge import kokoro_engine

    monkeypatch.setattr(kokoro_engine, "is_installed", lambda root=None: True)
    monkeypatch.setattr(kokoro_engine, "list_presets", lambda root=None: ["af_heart", "ff_siwis"])

    english = client.get("/v1/audio/voices").get_json()
    everything = client.get("/v1/audio/voices?language=all").get_json()

    kokoro = lambda body: {v["voice_id"] for v in body["data"] if v["engine"] == "kokoro"}  # noqa: E731
    assert kokoro(english) == {"kokoro:af_heart"}
    assert kokoro(everything) == {"kokoro:af_heart", "kokoro:ff_siwis"}
    assert english["language_filter"] == "en" and english["hidden_by_language_filter"] >= 1
    assert everything["language_filter"] == "all" and everything["hidden_by_language_filter"] == 0


def test_a_hidden_voice_can_still_be_requested(client, monkeypatch):
    from persona_forge import kokoro_engine

    class Fake:
        def synthesize(self, text, language, **kw):
            import numpy as np
            return np.zeros(240, dtype="float32"), 24000, None

    monkeypatch.setattr(speech_engines, "adapter_for", lambda engine: Fake())
    monkeypatch.setattr(kokoro_engine, "is_installed", lambda root=None: True)

    response = client.post(
        "/v1/audio/speech",
        json={"model": "kokoro", "input": "Bonjour", "voice": "kokoro:ff_siwis", "response_format": "wav"},
    )

    assert response.status_code == 200


def test_kitten_clone_without_a_transcript_explains_how_to_fix_it(monkeypatch, tmp_path):
    import pytest as _pytest

    from persona_forge import kitten2_engine

    voice = voice_library.save_voice(
        b"RIFF....", description="x", sample_text="", language="English"
    )
    engine = _kitten_engine(monkeypatch, tmp_path)

    with _pytest.raises(kitten2_engine.InvalidVoice, match="Transcribe"):
        engine.synthesize("hi", "English", voice_id=voice["voice_id"])
    assert not [r for r in _FakeWorker.instances[0].requests if r["op"] == "prepare"]


def test_builtin_catalog_lists_pack_presets_only_when_asked(client, monkeypatch):
    from persona_forge import provisioned_engines

    class _Stub:
        PRESET_PREFIX = "kokoro:"

        def is_installed(self):
            return True

        def list_presets(self):
            return ["af_heart", "ff_siwis"]

        def preset_language(self, name):
            return "fr" if name.startswith("ff") else "en"

    class _Entry:
        engine = _Stub()
        engine_id = "kokoro"

    monkeypatch.setattr(provisioned_engines, "get", lambda eid: _Entry() if eid == "kokoro" else None)
    plain = client.get("/voices/built-in").get_json()
    assert all(v["backend"] == "pocket_tts" for v in plain["voices"]) and "engines" not in plain
    full = client.get("/voices/built-in?engines=all").get_json()
    ids = {v["voice_id"] for v in full["voices"]}
    assert {"kokoro:af_heart", "kokoro:ff_siwis"} <= ids
    kokoro = next(e for e in full["engines"] if e["id"] == "kokoro")
    assert kokoro == {
        "id": "kokoro", "label": "Kokoro 82M", "installed": True, "voices": 2,
        "import_prepared_voice": False,
    }
    assert next(v for v in full["voices"] if v["voice_id"] == "kokoro:ff_siwis")["language_code"] == "fr"
    assert all(v["installed"] for v in full["voices"])


def test_builtin_catalog_lists_an_uninstalled_engine_from_the_bundled_catalog(client, monkeypatch):
    from persona_forge import provisioned_engines, voice_catalog

    class _NotInstalled:
        PRESET_PREFIX = "kokoro:"

        def is_installed(self):
            return False

        def list_presets(self):  # an engine that is not installed has nothing to report
            return []

        def preset_language(self, name):
            return "en"

    class _Entry:
        engine = _NotInstalled()
        engine_id = "kokoro"

    monkeypatch.setattr(provisioned_engines, "get", lambda eid: _Entry() if eid == "kokoro" else None)
    full = client.get("/voices/built-in?engines=all").get_json()

    bundled = voice_catalog.bundled_voices("kokoro")
    listed = [v for v in full["voices"] if v["engine"] == "kokoro"]
    assert bundled and len(listed) == len(bundled)
    assert not any(v["installed"] for v in listed)
    assert next(v for v in full["voices"] if v["engine"] == "pocket-tts")["installed"] is True
    summary = next(e for e in full["engines"] if e["id"] == "kokoro")
    assert summary["installed"] is False and summary["voices"] == len(bundled)


def _streaming_fake(calls):
    class Fake:
        def stream_pcm(self, text, language, **kw):
            calls.append(kw)
            yield b"\x01\x00" * 50
            yield b"\x02\x00" * 50

        def synthesize(self, text, language, **kw):
            import numpy as np

            calls.append({"whole": True, **kw})
            return np.zeros(240, dtype="float32"), 24000, None

    return Fake()


@pytest.mark.parametrize(
    ("model_name", "voice"), [("phonon-31m", "phonon:Zoey"), ("pocket-lite", "pocket-lite:jane")]
)
def test_streaming_pack_engines_send_pcm_chunks(client, monkeypatch, model_name, voice):
    calls = []
    monkeypatch.setattr(speech_engines, "adapter_for", lambda engine: _streaming_fake(calls))

    response = client.post(
        "/v1/audio/speech",
        json={"model": model_name, "input": "hi", "voice": voice, "response_format": "pcm", "seed": 5},
    )

    assert response.status_code == 200 and response.content_type == "audio/pcm"
    assert response.data == b"\x01\x00" * 50 + b"\x02\x00" * 50
    assert response.headers["X-Seed"] == "5" and response.headers["X-Audio-Sample-Rate"] == "24000"
    assert calls == [{"voice_id": voice, "seed_value": 5, "speed": None}]


def test_kokoro_does_not_stream_even_for_pcm(client, monkeypatch):
    calls = []
    monkeypatch.setattr(speech_engines, "adapter_for", lambda engine: _streaming_fake(calls))

    response = client.post(
        "/v1/audio/speech",
        json={"model": "kokoro", "input": "hi", "voice": "kokoro:af_heart", "response_format": "pcm"},
    )

    assert response.status_code == 200
    assert calls and calls[0].get("whole") is True  # one whole clip, never the chunk path
    assert speech_engines.ENGINES["kokoro"].capabilities.streaming == "none"


def test_temporary_model_patches_restore_generation_and_adapters(client, app_module, rt):
    """A failed capture request must not poison the next test's shared fake."""
    original_backend = rt.TTS_BACKEND
    original_generate = rt._run_generate
    original_started = rt._service_started
    original_adapters = dict(speech_engines.ADAPTERS)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(rt, "_service_started", not original_started)
        assert app_module.model._service_started is not original_started
    assert rt._service_started == app_module.model._service_started == original_started

    def capture_only(*args, **kwargs):
        raise RuntimeError("temporary capture failure")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(rt, "_run_generate", capture_only)
        patch.setattr(rt, "TTS_BACKEND", "pocket_tts")
        patch.setattr(rt, "_service_started", True)
        patch.setattr(rt, "_capture_only_marker", True, raising=False)
        patch.setitem(speech_engines.ADAPTERS, "kitten2", object())
        response = client.post("/v1/audio/speech", json={"input": "hello"})
        assert response.status_code == 500
        assert "temporary capture failure" in response.get_json()["error"]["message"]

    assert rt.TTS_BACKEND == app_module.model.TTS_BACKEND == original_backend
    assert rt._run_generate is app_module.model._run_generate is original_generate
    assert rt._service_started == app_module.model._service_started == original_started
    assert not hasattr(rt, "_capture_only_marker")
    assert not hasattr(app_module.model, "_capture_only_marker")
    assert speech_engines.ADAPTERS == original_adapters
    response = client.post("/v1/audio/speech", json={"input": "hello"})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.content_type.startswith("audio/")


def test_engine_card_exposes_the_effective_idle_unload(client, monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))
    monkeypatch.delenv("KITTEN2_IDLE_UNLOAD_S", raising=False)
    pack = tmp_path / "kitten2"
    pack.mkdir()
    (pack / "manifest.json").write_text(
        '{"id": "kitten2", "engine_id": "kitten2", "version": "1", "provisioner": "kitten2",'
        ' "artifacts": [], "idle_unload_after": 123}',
        encoding="utf-8",
    )

    card = {c["id"]: c for c in client.get("/engines").get_json()["engines"]}["kitten2"]

    assert card["load_status"]["idle_unload_after"] == 123.0
    assert card["load_status"]["idle_unload_source"] == "manifest"
    assert card["pack"]["idle_unload_after"] == 123.0

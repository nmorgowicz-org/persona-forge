"""Regressions for the review findings: idle unload, pack removal, Kokoro verify, normaliser."""

from __future__ import annotations

import json

from persona_forge import engine_packs, kokoro_pack, speech_engines, text_normalizer
from tests.tier2_backend.test_imported_voices import store as store  # noqa: F401 - pytest fixture
from tests.tier2_backend.test_phonon_import import engine as engine  # noqa: F401 - pytest fixture


def test_idle_unload_leaves_a_worker_with_a_stream_in_flight(engine, store):  # noqa: F811
    engine._ensure_started()
    process = engine._process
    engine._active = 1

    engine._unload_if_idle()

    assert engine._process is process and process.is_alive
    engine._active = 0
    engine._unload_if_idle()
    assert engine._process is None


def test_removing_a_pack_stops_its_loaded_worker(client, monkeypatch, tmp_path):
    stopped: list[str] = []

    class Loaded:
        def unload(self):
            stopped.append("unloaded")

    monkeypatch.setitem(speech_engines.ADAPTERS, "demo-engine", Loaded())
    monkeypatch.setattr(engine_packs, "remove_pack", lambda engine_id: True)

    response = client.post("/engines/demo-engine/remove")

    assert response.status_code == 200
    assert stopped == ["unloaded", "unloaded"]  # before the delete, and for a racing restart


def test_kokoro_verify_catches_a_damaged_or_missing_model_file(tmp_path):
    pack = tmp_path / "kokoro-pack"
    (pack / "models").mkdir(parents=True)
    (pack / "manifest.json").write_text(json.dumps(kokoro_pack.build_manifest()), encoding="utf-8")
    stamp = engine_packs.load_manifest(pack).manifest_sha256
    engine_packs._write_verification_stamp(pack, stamp)
    model_file = pack / "models" / kokoro_pack.MODEL_FILE[0]
    voices_file = pack / "models" / kokoro_pack.VOICES_FILE[0]
    model_file.write_bytes(b"damaged")

    status = engine_packs.inspect_pack(pack, verify=True)

    assert not status.verified
    assert any(f"hash mismatch: models/{kokoro_pack.MODEL_FILE[0]}" in e for e in status.errors)
    assert any(f"missing models/{kokoro_pack.VOICES_FILE[0]}" in e for e in status.errors)
    assert voices_file.exists() is False
    # Verifying never mints the installer's stamp: it is the one written above, untouched.
    assert engine_packs._verification_stamp(pack)["manifest_sha256"] == stamp


def test_pocket_normalises_numbers_only_for_english(monkeypatch):
    seen: list[str] = []

    class Model:
        executor = type("E", (), {"submit": staticmethod(lambda fn, text, *a, **k: _Done(fn(text)))})
        _run_generate = staticmethod(lambda text, *a, **k: seen.append(text) or (None, 1, None))

    class _Done:
        def __init__(self, value):
            self.value = value

        def result(self, timeout=None):
            return self.value

    import persona_forge

    monkeypatch.setattr(persona_forge, "model", Model, raising=False)
    monkeypatch.setitem(__import__("sys").modules, "persona_forge.model", Model)
    monkeypatch.delenv("POCKET_TTS_LANGUAGE", raising=False)
    adapter = speech_engines.PocketTtsEngine()

    adapter.synthesize("I have 2 cats", "English")
    adapter.synthesize("J'ai 2 chats", "French")
    monkeypatch.setenv("POCKET_TTS_LANGUAGE", "french")
    adapter.synthesize("J'ai 2 chats", "English")

    assert seen[0] == text_normalizer.normalize("I have 2 cats") != "I have 2 cats"
    assert seen[1:] == ["J'ai 2 chats", "J'ai 2 chats"]

    monkeypatch.delenv("POCKET_TTS_LANGUAGE")
    adapter.synthesize("J'ai 2 chats", "Auto")  # auto-detected French
    adapter.synthesize("I have 2 cats", "Auto")  # auto-detected English
    assert seen[3] == "J'ai 2 chats"
    assert seen[4] == seen[0]


def test_a_ready_worker_stops_serving_once_its_pack_is_gone(engine, store, monkeypatch):  # noqa: F811
    import pytest

    from persona_forge.kitten2_engine import EngineUnavailable

    engine._ensure_started()
    process = engine._process
    monkeypatch.setattr(engine, "_pack_python", lambda: None)

    with pytest.raises(EngineUnavailable):
        engine._await_ready()

    assert engine._process is None and not process.is_alive

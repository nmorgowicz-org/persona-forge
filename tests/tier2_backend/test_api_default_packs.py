"""API default on a pack engine (plan §4.5, §5.3, journey 6): set, route, persist, repair, remove guard.

Packs are stubbed at the engine-module boundary (``is_installed`` / ``list_presets``) and the
adapter, so no worker process starts; everything above that is the real route code.
"""

from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
import pytest

from persona_forge import (
    engine_packs,
    kitten2_engine,
    kokoro_engine,
    phonon_engine,
    pocket_lite_engine,
    speech_engines,
    voice_library,
)

KOKORO_VOICES = ["af_heart", "bm_george"]
PHONON_VOICES = ["Zoey", "Captain Silas Blackwater"]


@pytest.fixture(autouse=True)
def isolated_api_default(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_library, "VOICE_LIBRARY_DIR", tmp_path)
    monkeypatch.setattr(voice_library, "ACTIVE_DEFAULT_FILE", tmp_path / ".active_default")
    monkeypatch.setattr(voice_library, "API_DEFAULT_FILE", tmp_path / ".api_default.json")


@pytest.fixture
def packs(monkeypatch, rt, app_module):
    """Kokoro, Phonon, Pocket Lite and Kitten 2 'installed'; Pocket is the active backend."""
    state = {"kokoro": True, "phonon": True, "lite": True, "kitten": True}
    monkeypatch.setattr(kokoro_engine, "is_installed", lambda root=None: state["kokoro"])
    monkeypatch.setattr(kokoro_engine, "list_presets", lambda root=None: list(KOKORO_VOICES))
    monkeypatch.setattr(phonon_engine, "is_installed", lambda root=None: state["phonon"])
    monkeypatch.setattr(phonon_engine, "list_presets", lambda root=None: list(PHONON_VOICES))
    monkeypatch.setattr(pocket_lite_engine, "is_installed", lambda root=None: state["lite"])
    monkeypatch.setattr(pocket_lite_engine, "list_presets", lambda root=None: ["alba", "jane"])
    monkeypatch.setattr(kitten2_engine, "is_installed", lambda root=None: state["kitten"])
    monkeypatch.setattr(kitten2_engine, "list_presets", lambda root=None: ["Bruno"])
    monkeypatch.setattr(rt, "TTS_BACKEND", "pocket_tts")
    monkeypatch.setattr(app_module, "_generation_ready", lambda: True)
    monkeypatch.setattr(rt, "_service_started", True)
    return state


@pytest.fixture
def served(monkeypatch):
    """Replace the adapters; every call is recorded as ``(engine_id, kwargs)``."""
    calls: list[tuple[str, dict]] = []

    class Fake:
        def __init__(self, engine_id):
            self.engine_id = engine_id

        def synthesize(self, text, language, **kw):
            calls.append((self.engine_id, kw))
            return np.zeros(240, dtype="float32"), 24000, None

        def stream_pcm(self, text, language, **kw):
            calls.append((self.engine_id, kw))
            yield b"\x01\x00" * 10

    monkeypatch.setattr(speech_engines, "adapter_for", lambda engine: Fake(engine.id))
    return calls


def _speak(client, **payload):
    return client.post(
        "/v1/audio/speech", json={"input": "hello", "response_format": "wav", **payload}
    )


def _saved_voice(transcript="a transcript"):
    return voice_library.save_voice(
        b"RIFF....", description="Mine", sample_text=transcript, language="English"
    )["voice_id"]


# ── setting ──────────────────────────────────────────────────────────────────────────────────


def test_a_pack_voice_can_be_the_api_default(client, packs):
    response = client.put("/api-default", json={"voice": "kokoro:af_heart"})

    assert response.status_code == 200
    record = response.get_json()["default"]
    assert record["voice"] == "kokoro:af_heart"
    assert record["engine"] == "kokoro" and record["engine_label"] == "Kokoro 82M"
    assert record["kind"] == "preset" and record["servable"] is True and record["problem"] is None
    assert record["display_name"] == "af_heart"
    # The legacy mirror drives the active backend's runtime voice; a pack default clears it.
    assert voice_library.get_active_default_voice_id() is None
    assert client.get("/api-default").get_json()["default"]["voice"] == "kokoro:af_heart"


def test_pack_voice_names_may_contain_spaces(client, packs):
    response = client.put("/api-default", json={"voice": "phonon:Captain Silas Blackwater"})

    assert response.status_code == 200
    assert response.get_json()["default"]["engine"] == "phonon-31m"


def test_setting_a_pack_default_replaces_a_saved_voice_mirror(client, packs):
    voice_library.set_api_default("pocket_tts", _saved_voice())
    assert voice_library.get_active_default_voice_id() is not None

    client.put("/api-default", json={"voice": "kokoro:af_heart"})

    assert voice_library.get_active_default_voice_id() is None


@pytest.mark.parametrize(
    ("payload", "status", "needle"),
    [
        ({"voice": "kokoro:nobody"}, 404, "unknown Kokoro 82M voice"),
        ({"voice": "kokoro:af_heart", "engine": "phonon-31m"}, 400, "belongs to engine"),
        ({"voice": "madeup:voice"}, 400, "unknown voice namespace"),
        ({"voice": "kokoro:../evil"}, 400, "invalid preset voice"),
    ],
)
def test_set_time_validation(client, packs, payload, status, needle):
    response = client.put("/api-default", json=payload)

    assert response.status_code == status
    assert needle in response.get_json()["error"]
    assert voice_library.get_api_default() is None  # nothing was persisted


def test_an_engine_that_is_not_installed_is_refused(client, packs):
    packs["kokoro"] = False

    response = client.put("/api-default", json={"voice": "kokoro:af_heart"})

    assert response.status_code == 409
    assert "not installed" in response.get_json()["error"]
    assert voice_library.get_api_default() is None


def test_a_failed_set_keeps_the_previous_default(client, packs, monkeypatch):
    client.put("/api-default", json={"voice": "pocket:vera"})
    before = voice_library.API_DEFAULT_FILE.read_text()

    def boom(path, payload):
        raise OSError("disk full")

    monkeypatch.setattr(voice_library, "_write_text_atomic", boom)
    response = client.put("/api-default", json={"voice": "kokoro:af_heart"})

    assert response.status_code == 500
    assert voice_library.API_DEFAULT_FILE.read_text() == before


# ── serving ──────────────────────────────────────────────────────────────────────────────────


def test_a_request_without_a_voice_is_served_by_the_defaults_engine(client, packs, served):
    client.put("/api-default", json={"voice": "kokoro:af_heart"})

    for extra in ({}, {"model": "tts-1"}, {"model": "persona-forge"}, {"model": "not-a-model"}):
        response = _speak(client, **extra)
        assert response.status_code == 200, response.get_data(as_text=True)

    assert [c[0] for c in served] == ["kokoro"] * 4
    assert all(c[1]["voice_id"] == "kokoro:af_heart" for c in served)


def test_a_streaming_pack_default_streams_pcm(client, packs, served):
    client.put("/api-default", json={"voice": "phonon:Zoey"})

    response = _speak(client, response_format="pcm")

    assert response.status_code == 200 and response.content_type == "audio/pcm"
    assert [(engine, kw["voice_id"]) for engine, kw in served] == [("phonon-31m", "phonon:Zoey")]


def test_a_request_naming_another_engine_does_not_use_the_default(client, packs, served):
    client.put("/api-default", json={"voice": "kokoro:af_heart"})

    response = _speak(client, model="pocket-tts")

    assert response.status_code == 200
    assert served[0][0] == "pocket-tts" and served[0][1]["voice_id"] is None


@pytest.mark.parametrize("default_kind", ["pocket", "saved"])
@pytest.mark.parametrize("model_name,engine_id", [
    ("kitten-tts-2", "kitten2"), ("kokoro-82m", "kokoro"),
])
@pytest.mark.parametrize("fmt", ["wav", "pcm"])
def test_a_named_pack_uses_its_own_voice_instead_of_the_active_backends_default(
    client, packs, served, default_kind, model_name, engine_id, fmt
):
    voice = "pocket:vera" if default_kind == "pocket" else _saved_voice()
    voice_library.set_api_default("pocket_tts", voice)

    response = _speak(client, model=model_name, response_format=fmt)

    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.data
    assert len(served) == 1
    assert served[0][0] == engine_id
    assert served[0][1]["voice_id"] is None
    assert served[0][1].get("voice_variant_id") is None


def test_an_explicit_voice_wins_over_the_default(client, packs, served):
    client.put("/api-default", json={"voice": "kokoro:af_heart"})

    _speak(client, voice="pocket:jane", model="pocket-tts")

    assert served[0][0] == "pocket-tts" and served[0][1]["voice_id"] == "pocket:jane"


def test_a_namespaced_voice_implies_its_engine(client, packs, served):
    _speak(client, voice="phonon:Zoey", model="tts-1")
    _speak(client, voice="kokoro:af_heart")
    mismatch = _speak(client, voice="kokoro:af_heart", model="pocket-tts")

    # An explicit model remains authoritative: reject its mismatched voice, never render it
    # with another speaker (or silently route to the voice's engine).
    assert mismatch.status_code == 400
    assert "engine" in mismatch.get_json()["error"]["message"]
    assert [c[0] for c in served] == ["phonon-31m", "kokoro"]


def test_pocket_and_saved_voice_defaults_are_served_as_before(client, packs, served):
    client.put("/api-default", json={"voice": "pocket:vera"})
    _speak(client)
    assert served[-1][0] == "pocket-tts" and served[-1][1]["voice_id"] == "pocket:vera"

    saved = _saved_voice()
    voice_library.set_api_default("pocket_tts", saved)
    _speak(client)
    assert served[-1][0] == "pocket-tts" and served[-1][1]["voice_id"] == saved


# ── repair, never a silent fallback ──────────────────────────────────────────────────────────


def _assert_actionable(response, *needles):
    assert response.status_code == 409
    error = response.get_json()["error"]
    assert error["code"] == "api_default_unavailable" and error["type"] == "invalid_request_error"
    for needle in needles:
        assert needle in error["message"]


def test_a_removed_engine_gives_an_actionable_error_and_no_audio(client, packs, served):
    client.put("/api-default", json={"voice": "kokoro:af_heart"})
    packs["kokoro"] = False  # the pack disappeared outside the app

    for extra in ({}, {"model": "kokoro"}):
        _assert_actionable(
            _speak(client, **extra), "kokoro:af_heart", "Kokoro 82M", "not installed", "Runtime → Speech engines"
        )
    assert served == []  # neither another speaker nor another engine was used

    view = client.get("/api-default").get_json()["default"]
    assert view["servable"] is False
    assert view["problem"]["code"] == "engine_not_installed"
    assert "Install Kokoro 82M again" in view["problem"]["repair"]


def test_a_vanished_voice_gives_an_actionable_error(client, packs, served, monkeypatch):
    client.put("/api-default", json={"voice": "kokoro:bm_george"})
    monkeypatch.setattr(kokoro_engine, "list_presets", lambda root=None: ["af_heart"])

    _assert_actionable(_speak(client), "kokoro:bm_george", "no longer offered", "different API default")
    assert served == []
    problem = client.get("/api-default").get_json()["default"]["problem"]
    assert problem["code"] == "voice_missing"


def test_an_explicit_voice_still_works_while_the_default_is_broken(client, packs, served):
    client.put("/api-default", json={"voice": "kokoro:af_heart"})
    packs["kokoro"] = False

    response = _speak(client, voice="phonon:Zoey")

    assert response.status_code == 200 and served[0][0] == "phonon-31m"


# ── saved voices cloned on a pack engine ─────────────────────────────────────────────────────


def test_a_saved_voice_can_be_the_default_on_a_cloning_pack_engine(client, packs, served):
    saved = _saved_voice()
    voice_library.set_api_default("pocket_tts", "pocket:vera")

    response = client.put("/api-default", json={"voice": saved, "engine": "pocket-lite"})

    assert response.status_code == 200
    record = response.get_json()["default"]
    assert record["engine"] == "pocket-lite" and record["kind"] == "library"
    assert record["servable"] is True
    assert voice_library.get_active_default_voice_id() is None  # active backend untouched

    assert _speak(client).status_code == 200
    assert served == [("pocket-lite", {**served[0][1], "voice_id": saved})]


def test_saved_voice_defaults_on_the_active_backend_keep_their_mirror(client, packs, monkeypatch, app_module):
    saved = _saved_voice()
    monkeypatch.setattr(app_module, "_activate_library_voice_for_api", lambda voice: ({}, None))

    response = client.put("/api-default", json={"voice": saved})

    assert response.status_code == 200
    assert response.get_json()["default"]["engine"] == "pocket_tts"
    assert voice_library.get_active_default_voice_id() == saved


def test_a_failed_save_puts_the_previous_runtime_voice_back(client, packs, monkeypatch, app_module):
    previous, attempted = _saved_voice(), _saved_voice()
    voice_library.set_api_default("pocket_tts", previous)
    activated = []
    monkeypatch.setattr(
        app_module, "_activate_library_voice_for_api", lambda voice: activated.append(voice) or ({}, None)
    )

    def boom(path, payload):
        raise OSError("disk full")

    monkeypatch.setattr(voice_library, "_write_text_atomic", boom)
    response = client.put("/api-default", json={"voice": attempted})

    assert response.status_code == 500
    assert activated == [attempted, previous]  # swapped, then swapped back
    current = voice_library.get_api_default()
    assert current is not None and current["voice"] == previous


def test_engines_that_cannot_clone_refuse_a_saved_voice(client, packs):
    response = client.put("/api-default", json={"voice": _saved_voice(), "engine": "kokoro"})

    assert response.status_code == 400 and "cannot clone" in response.get_json()["error"]
    assert voice_library.get_api_default() is None


def test_kitten_needs_a_transcript_before_it_can_be_the_default(client, packs):
    response = client.put(
        "/api-default", json={"voice": _saved_voice(transcript=""), "engine": "kitten2"}
    )

    assert response.status_code == 400 and "transcript" in response.get_json()["error"]


def test_a_deleted_saved_voice_default_on_a_pack_engine_is_reported(client, packs, served):
    saved = _saved_voice()
    client.put("/api-default", json={"voice": saved, "engine": "pocket-lite"})

    assert client.delete(f"/voices/{saved}").status_code == 200

    _assert_actionable(_speak(client), saved, "was deleted")
    assert served == []
    view = client.get("/api-default").get_json()["default"]
    assert view["problem"]["code"] == "voice_missing" and view["servable"] is False


# ── removing the engine ──────────────────────────────────────────────────────────────────────


def test_the_engine_serving_the_default_cannot_be_removed(client, packs, monkeypatch):
    removed = []
    monkeypatch.setattr(engine_packs, "remove_pack", lambda engine_id, root=None: removed.append(engine_id) or True)
    client.put("/api-default", json={"voice": "kokoro:af_heart"})

    response = client.post("/engines/kokoro/remove")

    assert response.status_code == 409
    body = response.get_json()
    assert "Change the API default first" in body["error"]
    assert body["code"] == "api_default_engine"
    assert removed == []
    cards = {c["id"]: c for c in client.get("/engines").get_json()["engines"]}
    assert cards["kokoro"]["api_default"] is True and cards["phonon-31m"]["api_default"] is False

    # Another engine is not affected, and the guard lifts once the default moves.
    assert client.post("/engines/phonon-31m/remove").status_code == 200
    client.put("/api-default", json={"voice": "pocket:vera"})
    assert client.post("/engines/kokoro/remove").status_code == 200
    assert removed == ["phonon-31m", "kokoro"]


def test_a_saved_voice_default_on_a_pack_engine_also_blocks_removal(client, packs, monkeypatch):
    monkeypatch.setattr(engine_packs, "remove_pack", lambda engine_id, root=None: True)
    client.put("/api-default", json={"voice": _saved_voice(), "engine": "pocket-lite"})

    response = client.post("/engines/pocket-lite/remove")

    assert response.status_code == 409
    assert "Change the API default first" in response.get_json()["error"]


# ── persistence ──────────────────────────────────────────────────────────────────────────────


def test_the_default_survives_a_restart(client, packs, tmp_path):
    client.put("/api-default", json={"voice": "phonon:Zoey"})

    # A new process knows nothing but the files on disk.
    code = (
        "import json;from persona_forge import voice_library as v;"
        "print(json.dumps(v.get_api_default()))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        env={"VOICE_LIBRARY_DIR": str(tmp_path), "PATH": "", "PYTHONPATH": ":".join(sys.path)},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    restored = json.loads(out)

    assert restored["voice"] == "phonon:Zoey" and restored["engine"] == "phonon-31m"

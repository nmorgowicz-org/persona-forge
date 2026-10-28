"""HTTP routes behind the My voices Engines row: binding status, Prepare for..., transcript review."""

from __future__ import annotations

import io
import threading
import time

import numpy as np
import pytest
import soundfile as sf

from persona_forge import engine_lifecycle, speech_engines, voice_bindings, voice_library, voice_prepare
from persona_forge.pack_process import PackProcessError


def _clip(seed: int = 0) -> bytes:
    samples = (np.random.default_rng(seed).standard_normal(24000) * 0.05).astype(np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, samples, 24000, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


class StubAdapter:
    def __init__(self, engine_id, *, error=None, gate=None):
        self.engine_id, self.error, self.gate = engine_id, error, gate
        self.calls: list[str] = []

    def prepare_voice(self, voice_id, *, cancel=None):
        self.calls.append(voice_id)
        if self.gate is not None:
            while not self.gate.wait(0.01):
                if cancel is not None and cancel.is_set():
                    raise engine_lifecycle.PrepareCancelled("cancelled")
        if self.error is not None:
            raise self.error
        meta = voice_library.get_voice(voice_id)
        assert meta is not None
        voice_bindings.write_marker(voice_id, self.engine_id, voice_bindings.current_key(meta, self.engine_id))


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_library, "VOICE_LIBRARY_DIR", tmp_path / "voices")
    present = {"kitten2", "pocket-lite"}
    monkeypatch.setattr(voice_bindings, "_is_installed", lambda engine_id: engine_id in present)
    monkeypatch.setattr(voice_bindings, "engine_revision", lambda engine_id: "rev-1")
    monkeypatch.setattr(voice_bindings, "_needs_transcript", lambda engine_id: engine_id == "kitten2")
    adapters = {
        "kitten2": StubAdapter("kitten2"),
        "pocket-lite": StubAdapter("pocket-lite"),
    }
    for engine_id, adapter in adapters.items():
        monkeypatch.setitem(speech_engines.ADAPTERS, engine_id, adapter)
    voice_prepare.reset()
    yield {"present": present, "adapters": adapters}
    voice_prepare.reset()


def _voice(text="hello there", seed=0):
    return voice_library.save_voice(_clip(seed), description="d", sample_text=text, language="English")


def _wait(predicate, what, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


def _binding(client, voice_id, engine_id):
    body = client.get(f"/voices/{voice_id}/engines").get_json()
    return next(b for b in body["engines"] if b["engine"] == engine_id)


def _prepare(client, voice_id, engine_id, **body):
    return client.post(f"/voices/{voice_id}/engines/{engine_id}/prepare", json=body or None)


def test_engines_route_lists_a_binding_per_engine_for_one_voice(client, env):
    voice = _voice()

    response = client.get(f"/voices/{voice['voice_id']}/engines")

    assert response.status_code == 200
    body = response.get_json()
    assert body["voice_id"] == voice["voice_id"]
    by_engine = {b["engine"]: b for b in body["engines"]}
    assert by_engine["pocket-tts"]["status"] == "ready"
    assert by_engine["kitten2"]["status"] == "needs_preparation"
    assert by_engine["pocket-lite"]["status"] == "needs_preparation"
    assert by_engine["phonon-31m"] == {
        **by_engine["phonon-31m"], "status": "unsupported", "reason": "no local cloning"
    }
    assert by_engine["kokoro"]["status"] == "unsupported"


def test_engines_route_for_an_unknown_voice_is_404(client, env):
    assert client.get("/voices/vd_000000000abc/engines").status_code == 404
    assert client.get("/voices/not-a-voice/engines").status_code == 404


def test_the_collection_route_returns_every_voice_in_one_call(client, env):
    first, second = _voice(seed=1), _voice(seed=2)

    body = client.get("/voices/engines").get_json()

    assert set(body["voices"]) == {first["voice_id"], second["voice_id"]}
    assert [e["id"] for e in body["engines"]] == [e.id for e in speech_engines.list_engines()]
    capabilities = {e["id"]: e for e in body["engines"]}
    assert capabilities["phonon-31m"]["clone"] is False
    assert capabilities["kitten2"]["clone"] is True


def test_prepare_returns_202_then_the_binding_flips_to_ready(client, env):
    voice = _voice()

    response = _prepare(client, voice["voice_id"], "pocket-lite")

    assert response.status_code == 202
    assert response.get_json()["binding"]["engine"] == "pocket-lite"
    _wait(lambda: _binding(client, voice["voice_id"], "pocket-lite")["status"] == "ready", "ready")
    assert env["adapters"]["pocket-lite"].calls == [voice["voice_id"]]


def test_a_running_preparation_polls_as_preparing_and_can_be_cancelled(client, env):
    gate = threading.Event()
    env["adapters"]["pocket-lite"].gate = gate
    voice = _voice()
    _prepare(client, voice["voice_id"], "pocket-lite")
    assert _binding(client, voice["voice_id"], "pocket-lite")["status"] == "preparing"
    _wait(lambda: env["adapters"]["pocket-lite"].calls, "running")

    cancelled = client.delete(f"/voices/{voice['voice_id']}/engines/pocket-lite/prepare")

    assert cancelled.status_code == 200 and cancelled.get_json()["cancelled"] is True
    _wait(
        lambda: _binding(client, voice["voice_id"], "pocket-lite")["status"] == "needs_preparation",
        "cancelled",
    )
    gate.set()


def test_cancel_with_nothing_running_reports_false(client, env):
    voice = _voice()

    response = client.delete(f"/voices/{voice['voice_id']}/engines/pocket-lite/prepare")

    assert response.status_code == 200 and response.get_json()["cancelled"] is False


def test_a_failed_preparation_is_reported_with_its_reason_and_can_be_retried(client, env):
    env["adapters"]["pocket-lite"].error = PackProcessError("worker died")
    voice = _voice()

    _prepare(client, voice["voice_id"], "pocket-lite")
    _wait(lambda: _binding(client, voice["voice_id"], "pocket-lite")["status"] == "failed", "failed")
    assert _binding(client, voice["voice_id"], "pocket-lite")["error"] == "worker died"

    env["adapters"]["pocket-lite"].error = None
    assert _prepare(client, voice["voice_id"], "pocket-lite").status_code == 202
    _wait(lambda: _binding(client, voice["voice_id"], "pocket-lite")["status"] == "ready", "ready")


# -- missing-transcript flow -------------------------------------------------------------------------


def test_a_voice_without_a_transcript_asks_for_one_and_runs_nothing(client, env):
    voice = _voice(text="")

    response = _prepare(client, voice["voice_id"], "kitten2")

    assert response.status_code == 409
    body = response.get_json()
    assert body["code"] == "transcript_review" and body["reason"] == "missing"
    assert body["transcript"] == "" and "transcript" in body["error"]
    assert env["adapters"]["kitten2"].calls == []


def test_a_typed_transcript_is_saved_to_the_voice_and_the_voice_is_prepared(client, env):
    voice = _voice(text="")

    response = _prepare(client, voice["voice_id"], "kitten2", transcript="  the real words  ")

    assert response.status_code == 202
    saved = voice_library.get_voice(voice["voice_id"])
    assert saved is not None
    assert saved["sample_text"] == "the real words" and saved["sample_text_source"] == "user"
    _wait(lambda: _binding(client, voice["voice_id"], "kitten2")["status"] == "ready", "ready")


def test_editing_the_transcript_afterwards_invalidates_the_binding(client, env):
    voice = _voice(text="first words")
    _prepare(client, voice["voice_id"], "kitten2")
    _wait(lambda: _binding(client, voice["voice_id"], "kitten2")["status"] == "ready", "ready")

    client.patch(f"/voices/{voice['voice_id']}", json={"sample_text": "second words"})

    assert _binding(client, voice["voice_id"], "kitten2")["status"] == "needs_preparation"


def test_an_unreviewed_transcript_is_confirmed_in_the_request_and_kept_unchanged(client, env):
    import json

    voice = _voice(text="what whisper heard")
    meta_path = voice_library.VOICE_LIBRARY_DIR / voice["voice_id"] / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["asr"] = {"severity": "warn"}
    meta_path.write_text(json.dumps(meta))

    refused = _prepare(client, voice["voice_id"], "kitten2")
    assert refused.status_code == 409 and refused.get_json()["reason"] == "unreviewed"
    assert refused.get_json()["transcript"] == "what whisper heard"

    accepted = _prepare(client, voice["voice_id"], "kitten2", transcript_confirmed=True)

    assert accepted.status_code == 202
    saved = voice_library.get_voice(voice["voice_id"])
    assert saved is not None
    assert saved["sample_text"] == "what whisper heard" and saved["sample_text_source"] == "user"


def test_confirming_an_empty_transcript_does_not_count(client, env):
    voice = _voice(text="")

    response = _prepare(client, voice["voice_id"], "kitten2", transcript_confirmed=True)

    assert response.status_code == 409 and response.get_json()["reason"] == "missing"


def test_a_non_text_transcript_is_a_bad_request(client, env):
    voice = _voice(text="")

    response = _prepare(client, voice["voice_id"], "kitten2", transcript=["nope"])

    assert response.status_code == 400


def test_an_engine_that_needs_no_transcript_prepares_a_voice_that_has_none(client, env):
    voice = _voice(text="")

    assert _prepare(client, voice["voice_id"], "pocket-lite").status_code == 202


# -- refusals ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("engine_id", "status", "code"),
    [
        ("phonon-31m", 400, "unsupported"),
        ("kokoro", 400, "unsupported"),
        ("pocket-tts", 400, "nothing_to_prepare"),
        ("nope", 404, "unknown_engine"),
    ],
)
def test_prepare_refuses_engines_that_cannot_prepare(client, env, engine_id, status, code):
    voice = _voice()

    response = _prepare(client, voice["voice_id"], engine_id)

    assert response.status_code == status and response.get_json()["code"] == code


def test_prepare_refuses_an_engine_that_is_not_installed(client, env):
    env["present"].discard("kitten2")
    voice = _voice()

    response = _prepare(client, voice["voice_id"], "kitten2")

    assert response.status_code == 409 and response.get_json()["code"] == "engine_not_installed"


def test_prepare_for_an_unknown_voice_is_404(client, env):
    response = _prepare(client, "vd_000000000abc", "pocket-lite")

    assert response.status_code == 404 and response.get_json()["code"] == "voice_not_found"


def test_a_deleted_voice_leaves_the_collection(client, env):
    voice = _voice()
    _prepare(client, voice["voice_id"], "pocket-lite")
    _wait(lambda: _binding(client, voice["voice_id"], "pocket-lite")["status"] == "ready", "ready")

    client.delete(f"/voices/{voice['voice_id']}")

    assert voice["voice_id"] not in client.get("/voices/engines").get_json()["voices"]

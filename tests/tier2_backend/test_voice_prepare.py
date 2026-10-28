"""Explicit preparation of a saved voice on a cloning engine: adapters, wait helper and job service.

Workers are stubbed at the ``PackProcess`` seam, so the adapters, the marker files and the job
registry are the real code under test.
"""

from __future__ import annotations

import io
import threading
import time
import wave

import numpy as np
import pytest
import soundfile as sf

from persona_forge import (
    engine_lifecycle,
    kitten2_engine,
    pack_preset_engine,
    pocket_lite_engine,
    speech_engines,
    voice_bindings,
    voice_library,
    voice_prepare,
)
from persona_forge.kitten2_engine import EngineUnavailable, EngineWarming, InvalidVoice
from persona_forge.pack_process import PackProcessError


def _clip(seed: int = 0) -> bytes:
    samples = (np.random.default_rng(seed).standard_normal(24000) * 0.05).astype(np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, samples, 24000, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def _speech() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x10" * 240)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_library, "VOICE_LIBRARY_DIR", tmp_path / "voices")
    monkeypatch.setattr(voice_bindings, "engine_revision", lambda engine_id: "rev-1")
    voice_bindings.reset_jobs()
    return tmp_path / "voices"


def _voice(text="hello there", seed=0):
    return voice_library.save_voice(_clip(seed), description="d", sample_text=text, language="English")


class FakeProcess:
    """Records requests; behaviour is steered through class attributes the tests set."""

    instances: list["FakeProcess"] = []
    fail_prepare: str | None = None
    load_gate: threading.Event | None = None

    def __init__(self, command, **kwargs):
        self.requests: list[dict] = []
        self.timeouts: list[float | None] = []
        self.is_alive = True
        FakeProcess.instances.append(self)

    def start(self):
        pass

    def request(self, payload, *, timeout=None):
        self.requests.append(dict(payload))
        self.timeouts.append(timeout)
        if payload["op"] == "load" and FakeProcess.load_gate is not None:
            assert FakeProcess.load_gate.wait(10), "test never released load"
        if payload["op"] == "prepare" and FakeProcess.fail_prepare:
            self.is_alive = False
            raise PackProcessError(FakeProcess.fail_prepare)
        return {"ok": True, "mode": "cpu"}

    def synthesize(self, payload):
        self.requests.append({"op": "synthesize", **payload})
        return _speech()

    def close(self):
        self.is_alive = False

    def ops(self):
        return [r["op"] for r in self.requests]


@pytest.fixture(autouse=True)
def _reset_fake():
    FakeProcess.instances.clear()
    FakeProcess.fail_prepare = None
    FakeProcess.load_gate = None
    yield
    if FakeProcess.load_gate is not None:
        FakeProcess.load_gate.set()


@pytest.fixture
def kitten(monkeypatch, tmp_path):
    python = tmp_path / "python"
    python.write_text("")
    monkeypatch.setenv("KITTEN2_PYTHON", str(python))
    monkeypatch.setattr(kitten2_engine, "PackProcess", FakeProcess)
    monkeypatch.setenv("ENGINE_WARM_WAIT_S", "0.05")
    return kitten2_engine.Kitten2Engine(idle_unload_s=0)


@pytest.fixture
def lite(monkeypatch, tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    monkeypatch.setattr(pocket_lite_engine, "pack_directory", lambda root=None: pack)
    monkeypatch.setattr(pocket_lite_engine, "pack_python", lambda root=None: tmp_path / "python")
    monkeypatch.setattr(pack_preset_engine, "PackProcess", FakeProcess)
    monkeypatch.setenv("ENGINE_WARM_WAIT_S", "0.05")
    return pocket_lite_engine.PocketLiteEngine(idle_unload_s=0)


def _status(voice_id, engine_id):
    return next(b for b in voice_bindings.bindings_for_voice(voice_id) if b["engine"] == engine_id)


def _prepare_requests():
    return [r for p in FakeProcess.instances for r in p.requests if r["op"] == "prepare"]


# -- wait helper -----------------------------------------------------------------------------------


def test_wait_until_ready_retries_a_warming_engine_until_it_settles():
    calls = []

    def await_ready():
        calls.append(1)
        if len(calls) < 3:
            raise EngineWarming("E", "loading", 1)

    engine_lifecycle.wait_until_ready(await_ready, EngineWarming, patience_s=5)

    assert len(calls) == 3


def test_wait_until_ready_gives_up_after_its_patience():
    ticks = iter([0.0, 1.0, 2.0, 99.0, 100.0])

    def await_ready():
        raise EngineWarming("E", "warming", 1)

    with pytest.raises(EngineWarming):
        engine_lifecycle.wait_until_ready(
            await_ready, EngineWarming, patience_s=10, clock=lambda: next(ticks)
        )


def test_wait_until_ready_stops_when_cancelled_and_does_not_swallow_other_errors():
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(engine_lifecycle.PrepareCancelled):
        engine_lifecycle.wait_until_ready(lambda: None, EngineWarming, cancel=cancel)

    def broken():
        raise EngineUnavailable("not installed")

    with pytest.raises(EngineUnavailable):
        engine_lifecycle.wait_until_ready(broken, EngineWarming)


# -- Kitten 2 adapter ------------------------------------------------------------------------------


def test_kitten_prepare_sends_the_transcript_records_a_marker_and_synthesizes_nothing(kitten):
    voice = _voice(text="the exact words")
    assert _status(voice["voice_id"], "kitten2")["status"] == "needs_preparation"

    kitten.prepare_voice(voice["voice_id"])

    process = FakeProcess.instances[0]
    prepare = [r for r in process.requests if r["op"] == "prepare"]
    assert len(prepare) == 1 and prepare[0]["reference_text"] == "the exact words"
    assert "synthesize" not in process.ops()
    assert _status(voice["voice_id"], "kitten2")["status"] == "ready"


def test_kitten_prepare_is_bounded_by_its_own_timeout(kitten):
    voice = _voice()

    kitten.prepare_voice(voice["voice_id"])

    prepare_index = FakeProcess.instances[0].ops().index("prepare")
    assert FakeProcess.instances[0].timeouts[prepare_index] == kitten2_engine.PREPARE_TIMEOUT_S


def test_first_synthesis_prepares_lazily_and_records_the_same_marker(kitten):
    voice = _voice()

    kitten.synthesize("hi", "English", voice_id=voice["voice_id"])

    assert _status(voice["voice_id"], "kitten2")["status"] == "ready"


def test_a_missing_transcript_is_refused_at_preparation_with_no_worker_prepare(kitten):
    voice = _voice(text="")

    with pytest.raises(InvalidVoice, match="no transcript"):
        kitten.prepare_voice(voice["voice_id"])

    assert _prepare_requests() == []
    assert _status(voice["voice_id"], "kitten2")["status"] == "needs_preparation"


def test_editing_the_transcript_reprepares_a_voice_the_worker_already_holds(kitten):
    voice = _voice(text="old words")
    kitten.synthesize("a", "English", voice_id=voice["voice_id"])
    kitten.synthesize("b", "English", voice_id=voice["voice_id"])
    assert len(_prepare_requests()) == 1

    voice_library.update_voice(voice["voice_id"], sample_text="new words")
    assert _status(voice["voice_id"], "kitten2")["status"] == "needs_preparation"
    kitten.synthesize("c", "English", voice_id=voice["voice_id"])

    prepares = _prepare_requests()
    assert len(prepares) == 2 and prepares[1]["reference_text"] == "new words"
    assert _status(voice["voice_id"], "kitten2")["status"] == "ready"


def test_explicit_prepare_runs_even_when_the_worker_already_holds_the_voice(kitten, monkeypatch):
    voice = _voice()
    kitten.synthesize("a", "English", voice_id=voice["voice_id"])
    monkeypatch.setattr(voice_bindings, "engine_revision", lambda engine_id: "rev-2")
    assert _status(voice["voice_id"], "kitten2")["status"] == "needs_preparation"

    kitten.prepare_voice(voice["voice_id"])

    assert len(_prepare_requests()) == 2  # a cache hit must not leave the marker stale
    assert _status(voice["voice_id"], "kitten2")["status"] == "ready"


def test_a_failed_worker_prepare_raises_and_leaves_the_voice_unprepared(kitten):
    voice = _voice()
    FakeProcess.fail_prepare = "worker died"

    with pytest.raises(PackProcessError, match="worker died"):
        kitten.prepare_voice(voice["voice_id"])

    assert _status(voice["voice_id"], "kitten2")["status"] == "needs_preparation"


def test_preparing_an_unknown_voice_is_refused(kitten):
    with pytest.raises(InvalidVoice, match="saved voice"):
        kitten.prepare_voice("vd_000000000abc")


def test_prepare_waits_for_a_loading_engine_instead_of_failing(kitten):
    voice = _voice()
    FakeProcess.load_gate = threading.Event()
    result: list[object] = []
    worker = threading.Thread(
        target=lambda: result.append(kitten.prepare_voice(voice["voice_id"])), daemon=True
    )
    worker.start()
    time.sleep(0.3)  # several warm-wait windows pass: a request would have been told to retry
    assert worker.is_alive()

    FakeProcess.load_gate.set()
    worker.join(5)

    assert not worker.is_alive()
    assert _status(voice["voice_id"], "kitten2")["status"] == "ready"


def test_cancelling_while_the_engine_loads_stops_the_wait(kitten):
    voice = _voice()
    FakeProcess.load_gate = threading.Event()
    cancel = threading.Event()
    errors: list[BaseException] = []

    def run():
        try:
            kitten.prepare_voice(voice["voice_id"], cancel=cancel)
        except BaseException as exc:  # noqa: BLE001 - the test inspects what was raised
            errors.append(exc)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    time.sleep(0.2)
    cancel.set()
    worker.join(5)

    assert not worker.is_alive()
    assert [type(e) for e in errors] == [engine_lifecycle.PrepareCancelled]


# -- Pocket Lite adapter ---------------------------------------------------------------------------


def test_pocket_lite_prepare_records_a_marker_without_needing_a_transcript(lite):
    voice = _voice(text="")

    lite.prepare_voice(voice["voice_id"])

    process = FakeProcess.instances[0]
    prepare = [r for r in process.requests if r["op"] == "prepare"]
    assert len(prepare) == 1 and "reference_text" not in prepare[0]
    assert "synthesize" not in process.ops()
    assert _status(voice["voice_id"], "pocket-lite")["status"] == "ready"


def test_pocket_lite_lazy_synthesis_records_the_marker_too(lite):
    voice = _voice()

    lite.synthesize("hi", "English", voice_id=voice["voice_id"])

    assert _status(voice["voice_id"], "pocket-lite")["status"] == "ready"


def test_pocket_lite_stays_ready_when_only_the_transcript_changes(lite):
    voice = _voice(text="one")
    lite.prepare_voice(voice["voice_id"])

    voice_library.update_voice(voice["voice_id"], sample_text="two")

    assert _status(voice["voice_id"], "pocket-lite")["status"] == "ready"


def test_a_preset_only_engine_refuses_to_prepare_a_saved_voice(monkeypatch, tmp_path):
    from persona_forge import phonon_engine

    python = tmp_path / "python"
    python.write_text("")
    monkeypatch.setenv("PHONON_PYTHON", str(python))
    monkeypatch.setattr(pack_preset_engine, "PackProcess", FakeProcess)
    voice = _voice()

    with pytest.raises(InvalidVoice, match="cannot clone"):
        phonon_engine.PhononEngine(idle_unload_s=0).prepare_voice(voice["voice_id"])


# -- job service -----------------------------------------------------------------------------------


class StubAdapter:
    """What the service needs from an adapter: ``prepare_voice`` that writes the marker."""

    def __init__(self, engine_id, *, delay=0.0, error=None, wait_for=None):
        self.engine_id = engine_id
        self.delay, self.error, self.wait_for = delay, error, wait_for
        self.calls: list[str] = []
        self.running = 0
        self.max_running = 0

    def prepare_voice(self, voice_id, *, cancel=None):
        self.calls.append(voice_id)
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        try:
            if self.wait_for is not None:
                while not self.wait_for.wait(0.01):
                    if cancel is not None and cancel.is_set():
                        raise engine_lifecycle.PrepareCancelled("cancelled")
            time.sleep(self.delay)
            if self.error is not None:
                raise self.error
            meta = voice_library.get_voice(voice_id)
            assert meta is not None
            voice_bindings.write_marker(voice_id, self.engine_id, voice_bindings.current_key(meta, self.engine_id))
        finally:
            self.running -= 1


@pytest.fixture
def service(monkeypatch):
    present = {"kitten2", "pocket-lite"}
    monkeypatch.setattr(voice_bindings, "_is_installed", lambda engine_id: engine_id in present)
    monkeypatch.setattr(voice_bindings, "_needs_transcript", lambda engine_id: engine_id == "kitten2")
    adapters: dict[str, StubAdapter] = {}
    monkeypatch.setattr(speech_engines, "get_adapter", lambda engine_id: adapters.get(engine_id))
    voice_prepare.reset()
    yield adapters
    voice_prepare.reset()


def _wait(predicate, what, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


def test_start_reports_preparing_then_ready(service):
    gate = threading.Event()
    service["pocket-lite"] = StubAdapter("pocket-lite", wait_for=gate)
    voice = _voice()

    binding = voice_prepare.start(voice["voice_id"], "pocket-lite")
    assert binding["status"] == "preparing"
    assert _status(voice["voice_id"], "pocket-lite")["status"] == "preparing"

    gate.set()
    _wait(lambda: _status(voice["voice_id"], "pocket-lite")["status"] == "ready", "ready")


def test_a_failure_is_reported_on_the_binding_and_can_be_retried(service):
    service["pocket-lite"] = StubAdapter("pocket-lite", error=PackProcessError("worker died"))
    voice = _voice()

    voice_prepare.start(voice["voice_id"], "pocket-lite")
    _wait(lambda: _status(voice["voice_id"], "pocket-lite")["status"] == "failed", "failed")
    failed = _status(voice["voice_id"], "pocket-lite")
    assert failed["error"] == "worker died" and failed["can_prepare"] is True

    service["pocket-lite"] = StubAdapter("pocket-lite")
    voice_prepare.start(voice["voice_id"], "pocket-lite")
    _wait(lambda: _status(voice["voice_id"], "pocket-lite")["status"] == "ready", "ready")


def test_starting_twice_does_not_run_twice(service):
    gate = threading.Event()
    adapter = service["pocket-lite"] = StubAdapter("pocket-lite", wait_for=gate)
    voice = _voice()

    voice_prepare.start(voice["voice_id"], "pocket-lite")
    again = voice_prepare.start(voice["voice_id"], "pocket-lite")
    gate.set()
    _wait(lambda: _status(voice["voice_id"], "pocket-lite")["status"] == "ready", "ready")

    assert again["status"] == "preparing" and adapter.calls == [voice["voice_id"]]


def test_preparations_run_one_at_a_time_across_engines(service):
    lite = service["pocket-lite"] = StubAdapter("pocket-lite", delay=0.05)
    kitten = service["kitten2"] = StubAdapter("kitten2", delay=0.05)
    first, second = _voice(seed=1), _voice(seed=2)

    voice_prepare.start(first["voice_id"], "pocket-lite")
    voice_prepare.start(second["voice_id"], "kitten2")
    _wait(lambda: _status(second["voice_id"], "kitten2")["status"] == "ready", "both done")

    assert lite.max_running == 1 and kitten.max_running == 1
    assert _status(first["voice_id"], "pocket-lite")["status"] == "ready"


def test_cancel_stops_a_waiting_preparation_and_leaves_the_voice_unprepared(service):
    gate = threading.Event()
    service["pocket-lite"] = StubAdapter("pocket-lite", wait_for=gate)
    voice = _voice()
    voice_prepare.start(voice["voice_id"], "pocket-lite")
    _wait(lambda: service["pocket-lite"].running == 1, "running")

    assert voice_prepare.cancel(voice["voice_id"], "pocket-lite") is True
    _wait(lambda: _status(voice["voice_id"], "pocket-lite")["status"] == "needs_preparation", "cancelled")
    gate.set()

    assert _status(voice["voice_id"], "pocket-lite")["error"] is None  # cancelling is not a failure


def test_cancel_with_nothing_running_says_so(service):
    voice = _voice()

    assert voice_prepare.cancel(voice["voice_id"], "pocket-lite") is False


@pytest.mark.parametrize(
    ("engine_id", "code", "status"),
    [
        ("nope", "unknown_engine", 404),
        ("phonon-31m", "unsupported", 400),
        ("kokoro", "unsupported", 400),
        ("pocket-tts", "nothing_to_prepare", 400),
    ],
)
def test_starting_refuses_engines_that_cannot_prepare(service, engine_id, code, status):
    voice = _voice()

    with pytest.raises(voice_prepare.PrepareRefused) as info:
        voice_prepare.start(voice["voice_id"], engine_id)

    assert info.value.code == code and info.value.status == status


def test_starting_refuses_an_unknown_voice_and_an_engine_that_is_not_installed(service, monkeypatch):
    with pytest.raises(voice_prepare.PrepareRefused) as unknown:
        voice_prepare.start("vd_000000000abc", "pocket-lite")
    assert unknown.value.code == "voice_not_found" and unknown.value.status == 404

    voice = _voice()
    monkeypatch.setattr(voice_bindings, "_is_installed", lambda engine_id: engine_id == "pocket-lite")
    with pytest.raises(voice_prepare.PrepareRefused) as missing:
        voice_prepare.start(voice["voice_id"], "kitten2")
    assert missing.value.code == "engine_not_installed" and missing.value.status == 409


def test_a_missing_transcript_is_a_transcript_review_refusal_that_carries_the_stored_text(service):
    service["kitten2"] = StubAdapter("kitten2")
    voice = _voice(text="")

    with pytest.raises(voice_prepare.PrepareRefused) as info:
        voice_prepare.start(voice["voice_id"], "kitten2")

    refusal = info.value
    assert refusal.code == "transcript_review" and refusal.status == 409
    assert refusal.extra == {"reason": "missing", "transcript": ""}
    assert service["kitten2"].calls == []  # nothing ran, and nothing would have hit the network


def test_an_unreviewed_transcript_must_be_confirmed_first(service, library):
    import json

    service["kitten2"] = StubAdapter("kitten2")
    voice = _voice(text="heard by whisper")
    meta_path = library / voice["voice_id"] / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["asr"] = {"severity": "warn"}
    meta_path.write_text(json.dumps(meta))

    with pytest.raises(voice_prepare.PrepareRefused) as info:
        voice_prepare.start(voice["voice_id"], "kitten2")

    assert info.value.extra == {"reason": "unreviewed", "transcript": "heard by whisper"}


def test_a_supplied_transcript_is_saved_as_the_users_and_announced_before_queueing(service):
    service["kitten2"] = StubAdapter("kitten2")
    voice = _voice(text="")
    saved: list[str] = []

    voice_prepare.start(
        voice["voice_id"], "kitten2", transcript=" typed words ", on_transcript_saved=saved.append
    )
    _wait(lambda: _status(voice["voice_id"], "kitten2")["status"] == "ready", "ready")

    meta = voice_library.get_voice(voice["voice_id"])
    assert meta is not None
    assert meta["sample_text"] == "typed words" and meta["sample_text_source"] == "user"
    assert saved == [voice["voice_id"]]


def test_confirming_keeps_the_stored_words_and_marks_them_reviewed(service, library):
    import json

    service["kitten2"] = StubAdapter("kitten2")
    voice = _voice(text="heard words")
    meta_path = library / voice["voice_id"] / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["asr"] = {"severity": "fail"}
    meta_path.write_text(json.dumps(meta))

    voice_prepare.start(voice["voice_id"], "kitten2", confirm_transcript=True)
    _wait(lambda: _status(voice["voice_id"], "kitten2")["status"] == "ready", "ready")

    saved = voice_library.get_voice(voice["voice_id"])
    assert saved is not None
    assert saved["sample_text"] == "heard words" and saved["sample_text_source"] == "user"


def test_a_transcript_is_ignored_for_an_engine_that_does_not_clone_with_one(service):
    service["pocket-lite"] = StubAdapter("pocket-lite")
    voice = _voice(text="keep me")

    voice_prepare.start(voice["voice_id"], "pocket-lite", transcript="something else")
    _wait(lambda: _status(voice["voice_id"], "pocket-lite")["status"] == "ready", "ready")

    meta = voice_library.get_voice(voice["voice_id"])
    assert meta is not None and meta["sample_text"] == "keep me"


def test_a_refused_start_does_not_touch_the_transcript(service):
    voice = _voice(text="keep me")

    with pytest.raises(voice_prepare.PrepareRefused):
        voice_prepare.start(voice["voice_id"], "phonon-31m", transcript="overwritten?")

    meta = voice_library.get_voice(voice["voice_id"])
    assert meta is not None and meta["sample_text"] == "keep me"


@pytest.mark.parametrize("engine_id", ["kitten2", "pocket-lite"])
def test_lazy_prepare_uses_the_same_revision_key_as_explicit_prepare(
    engine_id, kitten, lite, monkeypatch
):
    adapter = kitten if engine_id == "kitten2" else lite
    voice_id = _voice()["voice_id"]
    adapter.synthesize("first", "English", voice_id=voice_id)
    monkeypatch.setattr(voice_bindings, "engine_revision", lambda _: "rev-2")

    adapter.synthesize("second", "English", voice_id=voice_id)

    assert len(_prepare_requests()) == 2
    assert _status(voice_id, engine_id)["status"] == "ready"


@pytest.mark.parametrize("engine_id", ["kitten2", "pocket-lite"])
def test_same_size_reference_edit_with_preserved_mtime_reprepares(
    engine_id, kitten, lite
):
    import os
    from pathlib import Path

    adapter = kitten if engine_id == "kitten2" else lite
    voice_id = _voice()["voice_id"]
    adapter.synthesize("first", "English", voice_id=voice_id)
    meta = voice_library.get_voice(voice_id)
    assert meta is not None
    path = Path(meta["wav_path"])
    stamp = path.stat()
    path.write_bytes(_clip(seed=9))
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))

    assert _status(voice_id, engine_id)["status"] == "needs_preparation"
    adapter.synthesize("second", "English", voice_id=voice_id)
    assert len(_prepare_requests()) == 2


def test_lazy_kitten_cannot_bypass_transcript_review(kitten, library):
    import json

    voice_id = _voice()["voice_id"]
    path = library / voice_id / "meta.json"
    meta = json.loads(path.read_text())
    meta["asr"] = {"severity": "fail"}
    path.write_text(json.dumps(meta))

    with pytest.raises(InvalidVoice, match="[Rr]eview"):
        kitten.synthesize("hello", "English", voice_id=voice_id)
    assert _prepare_requests() == []


def test_lite_rebuilds_prepared_state_after_worker_death(lite):
    voice_id = _voice()["voice_id"]
    lite.synthesize("first", "English", voice_id=voice_id)
    FakeProcess.instances[0].is_alive = False

    lite.synthesize("second", "English", voice_id=voice_id)

    assert FakeProcess.instances[1].ops() == ["load", "prepare", "synthesize"]


def test_preparation_queues_behind_existing_inference(service, monkeypatch, rt):
    from concurrent.futures import ThreadPoolExecutor

    gate, entered = threading.Event(), threading.Event()
    adapter = service["pocket-lite"] = StubAdapter("pocket-lite")
    voice_id = _voice()["voice_id"]

    def inference():
        entered.set()
        assert gate.wait(5)

    with ThreadPoolExecutor(max_workers=1) as executor:
        monkeypatch.setattr(rt, "executor", executor)
        future = executor.submit(inference)
        assert entered.wait(5)
        try:
            voice_prepare.start(voice_id, "pocket-lite")
            assert not adapter.calls
        finally:
            gate.set()
        future.result(5)
        _wait(lambda: _status(voice_id, "pocket-lite")["status"] == "ready", "ready")


def test_editing_words_in_prepare_request_is_not_ignored_when_already_ready(service):
    service["kitten2"] = StubAdapter("kitten2")
    voice_id = _voice(text="old words")["voice_id"]
    voice_prepare.start(voice_id, "kitten2")
    _wait(lambda: _status(voice_id, "kitten2")["status"] == "ready", "ready")

    voice_prepare.start(voice_id, "kitten2", transcript="new words")
    _wait(lambda: _status(voice_id, "kitten2")["status"] == "ready", "ready again")

    meta = voice_library.get_voice(voice_id)
    assert meta is not None and meta["sample_text"] == "new words"


def test_edit_during_worker_prepare_does_not_publish_or_synthesize_stale_inputs(kitten, monkeypatch):
    voice_id = _voice(text="old words")["voice_id"]
    request = FakeProcess.request

    def edit_during_prepare(process, payload, **kwargs):
        if payload["op"] == "prepare":
            voice_library.update_voice(voice_id, sample_text="changed during preparation")
        return request(process, payload, **kwargs)

    monkeypatch.setattr(FakeProcess, "request", edit_during_prepare)
    with pytest.raises(InvalidVoice, match="[Cc]hanged"):
        kitten.synthesize("hello", "English", voice_id=voice_id)
    assert _status(voice_id, "kitten2")["status"] == "needs_preparation"
    assert "synthesize" not in FakeProcess.instances[0].ops()

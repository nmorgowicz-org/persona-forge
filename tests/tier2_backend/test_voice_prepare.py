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

    def stream(self, payload):
        self.requests.append({"op": "stream", **payload})
        yield b"\x00\x10" * 240

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


# -- speech route: readiness is descriptive, not a mandatory explicit-Prepare gate -----------------


@pytest.fixture
def speech_route(monkeypatch, rt, app_module, kitten, lite, library):
    monkeypatch.setattr(rt, "TTS_BACKEND", "pocket_tts")
    monkeypatch.setattr(rt, "_service_started", True)
    monkeypatch.setattr(app_module, "_generation_ready", lambda: True)
    monkeypatch.setattr(voice_bindings, "_is_installed", lambda _: True)
    monkeypatch.setenv("ENGINE_WARM_WAIT_S", "5")
    monkeypatch.setitem(speech_engines.ADAPTERS, "kitten2", kitten)
    monkeypatch.setitem(speech_engines.ADAPTERS, "pocket-lite", lite)
    monkeypatch.setattr(voice_library, "API_DEFAULT_FILE", library / ".api_default.json")
    monkeypatch.setattr(voice_library, "ACTIVE_DEFAULT_FILE", library / ".active_default")

    def no_fallback(*args, **kwargs):
        pytest.fail("a pack request must not generate on or swap the built-in backend")

    # _FakeModule delegates writes to rt but has no matching attributes in its own __dict__.
    # Patch the owning runtime so pytest restores, rather than deleting from the proxy.
    monkeypatch.setattr(rt, "_run_generate", no_fallback)
    monkeypatch.setattr(rt, "apply_runtime_config", no_fallback)


def _post_speech(client, engine_id, voice_id, fmt="wav"):
    return client.post(
        "/v1/audio/speech",
        json={"model": engine_id, "voice": voice_id, "input": "hello", "response_format": fmt},
    )


def _speech_error(response, status, *message_parts):
    assert response.status_code == status, response.get_data(as_text=True)
    assert response.is_json
    error = response.get_json()["error"]
    assert error["type"] == ("invalid_request_error" if status == 400 else "api_error")
    assert error["code"] is None
    for part in message_parts:
        assert part.lower() in error["message"].lower()
    assert "Retry-After" not in response.headers
    assert not any(
        r["op"] in ("synthesize", "stream") for p in FakeProcess.instances for r in p.requests
    )


@pytest.mark.parametrize("engine_id,fmt", [
    ("kitten2", "wav"), ("pocket-lite", "wav"), ("pocket-lite", "pcm"),
])
@pytest.mark.parametrize("state", ["needs_preparation", "failed", "ready", "stale"])
def test_speech_lazily_prepares_without_requiring_an_explicit_ready_binding(
    client, speech_route, engine_id, fmt, state
):
    from pathlib import Path

    voice_id = _voice()["voice_id"]
    meta = voice_bindings.meta_with_path(voice_id)
    assert meta is not None
    key = voice_bindings.current_key(meta, engine_id)
    if state == "failed":
        voice_bindings.set_job(voice_id, engine_id, "failed", key=key, error="previous worker died")
    elif state in ("ready", "stale"):
        voice_bindings.write_marker(voice_id, engine_id, key)
        if state == "stale":
            Path(meta["wav_path"]).write_bytes(_clip(seed=7))
    expected = "needs_preparation" if state == "stale" else state
    assert _status(voice_id, engine_id)["status"] == expected

    response = _post_speech(client, engine_id, voice_id, fmt)

    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.content_type.startswith("audio/")
    assert response.data
    # Even a persisted ready marker needs local state after worker start/idle unload.
    assert len(_prepare_requests()) == 1
    assert _prepare_requests()[0]["voice_id"] == voice_id
    assert _status(voice_id, engine_id)["status"] == "ready"


@pytest.mark.parametrize("fmt", ["wav", "pcm"])
@pytest.mark.parametrize("engine_id", ["kitten2", "pocket-lite"])
@pytest.mark.parametrize("ready_marker", [False, True])
def test_speech_failed_lazy_prepare_returns_actionable_json_before_audio(
    client, speech_route, engine_id, fmt, ready_marker
):
    voice_id = _voice()["voice_id"]
    if ready_marker:
        meta = voice_bindings.meta_with_path(voice_id)
        assert meta is not None
        voice_bindings.write_marker(voice_id, engine_id, voice_bindings.current_key(meta, engine_id))
    FakeProcess.fail_prepare = "reference encoder crashed"

    response = _post_speech(client, engine_id, voice_id, fmt)

    _speech_error(response, 503, "reference encoder crashed", "Voice Library", "Prepare", "Repair",
                  "Runtime → Speech engines")
    # Readiness is a validated-input marker, not a guarantee that this worker can encode it.
    assert _status(voice_id, engine_id)["status"] == ("ready" if ready_marker else "needs_preparation")


@pytest.mark.parametrize("engine_id", ["kitten2", "pocket-lite"])
def test_speech_missing_pack_overrides_a_previously_ready_marker(
    client, speech_route, engine_id, monkeypatch
):
    voice_id = _voice()["voice_id"]
    meta = voice_bindings.meta_with_path(voice_id)
    assert meta is not None
    voice_bindings.write_marker(voice_id, engine_id, voice_bindings.current_key(meta, engine_id))
    monkeypatch.setattr(voice_bindings, "_is_installed", lambda _: False)
    if engine_id == "kitten2":
        monkeypatch.setattr(kitten2_engine, "pack_python", lambda root=None: None)
    else:
        monkeypatch.setattr(pocket_lite_engine, "pack_python", lambda root=None: None)
    binding = _status(voice_id, engine_id)
    assert binding["installed"] is False and binding["blocker"] == "engine_not_installed"

    response = _post_speech(client, engine_id, voice_id)

    _speech_error(response, 503, "not installed", "install", "Runtime → Speech engines")
    assert FakeProcess.instances == []


@pytest.mark.parametrize("engine_id", ["kitten2", "pocket-lite"])
def test_speech_missing_reference_is_not_replaced_by_a_preset(
    client, speech_route, engine_id
):
    from pathlib import Path

    voice_id = _voice()["voice_id"]
    meta = voice_library.get_voice(voice_id)
    assert meta is not None
    Path(meta["wav_path"]).unlink()

    response = _post_speech(client, engine_id, voice_id)

    _speech_error(response, 400, "reference clip", "missing", "Voice Library")


@pytest.mark.parametrize("review", [False, True])
def test_speech_kitten_transcript_blocker_names_the_repair(
    client, speech_route, library, review
):
    import json

    voice_id = _voice(text="unconfirmed words" if review else "")["voice_id"]
    if review:
        path = library / voice_id / "meta.json"
        meta = json.loads(path.read_text())
        meta["asr"] = {"severity": "fail"}
        path.write_text(json.dumps(meta))

    response = _post_speech(client, "kitten2", voice_id)

    _speech_error(response, 400, "transcript", "Voice Library",
                  "confirm" if review else "Transcribe")
    assert _prepare_requests() == []


def test_speech_queued_explicit_prepare_does_not_make_a_lazy_request_fail(
    client, speech_route, rt, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor

    voice_id = _voice()["voice_id"]
    gate, entered = threading.Event(), threading.Event()

    def hold_executor():
        entered.set()
        assert gate.wait(5), "test never released executor"

    with ThreadPoolExecutor(max_workers=1) as executor:
        monkeypatch.setattr(rt, "executor", executor)
        blocker = executor.submit(hold_executor)
        assert entered.wait(5)
        try:
            binding = voice_prepare.start(voice_id, "kitten2")
            assert binding["status"] == "preparing"
            # Pack synthesis uses its adapter lock, not the model executor: it can finish before
            # the queued explicit job. A request-time "must be ready" gate would reject it.
            response = _post_speech(client, "kitten2", voice_id)
            assert response.status_code == 200, response.get_data(as_text=True)
        finally:
            gate.set()
            blocker.result(5)
            executor.submit(lambda: None).result(5)  # drain the explicit job, not just the blocker
            voice_prepare.reset()
    assert len(_prepare_requests()) == 1
    assert _status(voice_id, "kitten2")["status"] == "ready"


@pytest.mark.parametrize("engine_id,voice_id", [
    ("kitten2", "pocket:vera"), ("kokoro", "pocket:vera"),
    ("pocket-tts", "kitten2:Bruno"), ("kitten2", "kokoro:af_heart"),
])
def test_speech_explicit_engine_mismatch_never_uses_a_default_speaker(
    client, speech_route, engine_id, voice_id
):
    response = _post_speech(client, engine_id, voice_id)
    _speech_error(response, 400, "voice", "engine")
    assert FakeProcess.instances == []


@pytest.mark.parametrize("engine_id,fmt", [
    ("kokoro", "wav"), ("phonon-31m", "wav"), ("phonon-31m", "pcm"),
])
def test_speech_noncloning_engine_refuses_saved_voice_with_an_alternative(
    client, speech_route, engine_id, fmt
):
    voice_id = _voice()["voice_id"]
    response = _post_speech(client, engine_id, voice_id, fmt)
    _speech_error(response, 400, "cannot clone", "choose", "voice")
    assert FakeProcess.instances == []


def test_speech_lite_needs_no_transcript_and_keeps_the_pocket_preset_alias(
    client, speech_route
):
    voice_id = _voice(text="")["voice_id"]
    response = _post_speech(client, "pocket-lite", voice_id)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert len(_prepare_requests()) == 1

    preset = _post_speech(client, "pocket-lite", "pocket:vera")
    assert preset.status_code == 200, preset.get_data(as_text=True)
    assert FakeProcess.instances[0].requests[-1]["preset"] == "vera"


def test_speech_pocket_preset_requires_the_pocket_backend(client, speech_route, rt, monkeypatch):
    monkeypatch.setattr(rt, "TTS_BACKEND", "openvino")
    response = _post_speech(client, "pocket-tts", "pocket:vera")
    _speech_error(response, 400, "pocket_tts", "Runtime")


@pytest.mark.parametrize("backend", ["pocket_tts", "openvino"])
def test_speech_active_runtime_saved_voice_has_no_pack_preparation_gate(
    client, speech_route, app_module, rt, monkeypatch, backend
):
    voice_id = _voice(text="")["voice_id"]
    monkeypatch.setattr(rt, "TTS_BACKEND", backend)
    received = []

    def generate(text, language, **kwargs):
        received.append(kwargs["voice_id"])
        return np.zeros(240, dtype=np.float32), 24000, None

    monkeypatch.setattr(rt, "_run_generate", generate)
    assert _status(voice_id, "pocket-tts")["status"] == "ready"

    response = _post_speech(client, "pocket-tts", voice_id)

    assert response.status_code == 200, response.get_data(as_text=True)
    assert received == [voice_id]
    assert FakeProcess.instances == []


@pytest.mark.parametrize("engine_id,fmt", [
    ("kitten2", "wav"), ("pocket-lite", "wav"), ("pocket-lite", "pcm"),
])
def test_speech_reference_changed_during_lazy_prepare_returns_no_stale_audio(
    client, speech_route, engine_id, fmt, monkeypatch
):
    from pathlib import Path

    voice_id = _voice()["voice_id"]
    meta = voice_library.get_voice(voice_id)
    assert meta is not None
    request = FakeProcess.request

    def edit_during_prepare(process, payload, **kwargs):
        if payload["op"] == "prepare":
            Path(meta["wav_path"]).write_bytes(_clip(seed=8))
        return request(process, payload, **kwargs)

    monkeypatch.setattr(FakeProcess, "request", edit_during_prepare)
    response = _post_speech(client, engine_id, voice_id, fmt)

    _speech_error(response, 400, "changed", "Prepare", "again")
    assert _status(voice_id, engine_id)["status"] == "needs_preparation"


@pytest.mark.parametrize("engine_id,voice_id", [
    ("kokoro", "kokoro:af_heart"), ("phonon-31m", "phonon:Zoey"),
])
@pytest.mark.parametrize("fmt", ["wav", "pcm"])
def test_speech_missing_preset_pack_names_runtime_install_action(
    client, speech_route, engine_id, voice_id, fmt, monkeypatch
):
    from persona_forge.kokoro_engine import KokoroEngine
    from persona_forge.phonon_engine import PhononEngine

    adapter = KokoroEngine(idle_unload_s=0) if engine_id == "kokoro" else PhononEngine(idle_unload_s=0)
    monkeypatch.setattr(adapter, "_pack_python", lambda: None)
    monkeypatch.setitem(speech_engines.ADAPTERS, engine_id, adapter)

    response = _post_speech(client, engine_id, voice_id, fmt)

    _speech_error(response, 503, "not installed", "install", "Runtime → Speech engines")
    assert FakeProcess.instances == []


@pytest.mark.parametrize("fmt", ["wav", "mp3", "pcm"])
@pytest.mark.parametrize("include_voice", [False, True])
@pytest.mark.parametrize("model_name,voice,variant", [
    ("kitten-tts-2", "kitten2:Bruno", "pocket:vera"),
    ("pocket-lite", "pocket-lite:jane", "kokoro:af_heart"),
])
def test_speech_validates_the_effective_variant_namespace_before_default_or_audio(
    client, speech_route, model_name, voice, variant, include_voice, fmt
):
    # The request's higher-precedence voice must not bypass the model/voice guard, whether
    # supplied alone or alongside a perfectly valid lower-precedence voice.
    payload = {
        "model": model_name, "input": "hello", "response_format": fmt,
        "voice_variant_id": variant,
    }
    if include_voice:
        payload["voice"] = voice
    response = client.post("/v1/audio/speech", json=payload)

    _speech_error(response, 400, "voice", "engine")
    assert FakeProcess.instances == []


@pytest.mark.parametrize("fmt", ["wav", "pcm"])
@pytest.mark.parametrize("engine_id", ["kitten2", "pocket-lite"])
@pytest.mark.parametrize("include_voice", [False, True])
def test_speech_dotted_variant_is_the_effective_voice_for_batch_and_pcm(
    client, speech_route, library, engine_id, fmt, include_voice
):
    import json

    voice_id = _voice()["voice_id"]
    variant_id = f"{voice_id}.test-take"
    (library / voice_id / "test-take.wav").write_bytes(_clip(seed=3))
    (library / voice_id / "variants.json").write_text(
        json.dumps({"test-take": {"filename": "test-take.wav"}})
    )
    # Even a stored default must not be injected in place of an explicitly requested variant.
    voice_library.set_api_default("pocket_tts", "pocket:vera")
    payload = {
        "model": engine_id, "input": "hello", "response_format": fmt,
        "voice_variant_id": variant_id,
    }
    if include_voice:
        # A mismatched lower-precedence preset must not reject the actual valid saved variant.
        payload["voice_id"] = "kokoro:af_heart"
    response = client.post("/v1/audio/speech", json=payload)

    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.data
    assert _prepare_requests()[0]["voice_id"] == variant_id
    rendered = [
        r for p in FakeProcess.instances for r in p.requests if r["op"] in ("synthesize", "stream")
    ]
    assert len(rendered) == 1 and rendered[0]["voice_id"] == variant_id

"""Phonon imports: the worker registers a prepared voice file; the adapter feeds and forgets it."""

from __future__ import annotations

import io
import threading
import wave

import numpy as np
import pytest

from persona_forge import imported_voices, pack_preset_engine, phonon_engine, phonon_worker
from persona_forge.kitten2_engine import EngineUnavailable, EngineWarming, InvalidVoice


class StubModel:
    sample_rate = 24000

    def __init__(self, reject=None):
        self.added: list[tuple[str, str]] = []
        self.reject = reject
        self.calls: list[tuple[str, dict]] = []

    def add_voice(self, name, path):
        if self.reject:
            raise RuntimeError(self.reject)
        self.added.append((name, path))

    def set_conditions(self, conditions):
        pass

    def synth(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return np.full(2400, 0.25, dtype=np.float32)


def make_worker(reject=None):
    stub = StubModel(reject)
    return phonon_worker.PhononWorker(lambda: (stub, ["Easton", "Zoey"])), stub


@pytest.fixture
def voice_file(tmp_path):
    path = tmp_path / "imported-mine.safetensors"
    path.write_bytes(b"x")
    return str(path)


# -- worker ----------------------------------------------------------------------------------------


def test_import_registers_the_file_with_the_model_and_the_voice_becomes_servable(voice_file):
    worker, stub = make_worker()
    worker.handle({"op": "load"})

    reply = worker.handle({"op": "import_voice", "name": "imported-mine", "path": voice_file})

    assert reply["ok"] is True and stub.added == [("imported-mine", voice_file)]
    worker.handle({"op": "synthesize", "text": "hi", "preset": "imported-mine"})
    assert stub.calls == [("hi", {"voice": "imported-mine"})]


def test_an_unimported_name_is_still_an_unknown_preset():
    worker, _ = make_worker()
    worker.handle({"op": "load"})

    with pytest.raises(phonon_worker.WorkerError, match="unknown preset"):
        worker.handle({"op": "synthesize", "text": "hi", "preset": "imported-nobody"})


@pytest.mark.parametrize("name", ["Zoey", "../x", "imported-", "imported-A", "imported-a/b", "", None, 7])
def test_only_namespaced_names_can_be_imported(voice_file, name):
    worker, stub = make_worker()
    worker.handle({"op": "load"})

    with pytest.raises(phonon_worker.WorkerError, match="imported-"):
        worker.handle({"op": "import_voice", "name": name, "path": voice_file})

    assert stub.added == []


@pytest.mark.parametrize("path", ["/nonexistent/x.safetensors", "relative.safetensors", None, 3])
def test_a_path_that_is_not_an_existing_safetensors_file_is_refused(path):
    worker, stub = make_worker()
    worker.handle({"op": "load"})

    with pytest.raises(phonon_worker.WorkerError, match="existing"):
        worker.handle({"op": "import_voice", "name": "imported-mine", "path": path})

    assert stub.added == []


def test_a_file_with_another_extension_is_refused_even_if_it_exists(tmp_path):
    path = tmp_path / "imported-mine.pkl"
    path.write_bytes(b"x")
    worker, stub = make_worker()
    worker.handle({"op": "load"})

    with pytest.raises(phonon_worker.WorkerError, match="existing .safetensors"):
        worker.handle({"op": "import_voice", "name": "imported-mine", "path": str(path)})

    assert stub.added == []


def test_the_engines_own_refusal_comes_back_as_a_readable_error(voice_file):
    worker, _ = make_worker(reject='path: "x" header too large')
    worker.handle({"op": "load"})

    with pytest.raises(phonon_worker.WorkerError, match="could not read this voice file.*header too large"):
        worker.handle({"op": "import_voice", "name": "imported-mine", "path": voice_file})


def test_import_needs_a_loaded_model(voice_file):
    worker, _ = make_worker()

    with pytest.raises(phonon_worker.WorkerError, match="load the model first"):
        worker.handle({"op": "import_voice", "name": "imported-mine", "path": voice_file})


def test_load_registers_every_stored_import_and_reports_the_ones_it_could_not(tmp_path, voice_file):
    worker, stub = make_worker()
    missing = str(tmp_path / "gone.safetensors")

    reply = worker.handle(
        {
            "op": "load",
            "imported": [
                {"name": "imported-mine", "path": voice_file},
                {"name": "imported-gone", "path": missing},
            ],
        }
    )

    assert reply["ok"] is True and reply["imported_failed"] == ["imported-gone"]
    assert stub.added == [("imported-mine", voice_file)]
    worker.handle({"op": "synthesize", "text": "hi", "preset": "imported-mine"})


def test_an_import_cannot_shadow_a_built_in_voice_name(voice_file):
    worker, stub = make_worker()
    worker._factory = lambda: (stub, ["Easton", "imported-mine"])  # noqa: SLF001 - catalog clash
    worker.handle({"op": "load"})

    with pytest.raises(phonon_worker.WorkerError, match="built-in"):
        worker.handle({"op": "import_voice", "name": "imported-mine", "path": voice_file})


# -- adapter ---------------------------------------------------------------------------------------


class FakeProcess:
    instances: list["FakeProcess"] = []
    reject: str | None = None

    def __init__(self, command, **_kwargs):
        self.requests: list[dict] = []
        self.is_alive = True
        FakeProcess.instances.append(self)

    def start(self):
        pass

    def request(self, payload, *, timeout=None):
        self.requests.append(dict(payload))
        if payload["op"] == "import_voice" and FakeProcess.reject:
            raise pack_preset_engine.PackProcessError(FakeProcess.reject)
        return {"ok": True, "mode": "cpu"}

    def synthesize(self, payload):
        self.requests.append({"op": "synthesize", **payload})
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(24000)
            handle.writeframes(b"\x00\x10" * 240)
        return buffer.getvalue()

    def close(self):
        self.is_alive = False


@pytest.fixture
def engine(monkeypatch, tmp_path):
    FakeProcess.instances.clear()
    FakeProcess.reject = None
    python = tmp_path / "python"
    python.write_text("")
    monkeypatch.setenv("PHONON_PYTHON", str(python))
    monkeypatch.setenv("ENGINE_WARM_WAIT_S", "30")
    monkeypatch.setenv("IMPORTED_VOICES_DIR", str(tmp_path / "imported"))
    monkeypatch.setattr(pack_preset_engine, "PackProcess", FakeProcess)
    return phonon_engine.PhononEngine(idle_unload_s=0)


def test_a_plain_load_stays_a_plain_load_when_nothing_is_imported(engine):
    engine.synthesize("hi", "English", voice_id="phonon:Zoey")

    assert FakeProcess.instances[0].requests[0] == {"op": "load"}


def test_the_worker_is_told_about_stored_imports_when_it_starts(engine, monkeypatch):
    monkeypatch.setattr(
        imported_voices,
        "serving_entries",
        lambda engine_id: [{"name": "imported-mine", "path": "/data/imported-mine.safetensors"}],
    )

    engine.synthesize("hi", "English", voice_id="phonon:imported-mine")

    assert FakeProcess.instances[0].requests[0] == {
        "op": "load",
        "imported": [{"name": "imported-mine", "path": "/data/imported-mine.safetensors"}],
    }


def test_import_voice_sends_the_op_to_a_running_worker(engine):
    engine.import_voice("imported-mine", "/data/imported-mine.safetensors")

    requests = FakeProcess.instances[0].requests
    assert requests[-1] == {
        "op": "import_voice", "name": "imported-mine", "path": "/data/imported-mine.safetensors",
    }


def test_the_workers_refusal_becomes_invalid_voice_and_the_worker_stays_up(engine):
    FakeProcess.reject = "Phonon could not read this voice file: header too large"

    with pytest.raises(InvalidVoice, match="header too large"):
        engine.import_voice("imported-mine", "/data/x.safetensors")

    assert FakeProcess.instances[0].is_alive


def test_a_dead_worker_is_unavailable_not_a_bad_file(engine, monkeypatch):
    class Dying(FakeProcess):
        def request(self, payload, *, timeout=None):
            if payload["op"] == "import_voice":
                self.is_alive = False
                raise pack_preset_engine.PackProcessError("worker exited")
            return super().request(payload, timeout=timeout)

    monkeypatch.setattr(pack_preset_engine, "PackProcess", Dying)

    with pytest.raises(EngineUnavailable, match="exited"):
        engine.import_voice("imported-mine", "/data/x.safetensors")


def test_forgetting_an_import_restarts_the_worker_so_the_voice_is_gone(engine):
    engine.import_voice("imported-mine", "/data/x.safetensors")
    first = FakeProcess.instances[0]

    engine.forget_imported("imported-mine")

    assert first.is_alive is False
    engine.synthesize("hi", "English", voice_id="phonon:Zoey")
    assert len(FakeProcess.instances) == 2  # a fresh worker, started without the removed voice


def test_forgetting_with_no_worker_running_is_harmless(engine):
    engine.forget_imported("imported-mine")

    assert FakeProcess.instances == []


def test_imported_names_are_listed_beside_the_presets(monkeypatch):
    monkeypatch.setattr(imported_voices, "names", lambda engine_id: ["imported-mine"])

    assert phonon_engine.list_imported() == ["imported-mine"]


def test_import_waits_for_a_loading_worker(engine, monkeypatch):
    gate = threading.Event()
    original = FakeProcess.request

    def slow(self, payload, *, timeout=None):
        if payload["op"] == "load":
            assert gate.wait(5)
        return original(self, payload, timeout=timeout)

    monkeypatch.setattr(FakeProcess, "request", slow)
    monkeypatch.setenv("ENGINE_WARM_WAIT_S", "0.05")  # short, so the wait must retry
    warmings: list[int] = []
    original_await = engine._await_ready

    def counting():
        try:
            original_await()
        except EngineWarming:
            warmings.append(1)
            raise

    monkeypatch.setattr(engine, "_await_ready", counting)
    done = threading.Event()
    threading.Thread(
        target=lambda: (engine.import_voice("imported-mine", "/data/x.safetensors"), done.set()),
        daemon=True,
    ).start()
    assert not done.wait(0.3)
    assert warmings, "import never retried through EngineWarming"

    gate.set()

    assert done.wait(5)

"""Import/store/adapter trust-boundary regressions. No native model or subprocess is needed."""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path

import pytest

from persona_forge import imported_voices, pack_preset_engine, phonon_worker, speech_engines
from persona_forge.kitten2_engine import InvalidVoice
from tests.tier2_backend.test_imported_voices import GOOD, _import
from tests.tier2_backend.test_imported_voices import store as store  # noqa: F401 - pytest fixture, resolved by parameter name
from tests.tier2_backend.test_phonon_import import FakeProcess, make_worker
from tests.tier2_backend.test_phonon_import import engine as engine  # noqa: F401 - pytest fixture, resolved by parameter name


@pytest.fixture
def runtime(engine, store, monkeypatch):
    monkeypatch.setitem(speech_engines.ADAPTERS, "phonon-31m", engine)
    # Isolate a potential deadlock failure from the rest of the test process.
    monkeypatch.setattr(imported_voices, "_lock", threading.RLock())

    def stream(self, payload):
        if not self.is_alive:
            raise pack_preset_engine.PackProcessError("worker is not running")
        self.requests.append({"op": "stream", **payload})
        yield b"\0\0"

    monkeypatch.setattr(FakeProcess, "stream", stream, raising=False)
    yield engine, store[0]
    engine.unload()


@pytest.mark.parametrize("change", ["remove", "unlink", "tamper", "revision", "record"])
@pytest.mark.parametrize("stream", [False, True])
def test_a_warm_adapter_rechecks_imports_before_synthesis_and_streaming(runtime, monkeypatch, change, stream):
    adapter, root = runtime
    _import()
    adapter.synthesize("warm", "English", voice_id="phonon:imported-zoey-copy")
    first = FakeProcess.instances[0]
    before = list(first.requests)
    base = root / "phonon-31m"
    if change == "remove":
        imported_voices.remove("phonon-31m", "imported-zoey-copy")
    elif change == "unlink":
        (base / "imported-zoey-copy.safetensors").unlink()
    elif change == "tamper":
        (base / "imported-zoey-copy.safetensors").write_bytes(b"broken")
    elif change == "record":
        (base / "imported-zoey-copy.json").write_text("{}")
    else:
        monkeypatch.setattr(imported_voices, "_engine_revision", lambda engine_id: "rev-2")

    with pytest.raises(InvalidVoice):
        if stream:
            next(adapter.stream_pcm("unsafe", "English", voice_id="phonon:imported-zoey-copy"))
        else:
            adapter.synthesize("unsafe", "English", voice_id="phonon:imported-zoey-copy")

    assert not any(r.get("text") == "unsafe" for p in FakeProcess.instances for r in p.requests)
    assert first.requests == before


@pytest.mark.parametrize("stream", [False, True])
def test_import_is_rechecked_inside_the_inference_lock_after_waiting(runtime, monkeypatch, stream):
    adapter, root = runtime
    _import()
    original = adapter._await_ready

    def invalidated_while_waiting():
        original()
        (root / "phonon-31m" / "imported-zoey-copy.json").unlink(missing_ok=True)

    monkeypatch.setattr(adapter, "_await_ready", invalidated_while_waiting)
    with pytest.raises(InvalidVoice):
        if stream:
            next(adapter.stream_pcm("unsafe", "English", voice_id="phonon:imported-zoey-copy"))
        else:
            adapter.synthesize("unsafe", "English", voice_id="phonon:imported-zoey-copy")
    assert not any(r.get("text") == "unsafe" for p in FakeProcess.instances for r in p.requests)


def test_background_loading_can_read_the_store_while_import_waits(runtime):
    _adapter, _root = runtime
    done = threading.Event()
    errors = []

    def run():
        try:
            _import()
        except BaseException as exc:
            errors.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert done.wait(5), "import deadlocked with the background load's store read"
    assert errors == []
    assert imported_voices.names("phonon-31m") == ["imported-zoey-copy"]


def test_import_and_removal_of_the_same_slug_are_serialized(store, monkeypatch):
    _root, adapter = store
    entered, release, removed = threading.Event(), threading.Event(), threading.Event()
    errors = []
    original = adapter.import_voice

    def blocked(slug, path, sha256=None):
        entered.set()
        assert release.wait(5)
        original(slug, path, sha256=sha256)

    monkeypatch.setattr(adapter, "import_voice", blocked)

    def importing():
        try:
            _import()
        except BaseException as exc:
            errors.append(exc)

    def removing():
        try:
            assert imported_voices.remove("phonon-31m", "imported-zoey-copy")
        except BaseException as exc:
            errors.append(exc)
        finally:
            removed.set()

    first = threading.Thread(target=importing, daemon=True)
    second = threading.Thread(target=removing, daemon=True)
    first.start()
    assert entered.wait(5)
    second.start()
    try:
        assert not removed.wait(0.1), "removal crossed an uncommitted engine registration"
    finally:
        release.set()
        first.join(5)
        second.join(5)
    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert imported_voices.names("phonon-31m") == []
    assert adapter.forgotten == ["imported-zoey-copy"]


def test_reload_parser_failures_stop_the_import_being_offered(runtime, monkeypatch):
    adapter, _root = runtime
    _import()
    adapter.unload()
    original = FakeProcess.request

    def reject_on_load(self, payload, *, timeout=None):
        reply = original(self, payload, timeout=timeout)
        if payload["op"] == "load":
            reply["imported_failed"] = ["imported-zoey-copy"]
        return reply

    monkeypatch.setattr(FakeProcess, "request", reject_on_load)
    adapter.synthesize("catalog still works", "English", voice_id="phonon:Zoey")

    assert imported_voices.names("phonon-31m") == []
    assert imported_voices.list_imported("phonon-31m", include_broken=True)[0]["broken"]
    with pytest.raises(InvalidVoice):
        adapter.synthesize("unsafe", "English", voice_id="phonon:imported-zoey-copy")


@pytest.mark.parametrize("change", ["unlink", "tamper", "symlink"])
def test_worker_does_not_serve_a_cached_import_after_its_file_changes(tmp_path, change):
    path = tmp_path / "imported-mine.safetensors"
    path.write_bytes(GOOD)
    worker, model = make_worker()
    worker.handle({"op": "load"})
    worker.handle({"op": "import_voice", "name": "imported-mine", "path": str(path), "sha256": hashlib.sha256(GOOD).hexdigest()})
    if change == "unlink":
        path.unlink()
    elif change == "tamper":
        stamp = path.stat()
        path.write_bytes(GOOD[:-4] + b"\0\0\0\0")
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    else:
        other = tmp_path / "outside.safetensors"
        path.rename(other)
        path.symlink_to(other)

    with pytest.raises(phonon_worker.WorkerError):
        worker.handle({"op": "synthesize", "text": "unsafe", "preset": "imported-mine"})
    assert model.calls == []


def test_worker_stops_yielding_stream_chunks_when_the_import_is_removed(tmp_path, monkeypatch):
    import numpy as np

    path = tmp_path / "imported-mine.safetensors"
    path.write_bytes(GOOD)
    worker, model = make_worker()
    monkeypatch.setattr(model, "stream", lambda *args, **kwargs: iter([np.zeros(2), np.ones(2)]), raising=False)
    worker.handle({"op": "load"})
    worker.handle({"op": "import_voice", "name": "imported-mine", "path": str(path), "sha256": hashlib.sha256(GOOD).hexdigest()})
    chunks = worker.stream({"text": "unsafe", "preset": "imported-mine"})
    assert next(chunks)["chunk_b64"]
    path.unlink()

    with pytest.raises(phonon_worker.WorkerError):
        next(chunks)


def test_worker_rejects_bytes_replaced_between_parent_validation_and_native_parse(tmp_path):
    path = tmp_path / "imported-mine.safetensors"
    path.write_bytes(b"different bytes")
    worker, model = make_worker()
    worker.handle({"op": "load"})

    with pytest.raises(phonon_worker.WorkerError):
        worker.handle({"op": "import_voice", "name": "imported-mine", "path": str(path), "sha256": hashlib.sha256(GOOD).hexdigest()})
    assert model.added == []


def test_failed_reregistration_cannot_leave_the_old_voice_servable(tmp_path):
    path = tmp_path / "imported-mine.safetensors"
    path.write_bytes(GOOD)
    worker, model = make_worker()
    worker.handle({"op": "load"})
    request = {"op": "import_voice", "name": "imported-mine", "path": str(path), "sha256": hashlib.sha256(GOOD).hexdigest()}
    worker.handle(request)
    model.reject = "native parser refused replacement"

    with pytest.raises(phonon_worker.WorkerError, match="refused replacement"):
        worker.handle(request)
    with pytest.raises(phonon_worker.WorkerError):
        worker.handle({"op": "synthesize", "text": "unsafe", "preset": "imported-mine"})
    assert model.calls == []


def test_native_parser_receives_an_immutable_verified_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "imported-mine.safetensors"
    path.write_bytes(GOOD)
    worker, model = make_worker()
    worker.handle({"op": "load"})
    parsed = []

    def replace_before_parse(name, snapshot):
        path.write_bytes(b"tampered after verification")
        parsed.append(Path(snapshot).read_bytes())

    monkeypatch.setattr(model, "add_voice", replace_before_parse)
    worker.handle({"op": "import_voice", "name": "imported-mine", "path": str(path), "sha256": hashlib.sha256(GOOD).hexdigest()})

    assert parsed == [GOOD]


def test_safetensors_library_roundtrip_preserves_tensor_and_provenance(store):
    st = pytest.importorskip("safetensors.numpy")
    import numpy as np

    tensor = np.full((1, 512, 125), 0.25, dtype="float32")
    blob = st.save({"speaker_wavs": tensor}, metadata={"epoch": "300", "sig": "ba7a5a45"})
    record = _import(blob=blob)
    root, _adapter = store
    stored = root / "phonon-31m" / "imported-zoey-copy.safetensors"

    assert np.array_equal(st.load_file(str(stored))["speaker_wavs"], tensor)
    assert record["sha256"] == hashlib.sha256(blob).hexdigest()
    assert record["source_filename"] == "zoey.safetensors"
    assert imported_voices.names("phonon-31m") == ["imported-zoey-copy"]


def test_real_catalog_safetensors_roundtrip_when_fixture_is_supplied(store):
    filename = os.environ.get("PHONON_CATALOG_VOICE_FILE")
    if not filename:
        pytest.skip("set PHONON_CATALOG_VOICE_FILE to a local pinned English catalog .safetensors file")
    blob = Path(filename).read_bytes()
    record = _import(filename=Path(filename).name, blob=blob)
    root, _adapter = store

    assert (root / "phonon-31m" / "imported-zoey-copy.safetensors").read_bytes() == blob
    assert record["sha256"] == hashlib.sha256(blob).hexdigest()
    assert imported_voices.names("phonon-31m") == ["imported-zoey-copy"]

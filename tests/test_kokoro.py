import base64
import hashlib
import io
import wave

import numpy as np
import pytest

from persona_forge import engine_packs, kokoro_engine, pack_preset_engine, kokoro_pack, kokoro_worker, speech_engines
from persona_forge.kitten2_engine import EngineUnavailable, InvalidVoice


class StubKokoro:
    def __init__(self):
        self.calls = []

    def create(self, text, voice, speed, lang):
        self.calls.append((text, voice, speed, lang))
        return np.full(2400, 0.25, dtype=np.float32), 24000


def make_worker():
    stub = StubKokoro()
    seen = {}

    def factory(model_path, voices_path, threads):
        seen.update(model=model_path, voices=voices_path, threads=threads)
        return stub, ["af_heart", "ff_siwis", "pf_dora"]

    return kokoro_worker.KokoroWorker(factory), stub, seen


LOAD = {"op": "load", "model_path": "m.onnx", "voices_path": "v.bin"}


@pytest.mark.parametrize(
    ("voice", "lang"),
    [("af_heart", "en-us"), ("bm_george", "en-gb"), ("ff_siwis", "fr-fr"), ("ef_dora", "es"),
     ("hf_alpha", "hi"), ("if_sara", "it"), ("pf_dora", "pt-br"), ("jf_alpha", None), ("zf_xiaobei", None)],
)
def test_voice_prefix_selects_the_language(voice, lang):
    assert kokoro_worker.language_for(voice) == lang


def test_worker_pins_threads_and_reports_them(monkeypatch):
    monkeypatch.setattr(kokoro_worker.os, "cpu_count", lambda: 16)
    worker, _, seen = make_worker()

    reply = worker.handle(LOAD)

    assert seen["threads"] == 4 and reply["mode"] == "cpu, 4 threads"


def test_worker_uses_every_core_on_a_small_machine(monkeypatch):
    monkeypatch.setattr(kokoro_worker.os, "cpu_count", lambda: 2)
    worker, _, seen = make_worker()

    worker.handle(LOAD)

    assert seen["threads"] == 2


def test_worker_synthesizes_with_the_voices_language_and_a_clamped_speed():
    worker, stub, _ = make_worker()
    worker.handle(LOAD)

    reply = worker.handle({"op": "synthesize", "text": "Bonjour", "preset": "ff_siwis", "speed": 9})

    assert stub.calls == [("Bonjour", "ff_siwis", 2.0, "fr-fr")]
    with wave.open(io.BytesIO(base64.b64decode(reply["audio_b64"]))) as handle:
        assert handle.getnframes() == 2400


def test_worker_defaults_to_a_voice_and_normal_speed():
    worker, stub, _ = make_worker()
    worker.handle(LOAD)

    worker.handle({"op": "synthesize", "text": "hi"})

    assert stub.calls == [("hi", "af_heart", 1.0, "en-us")]


@pytest.mark.parametrize(
    ("request_", "message"),
    [
        ({"op": "synthesize", "text": "hi"}, "load the model first"),
        ({"op": "load"}, "needs model_path"),
        ({"op": "nope"}, "unknown op"),
    ],
)
def test_worker_rejects_bad_requests(request_, message):
    worker, _, _ = make_worker()
    with pytest.raises(kokoro_worker.WorkerError, match=message):
        worker.handle(request_)


def test_worker_rejects_unknown_voices_and_empty_text():
    worker, _, _ = make_worker()
    worker.handle(LOAD)
    with pytest.raises(kokoro_worker.WorkerError, match="unknown preset"):
        worker.handle({"op": "synthesize", "text": "hi", "preset": "xx_nobody"})
    with pytest.raises(kokoro_worker.WorkerError, match="needs text"):
        worker.handle({"op": "synthesize", "text": " "})


class Recorder:
    def __init__(self, fail_on=None, message="boom"):
        self.commands = []
        self.fail_on = fail_on
        self.message = message

    def __call__(self, command, env=None):
        joined = " ".join(command)
        self.commands.append(joined)
        if self.fail_on and self.fail_on in joined:
            raise kokoro_pack.StepFailed(self.message)


@pytest.fixture(autouse=True)
def _fresh_job():
    kokoro_pack.reset_job()
    yield
    kokoro_pack.reset_job()


def run_install(tmp_path, runner=None, downloader=None, uv="uv"):
    runner = runner or Recorder()
    fetched = []
    kokoro_pack.install(
        tmp_path,
        runner=runner,
        downloader=downloader or (lambda directory, spec: fetched.append(spec[0])),
        uv=uv,
        platform="linux",
    )
    return runner, fetched


def test_install_runs_every_step_and_publishes_a_verified_pack(tmp_path):
    runner, fetched = run_install(tmp_path)

    assert kokoro_pack.job_status()["state"] == "done"
    assert fetched == [kokoro_pack.MODEL_FILE[0], kokoro_pack.VOICES_FILE[0]]
    assert any(f"kokoro-onnx=={kokoro_pack.KOKORO_ONNX_VERSION}" in c for c in runner.commands)
    assert "synthesize" in runner.commands[-1]
    assert engine_packs.inspect_pack(kokoro_pack.pack_dir(tmp_path)).status == "verified"


def test_a_download_failure_asks_the_user_to_check_the_connection(tmp_path):
    def broken(directory, spec):
        raise kokoro_pack.StepFailed("could not download x: [Errno 8] nodename nor servname")

    run_install(tmp_path, downloader=broken)

    job = kokoro_pack.job_status()
    assert job["state"] == "error" and "internet connection" in job["error"]
    assert engine_packs.inspect_pack(kokoro_pack.pack_dir(tmp_path)).status == "not-installed"


def test_a_failed_check_leaves_the_pack_uninstalled(tmp_path):
    run_install(tmp_path, runner=Recorder(fail_on="synthesize"))

    assert kokoro_pack.job_status()["state"] == "error"
    assert engine_packs.inspect_pack(kokoro_pack.pack_dir(tmp_path)).status == "not-installed"


def test_download_keeps_a_good_file_and_rejects_a_corrupt_one(tmp_path, monkeypatch):
    payload = b"x" * 100
    spec = ("model.bin", 100, hashlib.sha256(payload).hexdigest())
    served = {"data": payload, "hits": 0}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a) -> None:
            return None

    def fake_open(url, timeout=0):
        served["hits"] += 1
        return Response(served["data"])

    monkeypatch.setattr(kokoro_pack.urllib.request, "urlopen", fake_open)

    kokoro_pack.download_file(tmp_path, spec)
    kokoro_pack.download_file(tmp_path, spec)  # already present and verified: no second download
    assert served["hits"] == 1

    (tmp_path / "models" / "model.bin").unlink()
    served["data"] = b"y" * 100
    with pytest.raises(kokoro_pack.StepFailed, match="pinned size and checksum"):
        kokoro_pack.download_file(tmp_path, spec)
    assert not (tmp_path / "models" / "model.bin").exists()
    assert not (tmp_path / "models" / "model.bin.part").exists()


def test_presets_come_from_the_voices_file_without_japanese_or_chinese(monkeypatch, tmp_path):
    pack = tmp_path / "pack"
    (pack / "models").mkdir(parents=True)
    voices = {n: np.zeros(1) for n in ["af_heart", "ff_siwis", "jf_alpha", "zm_yunxi"]}
    with (pack / "models" / "voices-v1.0.bin").open("wb") as handle:
        np.savez(handle, **voices)  # type: ignore[arg-type]
    monkeypatch.setattr(kokoro_engine, "pack_directory", lambda root=None: pack)
    monkeypatch.setattr(kokoro_engine, "is_installed", lambda root=None: True)

    assert kokoro_engine.list_presets() == ["af_heart", "ff_siwis"]


class FakeProcess:
    instances = []

    def __init__(self, command, **_kwargs):
        self.requests = []
        self.is_alive = True
        FakeProcess.instances.append(self)

    def start(self):
        pass

    def request(self, payload, *, timeout=None):
        self.requests.append(dict(payload))
        return {"ok": True, "mode": "cpu, 4 threads"}

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
    python = tmp_path / "python"
    python.write_text("")
    pack = tmp_path / "pack"
    monkeypatch.setenv("KOKORO_PYTHON", str(python))
    monkeypatch.setattr(kokoro_engine, "pack_directory", lambda root=None: pack)
    monkeypatch.setattr(pack_preset_engine, "PackProcess", FakeProcess)
    return kokoro_engine.KokoroEngine(idle_unload_s=0)


def test_adapter_serves_a_voice_at_the_requested_speed(engine):
    wav, rate, job = engine.synthesize("hi", "French", voice_id="kokoro:ff_siwis", speed=1.2)

    assert rate == 24000 and job is None and len(wav) == 240
    process = FakeProcess.instances[0]
    assert process.requests[0]["op"] == "load" and process.requests[0]["model_path"].endswith(".onnx")
    assert process.requests[-1] == {"op": "synthesize", "text": "hi", "speed": 1.2, "preset": "ff_siwis"}


def test_adapter_refuses_to_clone_a_saved_voice(engine, monkeypatch):
    monkeypatch.setattr(pack_preset_engine.voice_library, "get_voice", lambda vid: {"voice_id": vid})

    with pytest.raises(InvalidVoice, match="cannot clone"):
        engine.synthesize("hi", "English", voice_id="vd_abc")


def test_adapter_maps_an_unknown_voice_to_invalid_voice(engine, monkeypatch):
    def fail(self, payload):
        raise pack_preset_engine.PackProcessError("unknown preset 'xx_nobody'")

    monkeypatch.setattr(FakeProcess, "synthesize", fail)

    with pytest.raises(InvalidVoice):
        engine.synthesize("hi", "English", voice_id="kokoro:xx_nobody")


def test_adapter_reports_a_missing_pack(monkeypatch):
    monkeypatch.delenv("KOKORO_PYTHON", raising=False)
    monkeypatch.setattr(kokoro_engine, "pack_python", lambda root=None: None)

    with pytest.raises(EngineUnavailable, match="not installed"):
        kokoro_engine.KokoroEngine(idle_unload_s=0).synthesize("hi", "English")


def test_registry_knows_kokoro_and_its_aliases():
    info = speech_engines.ENGINES["kokoro"]

    assert info.pack_only and info.capabilities.clone is False and info.capabilities.speed
    for alias in ("kokoro", "kokoro-82m", "kokoro82m"):
        assert speech_engines.MODEL_ALIASES[alias] == "kokoro"

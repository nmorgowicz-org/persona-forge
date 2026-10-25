import io
import json
import wave

import numpy as np
import pytest

from persona_forge import engine_packs, phonon_engine, phonon_pack, phonon_worker, speech_engines
from persona_forge.kitten2_engine import EngineUnavailable, InvalidVoice


class StubModel:
    sample_rate = 24000

    def __init__(self):
        self.calls = []

    def synth(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return np.full(2400, 0.25, dtype=np.float32)


def make_worker():
    stub = StubModel()
    return phonon_worker.PhononWorker(lambda: (stub, ["Easton", "Zoey"])), stub


def test_worker_loads_then_synthesizes_a_preset_with_a_seed():
    worker, stub = make_worker()
    assert worker.handle({"op": "load"}) == {"ok": True, "mode": "cpu", "voices": 2}

    reply = worker.handle({"op": "synthesize", "text": "hi", "preset": "Zoey", "seed": 7})

    assert reply["sample_rate"] == 24000
    assert stub.calls == [("hi", {"voice": "Zoey", "seed": 7})]
    with wave.open(io.BytesIO(__import__("base64").b64decode(reply["audio_b64"]))) as handle:
        assert handle.getnframes() == 2400


def test_worker_uses_the_default_voice_without_a_preset():
    worker, stub = make_worker()
    worker.handle({"op": "load"})

    worker.handle({"op": "synthesize", "text": "hi"})

    assert stub.calls == [("hi", {})]


@pytest.mark.parametrize(
    ("request_", "message"),
    [
        ({"op": "synthesize", "text": "hi"}, "load the model first"),
        ({"op": "nope"}, "unknown op"),
    ],
)
def test_worker_rejects_bad_requests(request_, message):
    worker, _ = make_worker()
    with pytest.raises(phonon_worker.WorkerError, match=message):
        worker.handle(request_)


def test_worker_rejects_unknown_presets_and_empty_text():
    worker, _ = make_worker()
    worker.handle({"op": "load"})
    with pytest.raises(phonon_worker.WorkerError, match="unknown preset"):
        worker.handle({"op": "synthesize", "text": "hi", "preset": "Nobody"})
    with pytest.raises(phonon_worker.WorkerError, match="needs text"):
        worker.handle({"op": "synthesize", "text": "  "})


class Recorder:
    def __init__(self, fail_on=None, message="boom"):
        self.commands = []
        self.fail_on = fail_on
        self.message = message

    def __call__(self, command, env=None):
        joined = " ".join(command)
        self.commands.append(joined)
        if self.fail_on and self.fail_on in joined:
            raise phonon_pack.StepFailed(self.message)


@pytest.fixture(autouse=True)
def _fresh_job():
    phonon_pack.reset_job()
    yield
    phonon_pack.reset_job()


def run_install(tmp_path, runner=None, uv: str | None = "uv"):
    runner = runner or Recorder()
    phonon_pack.install(tmp_path, runner=runner, uv=uv, platform="linux")
    return runner


def test_install_runs_every_step_and_publishes_a_verified_pack(tmp_path):
    runner = run_install(tmp_path)

    assert phonon_pack.job_status()["state"] == "done"
    assert any(f"ptts=={phonon_pack.PTTS_VERSION}" in c for c in runner.commands)
    assert "--python 3.12" in runner.commands[0]
    assert "HF_HUB_OFFLINE" in runner.commands[-1]
    assert engine_packs.inspect_pack(phonon_pack.pack_dir(tmp_path)).status == "verified"


def test_install_falls_back_to_venv_and_pip_without_uv(tmp_path):
    runner = run_install(tmp_path, uv="")

    assert "-m venv" in runner.commands[0]
    assert any("-m pip install ptts==" in c for c in runner.commands)


def test_an_unsupported_cpu_gets_a_plain_message(tmp_path):
    runner = Recorder(fail_on="ptts==", message="No matching distribution found for ptts==0.4.1")
    run_install(tmp_path, runner=runner)

    job = phonon_pack.job_status()
    assert job["state"] == "error"
    assert "AVX2" in job["error"] and "Installing Phonon failed" in job["error"]
    assert engine_packs.inspect_pack(phonon_pack.pack_dir(tmp_path)).status == "not-installed"


def test_a_failed_offline_check_leaves_the_pack_uninstalled(tmp_path):
    run_install(tmp_path, runner=Recorder(fail_on="HF_HUB_OFFLINE"))

    assert phonon_pack.job_status()["state"] == "error"
    assert engine_packs.inspect_pack(phonon_pack.pack_dir(tmp_path)).status == "not-installed"


def test_start_install_refuses_a_second_concurrent_job(monkeypatch):
    started = []
    monkeypatch.setattr(phonon_pack, "install", lambda *a, **k: started.append(1))
    monkeypatch.setattr(phonon_pack.threading.Thread, "start", lambda self: None)

    assert phonon_pack.start_install() is True
    assert phonon_pack.start_install() is False


def write_catalog(tmp_path):
    pack = tmp_path / "pack"
    snap = pack / "hf" / "models--gradium--phonon-voices" / "snapshots" / "abc"
    snap.mkdir(parents=True)
    rows = [
        {"name": "Zoey", "language": "en"},
        {"name": "Easton", "language": "en"},
        {"name": "Amelie", "language": "fr"},
    ]
    (snap / "voices.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    return pack


def test_presets_are_the_english_voices_sorted(monkeypatch, tmp_path):
    pack = write_catalog(tmp_path)
    monkeypatch.setattr(phonon_engine, "pack_directory", lambda root=None: pack)
    monkeypatch.setattr(phonon_engine, "is_installed", lambda root=None: True)

    assert phonon_engine.list_presets() == ["Easton", "Zoey"]


def test_no_presets_when_not_installed(monkeypatch):
    monkeypatch.setattr(phonon_engine, "is_installed", lambda root=None: False)

    assert phonon_engine.list_presets() == []


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
    python = tmp_path / "python"
    python.write_text("")
    monkeypatch.setenv("PHONON_PYTHON", str(python))
    monkeypatch.setattr(phonon_engine, "PackProcess", FakeProcess)
    return phonon_engine.PhononEngine(idle_unload_s=0)


def test_adapter_serves_a_preset(engine):
    wav, rate, job = engine.synthesize("hi", "English", voice_id="phonon:Zoey", seed_value=3)

    assert rate == 24000 and job is None and len(wav) == 240
    assert FakeProcess.instances[0].requests[-1] == {
        "op": "synthesize", "text": "hi", "seed": 3, "preset": "Zoey",
    }
    assert engine.status()["mode"] == "cpu"


def test_adapter_refuses_to_clone_a_saved_voice(engine, monkeypatch):
    monkeypatch.setattr(phonon_engine.voice_library, "get_voice", lambda vid: {"voice_id": vid})

    with pytest.raises(InvalidVoice, match="cannot clone"):
        engine.synthesize("hi", "English", voice_id="vd_abc")


def test_adapter_maps_an_unknown_preset_to_invalid_voice(engine, monkeypatch):
    def fail(self, payload):
        raise phonon_engine.PackProcessError("unknown preset 'Nobody'")

    monkeypatch.setattr(FakeProcess, "synthesize", fail)

    with pytest.raises(InvalidVoice):
        engine.synthesize("hi", "English", voice_id="phonon:Nobody")


def test_adapter_reports_a_missing_pack(monkeypatch):
    monkeypatch.delenv("PHONON_PYTHON", raising=False)
    monkeypatch.setattr(phonon_engine, "pack_python", lambda root=None: None)

    with pytest.raises(EngineUnavailable, match="not installed"):
        phonon_engine.PhononEngine(idle_unload_s=0).synthesize("hi", "English")


def test_registry_knows_phonon_and_its_aliases():
    info = speech_engines.ENGINES["phonon-31m"]

    assert info.pack_only and info.capabilities.clone is False
    for alias in ("phonon", "phonon31m", "phonon-31m"):
        assert speech_engines.MODEL_ALIASES[alias] == "phonon-31m"

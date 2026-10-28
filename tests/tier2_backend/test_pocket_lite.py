import base64
import io
import wave

import numpy as np
import pytest

from persona_forge import (
    engine_packs,
    pack_preset_engine,
    pocket_lite_engine,
    pocket_lite_pack,
    pocket_lite_worker,
    provisioned_engines,
    speech_engines,
)
from persona_forge.kitten2_engine import EngineUnavailable, InvalidVoice


class StubModel:
    sample_rate = 24000
    chunks = 3

    def __init__(self, cloning=True):
        self.has_voice_cloning = cloning
        self.prompts = []
        self.generated = []

    def get_state_for_audio_prompt(self, source):
        self.prompts.append(str(source))
        return {"state": str(source)}

    def generate_audio_stream(self, state, text):
        self.generated.append((state["state"], text))
        for _ in range(self.chunks):
            yield np.full(480, 0.5, dtype=np.float32)

    def generate_audio(self, state, text):
        self.generated.append((state["state"], text))
        return np.full(2400, 0.25, dtype=np.float32)


def make_worker(cloning=True):
    model = StubModel(cloning)
    return pocket_lite_worker.PocketLiteWorker(lambda: model), model


def test_worker_prepares_a_reference_and_synthesizes_with_it():
    worker, model = make_worker()
    worker.handle({"op": "load"})
    worker.handle({"op": "prepare", "voice_id": "vd_1", "reference_path": "/ref.wav"})

    reply = worker.handle({"op": "synthesize", "text": "Hello", "voice_id": "vd_1"})

    assert model.generated == [("/ref.wav", "Hello")]
    with wave.open(io.BytesIO(base64.b64decode(reply["audio_b64"]))) as handle:
        assert handle.getnframes() == 2400 and handle.getframerate() == 24000


def test_worker_serves_and_caches_a_preset_voice():
    worker, model = make_worker()
    worker.handle({"op": "load"})

    worker.handle({"op": "synthesize", "text": "a", "preset": "jane"})
    worker.handle({"op": "synthesize", "text": "b", "preset": "jane"})

    assert model.prompts == ["jane"]  # the state is built once
    assert [g[0] for g in model.generated] == ["jane", "jane"]


def test_worker_defaults_to_a_preset():
    worker, model = make_worker()
    worker.handle({"op": "load"})

    worker.handle({"op": "synthesize", "text": "hi"})

    assert model.generated == [("alba", "hi")]


def test_a_seed_is_applied_to_every_generator_the_model_draws_from(monkeypatch):
    import random

    torch = pytest.importorskip("torch")  # the lean CI lane installs no torch
    worker, _ = make_worker()
    worker.handle({"op": "load"})
    draws = []
    for _ in range(2):
        worker.handle({"op": "synthesize", "text": "hi", "seed": 5})
        draws.append((torch.rand(1).item(), np.random.rand(), random.random()))

    assert draws[0] == draws[1]


def test_worker_streams_pcm_chunks_then_done():
    worker, model = make_worker()
    worker.handle({"op": "load"})

    messages = list(worker.stream({"text": "Hello", "preset": "jane"}))

    assert [m.get("done", False) for m in messages] == [False, False, False, True]
    pcm = np.frombuffer(base64.b64decode(messages[0]["chunk_b64"]), dtype="<i2")
    assert len(pcm) == 480 and abs(int(pcm[0]) - 16383) <= 1
    assert model.generated == [("jane", "Hello")]


def test_worker_stream_clones_a_prepared_voice_and_rejects_bad_requests():
    worker, model = make_worker()
    worker.handle({"op": "load"})
    worker.handle({"op": "prepare", "voice_id": "vd_1", "reference_path": "/ref.wav"})

    list(worker.stream({"text": "hi", "voice_id": "vd_1"}))
    assert model.generated[-1][0] == "/ref.wav"
    with pytest.raises(pocket_lite_worker.WorkerError, match="needs text"):
        list(worker.stream({"text": ""}))
    with pytest.raises(pocket_lite_worker.WorkerError, match="unknown preset"):
        list(worker.stream({"text": "hi", "preset": "giovanni"}))


def test_serve_writes_one_line_per_stream_message_and_survives_a_bad_request():
    import json

    worker, _ = make_worker()
    worker.handle({"op": "load"})
    lines = [
        json.dumps({"op": "stream", "text": "hi", "preset": "jane"}),
        json.dumps({"op": "stream", "text": ""}),
        json.dumps({"op": "ping"}),
    ]
    out = io.StringIO()

    pocket_lite_worker.serve(worker, io.StringIO("\n".join(lines) + "\n"), out)

    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r.get("done", False) for r in replies[:4]] == [False, False, False, True]
    assert replies[4]["ok"] is False and "needs text" in replies[4]["error"]
    assert replies[5]["ok"] is True


def test_worker_refuses_a_model_without_cloning_weights():
    worker, _ = make_worker(cloning=False)
    with pytest.raises(pocket_lite_worker.WorkerError, match="cloning weights"):
        worker.handle({"op": "load"})


@pytest.mark.parametrize(
    ("request_", "message"),
    [
        ({"op": "synthesize", "text": "hi"}, "load the model first"),
        ({"op": "nope"}, "unknown op"),
    ],
)
def test_worker_rejects_bad_requests(request_, message):
    worker, _ = make_worker()
    with pytest.raises(pocket_lite_worker.WorkerError, match=message):
        worker.handle(request_)


def test_worker_rejects_unknown_presets_unprepared_voices_and_empty_text():
    worker, _ = make_worker()
    worker.handle({"op": "load"})
    with pytest.raises(pocket_lite_worker.WorkerError, match="unknown preset"):
        worker.handle({"op": "synthesize", "text": "hi", "preset": "giovanni"})  # not English
    with pytest.raises(pocket_lite_worker.WorkerError, match="not been prepared"):
        worker.handle({"op": "synthesize", "text": "hi", "voice_id": "vd_x"})
    with pytest.raises(pocket_lite_worker.WorkerError, match="needs text"):
        worker.handle({"op": "synthesize", "text": " "})


def test_unload_drops_the_model_and_every_state():
    worker, _ = make_worker()
    worker.handle({"op": "load"})
    worker.handle({"op": "prepare", "voice_id": "vd_1", "reference_path": "/r.wav"})

    worker.handle({"op": "unload"})

    with pytest.raises(pocket_lite_worker.WorkerError, match="load the model first"):
        worker.handle({"op": "synthesize", "text": "hi", "voice_id": "vd_1"})


class Recorder:
    def __init__(self, fail_on=None, message="boom"):
        self.commands = []
        self.envs = []
        self.fail_on = fail_on
        self.message = message

    def __call__(self, command, env=None):
        joined = " ".join(command)
        self.commands.append(joined)
        self.envs.append(env or {})
        if self.fail_on and self.fail_on in joined:
            raise pocket_lite_pack.StepFailed(self.message)


@pytest.fixture(autouse=True)
def _fresh_job():
    pocket_lite_pack.reset_job()
    yield
    pocket_lite_pack.reset_job()


def test_install_downloads_online_checks_offline_and_publishes(tmp_path):
    runner = Recorder()

    pocket_lite_pack.install(tmp_path, runner=runner, token="hf_secret")

    assert pocket_lite_pack.job_status()["state"] == "done"
    assert len(runner.commands) == 2
    assert "has_voice_cloning" in runner.commands[0] and "synthesize" in runner.commands[1]
    assert runner.envs[0]["HF_TOKEN"] == "hf_secret" and "HF_HUB_OFFLINE" not in runner.envs[0]
    assert runner.envs[1]["HF_HUB_OFFLINE"] == "1" and "HF_TOKEN" not in runner.envs[1]
    assert engine_packs.inspect_pack(pocket_lite_pack.pack_dir(tmp_path)).status == "verified"


def test_install_without_a_token_does_not_send_one(tmp_path):
    runner = Recorder()

    pocket_lite_pack.install(tmp_path, runner=runner, token="")

    assert "HF_TOKEN" not in runner.envs[0]


def test_a_gated_download_failure_tells_the_user_to_accept_the_terms(tmp_path):
    runner = Recorder(fail_on="has_voice_cloning", message="AssertionError: no cloning weights")

    pocket_lite_pack.install(tmp_path, runner=runner, token="")

    job = pocket_lite_pack.job_status()
    assert job["state"] == "error" and "accept its terms" in job["error"].lower()
    assert "hf_" not in job["error"]
    assert engine_packs.inspect_pack(pocket_lite_pack.pack_dir(tmp_path)).status == "not-installed"


def test_a_network_failure_asks_the_user_to_check_the_connection(tmp_path):
    runner = Recorder(fail_on="has_voice_cloning", message="Name or service not known")

    pocket_lite_pack.install(tmp_path, runner=runner, token="x")

    assert "internet connection" in pocket_lite_pack.job_status()["error"]


def test_a_failed_offline_check_leaves_the_pack_uninstalled(tmp_path):
    pocket_lite_pack.install(tmp_path, runner=Recorder(fail_on="synthesize"), token="x")

    assert pocket_lite_pack.job_status()["state"] == "error"
    assert engine_packs.inspect_pack(pocket_lite_pack.pack_dir(tmp_path)).status == "not-installed"


class FakeProcess:
    instances = []

    def __init__(self, command, **kwargs):
        self.requests = []
        self.env = kwargs.get("env")
        self.is_alive = True
        FakeProcess.instances.append(self)

    def start(self):
        pass

    def request(self, payload, *, timeout=None):
        self.requests.append(dict(payload))
        return {"ok": True, "mode": "cpu"}

    def stream(self, payload):
        self.requests.append({"op": "stream", **payload})
        yield b"\x01\x00" * 100
        yield b"\x02\x00" * 100

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
    pack = tmp_path / "pack"
    pack.mkdir()
    monkeypatch.setattr(pocket_lite_engine, "pack_directory", lambda root=None: pack)
    monkeypatch.setattr(pocket_lite_engine, "pack_python", lambda root=None: tmp_path / "python")
    monkeypatch.setattr(pack_preset_engine, "PackProcess", FakeProcess)
    return pocket_lite_engine.PocketLiteEngine(idle_unload_s=0)


def test_adapter_asks_for_a_repair_when_pocket_tts_changed_since_install(engine, monkeypatch, tmp_path):
    pocket_lite_pack.install(tmp_path, runner=Recorder(), token="x")
    pack = pocket_lite_pack.pack_dir(tmp_path)
    monkeypatch.setattr(pocket_lite_engine, "pack_directory", lambda root=None: pack)
    monkeypatch.setattr(pocket_lite_pack, "pocket_tts_version", lambda: "9.9.9")

    with pytest.raises(EngineUnavailable, match="Repair"):
        engine.synthesize("hi", "English", voice_id="pocket-lite:jane")


def test_the_manifest_records_the_pocket_tts_version_used_for_the_download(tmp_path):
    pocket_lite_pack.install(tmp_path, runner=Recorder(), token="x")

    manifest = engine_packs.load_manifest(pocket_lite_pack.pack_dir(tmp_path))
    assert f"pocket-tts=={pocket_lite_pack.pocket_tts_version()}" in manifest.requirements


def saved_voice(monkeypatch, tmp_path, name="vd_1"):
    wav = tmp_path / f"{name}.wav"
    wav.write_bytes(b"RIFF")
    monkeypatch.setattr(
        pocket_lite_engine.voice_library,
        "get_voice",
        lambda vid: {"voice_id": vid, "wav_path": str(wav)} if vid == name else None,
    )
    return wav


def test_adapter_starts_the_worker_offline_with_its_own_weights(engine, tmp_path):
    engine.synthesize("hi", "English", voice_id="pocket-lite:jane")

    process = FakeProcess.instances[0]
    assert process.requests[0] == {"op": "load"}
    assert process.env["HF_HUB_OFFLINE"] == "1"
    assert process.env["HF_HOME"] == str(tmp_path / "pack" / "hf")
    assert process.requests[-1] == {"op": "synthesize", "text": "hi", "preset": "jane"}


def test_adapter_accepts_the_standard_pocket_voice_names(engine):
    engine.synthesize("hi", "English", voice_id="pocket:marius")

    assert FakeProcess.instances[0].requests[-1]["preset"] == "marius"


def test_adapter_clones_a_saved_voice_without_a_transcript(engine, monkeypatch, tmp_path):
    wav = saved_voice(monkeypatch, tmp_path)

    engine.synthesize("hi", "English", voice_id="vd_1", seed_value=7)

    requests = FakeProcess.instances[0].requests
    assert requests[1] == {"op": "prepare", "voice_id": "vd_1", "reference_path": str(wav)}
    assert requests[-1] == {"op": "synthesize", "text": "hi", "voice_id": "vd_1", "seed": 7}


def test_adapter_prepares_a_voice_once_and_again_when_the_clip_changes(engine, monkeypatch, tmp_path):
    wav = saved_voice(monkeypatch, tmp_path)

    engine.synthesize("a", "English", voice_id="vd_1")
    engine.synthesize("b", "English", voice_id="vd_1")
    prepares = lambda: [r for r in FakeProcess.instances[0].requests if r["op"] == "prepare"]  # noqa: E731
    assert len(prepares()) == 1

    wav.write_bytes(b"RIFF-new")
    import os

    os.utime(wav, (wav.stat().st_atime, wav.stat().st_mtime + 5))
    engine.synthesize("c", "English", voice_id="vd_1")
    assert len(prepares()) == 2


def test_adapter_streams_a_preset_in_chunks(engine):
    chunks = list(engine.stream_pcm("hi", "English", voice_id="pocket-lite:jane", seed_value=4))

    assert len(chunks) == 2 and all(len(c) == 200 for c in chunks)
    assert FakeProcess.instances[0].requests[-1] == {"op": "stream", "text": "hi", "seed": 4, "preset": "jane"}


def test_adapter_streams_a_cloned_saved_voice(engine, monkeypatch, tmp_path):
    wav = saved_voice(monkeypatch, tmp_path)

    list(engine.stream_pcm("hi", "English", voice_id="vd_1"))

    requests = FakeProcess.instances[0].requests
    assert requests[1] == {"op": "prepare", "voice_id": "vd_1", "reference_path": str(wav)}
    assert requests[-1] == {"op": "stream", "text": "hi", "voice_id": "vd_1"}


def test_adapter_reports_a_missing_reference_clip(engine, monkeypatch, tmp_path):
    wav = saved_voice(monkeypatch, tmp_path)
    wav.unlink()

    with pytest.raises(InvalidVoice, match="missing"):
        engine.synthesize("hi", "English", voice_id="vd_1")


def test_adapter_maps_an_unknown_preset_to_invalid_voice(engine, monkeypatch):
    def fail(self, payload):
        raise pack_preset_engine.PackProcessError("unknown preset 'nobody'")

    monkeypatch.setattr(FakeProcess, "synthesize", fail)

    with pytest.raises(InvalidVoice):
        engine.synthesize("hi", "English", voice_id="pocket-lite:nobody")


def test_adapter_reports_a_missing_pack(monkeypatch):
    monkeypatch.setattr(pocket_lite_engine, "pack_python", lambda root=None: None)

    with pytest.raises(EngineUnavailable, match="not installed"):
        pocket_lite_engine.PocketLiteEngine(idle_unload_s=0).synthesize("hi", "English")


def test_presets_are_the_english_catalogue_when_installed(monkeypatch):
    monkeypatch.setattr(pocket_lite_engine, "is_installed", lambda root=None: True)
    names = pocket_lite_engine.list_presets()
    assert "alba" in names and "giovanni" not in names and len(names) == 21

    monkeypatch.setattr(pocket_lite_engine, "is_installed", lambda root=None: False)
    assert pocket_lite_engine.list_presets() == []


def test_registry_knows_pocket_lite_and_its_aliases():
    info = speech_engines.ENGINES["pocket-lite"]

    assert info.pack_only and info.capabilities.clone and info.capabilities.seed
    assert info.capabilities.streaming == "frame"
    assert info.capabilities.languages == ("en",)
    for alias in ("pocket-lite", "pocket_lite", "pocket-lite-18m"):
        assert speech_engines.MODEL_ALIASES[alias] == "pocket-lite"
    assert "pocket-lite" in provisioned_engines.ids()
    assert speech_engines.MODEL_ALIASES["pocket"] == "pocket-tts"  # the standard engine is unchanged

"""The install-time speed check: one short real synthesis through the worker, recorded as RTF.

A slow machine is a labelled outcome, never an install failure, and the check never touches the
verified stamp (only the provisioner mints that).
"""

from __future__ import annotations

import io
import json
import sys
import wave
from pathlib import Path

import pytest

from persona_forge import (
    engine_packs,
    install_check,
    kitten2_pack,
    kokoro_pack,
    phonon_pack,
    pocket_lite_pack,
)
from persona_forge.pack_process import PackProcessError

# -- helpers -------------------------------------------------------------------------------------

def record_of(directory) -> dict:
    record = install_check.read_record(directory)
    assert record is not None, "no install check record was written"
    return record


def result_of(result) -> dict:
    assert result is not None, "the check did not run"
    return result



def wav_bytes(seconds: float, rate: int = 8000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(seconds * rate))
    return buffer.getvalue()


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class FakeProcess:
    """Stands in for PackProcess: advances a fake clock by what each request 'costs'."""

    def __init__(self, clock, *, load=None, costs=None, audio=2.0, fail_on=None):
        self.clock = clock
        self.load = {"ok": True, "mode": "cpu", **(load or {})}
        self.costs = {"load": 0.0, "warmup": 0.0, "prime": 0.0, "timed": 0.4, **(costs or {})}
        self.audio = audio
        self.fail_on = fail_on
        self.requests: list[dict] = []
        self.synth_texts: list[str] = []
        self.started = False
        self.closed = False

    def start(self):
        self.started = True

    def request(self, payload, *, timeout=None):
        self.requests.append(dict(payload))
        if self.fail_on == payload["op"]:
            raise PackProcessError(f"{payload['op']} blew up")
        if payload["op"] == "load":
            self.clock.now += self.costs["load"]
            return dict(self.load)
        if payload["op"] == "warmup":
            self.clock.now += self.costs["warmup"]
            return {"ok": True, **{k: v for k, v in self.load.items() if k != "warmup_pending"}}
        raise AssertionError(payload)

    def synthesize(self, payload):
        self.requests.append({"op": "synthesize", **payload})
        self.synth_texts.append(payload["text"])
        if self.fail_on == "synthesize":
            raise PackProcessError("synthesize blew up")
        timed = payload["text"] == install_check.CHECK_TEXT
        self.clock.now += self.costs["timed"] if timed else self.costs["prime"]
        return wav_bytes(self.audio)

    def close(self):
        self.closed = True


SPEC = install_check.SpeedCheckSpec(command=("python", "worker.py"), env={"A": "1"}, load_request={"op": "load"})


def run_with(process: FakeProcess, clock: Clock, **kwargs):
    return install_check.run(
        SPEC,
        process_factory=lambda command, **options: process,
        clock=clock,
        load_average=lambda: 1.25,
        **kwargs,
    )


# -- run() ---------------------------------------------------------------------------------------


def test_a_fast_run_records_rtf_device_and_load_average():
    clock = Clock()
    process = FakeProcess(clock, load={"backend": "mps", "mode": "mlx"}, costs={"timed": 0.4}, audio=2.0)

    result = run_with(process, clock)

    assert result["outcome"] == "ok"
    assert result["rtf"] == 0.2
    assert result["compute_seconds"] == 0.4 and result["audio_seconds"] == 2.0
    assert result["device"] == "mps" and result["mode"] == "mlx"
    assert result["load_average"] == 1.25
    assert result["at"]
    assert process.started and process.closed


def test_a_slower_than_real_time_run_is_labelled_not_an_error():
    clock = Clock()
    process = FakeProcess(clock, costs={"timed": 3.0}, audio=2.0)

    result = run_with(process, clock)

    assert result["outcome"] == "slow"
    assert result["rtf"] == 1.5


def test_exactly_real_time_is_not_flagged_slow():
    clock = Clock()
    result = run_with(FakeProcess(clock, costs={"timed": 2.0}, audio=2.0), clock)
    assert result["outcome"] == "ok" and result["rtf"] == 1.0


def test_the_timed_run_follows_the_warm_up_and_excludes_it():
    clock = Clock()
    process = FakeProcess(
        clock,
        load={"warmup_pending": True, "backend": "cuda", "mode": "compiled"},
        costs={"warmup": 33.0, "timed": 0.5},
        audio=2.0,
    )

    result = run_with(process, clock)

    ops = [request["op"] for request in process.requests]
    assert ops == ["load", "warmup", "synthesize"]
    assert result["rtf"] == 0.25  # the 33 s compile is not part of the speed
    assert result["warmup_seconds"] == 33.0
    assert result["device"] == "cuda" and result["mode"] == "compiled"
    assert process.synth_texts == [install_check.CHECK_TEXT]


def test_an_engine_without_a_warm_up_gets_one_untimed_priming_run_first():
    clock = Clock()
    process = FakeProcess(clock, costs={"prime": 9.0, "timed": 0.2}, audio=2.0)

    result = run_with(process, clock)

    assert len(process.synth_texts) == 2
    assert process.synth_texts[0] != install_check.CHECK_TEXT
    assert process.synth_texts[1] == install_check.CHECK_TEXT
    assert result["rtf"] == 0.1
    assert result["warmup_seconds"] is None


def test_a_fast_mode_problem_is_carried_into_the_record_as_a_note():
    clock = Clock()
    process = FakeProcess(
        clock,
        load={"fast_mode_issue": {"message": "Fast mode needs a C compiler.", "code": "x"}},
        costs={"timed": 3.0},
    )

    result = run_with(process, clock)

    assert result["outcome"] == "slow" and result["note"] == "Fast mode needs a C compiler."


@pytest.mark.parametrize("op", ["load", "synthesize"])
def test_a_worker_failure_is_recorded_as_unavailable_and_never_raised(op):
    clock = Clock()
    process = FakeProcess(clock, fail_on=op)

    result = run_with(process, clock)

    assert result["outcome"] == "unavailable"
    assert "blew up" in result["error"]
    assert result["rtf"] is None
    assert process.closed


def test_a_worker_that_cannot_start_is_unavailable():
    result = install_check.run(
        install_check.SpeedCheckSpec(command=("/no/such/python", "w.py"), env={}, load_request={"op": "load"})
    )
    assert result["outcome"] == "unavailable" and result["error"]


def test_zero_length_audio_is_unavailable_not_a_division_error():
    clock = Clock()
    result = run_with(FakeProcess(clock, audio=0.0), clock)
    assert result["outcome"] == "unavailable"


STUB_WORKER = r"""
import base64, io, json, os, sys, time, wave

def wav(seconds, rate=8000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()

for line in sys.stdin:
    req = json.loads(line)
    op = req["op"]
    if op == "synthesize":
        time.sleep(float(os.environ.get("STUB_SLEEP", "0")))
        out = {"ok": True, "audio_b64": base64.b64encode(wav(float(os.environ.get("STUB_AUDIO", "1")))).decode()}
    elif op == "load":
        out = {"ok": True, "mode": os.environ.get("STUB_MODE", "stubcpu")}
    else:
        out = {"ok": True}
    sys.stdout.write(json.dumps(out) + "\n"); sys.stdout.flush()
"""


@pytest.fixture
def stub_worker(tmp_path):
    path = tmp_path / "stub_worker.py"
    path.write_text(STUB_WORKER, encoding="utf-8")
    return path


def stub_spec(stub_worker: Path, **env: str):
    return install_check.SpeedCheckSpec(
        command=(sys.executable, str(stub_worker)), env=env, load_request={"op": "load"}
    )


def test_stub_worker_process_end_to_end_fast(stub_worker):
    result = install_check.run(stub_spec(stub_worker, STUB_SLEEP="0.01", STUB_AUDIO="2"))

    assert result["outcome"] == "ok"
    assert 0 < result["rtf"] < 1
    assert result["audio_seconds"] == 2.0
    assert result["device"] == "stubcpu"


def test_stub_worker_process_end_to_end_slow(stub_worker):
    result = install_check.run(stub_spec(stub_worker, STUB_SLEEP="0.4", STUB_AUDIO="0.1"))

    assert result["outcome"] == "slow"
    assert result["rtf"] > 1


# -- record file ---------------------------------------------------------------------------------


def test_record_round_trips_and_garbage_reads_as_none(tmp_path):
    assert install_check.read_record(tmp_path) is None
    install_check.write_record(tmp_path, {"outcome": "ok", "rtf": 0.18})
    assert install_check.read_record(tmp_path) == {"outcome": "ok", "rtf": 0.18}
    (tmp_path / install_check.RECORD_FILENAME).write_text("[", encoding="utf-8")
    assert install_check.read_record(tmp_path) is None
    (tmp_path / install_check.RECORD_FILENAME).write_text("[1]", encoding="utf-8")
    assert install_check.read_record(tmp_path) is None


def test_a_record_is_not_a_verification_stamp(tmp_path):
    pack = tmp_path / "kokoro"
    pack.mkdir()
    (pack / "manifest.json").write_text(json.dumps(kokoro_pack.build_manifest()), encoding="utf-8")

    install_check.write_record(pack, {"outcome": "ok", "rtf": 0.1})

    assert engine_packs.inspect_pack(pack).status == "not-installed"
    assert not (pack / engine_packs.VERIFIED_FILENAME).exists()


def test_check_and_record_survives_a_measure_that_raises(tmp_path):
    def broken(spec):
        raise RuntimeError("kaboom")

    result = result_of(install_check.check_and_record(tmp_path, SPEC, broken))

    assert result["outcome"] == "unavailable" and "kaboom" in result["error"]
    assert record_of(tmp_path)["outcome"] == "unavailable"


def test_the_check_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE_INSTALL_SPEED_CHECK", "0")
    started = []
    monkeypatch.setattr(install_check, "run", lambda spec: started.append(spec))

    assert install_check.check_and_record(tmp_path, SPEC) is None
    assert started == [] and install_check.read_record(tmp_path) is None


def test_an_explicit_measure_runs_even_when_the_env_default_is_off(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE_INSTALL_SPEED_CHECK", "0")
    result = install_check.check_and_record(tmp_path, SPEC, lambda spec: {"outcome": "ok", "rtf": 0.3})
    assert result == {"outcome": "ok", "rtf": 0.3}
    assert record_of(tmp_path)["rtf"] == 0.3


# -- every pack records one on install ------------------------------------------------------------


def _noop_runner(command, env=None):
    return None


def _install_kokoro(root, measure, runner=_noop_runner):
    kokoro_pack.reset_job()
    kokoro_pack.install(
        root, runner=runner, downloader=lambda directory, spec: None, uv="uv", platform="linux", measure=measure
    )
    return kokoro_pack


def _install_phonon(root, measure, runner=_noop_runner):
    phonon_pack.reset_job()
    phonon_pack.install(root, runner=runner, uv="uv", platform="linux", measure=measure)
    return phonon_pack


def _install_pocket_lite(root, measure, runner=_noop_runner):
    pocket_lite_pack.reset_job()
    pocket_lite_pack.install(root, runner=runner, token="x", measure=measure)
    return pocket_lite_pack


def _install_kitten2(root, measure, runner=_noop_runner):
    kitten2_pack.reset_job()
    kitten2_pack.install(
        root,
        detect=lambda: kitten2_pack.Target("mlx"),
        runner=runner,
        prefetch=lambda python, directory: None,
        uv="uv",
        platform="darwin",
        measure=measure,
    )
    return kitten2_pack


INSTALLERS = {
    "kokoro": _install_kokoro,
    "phonon-31m": _install_phonon,
    "pocket-lite": _install_pocket_lite,
    "kitten2": _install_kitten2,
}


@pytest.fixture(params=list(INSTALLERS))
def pack_case(request, tmp_path):
    engine_id = request.param
    yield engine_id, INSTALLERS[engine_id], tmp_path
    for module in (kokoro_pack, phonon_pack, pocket_lite_pack, kitten2_pack):
        module.reset_job()


def test_install_records_the_check_before_publishing_the_stamp(pack_case):
    engine_id, install, root = pack_case
    seen = []

    def measure(spec):
        seen.append(spec)
        directory = root / engine_id
        # The check runs before the provisioner mints the stamp.
        assert not (directory / engine_packs.VERIFIED_FILENAME).exists()
        return {"outcome": "ok", "rtf": 0.18, "device": "cpu", "mode": "cpu", "load_average": 0.5}

    module = install(root, measure)

    assert module.job_status()["state"] == "done"
    assert len(seen) == 1 and isinstance(seen[0], install_check.SpeedCheckSpec)
    directory = root / engine_id
    assert record_of(directory)["rtf"] == 0.18
    assert engine_packs.inspect_pack(directory).status == "verified"


def test_a_slow_machine_still_installs_and_carries_the_label(pack_case):
    engine_id, install, root = pack_case

    module = install(root, lambda spec: {"outcome": "slow", "rtf": 1.6, "device": "cuda"})

    assert module.job_status()["state"] == "done"
    assert module.job_status()["error"] is None
    directory = root / engine_id
    assert record_of(directory)["outcome"] == "slow"
    assert engine_packs.inspect_pack(directory).status == "verified"


def test_a_measure_that_explodes_does_not_fail_the_install(pack_case):
    engine_id, install, root = pack_case

    def boom(spec):
        raise OSError("disk on fire")

    module = install(root, boom)

    assert module.job_status()["state"] == "done"
    directory = root / engine_id
    assert record_of(directory)["outcome"] == "unavailable"
    assert engine_packs.inspect_pack(directory).status == "verified"


WORKER_FILES = {
    "kokoro": "kokoro_worker.py",
    "phonon-31m": "phonon_worker.py",
    "pocket-lite": "pocket_lite_worker.py",
    "kitten2": "kitten2_worker.py",
}


def test_the_spec_runs_the_pack_worker_with_the_pack_s_own_settings(pack_case):
    engine_id, install, root = pack_case
    seen = []
    install(root, lambda spec: seen.append(spec) or {"outcome": "ok", "rtf": 0.1})
    spec = seen[0]

    assert Path(spec.command[1]).name == WORKER_FILES[engine_id]
    assert spec.load_request["op"] == "load"
    if engine_id == "kitten2":
        assert spec.load_request["warmup"] is False  # the check sends the warm-up itself
    if engine_id in ("phonon-31m", "kitten2", "pocket-lite"):
        assert spec.env["HF_HUB_OFFLINE"] == "1" and spec.env["HF_HOME"].endswith("hf")
    if engine_id == "kokoro":
        assert spec.load_request["model_path"].endswith(".onnx")
        assert spec.load_request["voices_path"].endswith(".bin")


def test_an_earlier_failure_leaves_no_record_and_never_measures(pack_case):
    engine_id, install, root = pack_case
    called = []

    def failing_runner(command, env=None):
        raise kitten2_pack.StepFailed("nope")

    module = install(root, lambda spec: called.append(spec), failing_runner)

    assert module.job_status()["state"] == "error"
    assert called == []
    assert install_check.read_record(root / engine_id) is None


# -- engine cards --------------------------------------------------------------------------------


def test_engine_cards_carry_the_install_check_of_an_installed_pack(tmp_path):
    _install_kokoro(tmp_path, lambda spec: {"outcome": "ok", "rtf": 0.18, "device": "cpu"})

    cards = {card["id"]: card for card in engine_packs.engine_cards("pocket_tts", tmp_path)}

    assert cards["kokoro"]["install_check"]["rtf"] == 0.18
    assert cards["pocket-tts"]["install_check"] is None
    assert cards["phonon-31m"]["install_check"] is None


def test_get_engines_returns_the_install_check(client, monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))
    _install_phonon(tmp_path, lambda spec: {"outcome": "slow", "rtf": 1.4, "device": "cpu"})

    body = client.get("/engines").get_json()

    card = next(item for item in body["engines"] if item["id"] == "phonon-31m")
    assert card["install_check"]["outcome"] == "slow" and card["install_check"]["rtf"] == 1.4

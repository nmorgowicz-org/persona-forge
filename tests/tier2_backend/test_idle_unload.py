"""Idle unload is uniform across the pack engines and driven by the pack manifest.

Effective seconds resolve as: constructor argument > env override > manifest
``idle_unload_after`` > the engine's own default (older packs have no field). A fake clock fires the
timers so each engine is shown to unload its worker, return to ``idle`` and reload on demand.
"""

from __future__ import annotations

import io
from typing import Callable
import json
import wave

import pytest

from persona_forge import (
    engine_packs,
    kitten2_engine,
    kitten2_pack,
    kokoro_engine,
    kokoro_pack,
    pack_preset_engine,
    phonon_engine,
    phonon_pack,
    pocket_lite_engine,
    pocket_lite_pack,
)


class FakeClock:
    """A clock plus a ``threading.Timer`` stand-in that fires when the clock is advanced."""

    def __init__(self) -> None:
        self.now = 0.0
        self.timers: list[FakeTimer] = []

    def factory(self, interval, function):
        timer = FakeTimer(self, interval, function)
        self.timers.append(timer)
        return timer

    def advance(self, seconds: float) -> None:
        target = self.now + seconds
        while True:
            due = sorted(
                (t for t in self.timers if t.live and t.deadline <= target),
                key=lambda t: t.deadline,
            )
            if not due:
                break
            timer = due[0]
            self.now = timer.deadline
            timer.live = False
            timer.function()
        self.now = target

    @property
    def armed(self) -> int:
        return sum(1 for t in self.timers if t.live)


class FakeTimer:
    def __init__(self, clock, interval, function) -> None:
        self.clock, self.interval, self.function = clock, interval, function
        self.deadline = 0.0
        self.live = False
        self.daemon = False

    def start(self) -> None:
        self.deadline = self.clock.now + self.interval
        self.live = True

    def cancel(self) -> None:
        self.live = False


def _wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x10" * 240)
    return buffer.getvalue()


STREAM_HOOKS: list[Callable[[], object]] = []  # run mid-stream by FakeProcess.stream


class FakeProcess:
    instances: list[FakeProcess] = []

    def __init__(self, command, **_kwargs):
        self.is_alive = True
        self.closed = False
        FakeProcess.instances.append(self)

    def start(self):
        pass

    def request(self, payload, *, timeout=None):
        return {"ok": True, "mode": "cpu"}

    def synthesize(self, payload):
        return _wav()

    def stream(self, payload, *, timeout=None):
        yield b"\x01\x00" * 50
        for hook in STREAM_HOOKS:
            hook()
        yield b"\x02\x00" * 50

    def close(self):
        self.is_alive = False
        self.closed = True


CASES = {
    "kitten2": (kitten2_engine.Kitten2Engine, kitten2_pack.ENGINE_ID, "KITTEN2_IDLE_UNLOAD_S"),
    "phonon": (phonon_engine.PhononEngine, phonon_pack.ENGINE_ID, "PHONON_IDLE_UNLOAD_S"),
    "kokoro": (kokoro_engine.KokoroEngine, kokoro_pack.ENGINE_ID, "KOKORO_IDLE_UNLOAD_S"),
    "pocket-lite": (
        pocket_lite_engine.PocketLiteEngine,
        pocket_lite_pack.ENGINE_ID,
        "POCKET_LITE_IDLE_UNLOAD_S",
    ),
}
PACK_DEFAULTS = {
    "kitten2": kitten2_pack.IDLE_UNLOAD_AFTER_S,
    "phonon": phonon_pack.IDLE_UNLOAD_AFTER_S,
    "kokoro": kokoro_pack.IDLE_UNLOAD_AFTER_S,
    "pocket-lite": pocket_lite_pack.IDLE_UNLOAD_AFTER_S,
}


@pytest.fixture
def clock(monkeypatch, tmp_path):
    FakeProcess.instances.clear()
    STREAM_HOOKS.clear()
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path / "packs"))
    for name in (c[2] for c in CASES.values()):
        monkeypatch.delenv(name, raising=False)
    python = tmp_path / "python"
    python.write_text("")
    for var in ("KITTEN2_PYTHON", "PHONON_PYTHON", "KOKORO_PYTHON"):
        monkeypatch.setenv(var, str(python))
    monkeypatch.setattr(kitten2_engine, "PackProcess", FakeProcess)
    monkeypatch.setattr(pack_preset_engine, "PackProcess", FakeProcess)
    monkeypatch.setattr(pocket_lite_engine, "pack_python", lambda root=None: python)
    monkeypatch.setattr(
        pocket_lite_engine.PocketLiteEngine, "_load_request", lambda self: ({"op": "load"}, {})
    )
    return FakeClock()


def write_manifest(tmp_path, engine_id, **extra):
    directory = tmp_path / "packs" / engine_id
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": engine_id,
        "engine_id": engine_id,
        "version": "1",
        "provisioner": engine_id,
        "artifacts": [],
        **extra,
    }
    (directory / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def make(case, clock, **kwargs):
    cls = CASES[case][0]
    return cls(timer_factory=clock.factory, **kwargs)


def speak(engine):
    return engine.synthesize("hi", "English")


@pytest.fixture(params=list(CASES))
def case(request):
    return request.param


# -- effective value -------------------------------------------------------------------------------


def test_the_manifest_value_is_the_effective_value(case, clock, tmp_path):
    write_manifest(tmp_path, CASES[case][1], idle_unload_after=42)

    engine = make(case, clock)

    assert engine.idle_unload_after == 42.0
    assert engine.status()["idle_unload_after"] == 42.0
    assert engine.status()["idle_unload_source"] == "manifest"


def test_a_pack_without_the_field_falls_back_to_the_engine_default(case, clock, tmp_path):
    write_manifest(tmp_path, CASES[case][1])  # an older pack

    engine = make(case, clock)

    assert engine.idle_unload_after == PACK_DEFAULTS[case]
    assert engine.status()["idle_unload_source"] == "default"


def test_no_pack_at_all_also_uses_the_engine_default(case, clock):
    assert make(case, clock).idle_unload_after == PACK_DEFAULTS[case]


def test_the_installer_default_is_what_each_pack_writes(case):
    manifest = {
        "kitten2": lambda: kitten2_pack.build_manifest(kitten2_pack.Target("mlx")),
        "phonon": phonon_pack.build_manifest,
        "kokoro": kokoro_pack.build_manifest,
        "pocket-lite": pocket_lite_pack.build_manifest,
    }[case]()

    assert manifest["idle_unload_after"] == PACK_DEFAULTS[case] > 0
    assert engine_packs.parse_manifest(manifest).idle_unload_after == PACK_DEFAULTS[case]


def test_the_env_override_beats_the_manifest(case, clock, tmp_path, monkeypatch):
    write_manifest(tmp_path, CASES[case][1], idle_unload_after=42)
    monkeypatch.setenv(CASES[case][2], "3")

    engine = make(case, clock)

    assert engine.idle_unload_after == 3.0
    assert engine.status()["idle_unload_source"] == "env"


def test_an_env_zero_keeps_the_engine_loaded_despite_the_manifest(
    case, clock, tmp_path, monkeypatch
):
    write_manifest(tmp_path, CASES[case][1], idle_unload_after=42)
    monkeypatch.setenv(CASES[case][2], "0")
    engine = make(case, clock)

    speak(engine)
    clock.advance(10_000)

    assert FakeProcess.instances[0].is_alive
    assert engine.idle_unload_after == 0.0


@pytest.mark.parametrize("bad", ["soon", "-5", "nan", ""])
def test_a_bad_env_value_is_ignored(case, clock, tmp_path, monkeypatch, bad):
    write_manifest(tmp_path, CASES[case][1], idle_unload_after=42)
    monkeypatch.setenv(CASES[case][2], bad)

    assert make(case, clock).idle_unload_after == 42.0


def test_the_constructor_argument_beats_everything(case, clock, tmp_path, monkeypatch):
    write_manifest(tmp_path, CASES[case][1], idle_unload_after=42)
    monkeypatch.setenv(CASES[case][2], "3")

    engine = make(case, clock, idle_unload_s=7)

    assert engine.idle_unload_after == 7.0
    assert engine.status()["idle_unload_source"] == "argument"


def test_a_manifest_edit_is_picked_up_without_recreating_the_engine(case, clock, tmp_path):
    engine = make(case, clock)
    assert engine.idle_unload_after == PACK_DEFAULTS[case]

    write_manifest(tmp_path, CASES[case][1], idle_unload_after=11)

    assert engine.idle_unload_after == 11.0


# -- unload and reload on a fake clock -------------------------------------------------------------


def test_the_worker_unloads_after_the_idle_period_and_reloads_on_demand(case, clock, tmp_path):
    write_manifest(tmp_path, CASES[case][1], idle_unload_after=60)
    engine = make(case, clock)

    speak(engine)
    first = FakeProcess.instances[0]
    assert engine.status()["state"] == "ready"

    clock.advance(59)
    assert first.is_alive and engine.status()["state"] == "ready"

    clock.advance(2)
    assert first.closed
    assert engine.status()["state"] == "idle"  # not stuck on ready after the unload

    speak(engine)  # the next request reloads
    assert len(FakeProcess.instances) == 2 and FakeProcess.instances[1].is_alive
    assert engine.status()["state"] == "ready"


def test_each_request_restarts_the_idle_period(case, clock, tmp_path):
    write_manifest(tmp_path, CASES[case][1], idle_unload_after=60)
    engine = make(case, clock)

    speak(engine)
    clock.advance(50)
    speak(engine)
    clock.advance(50)  # 100 s since the first request, 50 s since the second

    assert FakeProcess.instances[0].is_alive
    assert clock.armed == 1  # re-arming replaced the earlier timer instead of stacking
    clock.advance(11)
    assert FakeProcess.instances[0].closed


def test_a_zero_manifest_value_never_unloads(case, clock, tmp_path):
    write_manifest(tmp_path, CASES[case][1], idle_unload_after=0)
    engine = make(case, clock)

    speak(engine)
    clock.advance(1_000_000)

    assert FakeProcess.instances[0].is_alive
    assert engine.status()["state"] == "ready"
    assert clock.armed == 0


def test_a_pack_without_the_field_unloads_at_the_engine_default(case, clock, tmp_path):
    write_manifest(tmp_path, CASES[case][1])
    engine = make(case, clock)

    speak(engine)
    clock.advance(PACK_DEFAULTS[case] - 1)
    assert FakeProcess.instances[0].is_alive
    clock.advance(2)

    assert FakeProcess.instances[0].closed
    assert engine.status()["state"] == "idle"


def test_unloading_twice_is_harmless(case, clock, tmp_path):
    write_manifest(tmp_path, CASES[case][1], idle_unload_after=60)
    engine = make(case, clock)
    speak(engine)

    engine.unload()
    engine.unload()

    assert engine.status()["state"] == "idle"


@pytest.mark.parametrize("case", ["phonon", "pocket-lite"])
def test_an_idle_timer_cannot_kill_a_worker_that_is_streaming(case, clock, tmp_path):
    write_manifest(tmp_path, CASES[case][1], idle_unload_after=60)
    engine = make(case, clock)
    speak(engine)  # arms a timer
    first = FakeProcess.instances[0]

    STREAM_HOOKS.append(lambda: clock.advance(120))  # the period elapses mid-stream
    chunks = list(engine.stream_pcm("hi", "English"))

    assert len(chunks) == 2
    assert not first.closed
    clock.advance(61)  # idle again after the stream ends
    assert first.closed
    assert engine.status()["state"] == "idle"

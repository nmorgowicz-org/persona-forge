"""Engine ``warming`` state: loading -> warming -> ready, and the retryable 503 while it lasts.

A stub worker blocks inside ``load`` and ``warmup`` on events the test controls, so each state is
observed for real through ``GET /engines`` rather than inferred.
"""

from __future__ import annotations

import io
import threading
import time
import wave

import pytest

from persona_forge import kitten2_engine, pack_preset_engine, phonon_engine, speech_engines


def _wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x10" * 240)
    return buffer.getvalue()


class Gates:
    """Events that hold the stub worker inside ``load`` / ``warmup`` until the test releases them."""

    def __init__(self, *, warmup: bool = True) -> None:
        self.load = threading.Event()
        self.warm = threading.Event()
        self.warmup = warmup
        self.requests: list[dict] = []
        self.fail_load: str | None = None


def _worker_class(gates: Gates):
    class SlowWorker:
        def __init__(self, command, **_kwargs):
            self.is_alive = True

        def start(self):
            pass

        def request(self, payload, *, timeout=None):
            gates.requests.append(dict(payload))
            op = payload["op"]
            if op == "load":
                assert gates.load.wait(10), "test never released load"
                if gates.fail_load:
                    raise pack_preset_engine.PackProcessError(gates.fail_load)
                return {"ok": True, "mode": None, "warmup_pending": gates.warmup}
            if op == "warmup":
                assert gates.warm.wait(10), "test never released warmup"
                return {"ok": True, "mode": "compiled", "fast_mode_issue": None}
            return {"ok": True}

        def synthesize(self, payload):
            gates.requests.append({"op": "synthesize", **payload})
            return _wav()

        def stream(self, payload, *, timeout=None):
            gates.requests.append({"op": "stream", **payload})
            yield b"\x01\x00" * 50

        def close(self):
            self.is_alive = False

    return SlowWorker


@pytest.fixture
def gates():
    value = Gates()
    yield value
    value.load.set()  # never leave a load thread parked behind a failed assertion
    value.warm.set()


@pytest.fixture
def kitten(monkeypatch, tmp_path, gates):
    python = tmp_path / "python"
    python.write_text("")
    monkeypatch.setenv("KITTEN2_PYTHON", str(python))
    monkeypatch.setattr(kitten2_engine, "PackProcess", _worker_class(gates))
    engine = kitten2_engine.Kitten2Engine(idle_unload_s=0)
    monkeypatch.setitem(speech_engines.ADAPTERS, "kitten2", engine)
    return engine


@pytest.fixture
def phonon(monkeypatch, tmp_path, gates):
    python = tmp_path / "python"
    python.write_text("")
    monkeypatch.setenv("PHONON_PYTHON", str(python))
    monkeypatch.setattr(pack_preset_engine, "PackProcess", _worker_class(gates))
    engine = phonon_engine.PhononEngine(idle_unload_s=0)
    monkeypatch.setitem(speech_engines.ADAPTERS, "phonon-31m", engine)
    return engine


@pytest.fixture
def serving(app_module, rt, monkeypatch):
    monkeypatch.setattr(rt, "TTS_BACKEND", "pocket_tts")
    monkeypatch.setattr(app_module, "_generation_ready", lambda: True)
    monkeypatch.setattr(rt, "_service_started", True)


def _status(client, engine_id):
    cards = {c["id"]: c for c in client.get("/engines").get_json()["engines"]}
    return cards[engine_id]["load_status"]


def _wait_for(predicate, what, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


def _speak(client, model, **extra):
    return client.post(
        "/v1/audio/speech",
        json={"model": model, "input": "hello", "response_format": "wav", **extra},
    )


# -- state transitions through GET /engines --------------------------------------------------------


def test_a_slow_loading_worker_shows_loading_then_warming_then_ready(client, kitten, gates):
    assert _status(client, "kitten2")["state"] == "idle"

    assert kitten.recheck() is True
    _wait_for(lambda: _status(client, "kitten2")["state"] == "loading", "loading")
    loading = _status(client, "kitten2")
    assert loading["elapsed_s"] is not None and loading["estimated_s"] is None

    gates.load.set()
    _wait_for(lambda: _status(client, "kitten2")["state"] == "warming", "warming")
    warming = _status(client, "kitten2")
    assert warming["elapsed_s"] is not None
    assert warming["estimated_s"] == kitten2_engine.WARMUP_ESTIMATE_S
    assert warming["mode"] is None  # the speed mode is only known once warm-up has run

    gates.warm.set()
    _wait_for(lambda: _status(client, "kitten2")["state"] == "ready", "ready")
    ready = _status(client, "kitten2")
    assert ready["mode"] == "compiled" and ready["elapsed_s"] is None
    assert [r["op"] for r in gates.requests] == ["load", "warmup"]


def test_load_is_sent_without_warmup_so_the_adapter_can_report_warming_separately(
    client, kitten, gates
):
    gates.load.set()
    gates.warm.set()
    kitten.recheck()
    _wait_for(lambda: _status(client, "kitten2")["state"] == "ready", "ready")

    assert gates.requests[0] == {"op": "load", "warmup": False}


def test_an_engine_without_a_warmup_step_goes_straight_from_loading_to_ready(
    client, phonon, gates
):
    gates.warmup = False

    phonon.recheck()
    _wait_for(lambda: _status(client, "phonon-31m")["state"] == "loading", "loading")
    gates.load.set()
    _wait_for(lambda: _status(client, "phonon-31m")["state"] == "ready", "ready")

    assert [r["op"] for r in gates.requests] == ["load"]


def test_a_preset_engine_whose_worker_asks_for_warmup_reports_warming(client, phonon, gates):
    phonon.recheck()
    gates.load.set()
    _wait_for(lambda: _status(client, "phonon-31m")["state"] == "warming", "warming")

    gates.warm.set()
    _wait_for(lambda: _status(client, "phonon-31m")["state"] == "ready", "ready")
    assert [r["op"] for r in gates.requests] == ["load", "warmup"]


def test_a_failed_load_reports_the_error_and_a_later_request_retries(client, kitten, gates):
    gates.fail_load = "worker exploded"
    gates.load.set()
    kitten.recheck()
    _wait_for(lambda: _status(client, "kitten2")["state"] == "error", "error")
    assert _status(client, "kitten2")["error"] == "worker exploded"

    gates.fail_load = None
    gates.warm.set()
    assert kitten.recheck() is True
    _wait_for(lambda: _status(client, "kitten2")["state"] == "ready", "ready")
    assert _status(client, "kitten2")["error"] is None


def test_unloading_returns_the_engine_to_idle(client, kitten, gates):
    gates.load.set()
    gates.warm.set()
    kitten.recheck()
    _wait_for(lambda: _status(client, "kitten2")["state"] == "ready", "ready")

    kitten.unload()

    assert _status(client, "kitten2")["state"] == "idle"


# -- the retryable 503 -----------------------------------------------------------------------------


def test_a_request_while_warming_gets_a_documented_503_with_retry_after(
    client, serving, kitten, gates, monkeypatch
):
    monkeypatch.setenv("ENGINE_WARM_WAIT_S", "0")
    kitten.recheck()
    gates.load.set()
    _wait_for(lambda: _status(client, "kitten2")["state"] == "warming", "warming")

    response = _speak(client, "kitten2", voice="Bruno")

    assert response.status_code == 503
    assert int(response.headers["Retry-After"]) >= 1
    error = response.get_json()["error"]
    assert error["type"] == "api_error" and error["code"] == "engine_warming"
    assert "Kitten TTS 2" in error["message"] and "warming up" in error["message"]
    assert [r["op"] for r in gates.requests if r["op"] == "synthesize"] == []  # never queued


def test_a_request_that_starts_a_cold_load_returns_503_and_a_retry_succeeds(
    client, serving, kitten, gates, monkeypatch
):
    monkeypatch.setenv("ENGINE_WARM_WAIT_S", "0")

    first = _speak(client, "kitten2", voice="Bruno")

    assert first.status_code == 503 and first.headers["Retry-After"]
    assert first.get_json()["error"]["code"] == "engine_warming"
    assert "loading" in first.get_json()["error"]["message"]
    gates.load.set()
    gates.warm.set()
    _wait_for(lambda: _status(client, "kitten2")["state"] == "ready", "ready")
    second = _speak(client, "kitten2", voice="Bruno")
    assert second.status_code == 200


def test_a_short_warmup_is_waited_out_instead_of_failing_the_request(
    client, serving, kitten, gates, monkeypatch
):
    monkeypatch.setenv("ENGINE_WARM_WAIT_S", "5")
    threading.Timer(0.2, lambda: (gates.load.set(), gates.warm.set())).start()

    response = _speak(client, "kitten2", voice="Bruno")

    assert response.status_code == 200
    assert [r["op"] for r in gates.requests] == ["load", "warmup", "synthesize"]


def test_the_wait_is_bounded_so_a_long_warmup_still_answers_503(
    client, serving, kitten, gates, monkeypatch
):
    monkeypatch.setenv("ENGINE_WARM_WAIT_S", "0.2")

    started = time.monotonic()
    response = _speak(client, "kitten2", voice="Bruno")

    assert response.status_code == 503 and time.monotonic() - started < 3


def test_concurrent_requests_share_one_load(client, serving, kitten, gates, monkeypatch):
    monkeypatch.setenv("ENGINE_WARM_WAIT_S", "0")

    codes = [_speak(client, "kitten2", voice="Bruno").status_code for _ in range(3)]
    gates.load.set()
    gates.warm.set()
    _wait_for(lambda: _status(client, "kitten2")["state"] == "ready", "ready")

    assert codes == [503, 503, 503]
    assert [r["op"] for r in gates.requests].count("load") == 1


def test_a_load_that_fails_answers_503_with_the_reason_and_no_retry_after(
    client, serving, kitten, gates, monkeypatch
):
    monkeypatch.setenv("ENGINE_WARM_WAIT_S", "5")
    gates.fail_load = "worker exploded"
    gates.load.set()

    response = _speak(client, "kitten2", voice="Bruno")

    assert response.status_code == 503
    assert "Retry-After" not in response.headers
    assert "worker exploded" in response.get_json()["error"]["message"]
    assert response.get_json()["error"]["code"] != "engine_warming"


def test_the_streaming_pcm_path_also_answers_503_while_warming(
    client, serving, phonon, gates, monkeypatch
):
    monkeypatch.setenv("ENGINE_WARM_WAIT_S", "0")

    response = _speak(client, "phonon-31m", voice="phonon:Zoey", response_format="pcm")

    assert response.status_code == 503
    assert response.headers["Retry-After"]
    assert response.get_json()["error"]["code"] == "engine_warming"
    assert "Phonon 31M" in response.get_json()["error"]["message"]


def test_streaming_pcm_serves_once_the_engine_is_ready(client, serving, phonon, gates, monkeypatch):
    monkeypatch.setenv("ENGINE_WARM_WAIT_S", "5")
    gates.warmup = False
    gates.load.set()

    response = _speak(client, "phonon-31m", voice="phonon:Zoey", response_format="pcm")

    assert response.status_code == 200 and response.content_type == "audio/pcm"


def test_a_missing_pack_is_not_reported_as_warming(client, serving, monkeypatch, tmp_path):
    monkeypatch.delenv("KITTEN2_PYTHON", raising=False)
    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))
    monkeypatch.setitem(speech_engines.ADAPTERS, "kitten2", kitten2_engine.Kitten2Engine(0))

    response = _speak(client, "kitten2")

    assert response.status_code == 503 and "Retry-After" not in response.headers
    message = response.get_json()["error"]["message"]
    assert "not installed" in message
    # Journey 5: the error must name the exact action — install it, in the page that hosts
    # the Speech engines card (Runtime), not a stale Settings reference.
    assert "Runtime → Speech engines" in message
    assert _status(client, "kitten2")["state"] == "idle"


def test_the_benchmark_waits_through_warming_instead_of_failing(
    client, serving, kitten, gates, monkeypatch
):
    from persona_forge import hardware_fit

    monkeypatch.setenv("ENGINE_WARM_WAIT_S", "0")
    monkeypatch.setattr(hardware_fit, "save_result", lambda *_a, **_k: None)
    monkeypatch.setattr(kitten2_engine, "list_presets", lambda root=None: ["Bruno"])
    threading.Timer(0.3, lambda: (gates.load.set(), gates.warm.set())).start()

    response = client.post("/engines/kitten2/benchmark")

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["benchmark"]["cold_seconds"] >= 0.25

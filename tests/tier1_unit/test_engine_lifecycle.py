"""The engine load state machine: idle -> loading -> warming -> ready, or error."""

from __future__ import annotations

import threading

from persona_forge.engine_lifecycle import LoadTracker


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_a_new_tracker_is_idle_and_reports_no_progress():
    tracker = LoadTracker()

    assert tracker.snapshot() == {
        "state": "idle", "error": None, "elapsed_s": None, "estimated_s": None
    }


def test_progress_is_reported_only_while_loading_or_warming():
    clock = Clock()
    tracker = LoadTracker(estimates={"warming": 35.0}, clock=clock)

    tracker.enter("loading")
    clock.now += 2.5
    assert tracker.snapshot() == {
        "state": "loading", "error": None, "elapsed_s": 2.5, "estimated_s": None
    }

    tracker.enter("warming")
    clock.now += 10.0
    assert tracker.snapshot() == {
        "state": "warming", "error": None, "elapsed_s": 10.0, "estimated_s": 35.0
    }

    tracker.enter("ready")
    assert tracker.snapshot() == {
        "state": "ready", "error": None, "elapsed_s": None, "estimated_s": None
    }


def test_re_entering_the_same_state_does_not_restart_its_clock():
    clock = Clock()
    tracker = LoadTracker(clock=clock)
    tracker.enter("loading")
    clock.now += 4.0

    tracker.enter("loading")

    assert tracker.snapshot()["elapsed_s"] == 4.0


def test_claim_load_is_granted_once_while_a_load_is_in_flight():
    tracker = LoadTracker()

    assert tracker.claim_load() is True
    assert tracker.state == "loading"
    assert tracker.claim_load() is False
    tracker.enter("warming")
    assert tracker.claim_load() is False
    tracker.enter("ready")
    assert tracker.claim_load() is True  # a dead worker is reloaded


def test_claim_load_clears_a_previous_error():
    tracker = LoadTracker()
    tracker.fail("boom")

    assert tracker.claim_load() is True
    assert tracker.snapshot()["error"] is None


def test_fail_records_the_message_and_settles():
    tracker = LoadTracker()
    tracker.enter("loading")

    tracker.fail("pack is broken")

    assert tracker.snapshot() == {
        "state": "error", "error": "pack is broken", "elapsed_s": None, "estimated_s": None
    }


def test_wait_settled_returns_immediately_when_nothing_is_in_flight():
    assert LoadTracker().wait_settled(0.0) == "idle"


def test_wait_settled_times_out_while_warming():
    tracker = LoadTracker()
    tracker.enter("warming")

    assert tracker.wait_settled(0.05) == "warming"


def test_wait_settled_wakes_when_the_load_finishes():
    tracker = LoadTracker()
    tracker.enter("loading")
    threading.Timer(0.05, lambda: tracker.enter("ready")).start()

    assert tracker.wait_settled(5.0) == "ready"


def test_retry_after_uses_the_remaining_estimate_within_bounds():
    clock = Clock()
    tracker = LoadTracker(estimates={"warming": 35.0}, clock=clock)
    tracker.enter("warming")

    clock.now += 5.0
    assert tracker.retry_after_s() == 30
    clock.now += 28.0
    assert tracker.retry_after_s() == 2  # 2 s remain
    clock.now += 100.0
    assert tracker.retry_after_s() == 5  # overran the estimate: poll gently


def test_retry_after_without_an_estimate_is_a_gentle_default():
    tracker = LoadTracker()
    tracker.enter("loading")

    assert tracker.retry_after_s() == 5

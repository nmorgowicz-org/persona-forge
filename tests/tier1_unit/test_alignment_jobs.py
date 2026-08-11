"""Phase 2 gate: alignment jobs serialize + obey cancellation / idle-unload."""

from __future__ import annotations

import threading
import time

from persona_forge.alignment_jobs import AlignmentJobManager


def _wait_status(mgr, job_id, status, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = mgr.get(job_id)
        if job and job["status"] == status:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job never reached {status}: {mgr.get(job_id)}")


def test_completes_and_returns_result():
    mgr = AlignmentJobManager(lambda vid, cancel: {"voice": vid, "boundaries": []})
    job = mgr.submit("vd_a")
    assert job["status"] in ("queued", "running", "completed")
    done = _wait_status(mgr, job["job_id"], "completed")
    assert done["result"] == {"voice": "vd_a", "boundaries": []}


def test_runs_are_serialized():
    concurrent = 0
    peak = 0
    lock = threading.Lock()

    def runner(vid, cancel):
        nonlocal concurrent, peak
        with lock:
            concurrent += 1
            peak = max(peak, concurrent)
        time.sleep(0.05)
        with lock:
            concurrent -= 1
        return {"v": vid}

    mgr = AlignmentJobManager(runner)
    ids = [mgr.submit(f"vd_{i}")["job_id"] for i in range(4)]
    for jid in ids:
        _wait_status(mgr, jid, "completed")
    assert peak == 1  # never two alignments at once


def test_cancellation_stops_before_completion():
    started = threading.Event()

    def runner(vid, cancel):
        started.set()
        for _ in range(200):
            if cancel.is_set():
                return None
            time.sleep(0.01)
        return {"v": vid}

    mgr = AlignmentJobManager(runner)
    job = mgr.submit("vd_c")
    assert started.wait(1.0)
    assert mgr.cancel(job["job_id"])
    done = _wait_status(mgr, job["job_id"], "cancelled")
    assert done["status"] == "cancelled"


def test_idle_unload_releases_after_drain():
    unloaded = threading.Event()
    mgr = AlignmentJobManager(
        lambda vid, cancel: {"v": vid},
        idle_unload_seconds=0.05,
        unload=unloaded.set,
    )
    jid = mgr.submit("vd_u")["job_id"]
    _wait_status(mgr, jid, "completed")
    assert unloaded.wait(1.0), "idle-unload should fire once jobs drain"


def test_failed_runner_surfaces_error():
    def runner(vid, cancel):
        raise RuntimeError("boom")

    mgr = AlignmentJobManager(runner)
    jid = mgr.submit("vd_f")["job_id"]
    done = _wait_status(mgr, jid, "failed")
    assert "boom" in done["error"]


def test_unknown_job_id_returns_none():
    mgr = AlignmentJobManager(lambda vid, cancel: {})
    assert mgr.get("nope") is None
    assert mgr.cancel("nope") is False


def test_latency_budget_is_recorded_and_p95_fails_closed():
    timer_values = iter([10.0, 16.0])
    mgr = AlignmentJobManager(
        lambda vid, cancel: {"v": vid},
        latency_budget_seconds=5.0,
        timer=lambda: next(timer_values),
    )
    jid = mgr.submit("vd_slow")["job_id"]
    done = _wait_status(mgr, jid, "completed")
    assert done["duration_seconds"] == 6.0
    assert done["latency_budget_seconds"] == 5.0
    assert done["within_latency_budget"] is False
    assert mgr.performance() == {
        "sample_count": 1,
        "window_size": 100,
        "budget_seconds": 5.0,
        "p50_seconds": 6.0,
        "p95_seconds": 6.0,
        "within_budget": False,
        "breach_count": 1,
    }


def test_empty_performance_window_is_healthy_but_unmeasured():
    perf = AlignmentJobManager(lambda vid, cancel: {}).performance()
    assert perf["sample_count"] == 0
    assert perf["p95_seconds"] is None
    assert perf["within_budget"] is True

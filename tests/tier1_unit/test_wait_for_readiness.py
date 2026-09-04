"""Tests for the Phase 9 shared readiness harness (scripts/wait_for_readiness.py)."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from scripts.wait_for_readiness import ReadinessError, wait_for_readiness


class FakeProcess:
    """Stands in for subprocess.Popen: caller only needs .poll()."""

    def __init__(self, exit_code: int | None = None):
        self._exit_code = exit_code

    def poll(self) -> int | None:
        return self._exit_code


def _patch_health_sequence(monkeypatch: pytest.MonkeyPatch, sequence: list[dict[str, Any] | None]):
    calls = {"n": 0}

    def fake_fetch(url: str, timeout_seconds: float = 5.0):
        idx = min(calls["n"], len(sequence) - 1)
        calls["n"] += 1
        return sequence[idx]

    monkeypatch.setattr("scripts.wait_for_readiness._fetch_health", fake_fetch)
    return calls


class TestWaitForReadiness:
    def test_ready_immediately(self, monkeypatch: pytest.MonkeyPatch):
        _patch_health_sequence(
            monkeypatch,
            [{"status": "ok", "service_started": True, "resolved_backend": "pocket_tts"}],
        )
        result = wait_for_readiness(
            FakeProcess(), "http://fake/health", deadline_seconds=5, poll_interval_seconds=0
        )
        assert result.ready is True
        assert result.health["service_started"] is True

    def test_waits_out_swap_in_progress(self, monkeypatch: pytest.MonkeyPatch):
        _patch_health_sequence(
            monkeypatch,
            [
                {"status": "ok", "service_started": True, "swap_in_progress": True},
                {"status": "ok", "service_started": True, "swap_in_progress": True},
                {"status": "ok", "service_started": True, "swap_in_progress": False},
            ],
        )
        result = wait_for_readiness(
            FakeProcess(), "http://fake/health", deadline_seconds=5, poll_interval_seconds=0
        )
        assert result.ready is True
        assert result.health["swap_in_progress"] is False

    def test_waits_out_reconfig_in_progress(self, monkeypatch: pytest.MonkeyPatch):
        _patch_health_sequence(
            monkeypatch,
            [
                {"status": "ok", "service_started": True, "reconfig_in_progress": True},
                {"status": "ok", "service_started": True, "reconfig_in_progress": False},
            ],
        )
        result = wait_for_readiness(
            FakeProcess(), "http://fake/health", deadline_seconds=5, poll_interval_seconds=0
        )
        assert result.ready is True

    def test_does_not_require_model_loaded(self, monkeypatch: pytest.MonkeyPatch):
        _patch_health_sequence(
            monkeypatch,
            [{"status": "ok", "service_started": True, "model_loaded": False}],
        )
        result = wait_for_readiness(
            FakeProcess(), "http://fake/health", deadline_seconds=5, poll_interval_seconds=0
        )
        assert result.ready is True

    def test_checks_expected_backend(self, monkeypatch: pytest.MonkeyPatch):
        _patch_health_sequence(
            monkeypatch,
            [
                {"status": "ok", "service_started": True, "resolved_backend": "openvino"},
                {"status": "ok", "service_started": True, "resolved_backend": "pocket_tts"},
            ],
        )
        result = wait_for_readiness(
            FakeProcess(),
            "http://fake/health",
            deadline_seconds=5,
            poll_interval_seconds=0,
            expected_backend="pocket_tts",
        )
        assert result.ready is True
        assert result.health["resolved_backend"] == "pocket_tts"

    def test_raises_on_status_error(self, monkeypatch: pytest.MonkeyPatch):
        _patch_health_sequence(
            monkeypatch,
            [{"status": "error", "service_started": False, "error": "boom"}],
        )
        with pytest.raises(ReadinessError, match="status=error"):
            wait_for_readiness(
                FakeProcess(), "http://fake/health", deadline_seconds=5, poll_interval_seconds=0
            )

    def test_raises_when_child_exits_early(self, monkeypatch: pytest.MonkeyPatch):
        _patch_health_sequence(monkeypatch, [None])
        with pytest.raises(ReadinessError, match="exited early"):
            wait_for_readiness(
                FakeProcess(exit_code=1),
                "http://fake/health",
                deadline_seconds=5,
                poll_interval_seconds=0,
            )

    def test_raises_on_deadline_expiry(self, monkeypatch: pytest.MonkeyPatch):
        _patch_health_sequence(monkeypatch, [None])
        with pytest.raises(ReadinessError, match="deadline"):
            wait_for_readiness(
                FakeProcess(), "http://fake/health", deadline_seconds=0, poll_interval_seconds=0
            )

    def test_handles_malformed_response_then_recovers(self, monkeypatch: pytest.MonkeyPatch):
        _patch_health_sequence(
            monkeypatch,
            [None, {"status": "ok", "service_started": True}],
        )
        result = wait_for_readiness(
            FakeProcess(), "http://fake/health", deadline_seconds=5, poll_interval_seconds=0
        )
        assert result.ready is True


class TestRunAndWait:
    def test_terminates_process_on_readiness_error(self, monkeypatch: pytest.MonkeyPatch):
        from scripts.wait_for_readiness import run_and_wait

        _patch_health_sequence(monkeypatch, [None])

        terminated = {"called": False}
        killed = {"called": False}

        class FakePopen:
            def __init__(self, *a, **k):
                self._exit_code = None

            def poll(self):
                return self._exit_code

            def terminate(self):
                terminated["called"] = True
                self._exit_code = -15

            def wait(self, timeout=None):
                return self._exit_code

            def kill(self):
                killed["called"] = True

        monkeypatch.setattr(subprocess, "Popen", FakePopen)

        with pytest.raises(ReadinessError):
            run_and_wait(["fake-cmd"], "http://fake/health", deadline_seconds=0, poll_interval_seconds=0)

        assert terminated["called"] is True

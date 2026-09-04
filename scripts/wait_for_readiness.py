"""Shared readiness harness for Phase 9 hardware gates
(docs/plans/20260829-no_more_docker_requirement.md, Phase 9 "Shared readiness harness").

Polls a running Persona Forge process's ``/health`` endpoint until it reports semantic
readiness, or fails fast on a crashed child, a malformed/error response, or a deadline.
Used identically by Gate 9A (macOS), Gate 9B (Windows), and Gate 9C (docker-agent container) so
every hardware receipt is produced by the same code, not per-platform ad hoc polling.

Not tied to any one launch mechanism: pass an already-running ``subprocess.Popen`` (native
`persona-forge serve`, or a `docker exec`'d health check target) plus the URL to poll.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


class ReadinessError(RuntimeError):
    """Raised when the child process exits early, the deadline expires, or health reports an error."""


@dataclass
class ReadinessResult:
    ready: bool
    elapsed_seconds: float
    health: dict[str, Any] | None
    log: list[str] = field(default_factory=list)


def _fetch_health(url: str, timeout_seconds: float = 5.0) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            body = response.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _is_semantically_ready(health: dict[str, Any], expected_backend: str | None) -> bool:
    if health.get("status") == "error":
        raise ReadinessError(f"health reported status=error: {health.get('error')!r}")
    if not health.get("service_started"):
        return False
    if health.get("swap_in_progress") or health.get("reconfig_in_progress"):
        return False
    if expected_backend is not None and health.get("resolved_backend") != expected_backend:
        return False
    return True


def wait_for_readiness(
    process: subprocess.Popen,
    url: str,
    *,
    deadline_seconds: float = 300.0,
    poll_interval_seconds: float = 1.0,
    expected_backend: str | None = None,
) -> ReadinessResult:
    """Poll ``url`` (a Persona Forge ``/health`` endpoint) until semantic readiness.

    Readiness requires ``service_started=true``, the expected backend active (when given), and
    no swap/reconfiguration underway (Phase 9 acceptance rule 2). Fails on child exit, a
    malformed/error response persisting past the deadline, or the deadline itself (rule 1).
    ``model_loaded`` is recorded but never required — idle-unload can make it false later
    without meaning the service stopped being ready (rule 3).
    """
    start = time.monotonic()
    log: list[str] = []
    last_health: dict[str, Any] | None = None

    while True:
        elapsed = time.monotonic() - start

        exit_code = process.poll()
        if exit_code is not None:
            log.append(f"[{elapsed:.1f}s] child exited early with code {exit_code}")
            raise ReadinessError(f"child process exited early with code {exit_code}")

        health = _fetch_health(url)
        if health is not None:
            last_health = health
            log.append(f"[{elapsed:.1f}s] health: {json.dumps(health, default=str)[:500]}")
            if _is_semantically_ready(health, expected_backend):
                return ReadinessResult(
                    ready=True, elapsed_seconds=elapsed, health=health, log=log
                )
        else:
            log.append(f"[{elapsed:.1f}s] health endpoint unreachable or malformed response")

        if elapsed >= deadline_seconds:
            raise ReadinessError(
                f"readiness deadline ({deadline_seconds}s) expired; last health={last_health!r}"
            )

        time.sleep(poll_interval_seconds)


def run_and_wait(
    command: list[str],
    url: str,
    *,
    deadline_seconds: float = 300.0,
    poll_interval_seconds: float = 1.0,
    expected_backend: str | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> tuple[subprocess.Popen, ReadinessResult]:
    """Launch ``command``, wait for readiness, and return ``(process, result)`` still running.

    Callers own shutdown: terminate, wait, then kill only on timeout, all inside ``finally``
    (rule 4) — this function deliberately does not tear the process down so the caller can run
    its generation smoke against it first.
    """
    process = subprocess.Popen(command, env=env, cwd=cwd)
    try:
        result = wait_for_readiness(
            process,
            url,
            deadline_seconds=deadline_seconds,
            poll_interval_seconds=poll_interval_seconds,
            expected_backend=expected_backend,
        )
    except ReadinessError:
        _terminate(process)
        raise
    return process, result


def _terminate(process: subprocess.Popen, *, timeout_seconds: float = 10.0) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout_seconds)

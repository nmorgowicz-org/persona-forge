"""Managed pack worker process transport (Phase C3b)."""

from __future__ import annotations

import errno
import os
import signal
import sys
from pathlib import Path

import pytest

from persona_forge import pack_process
from persona_forge.pack_process import PackProcess, PackProcessError

WORKER_SOURCE = """
import base64
import json
import sys
import time

for line in sys.stdin:
    message = json.loads(line)
    op = message.get("op")
    if op == "ping":
        print(json.dumps({"ok": True}), flush=True)
    elif op == "synthesize":
        payload = base64.b64encode(b"pcm").decode()
        print(json.dumps({"ok": True, "audio_b64": payload}), flush=True)
    elif op == "fail":
        print(json.dumps({"ok": False, "error": "boom"}), flush=True)
    elif op == "sleep":
        time.sleep(5)
        print(json.dumps({"ok": True}), flush=True)
"""


@pytest.fixture()
def worker_command(tmp_path: Path) -> list[str]:
    script = tmp_path / "worker.py"
    script.write_text(WORKER_SOURCE, encoding="utf-8")
    return [sys.executable, str(script)]


def test_ping_and_synthesize(worker_command):
    with PackProcess(worker_command, request_timeout=5) as worker:
        worker.ping()

        assert worker.synthesize({}) == b"pcm"
        assert worker.is_alive is True


def test_worker_error_is_raised(worker_command):
    with PackProcess(worker_command, request_timeout=5) as worker:
        with pytest.raises(PackProcessError, match="boom"):
            worker.request({"op": "fail"})


def test_timeout_kills_the_worker(worker_command):
    worker = PackProcess(worker_command, request_timeout=0.2)
    worker.start()

    with pytest.raises(PackProcessError, match="timed out"):
        worker.request({"op": "sleep"})

    assert worker.is_alive is False


@pytest.mark.skipif(sys.platform == "win32", reason="EPERM on os.kill is POSIX semantics; Windows uses TerminateProcess")
def test_kill_survives_container_pid_reuse_eperm(worker_command, monkeypatch):
    """ARC containers recycle pids, so SIGTERM can raise EPERM instead of ESRCH.

    CPython raises PermissionError only when kill() answers EPERM for a pid we created
    ourselves - the pid was reused by a process we may not signal. A wedged-but-live worker
    still gets SIGKILL after the SIGTERM grace, so only the gone signal is tolerated.
    """
    real_kill = os.kill

    def fake_kill(pid: int, sig: int) -> None:
        if sig == int(signal.SIGTERM):
            # The child died between poll() and the signal, and its pid was recycled.
            real_kill(pid, int(signal.SIGKILL))
            raise PermissionError(errno.EPERM, "Permission denied")
        real_kill(pid, sig)

    monkeypatch.setattr(os, "kill", fake_kill)
    worker = PackProcess(worker_command, request_timeout=5)
    worker.start()
    worker.kill()
    assert worker.is_alive is False


def test_kill_never_raises_when_signals_are_refused(worker_command, monkeypatch):
    """ARC containers answered EPERM for the worker's own pid, so neither signal lands.

    ``kill`` runs on the request path: an exception here replaced the caller's own
    "timed out" report with a transport-level PermissionError.
    """
    monkeypatch.setattr(pack_process, "_signal_child", lambda process, sig: False)
    worker = pack_process.PackProcess(worker_command, request_timeout=0.2)
    worker.start()

    with pytest.raises(PackProcessError, match="timed out"):
        worker.request({"op": "sleep"})

    assert worker.is_alive is False


def test_kill_abandons_a_worker_whose_death_cannot_be_confirmed(worker_command, monkeypatch):
    """Signals can be accepted while ``waitpid`` still answers "running" for a recycled pid.

    The transport must stop blocking and stop claiming the worker is usable, instead of
    surfacing subprocess.TimeoutExpired from the teardown of an unrelated request.
    """
    monkeypatch.setattr(pack_process, "_reap", lambda process, timeout: False)
    worker = pack_process.PackProcess(worker_command, request_timeout=5)
    worker.start()

    worker.kill()

    assert worker.is_alive is False


def test_close_is_idempotent(worker_command):
    worker = PackProcess(worker_command, request_timeout=5)
    worker.start()
    worker.close()
    worker.close()

    assert worker.is_alive is False


def test_missing_binary_is_reported(tmp_path):
    with pytest.raises(PackProcessError, match="could not start worker"):
        PackProcess([str(tmp_path / "does-not-exist")]).start()

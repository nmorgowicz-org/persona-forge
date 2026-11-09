"""Managed child process for pack engines (Phase C3b).

Every non-Pocket engine runs in its own process so its dependencies, crashes and memory
cannot reach the web worker. This module is the transport only: newline-delimited JSON over
stdin/stdout, one request in flight, health ping, bounded waits and a hard kill on timeout.
Engine-specific work lives in the worker, not here.

The engine adapters (``PackPresetEngine`` and the Kitten 2 adapter) each own at most one
``PackProcess``, started lazily on the first request that needs the engine and closed again by
idle unload. Keeping the transport separate means an adapter adds a protocol, not a process
manager.
"""

from __future__ import annotations

import base64
import errno
import json
import os
import queue
import signal
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from persona_forge import pack_logs

# ESRCH/EPERM from a signal on our own child both mean "this transport cannot end it": the
# process is gone, or the sandbox refuses signal delivery outright (a container AppArmor
# profile that mediates signals but allows none still answers kill(pid, 0) with success).
# Neither case improves by signalling again, and a repeated signal can only reach whatever
# process owns the pid now.
_SIGNAL_GONE = (errno.ESRCH, errno.EPERM)

# Teardown bounds. SIGTERM gets the graceful window; SIGKILL only needs long enough for the
# kernel to reap an already-dead child, so a hostile runner cannot stall the request path twice.
_SIGTERM_GRACE = 5.0
_SIGKILL_GRACE = 2.0


def _signal_child(process: subprocess.Popen[str], sig: signal.Signals) -> bool:
    """Send ``sig`` to the child; False when it is already gone, never raising for a dead one."""
    try:
        process.send_signal(sig)
    except OSError as exc:
        return exc.errno not in _SIGNAL_GONE
    return True


def _force_kill(process: subprocess.Popen[str]) -> bool:
    """Force-terminate the child; False when it is already gone.

    Windows has no ``SIGKILL``, so escalation there goes through ``Popen.kill()``
    (``TerminateProcess``). Never raises for a dead or unsignalable child.
    """
    sigkill = getattr(signal, "SIGKILL", None)
    if sigkill is None:
        try:
            process.kill()
        except OSError as exc:
            return exc.errno not in _SIGNAL_GONE
        return True
    return _signal_child(process, sigkill)


def _reap(process: subprocess.Popen[str], timeout: float) -> bool:
    """Wait for the child to exit; False when it is still running after ``timeout``.

    kill() is called from the request path, which must report its own timeout; a runner that
    refuses the signal (or whose pid namespace reuses the pid) must not surface as an unrelated
    PermissionError/TimeoutExpired from the transport.
    """
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    return True


class PackProcessError(RuntimeError):
    """The worker failed, exited, or did not answer in time."""


class PackProcess:
    """A single-worker subprocess speaking one-JSON-object-per-line.

    Requests are serialized: the app already serves one generation at a time per engine, and a
    lock makes request/response pairing unambiguous. Timeouts kill the process instead of leaving
    a wedged worker behind.
    """

    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        request_timeout: float = 120.0,
        log: Callable[[str], None] | None = None,
    ) -> None:
        # ``log`` receives each stderr line (already redacted) for the card's "View logs".
        self._log = log
        self._command = list(command)
        self._cwd = str(cwd) if cwd is not None else None
        self._env = dict(os.environ)
        if env:
            self._env.update(env)
        self._timeout = request_timeout
        self._process: subprocess.Popen[str] | None = None
        self._responses: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._lock = threading.Lock()
        self._stderr_lines: list[str] = []
        # Set when kill() could not confirm the child's death. A pid recycled inside the
        # container's namespace can leave a live process we do not own answering waitpid()
        # forever; the transport then reports its own verdict instead of a fresh poll.
        self._unowned = False

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process is not None else None

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None and not self._unowned

    @property
    def stderr_tail(self) -> str:
        return "\n".join(self._stderr_lines[-20:])

    def start(self) -> None:
        if self._process is not None:
            raise PackProcessError("worker already started")
        self._unowned = False
        try:
            self._process = subprocess.Popen(
                self._command,
                cwd=self._cwd,
                env=self._env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise PackProcessError(f"could not start worker: {exc}") from exc
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self.ping()

    def _read_stdout(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        for line in self._process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                self._stderr_lines.append(f"non-JSON worker output: {pack_logs.redact(line[:200])}")
                continue
            self._responses.put(message)
        self._responses.put(None)

    def _read_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        for line in self._process.stderr:
            clean = pack_logs.redact(line.rstrip())
            self._stderr_lines.append(clean)
            if self._log is not None:
                self._log(clean)
            if len(self._stderr_lines) > 200:
                del self._stderr_lines[:100]

    def _alive(self) -> bool:
        return self.is_alive

    def request(self, payload: Mapping[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        """Send one request and return its response; raises PackProcessError on failure."""
        if not self._alive() or self._process is None or self._process.stdin is None:
            raise PackProcessError(f"worker is not running{self._stderr_suffix()}")
        data = json.dumps(payload, separators=(",", ":"))
        wait = self._timeout if timeout is None else timeout
        with self._lock:
            try:
                self._process.stdin.write(data + "\n")
                self._process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise PackProcessError(f"worker pipe closed: {exc}") from exc
            try:
                response = self._responses.get(timeout=wait)
            except queue.Empty as exc:
                self.kill()
                raise PackProcessError(f"worker timed out after {wait:g}s") from exc
            if response is None:
                raise PackProcessError(f"worker exited unexpectedly{self._stderr_suffix()}")
            if not response.get("ok"):
                raise PackProcessError(str(response.get("error") or "worker error"))
            return response

    def stream(self, payload: Mapping[str, Any], *, timeout: float | None = None) -> Iterator[bytes]:
        """Send a ``stream`` request and yield decoded audio chunks until the worker says done.

        Holds the request lock for the whole stream, so requests are serialised. ``timeout``
        applies to each chunk, not the total. Closing the generator early kills the worker: the
        protocol has no cancel message, and the next request starts a fresh one.
        """
        if not self._alive() or self._process is None or self._process.stdin is None:
            raise PackProcessError(f"worker is not running{self._stderr_suffix()}")
        data = json.dumps({"op": "stream", **payload}, separators=(",", ":"))
        wait = self._timeout if timeout is None else timeout
        finished = False
        with self._lock:
            try:
                self._process.stdin.write(data + "\n")
                self._process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise PackProcessError(f"worker pipe closed: {exc}") from exc
            try:
                while True:
                    try:
                        message = self._responses.get(timeout=wait)
                    except queue.Empty as exc:
                        self.kill()
                        raise PackProcessError(f"worker timed out after {wait:g}s") from exc
                    if message is None:
                        raise PackProcessError(f"worker exited unexpectedly{self._stderr_suffix()}")
                    if not message.get("ok"):
                        raise PackProcessError(str(message.get("error") or "worker error"))
                    if message.get("done"):
                        finished = True
                        return
                    try:
                        yield base64.b64decode(message.get("chunk_b64", ""))
                    except ValueError as exc:
                        raise PackProcessError(f"worker returned invalid base64: {exc}") from exc
            finally:
                if not finished:
                    self.kill()

    def _stderr_suffix(self) -> str:
        tail = self.stderr_tail
        return f": {tail}" if tail else ""

    def ping(self, *, timeout: float = 10.0) -> None:
        self.request({"op": "ping"}, timeout=timeout)

    def synthesize(self, payload: Mapping[str, Any]) -> bytes:
        """Run one synthesis request; the worker returns base64 PCM/WAV bytes."""
        response = self.request({"op": "synthesize", **payload})
        audio = response.get("audio_b64")
        if not isinstance(audio, str):
            raise PackProcessError("worker response missing audio_b64")
        try:
            return base64.b64decode(audio)
        except ValueError as exc:
            raise PackProcessError(f"worker returned invalid base64: {exc}") from exc

    def kill(self) -> None:
        """Best-effort teardown; never raises.

        ``request`` calls this on its own timeout path, so a sandbox that refuses signal
        delivery (EPERM on a child we created ourselves) or whose ``waitpid`` cannot confirm the
        death must not surface here as an unrelated PermissionError or TimeoutExpired. When the
        death cannot be confirmed the worker is abandoned: it is never reused and ``is_alive``
        reports False.
        """
        process = self._process
        if process is None:
            return
        if process.poll() is not None:
            return
        if not _signal_child(process, signal.SIGTERM):
            # The pid already belongs to a process we may not signal: the worker is gone, and
            # escalating could hit whatever owns the pid now.
            self._abandon(process)
            return
        if _reap(process, _SIGTERM_GRACE):
            return
        _force_kill(process)
        if not _reap(process, _SIGKILL_GRACE):
            self._abandon(process)

    def _abandon(self, process: subprocess.Popen[str]) -> None:
        """Mark an unconfirmably-dead worker unusable and let it exit on EOF.

        Closing stdin lets a worker that is merely wedged drain its last request and finish;
        the process itself may outlive this call when the runner cannot deliver signals.
        """
        self._unowned = True
        try:
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
        except OSError:
            pass

    def close(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
        except OSError:
            pass
        if not self._unowned and not _reap(process, _SIGTERM_GRACE):
            self.kill()
        self._process = None

    def __enter__(self) -> "PackProcess":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

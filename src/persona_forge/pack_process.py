"""Managed child process for pack engines (Phase C3b).

Every non-Pocket engine will run in its own process so its dependencies, crashes and memory
cannot reach the web worker. This module is the transport only: newline-delimited JSON over
stdin/stdout, one request in flight, health ping, bounded waits and a hard kill on timeout.
Engine-specific work lives in the worker, not here.

The API does not spawn workers yet — that lands with the first screened engine. Keeping the
transport tested now means the adapter work adds a protocol, not a process manager.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence


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
    ) -> None:
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

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process is not None else None

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def stderr_tail(self) -> str:
        return "\n".join(self._stderr_lines[-20:])

    def start(self) -> None:
        if self._process is not None:
            raise PackProcessError("worker already started")
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
                self._stderr_lines.append(f"non-JSON worker output: {line[:200]}")
                continue
            self._responses.put(message)
        self._responses.put(None)

    def _read_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        for line in self._process.stderr:
            self._stderr_lines.append(line.rstrip())
            if len(self._stderr_lines) > 200:
                del self._stderr_lines[:100]

    def _alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

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
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def close(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.kill()
        self._process = None

    def __enter__(self) -> "PackProcess":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

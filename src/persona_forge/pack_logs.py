"""Bounded, redacted logs for pack installs and pack workers (the card's "View logs").

Two logs per engine, each the last ``MAX_LINES`` lines and nothing more:

- ``install``: step markers and the output of every install command, kept in memory and written to
  ``<pack dir>/install.log`` (owner-only) when the install ends, so the failure is still readable
  after a restart.
- ``worker``: the pack worker's stderr, in memory only. It survives the worker being unloaded or
  crashing, and is lost when the server restarts.

Every line passes through :func:`redact` before it is stored, so a token that a child process echoed
back (a request header, an ``HF_TOKEN=`` environment dump, a URL with ``?token=``) never reaches a
log, the details payload, or an error message. Redaction knows the stored token and the
environment's tokens exactly, and recognises token-shaped strings, headers and assignments.
"""

from __future__ import annotations

import collections
import contextlib
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from persona_forge import hf_access

MAX_LINES = 200
MAX_LINE_CHARS = 2000
INSTALL_LOG_FILENAME = "install.log"
REDACTED = "[redacted]"

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bhf_[A-Za-z0-9_\-]{6,}"), REDACTED),
    (re.compile(r"\bapi_org_[A-Za-z0-9]{6,}"), REDACTED),
    (re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer|token)?\s*)[^\s'\",;]+"), rf"\1{REDACTED}"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_.\-]{8,}"), f"Bearer {REDACTED}"),
    (
        re.compile(
            r"(?i)\b(hf_token|hugging_?face_hub_token|huggingface_token|access_token|hf_api_token)"
            r"(\s*[=:]\s*)[^\s'\",;&]+"
        ),
        rf"\1\2{REDACTED}",
    ),
    (re.compile(r"(?i)([?&](?:token|access_token)=)[^&\s'\"]+"), rf"\1{REDACTED}"),
)


def redact(text: str, extra: tuple[str, ...] | list[str] = ()) -> str:
    """Remove tokens from ``text``: exact known secrets first, then token-shaped patterns."""
    if not text:
        return text
    for secret in sorted({*hf_access.secrets(), *(s for s in extra if s and len(s) >= 4)}, key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RingLog:
    """Thread-safe last-N-lines buffer. Lines are redacted and length-capped on the way in."""

    def __init__(self, max_lines: int = MAX_LINES) -> None:
        self._lines: collections.deque[str] = collections.deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self._dropped = 0
        self._updated_at: float | None = None
        self._extra_secrets: list[str] = []

    def add_secret(self, secret: str | None) -> None:
        if secret and len(secret) >= 4 and secret not in self._extra_secrets:
            self._extra_secrets.append(secret)

    def append(self, text: str) -> None:
        for raw in str(text).splitlines() or [""]:
            line = redact(raw.rstrip(), self._extra_secrets)
            if not line.strip():
                continue
            if len(line) > MAX_LINE_CHARS:
                line = line[:MAX_LINE_CHARS] + " …"
            with self._lock:
                if len(self._lines) == self._lines.maxlen:
                    self._dropped += 1
                self._lines.append(line)
                self._updated_at = time.time()

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()
            self._dropped = 0
            self._updated_at = None
            self._extra_secrets = []

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "lines": list(self._lines),
                "dropped": self._dropped,
                "updated_at": self._updated_at,
            }


_registry: dict[tuple[str, str], RingLog] = {}
_registry_lock = threading.Lock()


def ring(engine_id: str, kind: str) -> RingLog:
    with _registry_lock:
        return _registry.setdefault((engine_id, kind), RingLog())


def forget(engine_id: str) -> None:
    """Drop an engine's in-memory logs (used when its pack is removed)."""
    with _registry_lock:
        for key in [key for key in _registry if key[0] == engine_id]:
            del _registry[key]


def worker_sink(engine_id: str) -> Callable[[str], None]:
    """Line sink for a pack worker's stderr."""
    return ring(engine_id, "worker").append


# -- install capture ------------------------------------------------------------------------

_local = threading.local()


class InstallSink:
    """Where one running install writes: step markers, command lines and command output."""

    def __init__(self, engine_id: str) -> None:
        self.engine_id = engine_id
        self.log = ring(engine_id, "install")

    def line(self, text: str) -> None:
        self.log.append(text)

    def note(self, text: str) -> None:
        self.log.append(f"-- {text}")

    def command(self, command: list[str]) -> None:
        self.log.append("$ " + " ".join(_short(part) for part in command))

    def add_secret(self, secret: str | None) -> None:
        self.log.add_secret(secret)


def _short(part: str) -> str:
    """Keep a long inline script (``python -c ...``) from flooding the log."""
    flat = " ".join(str(part).split())
    return flat if len(flat) <= 160 else flat[:157] + "..."


def current_sink() -> InstallSink | None:
    return getattr(_local, "sink", None)


def add_secret(secret: str | None) -> None:
    """Register a token the running install uses, so its exact value is redacted."""
    sink = current_sink()
    if sink is not None:
        sink.add_secret(secret)


def record_job_change(changes: Mapping[str, Any]) -> None:
    """Called from a pack's job-state setter: mirrors step changes and errors into the install log."""
    sink = current_sink()
    if sink is None:
        return
    step = changes.get("step")
    if step:
        index = changes.get("step_index")
        sink.note(f"Step {index}: {step}" if index else str(step))
    error = changes.get("error")
    if error:
        sink.note(f"FAILED: {error}")
    if changes.get("state") == "done":
        sink.note("Installed")


def _write_install_log(directory: Path | None, snapshot: Mapping[str, Any]) -> None:
    """Persist the install log atomically and owner-only. Best effort: a log must not fail an install."""
    if directory is None:
        return
    lines = list(snapshot.get("lines") or [])
    if snapshot.get("dropped"):
        lines.insert(0, f"-- {snapshot['dropped']} earlier lines dropped")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=".install-log.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
            os.replace(tmp_name, directory / INSTALL_LOG_FILENAME)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise
    except OSError:
        pass


@contextlib.contextmanager
def capture_install(engine_id: str, directory: Path | None) -> Iterator[InstallSink]:
    """Route the current thread's install output into the engine's install log, then persist it."""
    sink = InstallSink(engine_id)
    sink.log.clear()
    sink.note(f"Install started {time.strftime('%Y-%m-%d %H:%M:%S')}")
    previous = current_sink()
    _local.sink = sink
    try:
        yield sink
    finally:
        _local.sink = previous
        _write_install_log(directory, sink.log.snapshot())


def logs_install(engine_id: str, directory_for: Callable[[Path | None], Path]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for a pack's ``install(root, ...)``: capture its output as the install log."""

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(root: Path | None = None, *args: Any, **kwargs: Any) -> Any:
            with capture_install(engine_id, directory_for(root)):
                return function(root, *args, **kwargs)

        wrapper.__name__ = function.__name__
        wrapper.__doc__ = function.__doc__
        wrapper.__wrapped__ = function  # type: ignore[attr-defined]
        return wrapper

    return decorate


# -- reading --------------------------------------------------------------------------------


def _read_install_file(directory: Path | None) -> dict[str, Any] | None:
    if directory is None:
        return None
    path = directory / INSTALL_LOG_FILENAME
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        updated = path.stat().st_mtime
    except OSError:
        return None
    lines = [redact(line) for line in text.splitlines()][-MAX_LINES:]
    return {"lines": lines, "dropped": 0, "updated_at": updated}


def read(engine_id: str, directory: Path | None) -> dict[str, Any]:
    """Both logs for the details payload. Memory wins; the install file covers a restart."""
    install = ring(engine_id, "install").snapshot()
    install_source = "memory"
    if not install["lines"]:
        from_file = _read_install_file(directory)
        if from_file is not None:
            install, install_source = from_file, "file"
        else:
            install_source = "none"
    worker = ring(engine_id, "worker").snapshot()
    return {
        "install": {**install, "source": install_source},
        "worker": {**worker, "source": "memory" if worker["lines"] else "none"},
        "max_lines": MAX_LINES,
    }

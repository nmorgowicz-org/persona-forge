"""
Bounded, serialized background-job manager for forced alignment (Phase 2).

The generation `_JobState` is frame-generation specific (progress, cancellation,
RTF), so alignment gets its own small manager (plan §5.5). Guarantees:

- **Serialization:** at most one alignment runs at a time (a single worker lock),
  so alignment never collides with a model load/reconfigure or another align.
- **Cancellation:** each job carries a `threading.Event`; the runner is expected
  to check it, and a cancelled job never reports `completed`.
- **Idle-unload:** when the last job drains, an idle timer releases the ONNX
  session to reclaim RSS.
- **LOW_RAM_MODE:** submission is refused outright (the aligner's peak RSS is not
  affordable), surfaced as `LowRamError`.
- **Bounded:** terminal jobs are evicted by TTL / count so the map cannot grow
  without limit.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_TERMINAL = ("completed", "failed", "cancelled")


class LowRamError(RuntimeError):
    """Raised when alignment is refused because LOW_RAM_MODE is active."""


def low_ram_enabled() -> bool:
    return os.getenv("LOW_RAM_MODE", "").strip().lower() in ("1", "true", "on", "yes")


# runner(voice_id, cancel_event) -> result record (or None if cancelled mid-flight)
Runner = Callable[[str, threading.Event], Any]


class AlignmentJobManager:
    def __init__(
        self,
        runner: Runner,
        *,
        max_jobs: int = 50,
        ttl_seconds: float = 600.0,
        idle_unload_seconds: float = 120.0,
        unload: Optional[Callable[[], Any]] = None,
        low_ram: Optional[Callable[[], bool]] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._runner = runner
        self._unload = unload
        self._low_ram = low_ram or low_ram_enabled
        self._clock = clock
        self._max_jobs = max_jobs
        self._ttl = ttl_seconds
        self._idle_unload = idle_unload_seconds
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._worker = threading.Lock()  # serializes alignment work
        self._active = 0
        self._idle_timer: Optional[threading.Timer] = None

    # --- submission ---------------------------------------------------------

    def submit(self, voice_id: str, *, spawn: bool = True, **runner_kwargs: Any) -> dict[str, Any]:
        if self._low_ram():
            raise LowRamError("Forced alignment is disabled in LOW_RAM_MODE.")
        self._evict()
        job_id = uuid.uuid4().hex
        job = {
            "job_id": job_id,
            "voice_id": voice_id,
            "status": "queued",
            "created_at": self._clock(),
            "cancel": threading.Event(),
            "result": None,
            "error": None,
            "runner_kwargs": runner_kwargs,
        }
        with self._lock:
            self._jobs[job_id] = job
            self._active += 1
        self._cancel_idle_timer()
        if spawn:
            threading.Thread(target=self._run, args=(job_id,), daemon=True).start()
        return self.get(job_id)  # type: ignore[return-value]

    def _run(self, job_id: str) -> None:
        with self._worker:  # one alignment at a time
            job = self._jobs.get(job_id)
            if job is None:
                self._drain()
                return
            cancel: threading.Event = job["cancel"]
            if cancel.is_set():
                self._set(job_id, status="cancelled")
            else:
                self._set(job_id, status="running")
                try:
                    result = self._runner(job["voice_id"], cancel, **job.get("runner_kwargs", {}))
                    if cancel.is_set():
                        self._set(job_id, status="cancelled")
                    else:
                        self._set(job_id, status="completed", result=result)
                except Exception as exc:  # noqa: BLE001 — surface any failure to the caller
                    logger.exception("Alignment job %s failed", job_id)
                    self._set(job_id, status="failed", error=str(exc))
        self._drain()

    # --- control / query ----------------------------------------------------

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job["cancel"].set()
            if job["status"] == "queued":
                job["status"] = "cancelled"
        return True

    def get(self, job_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return {k: job[k] for k in ("job_id", "voice_id", "status", "created_at", "result", "error")}

    # --- internals ----------------------------------------------------------

    def _set(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.update(fields)

    def _drain(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)
            idle = self._active == 0
        if idle:
            self._schedule_idle_unload()

    def _evict(self) -> None:
        now = self._clock()
        with self._lock:
            if len(self._jobs) <= self._max_jobs:
                return
            for jid in [
                j for j, job in self._jobs.items()
                if job["status"] in _TERMINAL and now - job["created_at"] >= self._ttl
            ]:
                self._jobs.pop(jid, None)
            if len(self._jobs) > self._max_jobs:
                terminal = sorted(
                    (j for j, job in self._jobs.items() if job["status"] in _TERMINAL),
                    key=lambda k: self._jobs[k]["created_at"],
                )
                for jid in terminal[: len(self._jobs) - self._max_jobs]:
                    self._jobs.pop(jid, None)

    def _schedule_idle_unload(self) -> None:
        if self._unload is None or self._idle_unload <= 0:
            return
        self._cancel_idle_timer()
        timer = threading.Timer(self._idle_unload, self._maybe_unload)
        timer.daemon = True
        with self._lock:
            self._idle_timer = timer
        timer.start()

    def _maybe_unload(self) -> None:
        with self._lock:
            if self._active > 0:
                return
        try:
            if self._unload is not None:
                self._unload()
        except Exception:  # noqa: BLE001
            logger.exception("Idle unload of forced-aligner failed")

    def _cancel_idle_timer(self) -> None:
        with self._lock:
            timer = self._idle_timer
            self._idle_timer = None
        if timer is not None:
            timer.cancel()

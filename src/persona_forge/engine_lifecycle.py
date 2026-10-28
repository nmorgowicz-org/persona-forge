"""Load state shared by the pack-engine adapters: idle -> loading -> warming -> ready | error.

``loading`` is the worker starting and reading its weights. ``warming`` is the first synthesis call
that compiles or caches kernels (about 33 s for the compiled Kitten 2 path); the model is in memory
but a request would stall behind that compile. ``ready`` is the plan's ``active``: the worker can
serve now. The name stays ``ready`` because the engine cards and Compare already read it.

The tracker only records state and lets a caller wait for it to settle. It raises nothing: each
adapter turns "still loading or warming" into its own retryable error, because the exception types
live beside the adapters.
"""

from __future__ import annotations

import math
import os
import threading
import time
from typing import Any, Callable, Mapping

IN_FLIGHT = ("loading", "warming")
DEFAULT_RETRY_AFTER_S = 5
MAX_RETRY_AFTER_S = 60
DEFAULT_WARM_WAIT_S = 5.0


def warm_wait_s() -> float:
    """How long a request may wait for a load or warm-up before it gets a retryable 503.

    ``ENGINE_WARM_WAIT_S``; ``0`` never waits. Read on every call so a running app can be tuned.
    """
    try:
        return max(0.0, float(os.environ.get("ENGINE_WARM_WAIT_S", DEFAULT_WARM_WAIT_S)))
    except ValueError:
        return DEFAULT_WARM_WAIT_S


class LoadTracker:
    """Thread-safe load state with elapsed time and, where known, an estimate for the phase."""

    def __init__(
        self,
        *,
        estimates: Mapping[str, float] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._estimates = dict(estimates or {})
        self._clock = clock
        self._condition = threading.Condition()
        self._state = "idle"
        self._error: str | None = None
        self._since = clock()

    @property
    def state(self) -> str:
        return self._state

    @property
    def error(self) -> str | None:
        return self._error

    def enter(self, state: str, error: str | None = None) -> None:
        """Move to ``state``. Re-entering the current state keeps its clock running."""
        with self._condition:
            if state != self._state:
                self._since = self._clock()
            self._state = state
            self._error = error
            self._condition.notify_all()

    def fail(self, message: str) -> None:
        self.enter("error", message)

    def claim_load(self) -> bool:
        """Start a load unless one is already in flight. Exactly one caller wins the claim."""
        with self._condition:
            if self._state in IN_FLIGHT:
                return False
            self._state = "loading"
            self._error = None
            self._since = self._clock()
            self._condition.notify_all()
            return True

    def wait_settled(self, timeout: float) -> str:
        """Block until no load or warm-up is in flight, or ``timeout`` seconds pass."""
        deadline = self._clock() + max(timeout, 0.0)
        with self._condition:
            while self._state in IN_FLIGHT:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            return self._state

    def snapshot(self) -> dict[str, Any]:
        with self._condition:
            running = self._state in IN_FLIGHT
            estimate = self._estimates.get(self._state) if running else None
            return {
                "state": self._state,
                "error": self._error,
                "elapsed_s": round(self._clock() - self._since, 1) if running else None,
                "estimated_s": estimate,
            }

    def retry_after_s(self) -> int:
        """Seconds a client should wait before retrying: the remaining estimate, else a default."""
        with self._condition:
            estimate = self._estimates.get(self._state)
            if estimate is None:
                return DEFAULT_RETRY_AFTER_S
            remaining = estimate - (self._clock() - self._since)
            if remaining <= 0:
                return DEFAULT_RETRY_AFTER_S  # overran the estimate: poll gently
            return min(max(math.ceil(remaining), 1), MAX_RETRY_AFTER_S)


class IdleUnloader:
    """Per-engine idle-unload policy and timer, shared by every pack adapter.

    Effective seconds resolve as: explicit ``override`` > env var > pack manifest
    ``idle_unload_after`` > ``default_s`` (older packs have no field). ``0`` means never unload.
    Resolution happens on every call, so a pack installed or edited after start-up is honoured.

    ``on_idle`` runs on the timer thread. A timer that was superseded by a later ``arm`` or
    ``cancel`` never fires its callback, even if it was already running when cancelled.
    """

    def __init__(
        self,
        *,
        env_name: str,
        default_s: float,
        on_idle: Callable[[], None],
        manifest_value: Callable[[], float | None],
        override: float | None = None,
        timer_factory: Callable[..., Any] = threading.Timer,
    ) -> None:
        self._env_name = env_name
        self._default_s = default_s
        self._on_idle = on_idle
        self._manifest_value = manifest_value
        self._override = override
        self._timer_factory = timer_factory
        self._lock = threading.Lock()
        self._timer: Any = None
        self._generation = 0

    def resolve(self) -> tuple[float, str]:
        """Effective seconds and where they came from: argument | env | manifest | default."""
        if self._override is not None:
            return max(0.0, float(self._override)), "argument"
        raw = os.environ.get(self._env_name) if self._env_name else None
        if raw is not None:
            try:
                value = float(raw)
            except ValueError:
                value = math.nan
            if math.isfinite(value) and value >= 0:
                return value, "env"
        try:
            manifest = self._manifest_value()
        except Exception:  # an unreadable pack must not break serving
            manifest = None
        if manifest is not None:
            return manifest, "manifest"
        return self._default_s, "default"

    @property
    def seconds(self) -> float:
        return self.resolve()[0]

    def arm(self) -> None:
        """(Re)start the countdown from now; a no-op beyond cancelling when the value is 0."""
        seconds = self.seconds
        with self._lock:
            self._cancel_locked()
            if seconds <= 0:
                return
            generation = self._generation

            def fire() -> None:
                with self._lock:
                    if generation != self._generation:
                        return
                self._on_idle()

            timer = self._timer_factory(seconds, fire)
            timer.daemon = True
            self._timer = timer
            timer.start()

    def cancel(self) -> None:
        with self._lock:
            self._cancel_locked()

    def _cancel_locked(self) -> None:
        self._generation += 1
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

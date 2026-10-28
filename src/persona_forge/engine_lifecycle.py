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

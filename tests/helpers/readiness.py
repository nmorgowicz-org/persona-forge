"""Shared readiness-polling harness for spawned-process acceptance tests (Phase 2 Task 8).

Polls a running server's ``/health`` endpoint until it returns parseable JSON (or the deadline
passes) rather than asserting on a fixed sleep — spawned real WSGI servers (gunicorn/waitress)
take a variable amount of time to bind and accept connections.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


def poll_health(base_url: str, *, timeout: float = 15.0, interval: float = 0.2) -> dict[str, Any]:
    """Poll ``<base_url>/health`` until it returns JSON, or raise on timeout.

    Returns the last successfully parsed JSON body. A connection refused/reset is expected
    while the server is still starting and is treated as "not ready yet", not an error.
    """
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(interval)
    raise TimeoutError(f"{base_url}/health did not become ready within {timeout}s: {last_error}")

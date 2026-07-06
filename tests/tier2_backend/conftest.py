"""Tier 2 backend shared fixtures.

Install FakeModelRuntime into sys.modules["qwen3_tts.model"] BEFORE importing
qwen3_tts.app so that model-heavy imports see the fake, not the real runtime.
"""

from __future__ import annotations

import sys

import pytest

from tests.fixtures.fake_runtime import FakeModelRuntime

# ── Module-level setup ──

# Create and install a single FakeModelRuntime for the whole session.
_rt_instance = FakeModelRuntime(
    initial_service_started=True,
    model_loaded=True,
    startup_failed=False,
    tts_backend="openvino",
    generate_delay_ms=0,
    generate_should_fail=False,
    generate_error_code=500,
    swap_in_progress=False,
)
_rt_instance.install()

# Now safe to import app — it will get our fake model.
from qwen3_tts import app as _app_module  # noqa: E402

# Alias _runtime_live for runtime_config tests.
_rt_instance.live_config = _rt_instance._runtime_live


@pytest.fixture(scope="session")
def rt():
    """Shared FakeModelRuntime instance for all tier2_backend tests."""
    return _rt_instance


@pytest.fixture(scope="session")
def app_module():
    """qwen3_tts.app module using FakeModelRuntime."""
    return _app_module


@pytest.fixture(scope="module")
def client(app_module):
    """Fresh test_client per test module to avoid shared request contexts."""
    return app_module.app.test_client()

"""Tier 2 backend shared fixtures.

Install FakeModelRuntime into sys.modules["persona_forge.model"] BEFORE importing
persona_forge.app so that model-heavy imports see the fake, not the real runtime.
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
from persona_forge import app as _app_module  # noqa: E402

# Alias _runtime_live for runtime_config tests.
_rt_instance.live_config = _rt_instance._runtime_live


@pytest.fixture(scope="session")
def rt():
    """Shared FakeModelRuntime instance for all tier2_backend tests."""
    return _rt_instance


@pytest.fixture(scope="session")
def app_module():
    """persona_forge.app module using FakeModelRuntime."""
    return _app_module


@pytest.fixture(scope="module")
def client(app_module):
    """Fresh test_client per test module to avoid shared request contexts."""
    return app_module.app.test_client()


def _reset_swap_flags() -> None:
    """Clear the swap/reconfig-in-progress flags on the shared session-scoped fakes.

    rt/app_module are session-scoped singletons; several sibling tests flip these
    flags True and restore them in a try/finally, but any leak (a failed restore,
    or just unlucky xdist worker ordering) leaves the flag stuck True for every
    other test on that worker, causing spurious 503s (e.g. #206).
    """
    _rt_instance._reconfig_in_progress = False
    _rt_instance.swap_in_progress = False
    _app_module.voice_design._swap_in_progress = False
    _app_module.omnivoice_engine._swap_in_progress = False


@pytest.fixture(autouse=True)
def _reset_swap_state():
    _reset_swap_flags()
    yield
    _reset_swap_flags()

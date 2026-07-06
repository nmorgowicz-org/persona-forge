"""Tier 3 API integration tests — shared server fixture.

Starts fake_model_server once for the whole session, exposes `base_url` fixture.
All tests in this directory are black-box HTTP tests against that server.
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path

# Ensure ui/fixtures is importable.
_ui_fixtures = Path(__file__).resolve().parent.parent / "ui" / "fixtures"
if str(_ui_fixtures) not in sys.path:
    sys.path.insert(0, str(_ui_fixtures))

from fake_model_server import start_server  # noqa: E402


@pytest.fixture(scope="session")
def base_url():
    # Use dynamic port (0) so xdist workers don't collide on 18318.
    url, stop = start_server(port=0, frontend_enabled=False)
    yield url
    stop()

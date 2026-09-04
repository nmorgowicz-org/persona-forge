"""WSGI target for Phase 2 Task 8's model-free spawned-process acceptance test.

Installs FakeModelRuntime into sys.modules["persona_forge.model"] *before* importing
persona_forge.app, so a real gunicorn/waitress process started via
``persona-forge serve`` (with ``PERSONA_FORGE_WSGI_TARGET=tests.fixtures.fake_wsgi_app:app``)
never imports Torch/OpenVINO/Transformers. Reuses tests/fixtures/fake_runtime.py — the same
fake used by tests/ui/fixtures/fake_model_server.py — rather than inventing a second fake.

TEST_INJECT_STARTUP_ERROR=1 makes the fake report a failed startup, exercising the acceptance
fixture's "fails immediately on an injected startup error" requirement.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _setup_pythonpath() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for candidate in (repo_root, repo_root / "src"):
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


_setup_pythonpath()

from tests.fixtures.fake_runtime import FakeModelRuntime  # noqa: E402

_startup_failed = os.environ.get("TEST_INJECT_STARTUP_ERROR", "").strip() == "1"
_rt = FakeModelRuntime(
    initial_service_started=not _startup_failed,
    model_loaded=not _startup_failed,
    startup_failed=_startup_failed,
    tts_backend=os.environ.get("TTS_BACKEND", "pocket_tts"),
)
_rt.install()

from persona_forge.app import app  # noqa: E402

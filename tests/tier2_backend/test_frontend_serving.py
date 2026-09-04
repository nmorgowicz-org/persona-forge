"""Phase 3 Tests-first: an installed-style app process actually serves the resolved frontend.

Runs in a fresh subprocess (never the shared session-scoped ``app_module``) so it can set
``FRONTEND_DIST_DIR`` before ``persona_forge.app`` resolves it at import time, and installs
``FakeModelRuntime`` first (same technique as tests/tier2_backend/conftest.py) so importing
``persona_forge.app`` never touches the real Torch/model stack.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_SCRIPT = """
import sys
sys.path.insert(0, {tests_root!r})
from tests.fixtures.fake_runtime import FakeModelRuntime
FakeModelRuntime(
    initial_service_started=True, model_loaded=True, startup_failed=False,
    tts_backend="openvino", generate_delay_ms=0, generate_should_fail=False,
    generate_error_code=500, swap_in_progress=False,
).install()

from persona_forge import app as app_module

client = app_module.app.test_client()

resp = client.get("/")
assert resp.status_code == 200, resp.status_code
assert b"<html" in resp.data.lower(), resp.data[:200]

resp = client.get("/assets/app-abc123.js")
assert resp.status_code == 200, resp.status_code
assert resp.data == b"console.log('fake studio bundle');"

resp = client.get("/health")
assert resp.status_code == 200, (resp.status_code, resp.data)

print("FRONTEND_SERVING_OK")
"""


def test_installed_style_app_serves_ui_assets_and_health(tmp_path):
    dist_dir = tmp_path / "dist"
    (dist_dir / "assets").mkdir(parents=True)
    (dist_dir / "index.html").write_text("<html><body>Persona Forge Studio</body></html>")
    (dist_dir / "assets" / "app-abc123.js").write_text("console.log('fake studio bundle');")

    # persona_forge.voice_library resolves VOICE_LIBRARY_DIR (via paths.voice_library_dir())
    # at import time whenever no override env var is set, and that default path falls back to
    # Path.home() — which raises on a Windows service account with no profile directory. Give
    # the subprocess its own throwaway home so the import succeeds without touching the real
    # host home dir (keeps the sandboxing this test relies on for the __file__-relative proof).
    home_dir = tmp_path / "home"
    home_dir.mkdir()

    script = _SCRIPT.format(tests_root=str(REPO_ROOT))
    if sys.platform == "win32":
        env = {
            "PATH": "",
            "PYTHONPATH": str(REPO_ROOT / "src"),
            "FRONTEND_DIST_DIR": str(dist_dir),
            "USERPROFILE": str(home_dir),
            "HOMEDRIVE": home_dir.drive,
            "HOMEPATH": str(home_dir)[len(home_dir.drive) :],
        }
        # Windows' interpreter startup (winapi/socket init) needs SystemRoot to resolve
        # system DLLs — without it, python.exe itself fails before running any script.
        if system_root := os.environ.get("SystemRoot"):
            env["SystemRoot"] = system_root
    else:
        env = {
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(REPO_ROOT / "src"),
            "FRONTEND_DIST_DIR": str(dist_dir),
            "HOME": str(home_dir),
        }
        # Some Python builds (e.g. actions/setup-python's relocatable download) load libpython
        # from a bundled lib dir via LD_LIBRARY_PATH rather than the system loader path; without
        # it the interpreter itself fails to start. Carrying it through doesn't weaken the
        # __file__-relative-resolution proof this test cares about (PATH/cwd stay sandboxed).
        if ld_library_path := os.environ.get("LD_LIBRARY_PATH"):
            env["LD_LIBRARY_PATH"] = ld_library_path
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,  # outside the checkout: proves resolution is __file__-relative, not cwd
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FRONTEND_SERVING_OK" in result.stdout

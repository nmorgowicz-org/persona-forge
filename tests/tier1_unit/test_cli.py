"""Test persona_forge.cli: doctor/setup/build-ui/serve commands (Phase 2 Task 5/6/8)."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from persona_forge import cli
from persona_forge.config import DEFAULT_TTS_BACKEND

REPO_ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TestIsolatedImport:
    def test_importing_cli_alone_never_imports_heavy_modules(self):
        script = (
            "import sys\n"
            "import persona_forge.cli\n"
            "heavy = {'torch', 'openvino', 'transformers', 'persona_forge.model'}\n"
            "leaked = heavy & set(sys.modules)\n"
            "assert not leaked, leaked\n"
            "print('ok')\n"
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env=env,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "ok" in result.stdout


class TestDoctor:
    def test_json_is_parseable_and_stable_shape(self):
        report = cli._doctor_report({})
        # Round-trip through the real JSON encoder cmd_doctor uses.
        parsed = json.loads(json.dumps(report))
        for key in ("platform", "dependencies", "paths", "accelerator", "backend", "ui", "patches"):
            assert key in parsed

    def test_doctor_against_nonexistent_root_leaves_it_nonexistent(self, tmp_path):
        root = tmp_path / "does-not-exist-yet"
        environ = {"PERSONA_FORGE_HOME": str(root)}
        cli._doctor_report(environ)
        assert not root.exists()

    def test_resolved_backend_defaults_to_pocket_tts(self):
        report = cli._doctor_report({})
        assert report["backend"]["resolved"] == DEFAULT_TTS_BACKEND == "pocket_tts"

    def test_resolved_backend_honors_explicit_value(self):
        report = cli._doctor_report({"TTS_BACKEND": "openvino"})
        assert report["backend"]["resolved"] == "openvino"

    def test_survives_broken_torch_probe(self):
        # _probe_import itself catches import errors and turns them into diagnostic fields
        # rather than letting them raise — this is what lets _doctor_report (and therefore
        # `doctor`) survive a broken/missing Torch install instead of crashing.
        result = cli._probe_import("definitely_not_a_real_module_xyz")
        assert result == {"installed": False, "importable": False, "error": None}


class TestSetup:
    def test_setup_creates_documented_directories_and_is_idempotent(self, tmp_path, monkeypatch):
        root = tmp_path / "pf-home"
        monkeypatch.setenv("PERSONA_FORGE_HOME", str(root))
        args = cli.build_parser().parse_args(["setup", "--no-ui"])
        assert cli.cmd_setup(args) == 0
        assert root.is_dir()
        created_first = sorted(p for p in root.rglob("*") if p.is_dir())

        assert cli.cmd_setup(args) == 0
        created_second = sorted(p for p in root.rglob("*") if p.is_dir())
        assert created_first == created_second


class TestServerCommand:
    def test_posix_argv_exact(self):
        argv = cli._server_command("127.0.0.1", 8318, platform="linux")
        assert argv == [
            "gunicorn",
            "persona_forge.app:app",
            "-w",
            "1",
            "-k",
            "gthread",
            "--threads",
            "4",
            "--timeout",
            "300",
            "--bind",
            "127.0.0.1:8318",
            "--log-level",
            "info",
        ]
        assert "--preload" not in argv

    def test_windows_argv_exact(self):
        argv = cli._server_command("0.0.0.0", 9000, platform="win32")
        assert argv == [
            "waitress-serve",
            "--host=0.0.0.0",
            "--port=9000",
            "--threads=4",
            "persona_forge.app:app",
        ]

    def test_wsgi_target_override_for_tests(self, monkeypatch):
        monkeypatch.setenv("PERSONA_FORGE_WSGI_TARGET", "tests.fixtures.fake_wsgi_app:app")
        argv = cli._server_command("127.0.0.1", 8318, platform="linux")
        assert "tests.fixtures.fake_wsgi_app:app" in argv


class TestPortConflict:
    def test_detects_port_already_in_use(self):
        port = _free_port()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", port))
            listener.listen(1)
            assert cli._port_in_use("127.0.0.1", port) is True

    def test_free_port_is_not_in_use(self):
        port = _free_port()
        assert cli._port_in_use("127.0.0.1", port) is False


@pytest.mark.slow
class TestSpawnedProcessAcceptance:
    """Task 8: model-free spawned-process acceptance fixture.

    Starts the real installed console command against the fake WSGI target (no Torch/OpenVINO
    ever imported), polls /health through the shared readiness harness, and proves the
    effective default backend is Pocket-TTS.
    """

    def _spawn(self, tmp_path, port, *, extra_env=None):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + str(REPO_ROOT)
        env["PERSONA_FORGE_WSGI_TARGET"] = "tests.fixtures.fake_wsgi_app:app"
        env["PERSONA_FORGE_HOME"] = str(tmp_path)
        env.pop("TTS_BACKEND", None)
        if extra_env:
            env.update(extra_env)
        return subprocess.Popen(
            [sys.executable, "-m", "persona_forge", "serve", "--host", "127.0.0.1", "--port", str(port)],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def test_reaches_ready_with_pocket_tts_default(self, tmp_path):
        from tests.helpers.readiness import poll_health

        port = _free_port()
        proc = self._spawn(tmp_path, port)
        try:
            body = poll_health(f"http://127.0.0.1:{port}", timeout=20)
            assert body["status"] == "ok"
            assert body["service_started"] is True
            assert body["backend"] == "pocket_tts"
            assert body.get("swap_in_progress") is False
            assert body.get("reconfig_in_progress") is False
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

    def test_fails_fast_on_injected_startup_error(self, tmp_path):
        from tests.helpers.readiness import poll_health

        port = _free_port()
        proc = self._spawn(tmp_path, port, extra_env={"TEST_INJECT_STARTUP_ERROR": "1"})
        try:
            body = poll_health(f"http://127.0.0.1:{port}", timeout=20)
            assert body["status"] == "error"
            assert body["service_started"] is False
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

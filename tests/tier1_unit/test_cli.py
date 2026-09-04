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

    def test_torch_runtime_device_is_none_when_not_importable(self):
        # Task 3: the generic torch-capability signal must be a distinct field from
        # accelerator.device (the override-aware, active-backend effective device) and must
        # never raise doctor's own report when torch isn't importable.
        assert cli._torch_runtime_device({"importable": False}) is None

    def test_doctor_report_torch_dependency_carries_runtime_device_key(self):
        report = cli._doctor_report({})
        assert "runtime_device" in report["dependencies"]["torch"]


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


class TestQwenPatchSetup:
    """Task 6: default (no qwen/openvino), Qwen PyTorch, Qwen + OpenVINO, and unsupported
    Windows Qwen/OpenVINO must each behave distinctly. importlib.util.find_spec and sys.platform
    are monkeypatched rather than actually installing qwen_tts (Phase 5 keeps cli.py free of
    heavy imports at module scope)."""

    def test_default_no_qwen_installed_is_a_clean_noop(self, monkeypatch):
        # find_spec returning None short-circuits before persona_forge.compat_patch is ever
        # imported, so there's nothing further to stub — the absence of an import IS the no-op.
        monkeypatch.setattr(cli.importlib.util, "find_spec", lambda name: None)
        assert cli._qwen_patch_setup(apply=False) == 0
        assert cli._qwen_patch_setup(apply=True) == 0

    def test_qwen_installed_pytorch_only_verifies_by_default(self, monkeypatch):
        monkeypatch.setattr(cli.importlib.util, "find_spec", lambda name: object())
        monkeypatch.setattr(cli.sys, "platform", "linux")

        import persona_forge.compat_patch as compat_patch

        calls = []
        monkeypatch.setattr(
            compat_patch,
            "verify_qwen_patches",
            lambda: calls.append("verify") or {"status": "already_applied", "patches": []},
        )
        monkeypatch.setattr(
            compat_patch,
            "apply_qwen_patches",
            lambda: (_ for _ in ()).throw(AssertionError("apply should not run without the flag")),
        )
        assert cli._qwen_patch_setup(apply=False) == 0
        assert calls == ["verify"]

    def test_qwen_plus_openvino_present_applies_with_explicit_flag(self, monkeypatch):
        monkeypatch.setattr(cli.importlib.util, "find_spec", lambda name: object())
        monkeypatch.setattr(cli.sys, "platform", "linux")

        import persona_forge.compat_patch as compat_patch

        calls = []
        monkeypatch.setattr(
            compat_patch,
            "apply_qwen_patches",
            lambda: calls.append("apply") or {"status": "already_applied", "patches": []},
        )
        assert cli._qwen_patch_setup(apply=True) == 0
        assert calls == ["apply"]

    def test_unsupported_windows_qwen_reports_diagnostic_and_skips(self, monkeypatch, capsys):
        monkeypatch.setattr(cli.importlib.util, "find_spec", lambda name: object())
        monkeypatch.setattr(cli.sys, "platform", "win32")

        import persona_forge.compat_patch as compat_patch

        monkeypatch.setattr(
            compat_patch,
            "verify_qwen_patches",
            lambda: (_ for _ in ()).throw(AssertionError("must not verify on unsupported Windows")),
        )
        monkeypatch.setattr(
            compat_patch,
            "apply_qwen_patches",
            lambda: (_ for _ in ()).throw(AssertionError("must not apply on unsupported Windows")),
        )
        assert cli._qwen_patch_setup(apply=True) == 0
        out = capsys.readouterr().out
        assert "not supported on" in out.lower() and "windows" in out.lower()

    def test_failed_patch_status_fails_setup(self, monkeypatch):
        monkeypatch.setattr(cli.importlib.util, "find_spec", lambda name: object())
        monkeypatch.setattr(cli.sys, "platform", "linux")

        import persona_forge.compat_patch as compat_patch

        monkeypatch.setattr(
            compat_patch, "verify_qwen_patches", lambda: {"status": "failed", "patches": []}
        )
        assert cli._qwen_patch_setup(apply=False) == 1


class TestBuildUiStamp:
    """Task 3: package-lock hash stamp gates rebuild; subprocess mocked (Phase 3)."""

    def _fake_frontend_source(self, tmp_path):
        frontend_dir = tmp_path / "frontend"
        frontend_dir.mkdir()
        (frontend_dir / "package-lock.json").write_text('{"lockfileVersion": 1}')
        return frontend_dir

    def test_skips_when_stamp_matches_lockfile_hash(self, tmp_path, monkeypatch):
        frontend_dir = self._fake_frontend_source(tmp_path)
        dist_dir = frontend_dir / "dist"
        dist_dir.mkdir()
        (dist_dir / "index.html").write_text("<html></html>")
        monkeypatch.setattr(cli, "_FRONTEND_SOURCE_DIR", frontend_dir)
        monkeypatch.setattr(cli, "_CHECKOUT_DIST_DIR", dist_dir)
        (dist_dir / cli._BUILD_STAMP_NAME).write_text(cli._package_lock_hash())

        calls = []
        monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: calls.append(a))

        assert cli._build_checkout_frontend(force=False) == 0
        assert calls == []

    def test_stale_stamp_triggers_rebuild(self, tmp_path, monkeypatch):
        frontend_dir = self._fake_frontend_source(tmp_path)
        dist_dir = frontend_dir / "dist"
        dist_dir.mkdir()
        (dist_dir / "index.html").write_text("<html></html>")
        (dist_dir / cli._BUILD_STAMP_NAME).write_text("stale-hash")
        monkeypatch.setattr(cli, "_FRONTEND_SOURCE_DIR", frontend_dir)
        monkeypatch.setattr(cli, "_CHECKOUT_DIST_DIR", dist_dir)
        monkeypatch.setattr(cli.shutil, "which", lambda name: "/resolved/npm")

        calls = []

        def fake_run(step, cwd=None):
            calls.append(step)
            if step == ["/resolved/npm", "run", "build"]:
                (dist_dir / "index.html").write_text("<html>rebuilt</html>")
            return subprocess.CompletedProcess(step, 0)

        monkeypatch.setattr(cli.subprocess, "run", fake_run)
        assert cli._build_checkout_frontend(force=False) == 0
        assert calls == [
            ["/resolved/npm", "ci"],
            ["/resolved/npm", "run", "check"],
            ["/resolved/npm", "run", "build"],
        ]
        assert (dist_dir / cli._BUILD_STAMP_NAME).read_text() == cli._package_lock_hash()

    def test_force_rebuilds_even_when_stamp_current(self, tmp_path, monkeypatch):
        frontend_dir = self._fake_frontend_source(tmp_path)
        dist_dir = frontend_dir / "dist"
        dist_dir.mkdir()
        (dist_dir / "index.html").write_text("<html></html>")
        monkeypatch.setattr(cli, "_FRONTEND_SOURCE_DIR", frontend_dir)
        monkeypatch.setattr(cli, "_CHECKOUT_DIST_DIR", dist_dir)
        (dist_dir / cli._BUILD_STAMP_NAME).write_text(cli._package_lock_hash())
        monkeypatch.setattr(cli.shutil, "which", lambda name: "/resolved/npm")

        calls = []

        def fake_run(step, cwd=None):
            calls.append(step)
            return subprocess.CompletedProcess(step, 0)

        monkeypatch.setattr(cli.subprocess, "run", fake_run)
        assert cli._build_checkout_frontend(force=True) == 0
        assert calls == [
            ["/resolved/npm", "ci"],
            ["/resolved/npm", "run", "check"],
            ["/resolved/npm", "run", "build"],
        ]

    def test_missing_frontend_source_dir_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli, "_FRONTEND_SOURCE_DIR", tmp_path / "does-not-exist")
        monkeypatch.setattr(cli, "_CHECKOUT_DIST_DIR", tmp_path / "does-not-exist" / "dist")
        assert cli._build_checkout_frontend(force=False) == 1


class TestSetupFrontendBuild:
    """Task 4: setup builds a missing/stale checkout UI unless --no-ui; npm-missing is a failure."""

    def test_no_ui_flag_never_touches_npm(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PERSONA_FORGE_HOME", str(tmp_path / "pf-home"))
        monkeypatch.setattr(
            cli.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("npm ran"))
        )
        args = cli.build_parser().parse_args(["setup", "--no-ui"])
        assert cli.cmd_setup(args) == 0

    def test_skips_build_when_package_local_ui_already_present(self, tmp_path, monkeypatch):
        package_static = tmp_path / "pkg-static"
        package_static.mkdir()
        (package_static / "index.html").write_text("<html></html>")
        monkeypatch.setattr(cli.frontend, "PACKAGE_STATIC_DIR", package_static)
        monkeypatch.setenv("PERSONA_FORGE_HOME", str(tmp_path / "pf-home"))
        monkeypatch.setattr(
            cli,
            "_build_checkout_frontend",
            lambda **k: (_ for _ in ()).throw(AssertionError("checkout build attempted")),
        )
        args = cli.build_parser().parse_args(["setup"])
        assert cli.cmd_setup(args) == 0

    def test_fails_when_npm_absent_from_path(self, tmp_path, monkeypatch):
        frontend_dir = tmp_path / "frontend"
        frontend_dir.mkdir()
        (frontend_dir / "package-lock.json").write_text("{}")
        monkeypatch.setattr(cli, "_FRONTEND_SOURCE_DIR", frontend_dir)
        monkeypatch.setattr(cli, "_CHECKOUT_DIST_DIR", frontend_dir / "dist")
        monkeypatch.setattr(cli.frontend, "PACKAGE_STATIC_DIR", tmp_path / "no-such-package-static")
        monkeypatch.setenv("PERSONA_FORGE_HOME", str(tmp_path / "pf-home"))

        def raise_not_found(*a, **k):
            raise FileNotFoundError("npm not found")

        monkeypatch.setattr(cli.subprocess, "run", raise_not_found)
        args = cli.build_parser().parse_args(["setup"])
        assert cli.cmd_setup(args) != 0


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
@pytest.mark.skipif(
    sys.platform.startswith("win") and os.getenv("CI", "").lower() == "true",
    reason=(
        "the NetworkService Windows CI runner blocks parent-to-child TCP; "
        "semantic HTTP coverage uses WSGI transport"
    ),
)
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

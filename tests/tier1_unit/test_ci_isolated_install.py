"""Test scripts/ci_isolated_install.py: the Phase 6 non-editable-wheel install gate.

Real ``uv venv``/``uv pip install`` are never invoked here (too slow for the unit tier and would
need network access) - subprocess.run is monkeypatched to fake a venv layout, matching the plan's
"disposable environment, never the shared dev environment" style used elsewhere in this phase.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import ci_isolated_install as cii


class TestVenvPython:
    def test_finds_posix_python(self, tmp_path):
        venv = tmp_path / "venv"
        (venv / "bin").mkdir(parents=True)
        python = venv / "bin" / "python"
        python.touch()
        assert cii._venv_python(venv) == str(python)

    def test_finds_windows_python(self, tmp_path):
        venv = tmp_path / "venv"
        (venv / "Scripts").mkdir(parents=True)
        python = venv / "Scripts" / "python.exe"
        python.touch()
        assert cii._venv_python(venv) == str(python)

    def test_raises_when_missing(self, tmp_path):
        with pytest.raises(SystemExit):
            cii._venv_python(tmp_path / "venv")


class TestConsoleScript:
    def test_finds_posix_script(self, tmp_path):
        venv = tmp_path / "venv"
        (venv / "bin").mkdir(parents=True)
        script = venv / "bin" / "persona-forge"
        script.touch()
        assert cii._console_script(venv) == script

    def test_finds_windows_script(self, tmp_path):
        venv = tmp_path / "venv"
        (venv / "Scripts").mkdir(parents=True)
        script = venv / "Scripts" / "persona-forge.exe"
        script.touch()
        assert cii._console_script(venv) == script

    def test_raises_when_missing(self, tmp_path):
        with pytest.raises(SystemExit):
            cii._console_script(tmp_path / "venv")


class TestUv:
    def test_raises_when_uv_not_on_path(self, monkeypatch):
        monkeypatch.setattr(cii.shutil, "which", lambda name: None)
        with pytest.raises(SystemExit):
            cii._uv()

    def test_returns_uv_path_when_found(self, monkeypatch):
        monkeypatch.setattr(cii.shutil, "which", lambda name: "/usr/bin/uv")
        assert cii._uv() == "/usr/bin/uv"


class TestMain:
    def _fake_venv_layout(self, iso_root: Path) -> None:
        venv_dir = iso_root / "venv"
        (venv_dir / "bin").mkdir(parents=True)
        (venv_dir / "bin" / "python").touch()
        (venv_dir / "bin" / "persona-forge").touch()

    def _patch_common(self, monkeypatch, tmp_path, *, doctor_result: subprocess.CompletedProcess):
        iso_root = tmp_path / "iso"
        iso_root.mkdir()
        monkeypatch.setattr(cii.tempfile, "mkdtemp", lambda prefix=None: str(iso_root))
        monkeypatch.setattr(cii, "_uv", lambda: "/usr/bin/uv")

        calls = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ["/usr/bin/uv", "venv"]:
                self._fake_venv_layout(iso_root)
                return subprocess.CompletedProcess(cmd, 0)
            if cmd[:2] == ["/usr/bin/uv", "pip"]:
                return subprocess.CompletedProcess(cmd, 0)
            return doctor_result

        monkeypatch.setattr(cii.subprocess, "run", fake_run)
        return iso_root, calls

    def test_dist_dir_must_contain_exactly_one_wheel(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "dist").mkdir()
        with pytest.raises(SystemExit, match="expected exactly one"):
            cii.main()

    def test_fails_when_two_wheels_present(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "persona_forge-1.0-py3-none-any.whl").touch()
        (dist / "persona_forge-1.1-py3-none-any.whl").touch()
        with pytest.raises(SystemExit, match="expected exactly one"):
            cii.main()

    def test_succeeds_and_builds_receipt_from_doctor_json(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "persona_forge-1.3.0-py3-none-any.whl").touch()

        doctor_report = {
            "platform": {"sys_platform": "linux"},
            "backend": {"resolved": "pocket_tts"},
            "paths": {},
            "ui": {"source": "package"},
        }
        doctor_result = subprocess.CompletedProcess(
            ["doctor"], 0, stdout=json.dumps(doctor_report), stderr=""
        )
        iso_root, calls = self._patch_common(monkeypatch, tmp_path, doctor_result=doctor_result)

        rc = cii.main()

        assert rc == 0
        out = capsys.readouterr().out
        assert '"status": "pass"' in out
        assert '"backend_resolved": "pocket_tts"' in out
        assert not iso_root.exists()  # cleaned up in the finally block
        assert any(c[:2] == ["/usr/bin/uv", "venv"] for c in calls)
        assert any(c[:2] == ["/usr/bin/uv", "pip"] for c in calls)

    def test_fails_when_doctor_exits_nonzero(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "persona_forge-1.3.0-py3-none-any.whl").touch()

        doctor_result = subprocess.CompletedProcess(["doctor"], 1, stdout="", stderr="boom")
        self._patch_common(monkeypatch, tmp_path, doctor_result=doctor_result)

        with pytest.raises(SystemExit, match="exited 1"):
            cii.main()

    def test_fails_when_doctor_json_missing_expected_sections(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "persona_forge-1.3.0-py3-none-any.whl").touch()

        doctor_result = subprocess.CompletedProcess(
            ["doctor"], 0, stdout=json.dumps({"backend": {}}), stderr=""
        )
        self._patch_common(monkeypatch, tmp_path, doctor_result=doctor_result)

        with pytest.raises(SystemExit, match="missing expected sections"):
            cii.main()

    def test_cleans_up_isolated_workspace_even_on_failure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "persona_forge-1.3.0-py3-none-any.whl").touch()

        doctor_result = subprocess.CompletedProcess(["doctor"], 1, stdout="", stderr="boom")
        iso_root, _ = self._patch_common(monkeypatch, tmp_path, doctor_result=doctor_result)

        with pytest.raises(SystemExit):
            cii.main()

        assert not iso_root.exists()

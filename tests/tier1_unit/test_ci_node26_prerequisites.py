"""Exercise prerequisite branching with fake commands, never real apt or sudo."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(os.name == "nt" or not BASH, reason="requires native Bash")


def run_helper(tmp_path, *, system="Linux", installed=False, uid="1000", fail=""):
    commands = {
        "uname": 'echo "$FAKE_SYSTEM"',
        "dpkg-query": 'printf "query\\n" >> "$COMMAND_LOG"; '
        'if [ "$FAKE_INSTALLED" = yes ]; then printf "install ok installed"; else exit 1; fi',
        "id": 'echo "$FAKE_UID"',
        "sudo": 'printf "sudo %s\\n" "$*" >> "$COMMAND_LOG"; '
        '[ "$1" = -n ] || exit 98; shift; exec "$@"',
        "apt-get": 'printf "apt %s %s\\n" "$DEBIAN_FRONTEND" "$*" >> "$COMMAND_LOG"; '
        '[ "$1" != "$FAIL_APT" ] || exit 42',
    }
    for name, body in commands.items():
        command = tmp_path / name
        command.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        command.chmod(0o755)
    log = tmp_path / "commands.log"
    env = dict(os.environ, PATH=f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
               FAKE_SYSTEM=system, FAKE_INSTALLED="yes" if installed else "no",
               FAKE_UID=uid, FAIL_APT=fail, COMMAND_LOG=str(log))
    result = subprocess.run(
        [BASH, str(ROOT / "scripts/ci_node26_prerequisites.sh")],
        env=env, capture_output=True, text=True, check=False,
    )
    return result, log.read_text().splitlines() if log.exists() else []


@pytest.mark.parametrize("system", ["Darwin", "MINGW64_NT"])
def test_non_linux_skips_all_package_commands(tmp_path, system):
    result, commands = run_helper(tmp_path, system=system)
    assert result.returncode == 0, result.stderr
    assert commands == []


def test_installed_runtime_needs_no_network_or_privilege(tmp_path):
    result, commands = run_helper(tmp_path, installed=True)
    assert result.returncode == 0, result.stderr
    assert commands == ["query"]


@pytest.mark.parametrize("uid", ["0", "1000"])
def test_missing_runtime_installs_noninteractively_as_root_or_sudo(tmp_path, uid):
    result, commands = run_helper(tmp_path, uid=uid)
    assert result.returncode == 0, result.stderr
    assert [c for c in commands if c.startswith("apt ")] == [
        "apt noninteractive update",
        "apt noninteractive install -y --no-install-recommends libatomic1",
    ]
    sudo = [c for c in commands if c.startswith("sudo ")]
    assert len(sudo) == (0 if uid == "0" else 2)
    assert all(c.startswith("sudo -n env DEBIAN_FRONTEND=noninteractive apt-get ") for c in sudo)


@pytest.mark.parametrize("fail", ["update", "install"])
def test_dependency_errors_propagate(tmp_path, fail):
    result, commands = run_helper(tmp_path, fail=fail)
    assert result.returncode == 42
    if fail == "update":
        assert not any("apt noninteractive install" in c for c in commands)

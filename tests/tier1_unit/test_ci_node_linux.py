"""Exercise the Linux Node gate with fake commands and a local tarball, never the network."""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(
    os.name == "nt" or not BASH, reason="requires native Bash, tar and sha256sum"
)

SCRIPT = ROOT / "scripts" / "ci_node_linux.sh"

# The stub answers the gate the way real Node does: `--version`, and `-e <program> <major>
# <minor>` for the range probe (`node -e` puts the program in $2 and the operands after it).
# NODE_BODY takes the shell expression the stub evaluates as its own version, so a fixture can
# pin the version it installs while the host stub keeps reporting $FAKE_NODE_VERSION.
NODE_BODY = """#!/bin/sh
version={version}
printf 'node %s %s\\n' "$version" "$*" >> "$COMMAND_LOG"
case "$1" in
  --version) echo "v$version" ;;
  -e)
    major=${{version%%.*}}; rest=${{version#*.}}; minor=${{rest%%.*}}
    [ "$major" = "$3" ] && [ "$minor" -ge "$4" ] && exit 0
    exit 1
    ;;
esac
exit 0
"""

CURL_BODY = """#!/bin/sh
# Serve fixtures for `-o <file> <url>`; FAKE_CURL_FAILS counts refused attempts first.
out=""
url=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    --*) shift ;;
    *) url="$1"; shift ;;
  esac
done
printf 'curl %s\\n' "$url" >> "$COMMAND_LOG"
count=$(cat "$FAKE_CURL_STATE" 2>/dev/null || echo 0)
count=$((count + 1))
printf '%s' "$count" > "$FAKE_CURL_STATE"
if [ "$count" -le "${FAKE_CURL_FAILS:-0}" ]; then
  exit 22
fi
cp "$FAKE_DIST/$(basename "$url")" "$out" 2>/dev/null || exit 22
"""

ARCHIVE = "node-v24.11.1-linux-x64.tar.gz"


def make_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def build_dist(tmp_path: Path, *, checksum: str | None = None) -> Path:
    """Publish the SHASUMS256.txt and the archive the gate would fetch from nodejs.org."""
    stage = tmp_path / "stage" / "node-v24.11.1-linux-x64" / "bin"
    stage.mkdir(parents=True)
    for name in ("node", "npm", "npx"):
        make_executable(stage / name, NODE_BODY.format(version="24.11.1"))
    dist = tmp_path / "dist"
    dist.mkdir()
    archive = dist / ARCHIVE
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(stage.parent, arcname=stage.parent.name)
    digest = checksum or subprocess.run(
        ["sha256sum", archive.as_posix()], capture_output=True, text=True, check=True
    ).stdout.split()[0]
    (dist / "SHASUMS256.txt").write_text(
        f"{digest}  {ARCHIVE}\n{digest}  node-v24.11.1-linux-x64.tar.xz\n", encoding="utf-8"
    )
    return dist


def run_gate(
    tmp_path: Path,
    *,
    version: str | None,
    system: str = "Linux",
    fails: int = 0,
    checksum: str | None = None,
):
    stubs = tmp_path / "stub"
    stubs.mkdir()
    make_executable(
        stubs / "uname",
        '#!/bin/sh\nif [ "$1" = -s ]; then echo "$FAKE_SYSTEM"; else echo x86_64; fi\n',
    )
    make_executable(stubs / "curl", CURL_BODY)
    make_executable(stubs / "sleep", "#!/bin/sh\nexit 0\n")
    if version is not None:
        for name in ("node", "npm", "npx"):
            make_executable(stubs / name, NODE_BODY.format(version="$FAKE_NODE_VERSION"))
    log = tmp_path / "commands.log"
    log.write_text("", encoding="utf-8")
    path_file = tmp_path / "github_path"
    path_file.write_text("", encoding="utf-8")
    env = dict(
        os.environ,
        PATH=f"{stubs.as_posix()}:/usr/bin:/bin",
        FAKE_SYSTEM=system,
        FAKE_NODE_VERSION=version or "",
        FAKE_DIST=build_dist(tmp_path, checksum=checksum).as_posix(),
        FAKE_CURL_STATE=(tmp_path / "curl.count").as_posix(),
        FAKE_CURL_FAILS=str(fails),
        COMMAND_LOG=log.as_posix(),
        GITHUB_PATH=path_file.as_posix(),
        RUNNER_TOOL_CACHE=(tmp_path / "toolcache").as_posix(),
    )
    result = subprocess.run(
        [BASH, SCRIPT.as_posix(), "24", "11", "3"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, log.read_text().splitlines(), path_file.read_text()


def test_non_linux_leaves_the_toolchain_alone(tmp_path):
    result, commands, path_file = run_gate(tmp_path, version=None, system="Darwin")
    assert result.returncode == 0, result.stderr
    assert commands == []
    assert path_file == ""


def test_satisfied_toolchain_never_touches_the_network(tmp_path):
    result, commands, path_file = run_gate(tmp_path, version="24.12.3")
    assert result.returncode == 0, result.stderr
    assert [line for line in commands if line.startswith("curl")] == []
    assert path_file == ""
    assert "node v24.12.3" in result.stdout


def test_wrong_major_is_replaced_from_the_published_checksum_list(tmp_path):
    result, commands, path_file = run_gate(tmp_path, version="26.0.0")
    assert result.returncode == 0, result.stderr
    assert "curl https://nodejs.org/dist/latest-v24.x/SHASUMS256.txt" in commands
    # The gate must prove the provisioned toolchain, not the one setup-node claimed.
    assert any(line.startswith("node 24.11.1") for line in commands)
    installed = path_file.strip()
    assert installed.endswith("/node-v24.11.1-linux-x64/bin"), path_file
    assert (Path(installed) / "npx").is_file()


def test_one_stalled_attempt_is_retried_and_recovers(tmp_path):
    result, commands, path_file = run_gate(tmp_path, version="26.0.0", fails=1)
    assert result.returncode == 0, result.stderr
    assert "Node download attempt 1/3 failed" in result.stdout
    assert path_file.strip().endswith("/node-v24.11.1-linux-x64/bin")


def test_checksum_mismatch_never_installs_anything(tmp_path):
    result, commands, path_file = run_gate(tmp_path, version="26.0.0", checksum="0" * 64)
    assert result.returncode == 1
    assert "sha256 mismatch" in result.stdout
    assert path_file == ""
    assert "::error::no Node 24.11 toolchain" in result.stdout


def test_dead_egress_fails_closed_after_every_attempt(tmp_path):
    result, commands, path_file = run_gate(tmp_path, version=None, fails=99)
    assert result.returncode == 1
    assert "Node download attempt 3/3 failed" in result.stdout
    assert path_file == ""
    assert "::error::no Node 24.11 toolchain after 3 attempts" in result.stdout

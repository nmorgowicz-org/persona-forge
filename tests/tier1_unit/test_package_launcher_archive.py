"""Test scripts/package_launcher_archive.py: the Phase 7 launcher-archive assembler.

`uv pip compile` is monkeypatched to fake requirements-file resolution, matching the
subprocess-mocking convention in test_ci_isolated_install.py - no real cross-compiled binaries or
network access needed.
"""

from __future__ import annotations

import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

import scripts.package_launcher_archive as pla


def _fake_uv_pip_compile_ok(cmd, capture_output=True, text=True):
    out_path = Path(cmd[cmd.index("-o") + 1])
    out_path.write_text("persona-forge==1.3.0\n", encoding="utf-8")
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def _fake_uv_pip_compile_fails(cmd, capture_output=True, text=True):
    return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="no solution found")


@pytest.fixture
def inputs(tmp_path: Path) -> dict[str, Path]:
    launcher = tmp_path / "persona-forge-launcher"
    launcher.write_bytes(b"stub-launcher")
    uv_bin = tmp_path / "uv"
    uv_bin.write_bytes(b"stub-uv")
    wheel = tmp_path / "persona_forge-1.3.0-py3-none-any.whl"
    wheel.write_bytes(b"stub-wheel")
    return {"launcher": launcher, "uv": uv_bin, "wheel": wheel}


def test_missing_launcher_binary_fails_closed(tmp_path: Path, inputs: dict[str, Path]) -> None:
    code = pla.main(
        [
            "--target", "x86_64-unknown-linux-musl",
            "--version", "1.3.0",
            "--launcher-binary", str(tmp_path / "does-not-exist"),
            "--uv-binary", str(inputs["uv"]),
            "--uv-version", "0.12.9",
            "--wheel", str(inputs["wheel"]),
            "--out-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 1


def test_missing_wheel_fails_closed(tmp_path: Path, inputs: dict[str, Path]) -> None:
    code = pla.main(
        [
            "--target", "x86_64-unknown-linux-musl",
            "--version", "1.3.0",
            "--launcher-binary", str(inputs["launcher"]),
            "--uv-binary", str(inputs["uv"]),
            "--uv-version", "0.12.9",
            "--wheel", str(tmp_path / "does-not-exist.whl"),
            "--out-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 1


def test_uv_pip_compile_failure_raises(tmp_path: Path, inputs: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pla.subprocess, "run", _fake_uv_pip_compile_fails)
    with pytest.raises(SystemExit):
        pla.main(
            [
                "--target", "x86_64-unknown-linux-musl",
                "--version", "1.3.0",
                "--launcher-binary", str(inputs["launcher"]),
                "--uv-binary", str(inputs["uv"]),
                "--uv-version", "0.12.9",
                "--wheel", str(inputs["wheel"]),
                "--out-dir", str(tmp_path / "out"),
            ]
        )


@pytest.mark.parametrize(
    "target,expected_launcher,expected_uv,archive_suffix",
    [
        ("x86_64-unknown-linux-musl", "persona-forge-launcher", "uv", ".tar.gz"),
        ("x86_64-pc-windows-gnu", "persona-forge-launcher.exe", "uv.exe", ".zip"),
    ],
)
def test_builds_archive_with_expected_members(
    tmp_path: Path,
    inputs: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    expected_launcher: str,
    expected_uv: str,
    archive_suffix: str,
) -> None:
    monkeypatch.setattr(pla.subprocess, "run", _fake_uv_pip_compile_ok)
    out_dir = tmp_path / "out"

    code = pla.main(
        [
            "--target", target,
            "--version", "1.3.0",
            "--launcher-binary", str(inputs["launcher"]),
            "--uv-binary", str(inputs["uv"]),
            "--uv-version", "0.12.9",
            "--wheel", str(inputs["wheel"]),
            "--out-dir", str(out_dir),
        ]
    )
    assert code == 0

    asset_stem = pla.TARGETS[target][0]
    archive_path = out_dir / f"persona-forge-bootstrap-{asset_stem}{archive_suffix}"
    assert archive_path.is_file()

    if archive_suffix == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            names = set(zf.namelist())
            manifest = json.loads(zf.read("manifest.json"))
    else:
        with tarfile.open(archive_path, "r:gz") as tf:
            names = {m.name for m in tf.getmembers()}
            manifest_fh = tf.extractfile("manifest.json")
            assert manifest_fh is not None
            manifest = json.loads(manifest_fh.read())

    assert expected_launcher in names
    assert expected_uv in names
    assert inputs["wheel"].name in names
    assert f"requirements-{target}.txt" in names
    assert "README.txt" in names

    assert manifest["schema_version"] == 1
    assert manifest["app"] == "persona-forge"
    assert manifest["version"] == "1.3.0"
    assert manifest["target"] == target
    assert manifest["wheel"]["file"] == inputs["wheel"].name
    assert manifest["uv"]["file"] == expected_uv
    assert manifest["uv"]["version"] == "0.12.9"
    assert manifest["requirements_file"] == f"requirements-{target}.txt"


def test_staging_dir_is_cleaned_up_on_success(tmp_path: Path, inputs: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pla.subprocess, "run", _fake_uv_pip_compile_ok)
    out_dir = tmp_path / "out"

    pla.main(
        [
            "--target", "x86_64-unknown-linux-musl",
            "--version", "1.3.0",
            "--launcher-binary", str(inputs["launcher"]),
            "--uv-binary", str(inputs["uv"]),
            "--uv-version", "0.12.9",
            "--wheel", str(inputs["wheel"]),
            "--out-dir", str(out_dir),
        ]
    )

    assert not (out_dir / ".staging-x86_64-unknown-linux-musl").exists()

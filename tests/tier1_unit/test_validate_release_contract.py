"""Test scripts/validate_release_contract.py: the Phase 7 fail-closed release-set validator.

Covers Gate 7's required self-test categories: a clean positive release, a missing top-level
asset, an extra top-level asset, a checksums.json hash mismatch, and a bootstrap archive that is
missing one of its own required members.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.validate_release_contract import main

VERSION = "1.3.0"

BOOTSTRAP_MEMBERS = {
    "persona-forge-bootstrap-linux-x86_64.tar.gz": ("persona-forge-launcher", "uv"),
    "persona-forge-bootstrap-linux-aarch64.tar.gz": ("persona-forge-launcher", "uv"),
    "persona-forge-bootstrap-windows-x86_64.zip": ("persona-forge-launcher.exe", "uv.exe"),
    "persona-forge-bootstrap-macos-aarch64.tar.gz": ("persona-forge-launcher", "uv"),
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_bootstrap_archive(
    path: Path, wheel_name: str, wheel_bytes: bytes, drop_members: frozenset[str] = frozenset()
) -> None:
    launcher_name, uv_name = BOOTSTRAP_MEMBERS[path.name]
    target = path.name.replace("persona-forge-bootstrap-", "").rsplit(".", 1)[0]
    if target.endswith(".tar"):
        target = target[: -len(".tar")]
    manifest = {
        "schema_version": 1,
        "app": "persona-forge",
        "version": VERSION,
        "target": target,
        "python_constraint": ">=3.13,<3.14",
        "wheel": {"file": wheel_name, "sha256": _sha256_bytes(wheel_bytes)},
        "uv": {"file": uv_name, "sha256": "uvsha", "version": "0.12.9"},
        "requirements_file": f"requirements-{target}.txt",
        "requirements_sha256": "reqsha",
    }
    members = {
        launcher_name: b"stub-launcher",
        uv_name: b"stub-uv",
        wheel_name: wheel_bytes,
        f"requirements-{target}.txt": b"persona-forge==1.3.0\n",
        "manifest.json": json.dumps(manifest, indent=2).encode(),
        "README.txt": b"readme",
    }
    for name in drop_members:
        members.pop(name, None)

    if path.suffix == ".zip":
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in members.items():
                zf.writestr(name, data)
    else:
        with tarfile.open(path, "w:gz") as tf:
            for name, data in members.items():
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))


def _make_clean_release(release_dir: Path) -> dict[str, bytes]:
    release_dir.mkdir(parents=True, exist_ok=True)
    wheel_name = f"persona_forge-{VERSION}-py3-none-any.whl"
    sdist_name = f"persona_forge-{VERSION}.tar.gz"

    contents: dict[str, bytes] = {
        wheel_name: b"wheel-bytes",
        sdist_name: b"sdist-bytes",
    }
    for asset in BOOTSTRAP_MEMBERS:
        (release_dir / asset).write_bytes(b"")  # placeholder, overwritten below
    for f in [wheel_name, sdist_name]:
        (release_dir / f).write_bytes(contents[f])

    for asset in BOOTSTRAP_MEMBERS:
        _write_bootstrap_archive(release_dir / asset, wheel_name, contents[wheel_name])
        contents[asset] = (release_dir / asset).read_bytes()

    checksums = {"checksums": {name: _sha256_bytes(data) for name, data in contents.items()}}
    (release_dir / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    contents["checksums.json"] = (release_dir / "checksums.json").read_bytes()
    return contents


def test_clean_release_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    release_dir = tmp_path / "release"
    _make_clean_release(release_dir)

    code = main(["--dir", str(release_dir), "--version", VERSION])

    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "pass"
    assert out["failures"] == []


def test_missing_top_level_asset_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    release_dir = tmp_path / "release"
    _make_clean_release(release_dir)
    (release_dir / "persona-forge-bootstrap-windows-x86_64.zip").unlink()
    checksums = json.loads((release_dir / "checksums.json").read_text())
    checksums["checksums"].pop("persona-forge-bootstrap-windows-x86_64.zip")
    (release_dir / "checksums.json").write_text(json.dumps(checksums), encoding="utf-8")

    code = main(["--dir", str(release_dir), "--version", VERSION])

    assert code == 1
    out = json.loads(capsys.readouterr().out)
    assert any("missing release asset" in f for f in out["failures"])


def test_extra_top_level_asset_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    release_dir = tmp_path / "release"
    _make_clean_release(release_dir)
    (release_dir / "unexpected-extra-file.bin").write_bytes(b"nope")

    code = main(["--dir", str(release_dir), "--version", VERSION])

    assert code == 1
    out = json.loads(capsys.readouterr().out)
    assert any("unexpected extra release asset" in f for f in out["failures"])


def test_checksum_mismatch_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    release_dir = tmp_path / "release"
    _make_clean_release(release_dir)
    checksums = json.loads((release_dir / "checksums.json").read_text())
    sdist_name = f"persona_forge-{VERSION}.tar.gz"
    checksums["checksums"][sdist_name] = "0" * 64
    (release_dir / "checksums.json").write_text(json.dumps(checksums), encoding="utf-8")

    code = main(["--dir", str(release_dir), "--version", VERSION])

    assert code == 1
    out = json.loads(capsys.readouterr().out)
    assert any("checksums.json sha256" in f for f in out["failures"])


def test_archive_missing_internal_member_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    release_dir = tmp_path / "release"
    wheel_name = f"persona_forge-{VERSION}-py3-none-any.whl"
    sdist_name = f"persona_forge-{VERSION}.tar.gz"

    contents: dict[str, bytes] = {wheel_name: b"wheel-bytes", sdist_name: b"sdist-bytes"}
    release_dir.mkdir(parents=True)
    for f, data in contents.items():
        (release_dir / f).write_bytes(data)

    for asset in BOOTSTRAP_MEMBERS:
        drop = frozenset({"README.txt"}) if asset == "persona-forge-bootstrap-linux-x86_64.tar.gz" else frozenset()
        _write_bootstrap_archive(release_dir / asset, wheel_name, contents[wheel_name], drop_members=drop)
        contents[asset] = (release_dir / asset).read_bytes()

    checksums = {"checksums": {name: _sha256_bytes(data) for name, data in contents.items()}}
    (release_dir / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")

    code = main(["--dir", str(release_dir), "--version", VERSION])

    assert code == 1
    out = json.loads(capsys.readouterr().out)
    assert any(
        "persona-forge-bootstrap-linux-x86_64.tar.gz: missing member" in f and "README.txt" in f
        for f in out["failures"]
    )


def test_missing_release_dir_fails(tmp_path: Path) -> None:
    code = main(["--dir", str(tmp_path / "does-not-exist"), "--version", VERSION])
    assert code == 1

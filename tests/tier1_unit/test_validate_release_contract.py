"""Test scripts/validate_release_contract.py: the Phase 7 fail-closed release-set validator.

Tests cover a clean release, missing and legacy assets, checksum/manifest integrity, and signed
desktop update feed metadata.
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
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_bootstrap_archive(
    path: Path,
    wheel_name: str,
    wheel_bytes: bytes,
    drop_members: frozenset[str] = frozenset(),
    corrupt_accelerator: str | None = None,
) -> None:
    launcher_name, uv_name = BOOTSTRAP_MEMBERS[path.name]
    target = "x86_64-unknown-linux-gnu"
    requirements_name = f"requirements-{target}.txt"
    requirements_bytes = b"persona-forge==1.3.0\n"
    accelerator_bytes = {
        extra: f"persona-forge[{extra}]==1.3.0\n".encode()
        for extra in ("cuda12", "cuda13", "xpu", "rocm")
    }
    manifest = {
        "schema_version": 1,
        "app": "persona-forge",
        "version": VERSION,
        "target": target,
        "python_constraint": ">=3.13,<3.14",
        "wheel": {"file": wheel_name, "sha256": _sha256_bytes(wheel_bytes)},
        "uv": {"file": uv_name, "sha256": "uvsha", "version": "0.12.9"},
        "requirements_file": requirements_name,
        "requirements_sha256": _sha256_bytes(requirements_bytes),
        "accelerator_requirements": {
            extra: _sha256_bytes(data) for extra, data in accelerator_bytes.items()
        },
    }
    members = {
        launcher_name: b"stub-launcher",
        uv_name: b"stub-uv",
        wheel_name: wheel_bytes,
        requirements_name: requirements_bytes,
        "manifest.json": json.dumps(manifest, indent=2).encode(),
        "README.txt": b"readme",
    }
    for extra, data in accelerator_bytes.items():
        members[f"requirements-{target}-{extra}.txt"] = data
    if corrupt_accelerator:
        members[f"requirements-{target}-{corrupt_accelerator}.txt"] = b"corrupted\n"
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
        "PersonaForge-macos-aarch64.dmg": b"dmg-image",
        "PersonaForge-windows-x86_64-setup.exe": b"windows-installer",
        "PersonaForge-linux-x86_64.AppImage": b"linux-appimage",
        "PersonaForge-windows-x86_64-setup.exe.sig": b"windows-signature",
        "PersonaForge-linux-x86_64.AppImage.sig": b"linux-signature",
    }
    for name, data in contents.items():
        (release_dir / name).write_bytes(data)
    archive = "persona-forge-bootstrap-linux-x86_64.tar.gz"
    _write_bootstrap_archive(release_dir / archive, wheel_name, contents[wheel_name])
    contents[archive] = (release_dir / archive).read_bytes()
    dmg = release_dir / "PersonaForge-macos-aarch64.dmg"
    (release_dir / "appcast.xml").write_text(
        '<?xml version="1.0"?><rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">'
        '<channel><item><description sparkle:format="markdown"><![CDATA[Release notes]]></description>'
        '<enclosure url="https://example/release/PersonaForge-macos-aarch64.dmg" '
        f'length="{dmg.stat().st_size}" sparkle:version="{VERSION}" '
        f'sparkle:shortVersionString="{VERSION}" sparkle:edSignature="dmg-signature"/></item></channel></rss>',
        encoding="utf-8",
    )
    contents["appcast.xml"] = (release_dir / "appcast.xml").read_bytes()
    (release_dir / "latest.json").write_text(
        json.dumps({
            "pub_date": "2026-09-27T00:00:00Z",
            "notes": "Release notes",
            "version": VERSION,
            "platforms": {
                "windows-x86_64-nsis": {
                    "url": "https://example/release/PersonaForge-windows-x86_64-setup.exe",
                    "signature": "windows-signature",
                },
                "linux-x86_64-appimage": {
                    "url": "https://example/release/PersonaForge-linux-x86_64.AppImage",
                    "signature": "linux-signature",
                },
            },
        }),
        encoding="utf-8",
    )
    contents["latest.json"] = (release_dir / "latest.json").read_bytes()
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


def test_tauri_notes_reject_a_release_page_url(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    release_dir = tmp_path / "release"
    _make_clean_release(release_dir)
    latest_path = release_dir / "latest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest["notes"] = "https://example/release/notes"
    latest_path.write_text(json.dumps(latest), encoding="utf-8")

    code = main(["--dir", str(release_dir), "--version", VERSION])

    assert code == 1
    out = json.loads(capsys.readouterr().out)
    assert "latest.json notes must contain release notes text, not a URL" in out["failures"]


def test_missing_desktop_asset_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    release_dir = tmp_path / "release"
    _make_clean_release(release_dir)
    (release_dir / "PersonaForge-macos-aarch64.dmg").unlink()
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


@pytest.mark.parametrize(
    "legacy_archive",
    [
        "persona-forge-bootstrap-macos-aarch64.tar.gz",
        "persona-forge-bootstrap-windows-x86_64.zip",
    ],
)
def test_legacy_desktop_bootstrap_archives_are_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], legacy_archive: str
) -> None:
    release_dir = tmp_path / "release"
    _make_clean_release(release_dir)
    (release_dir / legacy_archive).write_bytes(b"legacy")
    assert main(["--dir", str(release_dir), "--version", VERSION]) == 1
    out = json.loads(capsys.readouterr().out)
    assert any("unexpected extra release asset" in f for f in out["failures"])


def test_latest_json_version_mismatch_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    release_dir = tmp_path / "release"
    _make_clean_release(release_dir)
    latest = json.loads((release_dir / "latest.json").read_text())
    latest["version"] = "9.9.9"
    (release_dir / "latest.json").write_text(json.dumps(latest))
    assert main(["--dir", str(release_dir), "--version", VERSION]) == 1
    out = json.loads(capsys.readouterr().out)
    assert any("latest.json version" in f for f in out["failures"])


def test_latest_json_signature_mismatch_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    release_dir = tmp_path / "release"
    _make_clean_release(release_dir)
    latest = json.loads((release_dir / "latest.json").read_text())
    latest["platforms"]["linux-x86_64-appimage"]["signature"] = "wrong-signature"
    (release_dir / "latest.json").write_text(json.dumps(latest))
    assert main(["--dir", str(release_dir), "--version", VERSION]) == 1
    out = json.loads(capsys.readouterr().out)
    assert any("signature does not match" in f for f in out["failures"])


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


def test_archive_missing_accelerator_requirements_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    release_dir = tmp_path / "release"
    contents = _make_clean_release(release_dir)
    archive = release_dir / "persona-forge-bootstrap-linux-x86_64.tar.gz"
    wheel_name = f"persona_forge-{VERSION}-py3-none-any.whl"
    _write_bootstrap_archive(
        archive,
        wheel_name,
        contents[wheel_name],
        drop_members=frozenset({"requirements-x86_64-unknown-linux-gnu-cuda13.txt"}),
    )

    assert main(["--dir", str(release_dir), "--version", VERSION]) == 1
    out = json.loads(capsys.readouterr().out)
    assert any("requirements members" in failure and "cuda13" in failure for failure in out["failures"])


def test_archive_accelerator_requirements_hash_mismatch_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    release_dir = tmp_path / "release"
    contents = _make_clean_release(release_dir)
    archive = release_dir / "persona-forge-bootstrap-linux-x86_64.tar.gz"
    wheel_name = f"persona_forge-{VERSION}-py3-none-any.whl"
    _write_bootstrap_archive(archive, wheel_name, contents[wheel_name], corrupt_accelerator="cuda13")

    assert main(["--dir", str(release_dir), "--version", VERSION]) == 1
    out = json.loads(capsys.readouterr().out)
    assert any("cuda13.txt sha256 does not match manifest" in failure for failure in out["failures"])


def test_missing_release_dir_fails(tmp_path: Path) -> None:
    code = main(["--dir", str(tmp_path / "does-not-exist"), "--version", VERSION])
    assert code == 1

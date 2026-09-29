"""Test scripts/generate_update_feeds.py (execution plan Phase 6B, Gate 6B).

Never skipped: a missing capable OpenSSL is a test failure, not a skip (Gate 6B requires zero
skipped tests). Set OPENSSL to a real OpenSSL 3 build if the system default is LibreSSL (macOS):
`OPENSSL=/opt/homebrew/bin/openssl pytest tests/tier1_unit/test_generate_update_feeds.py`.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts.generate_update_feeds import (
    DMG_ASSET,
    LINUX_ASSET,
    WINDOWS_ASSET,
    FeedGenerationError,
    build_appcast_xml,
    generate,
    main,
)

VERSION = "90.0.1"
TAG = "desktop-updater-test"
REPO = "nmorgowicz-org/persona-forge"
NOTES_URL = "https://github.com/nmorgowicz-org/persona-forge/releases/tag/desktop-updater-test"
RELEASE_NOTES = (
    "## Bug Fixes\n\n* **release:** validate the launcher requirements set.\n"
)


def _openssl_bin() -> str:
    return os.environ.get("OPENSSL", "openssl")


def _new_seed_b64() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def _derive_public_key_pem(seed_b64: str, tmp_path: Path) -> Path:
    """Uses the module's own seed->PEM conversion so the test proves the real signing path."""
    from scripts.generate_update_feeds import _seed_to_pem

    key_pem = tmp_path / "probe-key.pem"
    key_pem.write_text(_seed_to_pem(seed_b64), encoding="utf-8")
    pub_pem = tmp_path / "probe-pub.pem"
    subprocess.run(
        [_openssl_bin(), "pkey", "-in", str(key_pem), "-pubout", "-out", str(pub_pem)],
        check=True,
        capture_output=True,
    )
    return pub_pem


def _populate_release_dir(release_dir: Path) -> None:
    release_dir.mkdir(parents=True, exist_ok=True)
    (release_dir.parent / "release-notes.md").write_text(
        RELEASE_NOTES, encoding="utf-8"
    )
    (release_dir / DMG_ASSET).write_bytes(secrets.token_bytes(4096))
    (release_dir / WINDOWS_ASSET).write_bytes(secrets.token_bytes(2048))
    (release_dir / f"{WINDOWS_ASSET}.sig").write_text(
        "fake-windows-minisign-signature==\n", encoding="utf-8"
    )
    (release_dir / LINUX_ASSET).write_bytes(secrets.token_bytes(2048))
    (release_dir / f"{LINUX_ASSET}.sig").write_text(
        "fake-linux-minisign-signature==\n", encoding="utf-8"
    )


def test_appcast_signature_verifies_with_openssl(tmp_path: Path) -> None:
    seed_b64 = _new_seed_b64()
    release_dir = tmp_path / "release"
    _populate_release_dir(release_dir)

    generate(
        release_dir=release_dir,
        version=VERSION,
        tag=TAG,
        repo=REPO,
        notes_url=NOTES_URL,
        release_notes=RELEASE_NOTES,
        sparkle_seed_b64=seed_b64,
    )

    appcast = (release_dir / "appcast.xml").read_text(encoding="utf-8")
    import re

    match = re.search(r'sparkle:edSignature="([^"]+)"', appcast)
    assert match is not None, f"no sparkle:edSignature in appcast.xml: {appcast}"
    signature = base64.b64decode(match.group(1))

    pub_pem = _derive_public_key_pem(seed_b64, tmp_path)
    sig_file = tmp_path / "verify.sig"
    sig_file.write_bytes(signature)

    result = subprocess.run(
        [
            _openssl_bin(),
            "pkeyutl",
            "-verify",
            "-rawin",
            "-pubin",
            "-inkey",
            str(pub_pem),
            "-in",
            str(release_dir / DMG_ASSET),
            "-sigfile",
            str(sig_file),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"openssl pkeyutl -verify failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_appcast_contains_required_fields(tmp_path: Path) -> None:
    seed_b64 = _new_seed_b64()
    release_dir = tmp_path / "release"
    _populate_release_dir(release_dir)

    generate(
        release_dir=release_dir,
        version=VERSION,
        tag=TAG,
        repo=REPO,
        notes_url=NOTES_URL,
        release_notes=RELEASE_NOTES,
        sparkle_seed_b64=seed_b64,
    )

    appcast = (release_dir / "appcast.xml").read_text(encoding="utf-8")
    expected_url = f"https://github.com/{REPO}/releases/download/{TAG}/{DMG_ASSET}"
    assert expected_url in appcast
    assert f'sparkle:version="{VERSION}"' in appcast
    assert f'sparkle:shortVersionString="{VERSION}"' in appcast
    assert 'sparkle:minimumSystemVersion="14.0"' in appcast
    dmg_length = (release_dir / DMG_ASSET).stat().st_size
    assert f'length="{dmg_length}"' in appcast
    assert "sparkle:releaseNotesLink" not in appcast
    item = ET.fromstring(appcast).find("./channel/item")
    assert item is not None
    description = item.find("description")
    assert description is not None
    assert (
        description.get("{http://www.andymatuschak.org/xml-namespaces/sparkle}format")
        == "markdown"
    )
    assert description.text == RELEASE_NOTES


def test_appcast_preserves_cdata_terminators_in_release_notes() -> None:
    release_notes = "Notes may contain the CDATA terminator: ]]> safely."
    appcast = build_appcast_xml(
        version=VERSION,
        dmg_url="https://example.com/update.dmg",
        dmg_length=1,
        ed_signature="signature",
        release_notes=release_notes,
    )

    item = ET.fromstring(appcast).find("./channel/item")
    assert item is not None
    description = item.find("description")
    assert description is not None
    assert description.text == release_notes


def test_appcast_rejects_empty_release_notes() -> None:
    with pytest.raises(FeedGenerationError, match="release notes must not be empty"):
        build_appcast_xml(
            version=VERSION,
            dmg_url="https://example.com/update.dmg",
            dmg_length=1,
            ed_signature="signature",
            release_notes=" \n",
        )


def test_latest_json_has_required_keys_and_matching_version(tmp_path: Path) -> None:
    seed_b64 = _new_seed_b64()
    release_dir = tmp_path / "release"
    _populate_release_dir(release_dir)

    generate(
        release_dir=release_dir,
        version=VERSION,
        tag=TAG,
        repo=REPO,
        notes_url=NOTES_URL,
        release_notes=RELEASE_NOTES,
        sparkle_seed_b64=seed_b64,
    )

    latest = json.loads((release_dir / "latest.json").read_text(encoding="utf-8"))
    assert latest["version"] == VERSION

    appcast = (release_dir / "appcast.xml").read_text(encoding="utf-8")
    assert f'sparkle:version="{latest["version"]}"' in appcast

    assert "pub_date" in latest
    assert "notes" in latest
    assert latest["notes"] == NOTES_URL

    platforms = latest["platforms"]
    assert set(platforms) == {"windows-x86_64-nsis", "linux-x86_64-appimage"}
    for key, asset_name in (
        ("windows-x86_64-nsis", WINDOWS_ASSET),
        ("linux-x86_64-appimage", LINUX_ASSET),
    ):
        entry = platforms[key]
        assert entry["url"] == f"https://github.com/{REPO}/releases/download/{TAG}/{asset_name}"
        assert entry["signature"]
        sig_on_disk = (release_dir / f"{asset_name}.sig").read_text(encoding="utf-8").strip()
        assert entry["signature"] == sig_on_disk


@pytest.mark.parametrize(
    "missing_name",
    [DMG_ASSET, WINDOWS_ASSET, LINUX_ASSET, f"{WINDOWS_ASSET}.sig", f"{LINUX_ASSET}.sig"],
)
def test_each_missing_asset_raises(tmp_path: Path, missing_name: str) -> None:
    seed_b64 = _new_seed_b64()
    release_dir = tmp_path / "release"
    _populate_release_dir(release_dir)
    (release_dir / missing_name).unlink()

    with pytest.raises(FeedGenerationError, match="missing release asset"):
        generate(
            release_dir=release_dir,
            version=VERSION,
            tag=TAG,
            repo=REPO,
            notes_url=NOTES_URL,
            release_notes=RELEASE_NOTES,
            sparkle_seed_b64=seed_b64,
        )


def test_empty_signature_file_raises(tmp_path: Path) -> None:
    seed_b64 = _new_seed_b64()
    release_dir = tmp_path / "release"
    _populate_release_dir(release_dir)
    (release_dir / f"{WINDOWS_ASSET}.sig").write_text("", encoding="utf-8")

    with pytest.raises(FeedGenerationError, match="empty signature file"):
        generate(
            release_dir=release_dir,
            version=VERSION,
            tag=TAG,
            repo=REPO,
            notes_url=NOTES_URL,
            release_notes=RELEASE_NOTES,
            sparkle_seed_b64=seed_b64,
        )


def test_empty_dmg_raises(tmp_path: Path) -> None:
    seed_b64 = _new_seed_b64()
    release_dir = tmp_path / "release"
    _populate_release_dir(release_dir)
    (release_dir / DMG_ASSET).write_bytes(b"")

    with pytest.raises(FeedGenerationError, match="empty"):
        generate(
            release_dir=release_dir,
            version=VERSION,
            tag=TAG,
            repo=REPO,
            notes_url=NOTES_URL,
            release_notes=RELEASE_NOTES,
            sparkle_seed_b64=seed_b64,
        )


def test_seed_that_does_not_decode_to_32_bytes_raises(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    _populate_release_dir(release_dir)
    short_seed = base64.b64encode(secrets.token_bytes(16)).decode("ascii")

    with pytest.raises(FeedGenerationError, match="32 bytes"):
        generate(
            release_dir=release_dir,
            version=VERSION,
            tag=TAG,
            repo=REPO,
            notes_url=NOTES_URL,
            release_notes=RELEASE_NOTES,
            sparkle_seed_b64=short_seed,
        )


def test_no_key_material_appears_in_generated_files(tmp_path: Path) -> None:
    seed_b64 = _new_seed_b64()
    release_dir = tmp_path / "release"
    _populate_release_dir(release_dir)

    generate(
        release_dir=release_dir,
        version=VERSION,
        tag=TAG,
        repo=REPO,
        notes_url=NOTES_URL,
        release_notes=RELEASE_NOTES,
        sparkle_seed_b64=seed_b64,
    )

    appcast = (release_dir / "appcast.xml").read_text(encoding="utf-8")
    latest = (release_dir / "latest.json").read_text(encoding="utf-8")
    assert seed_b64 not in appcast
    assert seed_b64 not in latest
    # No leftover temp key/sig files in the release dir itself.
    leftover = {p.name for p in release_dir.iterdir()}
    assert leftover == {
        DMG_ASSET,
        WINDOWS_ASSET,
        f"{WINDOWS_ASSET}.sig",
        LINUX_ASSET,
        f"{LINUX_ASSET}.sig",
        "appcast.xml",
        "latest.json",
    }


def test_no_key_material_appears_in_stdout_or_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed_b64 = _new_seed_b64()
    release_dir = tmp_path / "release"
    _populate_release_dir(release_dir)

    old_env = os.environ.get("SPARKLE_ED_PRIVATE_KEY")
    os.environ["SPARKLE_ED_PRIVATE_KEY"] = seed_b64
    try:
        code = main(
            [
                "--release-dir",
                str(release_dir),
                "--version",
                VERSION,
                "--tag",
                TAG,
                "--repo",
                REPO,
                "--notes-url",
                NOTES_URL,
                "--release-notes-file",
                str(release_dir.parent / "release-notes.md"),
            ]
        )
    finally:
        if old_env is None:
            os.environ.pop("SPARKLE_ED_PRIVATE_KEY", None)
        else:
            os.environ["SPARKLE_ED_PRIVATE_KEY"] = old_env

    assert code == 0
    captured = capsys.readouterr()
    assert seed_b64 not in captured.out
    assert seed_b64 not in captured.err


def test_main_reports_missing_env_var(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    _populate_release_dir(release_dir)

    old_env = os.environ.pop("SPARKLE_ED_PRIVATE_KEY", None)
    try:
        with pytest.raises(SystemExit) as excinfo:
            main(
                [
                    "--release-dir",
                    str(release_dir),
                    "--version",
                    VERSION,
                    "--tag",
                    TAG,
                    "--repo",
                    REPO,
                    "--notes-url",
                    NOTES_URL,
                    "--release-notes-file",
                    str(release_dir.parent / "release-notes.md"),
                ]
            )
        assert excinfo.value.code == 2
    finally:
        if old_env is not None:
            os.environ["SPARKLE_ED_PRIVATE_KEY"] = old_env

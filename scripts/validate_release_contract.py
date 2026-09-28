"""Fail-closed validator for a Persona Forge release set (Phase 7).

For a release version, the directory must contain the Python wheel/sdist, Linux bootstrap archive,
signed macOS/Windows/Linux desktop artifacts, appcast.xml, latest.json, and checksums.json.

Checks enforce exact top-level membership, SHA-256 coverage with no stray checksum keys, bootstrap
archive members and manifest integrity, feed versions, asset URLs, signatures, and DMG length.
Exit 0 means every assertion passed; 1 means at least one failed (fail-closed).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

BOOTSTRAP_ASSETS = ("persona-forge-bootstrap-linux-x86_64.tar.gz",)

DESKTOP_ASSETS = (
    "PersonaForge-macos-aarch64.dmg",
    "PersonaForge-windows-x86_64-setup.exe",
    "PersonaForge-windows-x86_64-setup.exe.sig",
    "PersonaForge-linux-x86_64.AppImage",
    "PersonaForge-linux-x86_64.AppImage.sig",
    "appcast.xml",
    "latest.json",
)

BOOTSTRAP_MEMBERS = {
    "persona-forge-bootstrap-linux-x86_64.tar.gz": {
        "persona-forge-launcher",
        "uv",
        "manifest.json",
        "README.txt",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_assets(version: str) -> set[str]:
    return {
        f"persona_forge-{version}-py3-none-any.whl",
        f"persona_forge-{version}.tar.gz",
        *BOOTSTRAP_ASSETS,
        *DESKTOP_ASSETS,
        "checksums.json",
    }


def _archive_members(path: Path) -> dict[str, bytes]:
    """Return {basename: content} for the archive's top-level entries (wheel/requirements files
    inside vary by target and are matched by suffix, not by exact name, elsewhere)."""
    members: dict[str, bytes] = {}
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                members[Path(name).name] = zf.read(name)
        return members
    with tarfile.open(path, "r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            fh = tf.extractfile(member)
            members[Path(member.name).name] = fh.read() if fh else b""
    return members


def _member_names_including_wheel_and_requirements(path: Path) -> set[str]:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            return {Path(n).name for n in zf.namelist()}
    with tarfile.open(path, "r:gz") as tf:
        return {Path(m.name).name for m in tf.getmembers() if m.isfile()}


def check_archive(path: Path, version: str, top_level_wheel_sha256: str, failures: list[str]) -> None:
    expected_static = BOOTSTRAP_MEMBERS[path.name]
    actual_names = _member_names_including_wheel_and_requirements(path)

    wheel_members = {n for n in actual_names if n.endswith(".whl")}
    req_members = {n for n in actual_names if n.startswith("requirements-") and n.endswith(".txt")}
    dynamic_expected = wheel_members | req_members

    expected_total = expected_static | dynamic_expected
    missing = expected_static - actual_names
    if missing:
        failures.append(f"{path.name}: missing member(s) {sorted(missing)}")
    if len(wheel_members) != 1:
        failures.append(f"{path.name}: expected exactly one .whl member, found {sorted(wheel_members)}")
    if len(req_members) != 1:
        failures.append(f"{path.name}: expected exactly one requirements-*.txt member, found {sorted(req_members)}")
    extra = actual_names - expected_total
    if extra:
        failures.append(f"{path.name}: unexpected extra member(s) {sorted(extra)}")

    members = _archive_members(path)
    manifest_bytes = members.get("manifest.json")
    if manifest_bytes is None:
        failures.append(f"{path.name}: manifest.json missing, cannot cross-check")
        return
    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as e:
        failures.append(f"{path.name}: manifest.json is not valid JSON: {e}")
        return

    if manifest.get("app") != "persona-forge":
        failures.append(f"{path.name}: manifest.app is {manifest.get('app')!r}, expected 'persona-forge'")
    if manifest.get("version") != version:
        failures.append(f"{path.name}: manifest.version is {manifest.get('version')!r}, expected {version!r}")
    manifest_wheel_sha = (manifest.get("wheel") or {}).get("sha256")
    if manifest_wheel_sha != top_level_wheel_sha256:
        failures.append(
            f"{path.name}: manifest wheel sha256 {manifest_wheel_sha!r} does not match "
            f"the top-level wheel's sha256 {top_level_wheel_sha256!r}"
        )


def check_update_feeds(release_dir: Path, version: str, failures: list[str]) -> None:
    latest_path = release_dir / "latest.json"
    try:
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        failures.append(f"latest.json is invalid: {e}")
        latest = {}
    if not isinstance(latest, dict):
        failures.append("latest.json must be a JSON object")
        latest = {}
    pub_date = latest.get("pub_date")
    if not isinstance(pub_date, str) or not pub_date:
        failures.append("latest.json pub_date must be a non-empty string")
    notes = latest.get("notes")
    if not isinstance(notes, str) or not notes:
        failures.append("latest.json notes must be a non-empty string")
    if isinstance(notes, str) and not notes.startswith("https://"):
        failures.append("latest.json notes must be an HTTPS URL")
    if latest.get("version") != version:
        failures.append(f"latest.json version is {latest.get('version')!r}, expected {version!r}")
    platforms = latest.get("platforms")
    if not isinstance(platforms, dict):
        failures.append("latest.json platforms must be an object")
        platforms = {}
    for key, asset in (
        ("windows-x86_64-nsis", "PersonaForge-windows-x86_64-setup.exe"),
        ("linux-x86_64-appimage", "PersonaForge-linux-x86_64.AppImage"),
    ):
        entry = platforms.get(key)
        if not isinstance(entry, dict):
            failures.append(f"latest.json platforms.{key} must be an object")
            continue
        url = entry.get("url")
        if not isinstance(url, str) or not url.endswith(asset) or not (release_dir / asset).is_file():
            failures.append(f"latest.json platforms.{key}.url must end with existing asset {asset}")
        signature = entry.get("signature")
        sig_path = release_dir / f"{asset}.sig"
        try:
            expected_signature = sig_path.read_text(encoding="utf-8").strip()
        except OSError:
            expected_signature = None
        if not isinstance(signature, str) or not expected_signature or signature != expected_signature:
            failures.append(f"latest.json platforms.{key}.signature does not match {sig_path.name}")

    appcast_path = release_dir / "appcast.xml"
    try:
        root = ET.parse(appcast_path).getroot()
        enclosure = root.find(".//enclosure")
        if enclosure is None:
            raise ValueError("missing enclosure")
        if enclosure.get("{http://www.andymatuschak.org/xml-namespaces/sparkle}version") != version:
            failures.append("appcast.xml sparkle:version does not match requested version")
        short_version = enclosure.get(
            "{http://www.andymatuschak.org/xml-namespaces/sparkle}shortVersionString"
        )
        if short_version != version:
            failures.append("appcast.xml sparkle:shortVersionString does not match requested version")
        ed_signature = enclosure.get(
            "{http://www.andymatuschak.org/xml-namespaces/sparkle}edSignature"
        )
        if not ed_signature:
            failures.append("appcast.xml enclosure is missing sparkle:edSignature")
        dmg_name = "PersonaForge-macos-aarch64.dmg"
        if not enclosure.get("url", "").endswith(dmg_name) or not (release_dir / dmg_name).is_file():
            failures.append(f"appcast.xml enclosure URL must end with existing asset {dmg_name}")
        try:
            length = int(enclosure.get("length", ""))
        except ValueError:
            length = -1
        dmg_path = release_dir / dmg_name
        if not dmg_path.is_file() or length != dmg_path.stat().st_size:
            failures.append("appcast.xml enclosure length does not match DMG size")
    except (OSError, ET.ParseError, ValueError) as e:
        failures.append(f"appcast.xml is invalid: {e}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, type=Path, help="Directory containing the release assets")
    parser.add_argument("--version", required=True, help="e.g. 1.3.0 (no leading 'v')")
    args = parser.parse_args(argv)

    if not args.dir.is_dir():
        print(f"error: release directory {args.dir} does not exist", file=sys.stderr)
        return 1

    failures: list[str] = []

    expected = expected_assets(args.version)
    actual = {p.name for p in args.dir.iterdir() if p.is_file()}
    missing_assets = expected - actual
    extra_assets = actual - expected
    if missing_assets:
        failures.append(f"missing release asset(s): {sorted(missing_assets)}")
    if extra_assets:
        failures.append(f"unexpected extra release asset(s): {sorted(extra_assets)}")

    checksums_path = args.dir / "checksums.json"
    checksums: dict[str, str] = {}
    if checksums_path.is_file():
        try:
            checksums = json.loads(checksums_path.read_text(encoding="utf-8")).get("checksums", {})
        except json.JSONDecodeError as e:
            failures.append(f"checksums.json is not valid JSON: {e}")
    else:
        failures.append("checksums.json is missing")

    checked_assets = expected & actual
    for asset in sorted(checked_assets - {"checksums.json"}):
        actual_sha = sha256_file(args.dir / asset)
        recorded_sha = checksums.get(asset)
        if recorded_sha is None:
            failures.append(f"checksums.json is missing an entry for {asset}")
        elif recorded_sha.lower() != actual_sha.lower():
            failures.append(f"checksums.json sha256 for {asset} is {recorded_sha!r}, computed {actual_sha!r}")
    stray_checksum_keys = set(checksums) - (expected - {"checksums.json"})
    if stray_checksum_keys:
        failures.append(f"checksums.json has entr(y/ies) for unexpected asset(s): {sorted(stray_checksum_keys)}")

    wheel_name = f"persona_forge-{args.version}-py3-none-any.whl"
    wheel_path = args.dir / wheel_name
    top_level_wheel_sha256 = sha256_file(wheel_path) if wheel_path.is_file() else ""

    for asset in BOOTSTRAP_ASSETS:
        archive_path = args.dir / asset
        if archive_path.is_file():
            check_archive(archive_path, args.version, top_level_wheel_sha256, failures)
    check_update_feeds(args.dir, args.version, failures)

    receipt = {"status": "pass" if not failures else "fail", "version": args.version, "failures": failures}
    print(json.dumps(receipt, indent=2))

    if failures:
        print(f"\nrelease contract validation FAILED: {len(failures)} violation(s)", file=sys.stderr)
        return 1
    print("\nrelease contract validation PASSED", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

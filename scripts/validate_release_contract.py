"""Fail-closed validator for a Persona Forge release set (Phase 7).

For tag `persona-forge-vX.Y.Z` the release directory must contain exactly:

    persona_forge-X.Y.Z-py3-none-any.whl
    persona_forge-X.Y.Z.tar.gz
    persona-forge-bootstrap-linux-x86_64.tar.gz
    persona-forge-bootstrap-windows-x86_64.zip
    persona-forge-bootstrap-macos-aarch64.tar.gz
    checksums.json

Checks: exact top-level asset membership (no missing, no extra), checksums.json covers every
asset with a matching SHA-256 and no stray keys, each bootstrap archive has exactly its expected
member set, and each archive's manifest.json agrees with --version and with the top-level wheel's
hash. Exit 0 = every assertion passed; 1 = at least one failed (fail-closed).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import zipfile
from pathlib import Path

BOOTSTRAP_ASSETS = (
    "persona-forge-bootstrap-linux-x86_64.tar.gz",
    "persona-forge-bootstrap-windows-x86_64.zip",
    "persona-forge-bootstrap-macos-aarch64.tar.gz",
)

BOOTSTRAP_MEMBERS = {
    "persona-forge-bootstrap-linux-x86_64.tar.gz": {
        "persona-forge-launcher",
        "uv",
        "manifest.json",
        "README.txt",
    },
    "persona-forge-bootstrap-windows-x86_64.zip": {
        "persona-forge-launcher.exe",
        "uv.exe",
        "manifest.json",
        "README.txt",
    },
    "persona-forge-bootstrap-macos-aarch64.tar.gz": {
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

    receipt = {"status": "pass" if not failures else "fail", "version": args.version, "failures": failures}
    print(json.dumps(receipt, indent=2))

    if failures:
        print(f"\nrelease contract validation FAILED: {len(failures)} violation(s)", file=sys.stderr)
        return 1
    print("\nrelease contract validation PASSED", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

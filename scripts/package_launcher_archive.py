"""Assemble one Persona Forge launcher release archive (Phase 7).

Bundles: the persona-forge-launcher binary for one Rust target, a pinned/verified uv binary, the
built wheel, a hash-locked target requirements file, manifest.json, and README.txt - exactly the
architecture-contract payload (docs/plans/20260829-no_more_docker_architecture.md §9). Nothing
else: no weights, no IR, no generated audio, no tokens.

Fail-closed: aborts if any required input is missing, or if `uv export` fails to resolve the
target's dependency set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

# Rust build target -> (release asset stem, archive kind, uv --python-platform triple).
TARGETS = {
    "x86_64-unknown-linux-gnu": ("linux-x86_64", "tar.gz", "x86_64-unknown-linux-gnu"),
    "x86_64-pc-windows-gnu": ("windows-x86_64", "zip", "x86_64-pc-windows-msvc"),
    "aarch64-apple-darwin": ("macos-aarch64", "tar.gz", "aarch64-apple-darwin"),
}

README_TEMPLATE = """Persona Forge bootstrap launcher ({target})

This archive is the recommended native install for Persona Forge. It contains:
  - a native launcher
  - the Persona Forge application wheel
  - hash-locked requirements for this platform
  - a pinned uv binary and an integrity-checked manifest

It does not contain the Python runtime, large ML dependency wheels, or model weights.
Those are downloaded from their normal package/model sources on first use.

Before running the launcher, verify this archive against checksums.json from the same
GitHub Release. On macOS, if Gatekeeper blocks the extracted binary, first run:
  xattr -dr com.apple.quarantine .
Only run that command inside this verified archive directory.

Usage on Linux/macOS:
  ./persona-forge-launcher doctor --json
  ./persona-forge-launcher setup
  ./persona-forge-launcher serve

Usage on Windows PowerShell:
  .\\persona-forge-launcher.exe doctor --json
  .\\persona-forge-launcher.exe setup
  .\\persona-forge-launcher.exe serve

The first launcher command downloads Python and installs the application environment
under your user data directory. The first server start downloads model assets. Later
runs reuse the environment and cached data. To update, download the newer release
archive and run its launcher; existing voices, settings, and model caches are retained.
"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_requirements(target_platform: str, out_path: Path) -> None:
    # `uv export` resolves only for the host platform's existing uv.lock; getting a hash-locked
    # requirements file for a *different* target needs the pip-compatible resolver instead, which
    # accepts a full target triple via --python-platform (docs/plans/20260829-no_more_docker_architecture.md §9).
    cmd = [
        "uv",
        "pip",
        "compile",
        "pyproject.toml",
        "--generate-hashes",
        "--python-platform",
        target_platform,
        "--python-version",
        "3.13",
        "-o",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            f"uv pip compile failed for --python-platform {target_platform}:\n{result.stdout}\n{result.stderr}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument("--version", required=True, help="persona-forge version, e.g. 1.3.0")
    parser.add_argument("--launcher-binary", required=True, type=Path)
    parser.add_argument("--uv-binary", required=True, type=Path)
    parser.add_argument("--uv-version", required=True)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path, help="Where to write the finished archive")
    parser.add_argument("--work-dir", default=None, type=Path, help="Staging dir (default: temp under out-dir)")
    args = parser.parse_args(argv)

    if not args.launcher_binary.is_file():
        print(f"error: launcher binary not found: {args.launcher_binary}", file=sys.stderr)
        return 1
    if not args.uv_binary.is_file():
        print(f"error: uv binary not found: {args.uv_binary}", file=sys.stderr)
        return 1
    if not args.wheel.is_file():
        print(f"error: wheel not found: {args.wheel}", file=sys.stderr)
        return 1

    asset_stem, archive_kind, python_platform = TARGETS[args.target]
    is_windows = args.target.endswith("windows-gnu")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = args.work_dir or (args.out_dir / f".staging-{args.target}")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    launcher_name = "persona-forge-launcher.exe" if is_windows else "persona-forge-launcher"
    uv_name = "uv.exe" if is_windows else "uv"
    requirements_name = f"requirements-{args.target}.txt"

    shutil.copy2(args.launcher_binary, work_dir / launcher_name)
    shutil.copy2(args.uv_binary, work_dir / uv_name)
    shutil.copy2(args.wheel, work_dir / args.wheel.name)
    export_requirements(python_platform, work_dir / requirements_name)

    manifest = {
        "schema_version": 1,
        "app": "persona-forge",
        "version": args.version,
        "target": args.target,
        "python_constraint": ">=3.13,<3.14",
        "wheel": {"file": args.wheel.name, "sha256": sha256_file(work_dir / args.wheel.name)},
        "uv": {
            "file": uv_name,
            "sha256": sha256_file(work_dir / uv_name),
            "version": args.uv_version,
        },
        "requirements_file": requirements_name,
        "requirements_sha256": sha256_file(work_dir / requirements_name),
    }
    (work_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (work_dir / "README.txt").write_text(README_TEMPLATE.format(target=args.target), encoding="utf-8")

    asset_name = f"persona-forge-bootstrap-{asset_stem}"
    if archive_kind == "zip":
        archive_path = args.out_dir / f"{asset_name}.zip"
        if archive_path.exists():
            archive_path.unlink()
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for member in sorted(work_dir.iterdir()):
                zf.write(member, member.name)
    else:
        archive_path = args.out_dir / f"{asset_name}.tar.gz"
        if archive_path.exists():
            archive_path.unlink()
        with tarfile.open(archive_path, "w:gz") as tf:
            for member in sorted(work_dir.iterdir()):
                tf.add(member, arcname=member.name)

    shutil.rmtree(work_dir)
    print(json.dumps({"archive": str(archive_path), "sha256": sha256_file(archive_path), "manifest": manifest}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

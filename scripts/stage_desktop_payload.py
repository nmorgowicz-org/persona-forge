"""Stage the desktop app's bundled payload (Phase 3, contract §5/§7).

Writes exactly what `desktop/tauri.conf.json`'s `bundle.resources`/`bundle.externalBin` expect:

  desktop/payload/<wheel>
  desktop/payload/requirements-<target>.txt
  desktop/payload/manifest.json           (schema v1, same shape package_launcher_archive uses)
  desktop/binaries/uv-<target>[.exe]      (Tauri externalBin naming: target-triple-suffixed)

Reuses `package_launcher_archive`'s `sha256_file`, `export_requirements` and `build_manifest`
rather than re-implementing them, so the desktop payload and the CLI archive manifest never
drift apart (`ensure_env` in the launcher lib is unchanged either way — same schema).

Usage:
    stage_desktop_payload.py --target <triple> --version X.Y.Z --wheel <whl> --uv-binary <path>
                              --uv-version V --out-root desktop [--fake]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# When run as `python scripts/stage_desktop_payload.py`, sys.path[0] is scripts/, not the repo
# root, so `from scripts import ...` fails on a fresh checkout (tests work because pytest puts
# the repo root on sys.path). Put the repo root (this script's parent's parent) there.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import package_launcher_archive as pla

# Desktop build target -> uv --python-platform value. Reuses the values already verified in
# package_launcher_archive.TARGETS instead of adding keys there: that map drives CLI-archive
# target choices and .exe naming, which desktop targets (MSVC, not GNU, on Windows) don't share.
DESKTOP_TARGETS: dict[str, str] = {
    "aarch64-apple-darwin": pla.TARGETS["aarch64-apple-darwin"][2],
    "x86_64-pc-windows-msvc": pla.TARGETS["x86_64-pc-windows-gnu"][2],
    "x86_64-unknown-linux-gnu": pla.TARGETS["x86_64-unknown-linux-gnu"][2],
}

# A manifest with this sha256 (and only this one) can never be produced by a real build: it
# marks a --fake payload, so verify_payload's rejection message can name it explicitly.
FAKE_SHA256 = "0" * 64


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=sorted(DESKTOP_TARGETS))
    parser.add_argument("--version", required=True, help="persona-forge version, e.g. 1.3.0")
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--uv-binary", required=True, type=Path)
    parser.add_argument("--uv-version", required=True)
    parser.add_argument("--out-root", required=True, type=Path, help="desktop/ directory root")
    parser.add_argument(
        "--fake",
        action="store_true",
        help="Write placeholder payload files with an all-zero manifest hash; never runs "
        "`uv pip compile`. CI compile/test lanes only.",
    )
    args = parser.parse_args(argv)

    is_windows = args.target.endswith("windows-msvc")
    uv_name = f"uv-{args.target}.exe" if is_windows else f"uv-{args.target}"
    requirements_name = f"requirements-{args.target}.txt"

    payload_dir = args.out_root / "payload"
    binaries_dir = args.out_root / "binaries"
    payload_dir.mkdir(parents=True, exist_ok=True)
    binaries_dir.mkdir(parents=True, exist_ok=True)

    wheel_dest = payload_dir / args.wheel.name
    requirements_dest = payload_dir / requirements_name
    uv_dest = binaries_dir / uv_name

    if args.fake:
        wheel_dest.write_bytes(b"")
        requirements_dest.write_text("", encoding="utf-8")
        uv_dest.write_bytes(b"")
        manifest = pla.build_manifest(
            version=args.version,
            target=args.target,
            wheel_name=args.wheel.name,
            wheel_sha256=FAKE_SHA256,
            uv_name=uv_name,
            uv_sha256=FAKE_SHA256,
            uv_version=args.uv_version,
            requirements_name=requirements_name,
            requirements_sha256=FAKE_SHA256,
        )
    else:
        if not args.wheel.is_file():
            print(f"error: wheel not found: {args.wheel}", file=sys.stderr)
            return 1
        if not args.uv_binary.is_file():
            print(f"error: uv binary not found: {args.uv_binary}", file=sys.stderr)
            return 1

        shutil.copy2(args.wheel, wheel_dest)
        shutil.copy2(args.uv_binary, uv_dest)
        pla.export_requirements(
            DESKTOP_TARGETS[args.target], requirements_dest, uv_path=str(args.uv_binary)
        )

        manifest = pla.build_manifest(
            version=args.version,
            target=args.target,
            wheel_name=args.wheel.name,
            wheel_sha256=pla.sha256_file(wheel_dest),
            uv_name=uv_name,
            uv_sha256=pla.sha256_file(uv_dest),
            uv_version=args.uv_version,
            requirements_name=requirements_name,
            requirements_sha256=pla.sha256_file(requirements_dest),
        )

    (payload_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"payload_dir": str(payload_dir), "binaries_dir": str(binaries_dir), "manifest": manifest}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

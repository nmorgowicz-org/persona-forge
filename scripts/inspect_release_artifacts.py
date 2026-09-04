"""Fail-closed release-artifact inspector (Phase 6).

Verifies that a standard ``uv build`` produced a self-contained wheel and a reproducible sdist,
asserting both the *required* members (console entry point, CLI/bootstrap/paths/frontend modules,
the baked-in Studio UI, frontend sources + lockfile) and the *forbidden* members (secrets, model
weights, OpenVINO IR, generated audio, node_modules, and anything that should never ship in a
release artifact). Emits a machine-readable JSON receipt (with SHA-256) for CI upload.

Exit code 0 = every assertion passed; 1 = at least one assertion failed (fail-closed).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import zipfile
from pathlib import Path

_FORBIDDEN_BINARY_SUFFIXES = (".bin", ".xml", ".safetensors", ".pt", ".pth", ".ckpt", ".wav", ".mp3", ".onnx")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wheel_members(wheel_path: Path) -> list[str]:
    with zipfile.ZipFile(wheel_path) as zf:
        return zf.namelist()


def _sdist_members(sdist_path: Path) -> list[str]:
    with tarfile.open(sdist_path, "r:gz") as tf:
        names = tf.getnames()
    # sdist members are prefixed with the archive root dir (e.g. "persona_forge-1.3.0/...");
    # strip it so required/forbidden rules match the same paths as the wheel.
    return [n.split("/", 1)[1] if "/" in n else n for n in names]


def _find(artifacts: list[Path], suffix: str) -> Path:
    matches = [p for p in artifacts if p.name.endswith(suffix)]
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one {suffix} artifact in dist/, found {len(matches)}: {[str(m) for m in matches]}")
    return matches[0]


def _required_missing(members: list[str], required: list[str]) -> list[str]:
    missing: list[str] = []
    for req in required:
        if req.startswith("*"):
            suffix = req[1:]
            if not any(m.endswith(suffix) for m in members):
                missing.append(req)
        elif not any(m == req or m.startswith(req) for m in members):
            missing.append(req)
    return missing


def _forbidden_present(members: list[str], kind: str) -> list[str]:
    """Forbidden members differ per artifact: a *wheel* is an installable package and must carry no
    tests/export-tooling/lockfile, while an *sdist* is a source distribution and legitimately ships
    the test sources (but never build output, dependency caches, secrets, weights, or IR)."""
    hits: list[str] = []
    for m in members:
        lm = m.lower()
        if any(lm.endswith(s) for s in _FORBIDDEN_BINARY_SUFFIXES):
            hits.append(m)
        elif "hf_token" in lm:
            hits.append(m)
        elif "node_modules" in lm:
            hits.append(m)
        elif lm.endswith(".env") or lm.endswith("/.env"):
            hits.append(m)
        elif kind == "wheel" and (lm.endswith("uv.lock")):
            hits.append(m)
        elif kind == "wheel" and (lm.startswith("tests/") or "/tests/" in lm):
            hits.append(m)
        elif kind == "wheel" and (lm.startswith("src/export") or lm.startswith("export/")):
            hits.append(m)
        elif kind == "sdist" and (lm.startswith("frontend/dist/") or "/frontend/dist/" in lm):
            hits.append(m)
        elif kind == "sdist" and (lm.startswith("src/persona_forge/static/") or "/src/persona_forge/static/" in lm):
            hits.append(m)
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", default="dist", help="Directory containing the built wheel/sdist")
    parser.add_argument("--receipt-out", default=None, help="Also write the JSON receipt to this path (for CI artifact upload)")
    args = parser.parse_args(argv)

    dist_dir = Path(args.dist_dir)
    if not dist_dir.is_dir():
        print(f"error: dist directory {dist_dir} does not exist", file=sys.stderr)
        return 1

    artifacts = [p for p in dist_dir.iterdir() if p.is_file() and (p.name.endswith(".whl") or p.name.endswith(".tar.gz"))]
    if len(artifacts) < 2:
        print(f"error: expected a .whl and a .tar.gz in {dist_dir}, found {[p.name for p in artifacts]}", file=sys.stderr)
        return 1

    wheel = _find(artifacts, ".whl")
    sdist = _find(artifacts, ".tar.gz")

    wheel_required = [
        "persona_forge/cli.py",
        "persona_forge/bootstrap.py",
        "persona_forge/paths.py",
        "persona_forge/frontend.py",
        "persona_forge/config.py",
        "persona_forge/gpu_family.py",
        "persona_forge/device.py",
        "persona_forge/compat_patch.py",
        "persona_forge/static/index.html",
        "*.dist-info/METADATA",
    ]
    sdist_required = [
        "pyproject.toml",
        "hatch_build.py",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/index.html",
        "frontend/src/main.tsx",
        "src/persona_forge/cli.py",
    ]

    wheel_members = _wheel_members(wheel)
    sdist_members = _sdist_members(sdist)

    wheel_missing = _required_missing(wheel_members, wheel_required)
    sdist_missing = _required_missing(sdist_members, sdist_required)
    wheel_banned = _forbidden_present(wheel_members, "wheel")
    sdist_banned = _forbidden_present(sdist_members, "sdist")

    failures = (
        [{"kind": "wheel", "rule": "required-missing", "member": m} for m in wheel_missing]
        + [{"kind": "sdist", "rule": "required-missing", "member": m} for m in sdist_missing]
        + [{"kind": "wheel", "rule": "forbidden-present", "member": m} for m in wheel_banned]
        + [{"kind": "sdist", "rule": "forbidden-present", "member": m} for m in sdist_banned]
    )

    receipt = {
        "status": "pass" if not failures else "fail",
        "wheel": {"path": str(wheel), "sha256": _sha256(wheel), "members": len(wheel_members)},
        "sdist": {"path": str(sdist), "sha256": _sha256(sdist), "members": len(sdist_members)},
        "failures": failures,
    }
    print(json.dumps(receipt, indent=2))

    if args.receipt_out:
        Path(args.receipt_out).write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    if failures:
        print(f"\nartifact inspection FAILED: {len(failures)} violation(s)", file=sys.stderr)
        return 1
    print("\nartifact inspection PASSED: wheel + sdist are self-contained and clean", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

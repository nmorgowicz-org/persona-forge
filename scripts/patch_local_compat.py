#!/usr/bin/env python3
"""Thin wrapper around persona_forge.compat_patch for local dev.

The actual patch definitions and application logic live in
persona_forge/compat_patch.py (Phase 5) — the same module the Dockerfile invokes for the
container image. Run this once after `uv sync --extra qwen-tts` (idempotent — safe to re-run).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from persona_forge.compat_patch import apply_qwen_patches  # noqa: E402


def main() -> int:
    report = apply_qwen_patches()
    print(f"site-packages: {report['site_packages']}")
    for patch in report["patches"]:
        print(f"  [{patch['status']}] {patch['name']} ({patch['path']})")
    if report["status"] == "failed":
        print(json.dumps(report, indent=2), file=sys.stderr)
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

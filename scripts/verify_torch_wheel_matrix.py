#!/usr/bin/env python3
"""Live cp313 wheel-matrix verifier for persona_forge.accelerator_manifest (Phase 4 Task 8).

Checks that each ``ACCELERATOR_PINS`` entry's exact torch/torchaudio/``extra_pins`` wheel actually
exists on the real PyTorch package index, for cp313 and each of the pin's declared platforms, and
writes a dated JSON receipt to ``artifacts/accelerator-wheel-verification/`` (gitignored — this is
a live-network report, not a checked-in fact).

A network failure is reported as ``unknown``, never as ``missing``: this script exists precisely
to catch a real absence (the exact failure mode that produced the xpu/rocm pin corrections in the
manifest's own docstring), and treating an unreachable index as "confirmed absent" would turn a
transient network blip into a false failure. Exit code 1 only on a *confirmed* missing wheel;
unknown checks are reported but don't fail the run.
"""

from __future__ import annotations

import datetime
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from persona_forge.accelerator_manifest import ACCELERATOR_PINS, AcceleratorPin  # noqa: E402

# Substring, not exact tag: torch/torchaudio ship manylinux_2_28_x86_64 wheels, but
# pytorch-triton-rocm on the same index ships plain linux_x86_64 — "_x86_64" matches both
# (live-verified: rocm6.4's pytorch_triton_rocm-3.5.1-cp313-cp313-linux_x86_64.whl has no
# manylinux tag at all).
_PLATFORM_TAGS = {
    "linux": "_x86_64",
    "win32": "win_amd64",
}
_TIMEOUT_SECONDS = 15


def _fetch(url: str) -> str | None:
    """Return response text, or None on any network failure — never raises."""
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as resp:  # noqa: S310
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def _wheel_present(listing: str, package: str, version: str, platform_tag: str) -> bool:
    needle = f"{package.replace('-', '_')}-{version}"
    return any(
        needle in line and platform_tag in line and "cp313" in line
        for line in listing.splitlines()
    )


def verify_pin(extra: str, pin: AcceleratorPin) -> dict:
    packages = {
        "torch": pin.torch_version,
        "torchaudio": pin.torchaudio_version,
        **pin.extra_pins,
    }
    checks = []
    for package, version in packages.items():
        listing = _fetch(f"{pin.index_url}/{package}/")
        for platform in pin.platforms:
            tag = _PLATFORM_TAGS.get(platform)
            if tag is None:
                continue
            if listing is None:
                status, detail = "unknown", "network failure fetching index listing"
            elif _wheel_present(listing, package, version, tag):
                status, detail = "present", None
            else:
                status, detail = "missing", (
                    f"no cp313 {tag} wheel for {package}=={version} on {pin.index_url}"
                )
            checks.append(
                {
                    "package": package,
                    "version": version,
                    "platform": platform,
                    "status": status,
                    "detail": detail,
                }
            )
    return {"extra": extra, "gpu_family": pin.gpu_family, "checks": checks}


def main() -> int:
    receipts = [verify_pin(extra, pin) for extra, pin in ACCELERATOR_PINS.items()]
    all_checks = [c for r in receipts for c in r["checks"]]
    missing = [c for c in all_checks if c["status"] == "missing"]
    unknown = [c for c in all_checks if c["status"] == "unknown"]

    out_dir = REPO_ROOT / "artifacts" / "accelerator-wheel-verification"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{timestamp}.json"
    out_path.write_text(json.dumps({"generated_at": timestamp, "pins": receipts}, indent=2))
    print(f"wrote {out_path}")

    for r in receipts:
        for c in r["checks"]:
            marker = {"present": "OK", "missing": "MISSING", "unknown": "UNKNOWN"}[c["status"]]
            print(f"  [{marker}] {r['extra']}/{c['platform']}: {c['package']}=={c['version']}")

    if unknown:
        print(
            f"\n{len(unknown)} check(s) could not be verified (network failure) — "
            "not a failure, but re-run when online.",
            file=sys.stderr,
        )
    if missing:
        print(
            f"\n{len(missing)} confirmed-missing wheel(s) — the manifest pin is wrong.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Check that the pinned Torch stack is internally consistent.

The universal uv lock contains one exact wheel variant for each supported accelerator
extra, so different package versions in the lock are expected: ROCm uses 2.9.1 and
XPU uses 2.13.0 while the default/CUDA stack uses 2.14.0. This checks that those are
the only versions present, that the default resolution remains exact, and that the
container defaults match the manifest. It does not claim runtime compatibility; the
dependency-bump verifier still runs real Torch tests and image import smoke.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path


PACKAGES = ("torch", "torchaudio")


def _manifest_versions(root: Path, package: str) -> set[str]:
    src_dir = str(root / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from persona_forge.accelerator_manifest import ACCELERATOR_PINS

    attribute = f"{package}_version"
    return {getattr(pin, attribute) for pin in ACCELERATOR_PINS.values()}


def _default_version(root: Path, package: str) -> str:
    src_dir = str(root / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from persona_forge.accelerator_manifest import (
        DEFAULT_TORCH_VERSION,
        DEFAULT_TORCHAUDIO_VERSION,
    )

    return {
        "torch": DEFAULT_TORCH_VERSION,
        "torchaudio": DEFAULT_TORCHAUDIO_VERSION,
    }[package]


def _base_version(version: str) -> str:
    return version.split("+", 1)[0]


def _exact_pin(value: str, package: str) -> str | None:
    match = re.fullmatch(rf"{re.escape(package)}==([^\s;]+)", value.strip())
    return match.group(1) if match else None


def _add(found: dict[str, list[tuple[str, str]]], package: str, source: str, version: str) -> None:
    found[package].append((source, version))


def collect(root: Path) -> dict[str, list[tuple[str, str]]]:
    found = {package: [] for package in PACKAGES}

    with (root / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)

    for value in pyproject["project"]["dependencies"]:
        for package in PACKAGES:
            version = _exact_pin(value, package)
            if version:
                _add(found, package, "pyproject project.dependencies", version)

    for value in pyproject["tool"]["uv"]["override-dependencies"]:
        for package in PACKAGES:
            version = _exact_pin(value, package)
            if version:
                _add(found, package, "pyproject tool.uv.override-dependencies", version)

    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    for package, variable in (("torch", "TORCH_VERSION"), ("torchaudio", "TORCHAUDIO_VERSION")):
        match = re.search(rf"^ARG {variable}=([^\s]+)$", dockerfile, re.MULTILINE)
        if match:
            _add(found, package, f"Dockerfile ARG {variable}", match.group(1))

    with (root / "uv.lock").open("rb") as handle:
        lock = tomllib.load(handle)

    for override in lock.get("manifest", {}).get("overrides", []):
        package = override.get("name")
        if package in PACKAGES:
            version = _exact_pin(override.get("specifier", ""), package)
            if version:
                _add(found, package, "uv.lock manifest.overrides", version)

    for package_entry in lock.get("package", []):
        package = package_entry.get("name")
        if package in PACKAGES:
            _add(found, package, "uv.lock package.version", package_entry["version"])
        if package == "persona-forge":
            for requirement in package_entry.get("requires-dist", []):
                name = requirement.get("name")
                if name in PACKAGES:
                    version = _exact_pin(requirement.get("specifier", ""), name)
                    if version:
                        _add(found, name, "uv.lock persona-forge requires-dist", version)

    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository checkout to inspect")
    args = parser.parse_args()
    root = args.root.resolve()

    try:
        found = collect(root)
    except (KeyError, OSError, tomllib.TOMLDecodeError) as exc:
        print(f"ERROR: unable to inspect Torch contract in {root}: {exc}", file=sys.stderr)
        return 2

    errors: list[str] = []
    for package in PACKAGES:
        entries = found[package]
        if not entries:
            errors.append(f"{package}: no exact pin found")
            continue

        default_version = _default_version(root, package)
        docker_versions = {
            version for source, version in entries if source.startswith("Dockerfile ARG")
        }
        if docker_versions != {default_version}:
            errors.append(
                f"{package}: Dockerfile pin {sorted(docker_versions)!r}, expected {default_version}"
            )

        lock_versions = {
            _base_version(version)
            for source, version in entries
            if source == "uv.lock package.version"
        }
        expected_versions = _manifest_versions(root, package)
        if lock_versions != expected_versions:
            errors.append(
                f"{package}: uv.lock versions {sorted(lock_versions)!r}, "
                f"expected accelerator pins {sorted(expected_versions)!r}"
            )

        default_lock = {
            _base_version(version)
            for source, version in entries
            if source == "uv.lock package.version" and "+" not in version
        }
        if default_lock != {default_version}:
            errors.append(
                f"{package}: default uv.lock version {sorted(default_lock)!r}, "
                f"expected {default_version}"
            )

        print(f"OK: {package} default={default_version}; variants={sorted(lock_versions)}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

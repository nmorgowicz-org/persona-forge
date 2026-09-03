#!/usr/bin/env python3
"""Check that the pinned Torch CPU stack is internally consistent.

This is intentionally a source/lockfile contract check. It does not claim that a
new Torch release is runtime-compatible; the dependency-bump verifier must still
run the real Torch tests and, for image changes, the container build/import smoke.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path


PACKAGES = ("torch", "torchaudio")


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
        versions = {version for _, version in entries}
        if len(versions) != 1:
            detail = ", ".join(f"{source}={version}" for source, version in entries)
            errors.append(f"{package}: inconsistent pins ({detail})")
        else:
            version = next(iter(versions))
            print(f"OK: {package}={version} ({len(entries)} declarations)")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

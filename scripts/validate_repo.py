#!/usr/bin/env python3
"""Fast repository validation that does not download model weights."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONVENTIONAL_TYPES = (
    "feat",
    "fix",
    "perf",
    "refactor",
    "test",
    "docs",
    "build",
    "ci",
    "chore",
    "revert",
)
OVERRIDE_ENTRY_RE = re.compile(
    rf"^({'|'.join(CONVENTIONAL_TYPES)})(?:\([a-z0-9][a-z0-9._/-]*\))?!?: .+$"
)


def validate_pr_override_body(body: str) -> None:
    """Reject malformed Release Please override blocks when a PR supplies one."""
    begin = "BEGIN_COMMIT_OVERRIDE"
    end = "END_COMMIT_OVERRIDE"
    if begin not in body and end not in body:
        return
    if body.count(begin) != 1 or body.count(end) != 1:
        raise RuntimeError("PR body must contain exactly one complete commit override block")
    block = body.split(begin, 1)[1].split(end, 1)[0].strip()
    entries = [line.strip() for line in block.splitlines() if line.strip()]
    if not entries:
        raise RuntimeError("Release Please commit override block must not be empty")
    invalid = [entry for entry in entries if not OVERRIDE_ENTRY_RE.fullmatch(entry)]
    if invalid:
        raise RuntimeError(
            "Release Please override entries must each be a single Conventional Commit line "
            "without a Markdown list marker, with one supported type and an optional simple scope; "
            f"invalid entries: {invalid}"
        )


def validate_pr_event() -> None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    pull_request = event.get("pull_request")
    if isinstance(pull_request, dict):
        validate_pr_override_body(pull_request.get("body") or "")


def validate_python() -> None:
    paths = tuple((ROOT / "src").rglob("*.py")) + tuple((ROOT / "scripts").glob("*.py"))
    for path in paths:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def validate_workflows() -> None:
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    if not workflows:
        raise RuntimeError("No GitHub Actions workflows found")
    for path in workflows:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or "jobs" not in document:
            raise RuntimeError(f"{path.relative_to(ROOT)} is not a workflow mapping")

    release_config = json.loads(
        (ROOT / ".github" / "release-please" / "config.json5").read_text(encoding="utf-8")
    )
    configured_types = {
        section["type"] for section in release_config.get("changelog-sections", [])
    }
    if configured_types != set(CONVENTIONAL_TYPES):
        raise RuntimeError(
            "Release Please changelog sections must match the supported override types"
        )
    package_name = release_config["packages"]["."]["package-name"]
    tag_prefix = release_config.get("tag-prefix", "v")
    expected_release_tag = f"{package_name}-{tag_prefix}*"

    image_workflow = yaml.load(
        (ROOT / ".github" / "workflows" / "image.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    push_trigger = image_workflow["on"]["push"]
    if push_trigger.get("branches"):
        raise RuntimeError("Container images must not publish from branch pushes")
    if push_trigger.get("tags") != [expected_release_tag]:
        raise RuntimeError(
            "Container image tag trigger does not match the Release Please tag pattern: "
            f"expected {expected_release_tag!r}"
        )


def validate_repository_metadata() -> None:
    for path in sorted((ROOT / ".github").rglob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if document is None:
            raise RuntimeError(f"{path.relative_to(ROOT)} is empty")
    for path in (ROOT / "renovate.json", ROOT / ".github" / "release-please" / "config.json5"):
        json.loads(path.read_text(encoding="utf-8"))

    labeler = yaml.safe_load((ROOT / ".github" / "labeler.yml").read_text(encoding="utf-8"))
    for label in ("python", "shell", "ci", "github-actions", "documentation", "dependencies", "test"):
        rules = labeler.get(label)
        if not rules:
            raise RuntimeError(f"Labeler rule {label!r} has no changed-file patterns")
        patterns = rules[0].get("changed-files", [{}])[0].get("any-glob-to-any-file")
        if not isinstance(patterns, list) or not patterns:
            raise RuntimeError(f"Labeler rule {label!r} has no glob patterns")


def validate_compose() -> None:
    document = yaml.safe_load((ROOT / "compose.yml").read_text(encoding="utf-8"))
    services = document.get("services", {}) if isinstance(document, dict) else {}
    for service in ("persona-forge", "export"):
        if service not in services:
            raise RuntimeError(f"compose.yml is missing service {service!r}")
    if services["persona-forge"].get("image") != services["export"].get("image"):
        raise RuntimeError("compose.yml serving and export services must use the same image")
    if "target" in services["persona-forge"].get("build", {}):
        raise RuntimeError("compose.yml must not select a serving-only Docker target")
    if "target" in services["export"].get("build", {}):
        raise RuntimeError("compose.yml must not select an exporter-only Docker target")
    # Single image: the export service shares the serving image and only overrides the
    # command, so it must carry an explicit command (the image defaults to serving).
    if not services.get("export", {}).get("command"):
        raise RuntimeError("compose.yml export service must override 'command' for the single image")


def validate_dockerfile() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    # One image carries every capability: the serving contract plus the OpenVINO
    # export/quantization requirements. The compose `export` service overrides the
    # default serve command with scripts/export.py.
    for marker in (
        "HEALTHCHECK ",
        "persona_forge.app:app",
        "EXPOSE 8318",
        "requirements/requirements-openvino.txt",
        "requirements/requirements-export.txt",
        "from transformers import initialization as init",
        "s/create_sliding_window_causal_mask/create_causal_mask/g",
    ):
        if marker not in dockerfile:
            raise RuntimeError(f"Dockerfile single-image contract is missing {marker!r}")
    required_export_files = {
        "export_openvino.py",
        "ov_export_wrappers.py",
        "parity_contract.py",
        "test_vocoder_parity.py",
        "benchmark_vocoder.py",
        "test_transformer_parity.py",
        "test_stateful_main_parity.py",
        "ov_stateful_cache.py",
        "calibration_capture.py",
        "dump_audio.py",
    }
    missing = {f for f in required_export_files if not (ROOT / "src" / "export" / f).is_file()}
    if missing:
        raise RuntimeError(
            f"src/export is missing required modules: {', '.join(sorted(missing))}"
        )

    if not (ROOT / "SECURITY.md").is_file():
        raise RuntimeError("SECURITY.md is missing")


def validate_artifact_policy() -> None:
    forbidden = {".onnx", ".safetensors", ".wav", ".mp3"}
    # Raw RSS / generation-profile timelines are large and machine-specific; only the
    # curated numbers belong in docs. Match by name so legitimate JSON (renovate.json,
    # release manifests, bench_results/*) stays allowed.
    forbidden_name_res = (
        re.compile(r"^m9_rss_.*\.json$"),
        re.compile(r".*_rss_profile.*\.json$"),
        re.compile(r"^main_stateful_parity\.json$"),
    )
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    offenders = []
    for raw in tracked:
        if not raw:
            continue
        path = Path(raw.decode("utf-8"))
        if path.suffix.lower() in forbidden:
            offenders.append(path)
        elif any(pattern.match(path.name) for pattern in forbidden_name_res):
            offenders.append(path)
    if offenders:
        raise RuntimeError(
            f"Model, voice, or raw-profile artifacts must not be committed: {offenders}"
        )


def _dep_version(entries: list[str], package: str) -> str | None:
    """Return the ``==`` pin for ``package`` in an optional-dependencies entry list, or None."""
    for entry in entries:
        name = entry.split(";", 1)[0].strip()
        if name.startswith(f"{package}=="):
            return name.split("==", 1)[1]
    return None


def validate_accelerator_manifest() -> None:
    """Cross-check pyproject.toml's static accelerator extras against the manifest (Task 4).

    ``persona_forge.accelerator_manifest.ACCELERATOR_PINS`` is the single source of truth (see
    that module's docstring); this catches the manifest and pyproject.toml drifting apart —
    someone editing one without the other — rather than only surfacing as a live `uv lock` failure.
    """
    src_dir = str(ROOT / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from persona_forge.accelerator_manifest import ACCELERATOR_PINS

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    optional_deps = pyproject["project"]["optional-dependencies"]
    uv_sources = pyproject["tool"]["uv"]["sources"]
    uv_indexes = {entry["name"]: entry["url"] for entry in pyproject["tool"]["uv"]["index"]}

    errors: list[str] = []
    for extra, pin in ACCELERATOR_PINS.items():
        entries = optional_deps.get(extra)
        if entries is None:
            errors.append(f"[project.optional-dependencies] is missing extra {extra!r}")
            continue

        for package, expected_version in (
            ("torch", pin.torch_version),
            ("torchaudio", pin.torchaudio_version),
            *pin.extra_pins.items(),
        ):
            actual_version = _dep_version(entries, package)
            if actual_version != expected_version:
                errors.append(
                    f"extra {extra!r}: {package} pinned to {actual_version!r} in pyproject.toml, "
                    f"manifest says {expected_version!r}"
                )
            source_entries = uv_sources.get(package, [])
            matching = [s for s in source_entries if s.get("extra") == extra]
            if not matching:
                errors.append(
                    f"extra {extra!r}: [tool.uv.sources] {package} has no entry routing to an "
                    "index for this extra"
                )
            elif matching[0].get("index") != pin.index_name:
                errors.append(
                    f"extra {extra!r}: [tool.uv.sources] {package} routes to "
                    f"{matching[0].get('index')!r}, manifest says {pin.index_name!r}"
                )

        actual_index_url = uv_indexes.get(pin.index_name)
        if actual_index_url != pin.index_url:
            errors.append(
                f"[[tool.uv.index]] {pin.index_name!r} is {actual_index_url!r}, "
                f"manifest says {pin.index_url!r}"
            )

    if errors:
        raise RuntimeError(
            "pyproject.toml accelerator extras drifted from persona_forge.accelerator_manifest:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


def main() -> None:
    validate_pr_event()
    validate_python()
    validate_workflows()
    validate_repository_metadata()
    validate_compose()
    validate_dockerfile()
    validate_artifact_policy()
    validate_accelerator_manifest()
    print("repository validation passed")


if __name__ == "__main__":
    main()

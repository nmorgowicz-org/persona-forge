#!/usr/bin/env python3
"""Fast repository validation that does not download model weights."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
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
            "with one supported type and an optional simple scope; "
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
    paths = (
        ROOT / "app_api.py",
        ROOT / "app_worker.py",
        ROOT / "export_openvino.py",
        ROOT / "model_config.py",
        ROOT / "ov_export_wrappers.py",
        ROOT / "ov_stateful_cache.py",
        ROOT / "serve.py",
        ROOT / "test_vocoder_parity.py",
        ROOT / "test_transformer_parity.py",
        ROOT / "test_stateful_main_parity.py",
        ROOT / "calibration_capture.py",
        ROOT / "dump_audio.py",
        ROOT / "scripts" / "download_model.py",
        ROOT / "scripts" / "stateful_cache_spike.py",
        ROOT / "scripts" / "transform_stateful_ir.py",
    )
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


def validate_compose_example() -> None:
    document = yaml.safe_load((ROOT / "compose.example.yml").read_text(encoding="utf-8"))
    services = document.get("services", {}) if isinstance(document, dict) else {}
    for service in ("qwen3-tts", "qwen3-tts-download"):
        if service not in services:
            raise RuntimeError(f"compose.example.yml is missing service {service!r}")


def validate_dockerfile() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for target in ("runtime", "exporter"):
        if f" AS {target}" not in dockerfile:
            raise RuntimeError(f"Dockerfile target {target!r} is missing")
    for marker in ('HEALTHCHECK ', 'CMD ["python", "serve.py"]'):
        if marker not in dockerfile:
            raise RuntimeError(f"Dockerfile runtime contract is missing {marker!r}")
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
    exporter_copy_lines = [
        line for line in dockerfile.splitlines()
        if line.strip().startswith("COPY export_openvino.py")
    ]
    if not exporter_copy_lines:
        raise RuntimeError("Dockerfile exporter target is missing the export CLI sources")
    copy_target = " ".join(" ".join(exporter_copy_lines).split())
    missing = {f for f in required_export_files if f not in copy_target}
    if missing:
        raise RuntimeError(
            f"Dockerfile exporter target is missing: {', '.join(sorted(missing))}"
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


def main() -> None:
    validate_pr_event()
    validate_python()
    validate_workflows()
    validate_repository_metadata()
    validate_compose_example()
    validate_dockerfile()
    validate_artifact_policy()
    print("repository validation passed")


if __name__ == "__main__":
    main()

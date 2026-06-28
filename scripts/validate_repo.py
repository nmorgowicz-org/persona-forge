#!/usr/bin/env python3
"""Fast repository validation that does not download model weights."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def validate_python() -> None:
    paths = (
        ROOT / "app_api.py",
        ROOT / "app_worker.py",
        ROOT / "export_openvino.py",
        ROOT / "model_config.py",
        ROOT / "ov_export_wrappers.py",
        ROOT / "serve.py",
        ROOT / "test_vocoder_parity.py",
        ROOT / "scripts" / "download_model.py",
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
    if (
        "COPY export_openvino.py ov_export_wrappers.py test_vocoder_parity.py "
        "benchmark_vocoder.py ./"
        not in dockerfile
    ):
        raise RuntimeError("Dockerfile exporter target is missing the export CLI sources")

    if not (ROOT / "SECURITY.md").is_file():
        raise RuntimeError("SECURITY.md is missing")


def validate_artifact_policy() -> None:
    forbidden = {".onnx", ".safetensors", ".wav", ".mp3"}
    offenders = [
        path.relative_to(ROOT)
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.parts and path.suffix.lower() in forbidden
    ]
    if offenders:
        raise RuntimeError(f"Model or voice artifacts must not be committed: {offenders}")


def main() -> None:
    validate_python()
    validate_workflows()
    validate_repository_metadata()
    validate_compose_example()
    validate_dockerfile()
    validate_artifact_policy()
    print("repository validation passed")


if __name__ == "__main__":
    main()

"""Phase 8 semantic doc validator (docs/plans/20260829-no_more_docker_requirement.md, Phase 8).

Checks active documentation against actual code/config truth — not a weak regex scan of prose,
but structural cross-checks against pyproject.toml, the Dockerfile, the accelerator manifest, the
release workflow, and paths.py's own env-var literals, plus a narrow banned-phrase scan (with an
allowlist) for claims that are cheap to state wrong and expensive to leave wrong: stale container
pins, "Docker is required", wrong default backends.

Deliberately excludes docs/archive/** and docs/plans/** — those are historical record, not
active documentation, and Gate 8 explicitly says not to edit archive history to make this green.

Fail-closed: any failure returns exit code 1.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ACTIVE_DOCS = [
    "README.md",
    "docs/README.md",
    "docs/HOW_TO_RUN.md",
    "docs/RUN_LOCAL.md",
    "docs/MIGRATION.md",
    "docs/ENV_REFERENCE.md",
    "docs/TEST_STRATEGY.md",
    "docs/architecture/ACCELERATOR_FAMILIES.md",
    "docs/agent-reference/RUNTIME_AND_MEMORY.md",
    "docs/dev/LOCAL_SETUP.md",
    "docs/dev/validation_checks.md",
    "docs/dev/INTERNAL_OPERATIONS.md",
]

# (compiled pattern, human description). Matching text in an active doc is a failure.
BANNED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"isn'?t planned unless"), "claims standalone/native install isn't planned"),
    (re.compile(r"not planned unless"), "claims standalone/native install isn't planned"),
    (
        re.compile(r"TTS_BACKEND[`*]*\s*\(default\s*`?openvino`?\)"),
        "claims TTS_BACKEND defaults to openvino (actual default is pocket_tts)",
    ),
    (
        re.compile(r"\bDocker (is |)required\b", re.IGNORECASE),
        "claims Docker is required (native path exists)",
    ),
    (
        re.compile(r"only way to run|only supported way to run", re.IGNORECASE),
        "claims Docker is the only way to run Persona Forge",
    ),
]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def load_pyproject() -> dict:
    return tomllib.loads(_read("pyproject.toml"))


def check_console_entry_point(pyproject: dict, failures: list[str]) -> None:
    scripts = pyproject.get("project", {}).get("scripts", {})
    entry = scripts.get("persona-forge")
    if entry != "persona_forge.cli:main":
        failures.append(f"console entry point drifted from persona_forge.cli:main: {entry!r}")

    requires_python = pyproject.get("project", {}).get("requires-python", "")
    if requires_python != ">=3.13,<3.14":
        failures.append(f"requires-python drifted from '>=3.13,<3.14': {requires_python!r}")

    run_local = _read("docs/RUN_LOCAL.md")
    if requires_python and requires_python not in run_local:
        failures.append(
            f"docs/RUN_LOCAL.md does not mention the current requires-python bound {requires_python!r}"
        )


def check_docker_container_contract(failures: list[str]) -> None:
    dockerfile = _read("Dockerfile")

    cmd_match = re.search(r'CMD\s*\[(.*?)\]', dockerfile, re.DOTALL)
    if not cmd_match:
        failures.append("Dockerfile: could not locate a CMD [...] instruction to verify")
        return
    cmd_args = [tok.strip().strip('"') for tok in cmd_match.group(1).split(",")]
    if "gunicorn" not in cmd_args:
        failures.append("Dockerfile CMD no longer runs gunicorn — RUNTIME_AND_MEMORY.md's claim is stale")
        return
    if "-w" not in cmd_args or cmd_args[cmd_args.index("-w") + 1] != "1":
        failures.append("Dockerfile CMD is no longer single-worker (-w 1) — RUNTIME_AND_MEMORY.md's invariant is violated")

    runtime_doc = _read("docs/agent-reference/RUNTIME_AND_MEMORY.md")
    if "-w 1 -k gthread --threads 4" not in runtime_doc:
        failures.append(
            "docs/agent-reference/RUNTIME_AND_MEMORY.md no longer states the exact "
            "'-w 1 -k gthread --threads 4' gunicorn invocation matching the Dockerfile CMD"
        )

    expose_match = re.search(r"EXPOSE\s+(\d+)", dockerfile)
    port = expose_match.group(1) if expose_match else None
    if port != "8318":
        failures.append(f"Dockerfile EXPOSE port drifted from 8318: {port!r}")
    for doc_path in ("docs/RUN_LOCAL.md", "docs/MIGRATION.md"):
        if port and port not in _read(doc_path):
            failures.append(f"{doc_path} does not mention the current container port {port!r}")


def check_accelerator_manifest_parity(failures: list[str]) -> None:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    try:
        from persona_forge.accelerator_manifest import ACCELERATOR_PINS  # type: ignore
    except Exception as exc:  # pragma: no cover - environment-dependent
        failures.append(f"could not import persona_forge.accelerator_manifest: {exc}")
        return

    families_doc = _read("docs/architecture/ACCELERATOR_FAMILIES.md")
    env_doc = _read("docs/ENV_REFERENCE.md")
    pyproject = load_pyproject()
    extras = set(pyproject.get("project", {}).get("optional-dependencies", {}))

    for extra_name in ACCELERATOR_PINS:
        if extra_name not in extras:
            failures.append(
                f"accelerator_manifest declares {extra_name!r} but pyproject.toml has no matching extra"
            )
        if extra_name not in families_doc:
            failures.append(
                f"docs/architecture/ACCELERATOR_FAMILIES.md does not mention accelerator extra {extra_name!r}"
            )

    for family_var in ("GPU_FAMILY", "ACCEL_TORCH_INDEX_URL", "ACCEL_TORCH_VERSION", "ACCEL_TORCHAUDIO_VERSION"):
        if family_var not in env_doc:
            failures.append(f"docs/ENV_REFERENCE.md is missing accelerator var {family_var!r}")


def check_release_workflow_contract(failures: list[str]) -> None:
    try:
        import yaml  # type: ignore
    except ImportError:
        failures.append("PyYAML not installed - cannot validate release-launcher.yml structurally")
        return

    workflow_path = REPO_ROOT / ".github/workflows/release-launcher.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    on_block = workflow.get(True, workflow.get("on", {}))
    dispatch_inputs = on_block.get("workflow_dispatch", {}).get("inputs", {})
    if "tag_name" not in dispatch_inputs:
        failures.append("release-launcher.yml workflow_dispatch is missing the required 'tag_name' input")

    jobs = workflow.get("jobs", {})
    build_launcher = jobs.get("build-launcher", {})
    matrix_targets = {
        entry["target"] for entry in build_launcher.get("strategy", {}).get("matrix", {}).get("include", [])
    }
    expected_targets = {
        "x86_64-unknown-linux-musl",
        "x86_64-pc-windows-gnu",
        "aarch64-apple-darwin",
    }
    if matrix_targets != expected_targets:
        failures.append(
            f"release-launcher.yml build matrix targets {sorted(matrix_targets)} != expected {sorted(expected_targets)}"
        )

    launcher_src = REPO_ROOT / "launcher"
    if not launcher_src.is_dir():
        failures.append("release-launcher.yml references launcher/ but that directory does not exist")

    package_script = REPO_ROOT / "scripts" / "package_launcher_archive.py"
    if not package_script.is_file():
        failures.append("release-launcher.yml references scripts/package_launcher_archive.py which does not exist")


def check_env_name_parity(failures: list[str]) -> None:
    paths_src = _read("src/persona_forge/paths.py")
    migration_doc = _read("docs/MIGRATION.md")

    override_vars = [
        "PERSONA_FORGE_HOME",
        "MODEL_CACHE_DIR",
        "POCKET_TTS_ARTIFACT_DIR",
        "OV_DATA_DIR",
        "OV_CACHE_DIR",
        "VOICE_LIBRARY_DIR",
        "SEGMENT_LIBRARY_DIR",
        "DATA_DIR",
        "REF_AUDIO",
        "HF_TOKEN_FILE",
    ]
    for var in override_vars:
        if f'"{var}"' not in paths_src:
            failures.append(f"paths.py no longer reads env var {var!r} that MIGRATION.md documents as the native override")
        if var not in migration_doc:
            failures.append(f"docs/MIGRATION.md does not mention native override var {var!r} that paths.py reads")

    container_only_vars = [
        "MODEL_CACHE_CONTAINER_PATH",
        "VOICE_LIBRARY_PATH_CONTAINER",
    ]
    for var in container_only_vars:
        if var not in paths_src:
            failures.append(f"paths.py no longer reads container-side var {var!r} used in MIGRATION.md's mapping")


def check_banned_phrases(failures: list[str]) -> None:
    for rel_path in ACTIVE_DOCS:
        text = _read(rel_path)
        for pattern, description in BANNED_PATTERNS:
            if pattern.search(text):
                failures.append(f"{rel_path}: {description} (matched {pattern.pattern!r})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    failures: list[str] = []
    pyproject = load_pyproject()

    check_console_entry_point(pyproject, failures)
    check_docker_container_contract(failures)
    check_accelerator_manifest_parity(failures)
    check_release_workflow_contract(failures)
    check_env_name_parity(failures)
    check_banned_phrases(failures)

    status = "pass" if not failures else "fail"
    print(json.dumps({"status": status, "failures": failures}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

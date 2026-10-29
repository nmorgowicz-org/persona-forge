"""Keep the app/build runtime independent from Renovate's supported runtime.

These offline contract tests cover repository wiring and exact Renovate selectors.
Use the pinned Renovate toolchain separately to verify actual extraction/matching.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ".github/workflows/ci-renovate.yml"


def load_workflow(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def load_renovate() -> dict:
    return json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))


def test_only_validator_workflow_uses_node24():
    node_workflows = set()
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        relative = path.relative_to(ROOT).as_posix()
        workflow = load_workflow(relative)
        for job in workflow["jobs"].values():
            for step in job.get("steps", []):
                if not step.get("uses", "").startswith("actions/setup-node@"):
                    continue
                node_workflows.add(relative)
                version = step["with"]["node-version"]
                if version == "${{ env.NODE_VERSION }}":
                    version = workflow["env"]["NODE_VERSION"]
                assert version == ("24" if relative == VALIDATOR else "26"), relative
    assert node_workflows == {
        VALIDATOR,
        ".github/workflows/ci-ui.yml",
        ".github/workflows/ci-packaging.yml",
        ".github/workflows/desktop-build.yml",
        ".github/workflows/release-launcher.yml",
    }


def test_required_validate_gate_includes_reusable_validator():
    jobs = load_workflow(".github/workflows/ci.yml")["jobs"]
    caller = jobs["renovate"]
    required = jobs["validate"]
    reusable = load_workflow(VALIDATOR)
    # PyYAML's YAML 1.1 loader parses the unquoted GitHub Actions key 'on' as True.
    assert reusable.get("on", reusable.get(True)) == {"workflow_call": None}
    assert caller["uses"] == f"./{VALIDATOR}"
    assert required["needs"] == "renovate"
    # An ordinary needs-only job is skipped on dependency failure, which satisfies
    # required-check protection. Run on failures and explicitly fail instead.
    assert required["if"].startswith("!cancelled() && ")
    assert required["steps"][0]["run"] == "test '${{ needs.renovate.result }}' = 'success'"
    assert required["if"].removeprefix("!cancelled() && ") == caller["if"]
    assert reusable["jobs"]["validate-renovate"]["if"] == caller["if"]
    assert "head.repo.full_name == github.repository" in caller["if"]
    assert "!startsWith(github.event.head_commit.message, 'chore: release ')" in caller["if"]


def test_validator_pin_manager_tracks_new_workflow():
    managers = [m for m in load_renovate()["customManagers"] if m.get("depNameTemplate") == "renovate"]
    assert len(managers) == 1
    manager = managers[0]
    assert manager["datasourceTemplate"] == "npm"
    assert len(manager["managerFilePatterns"]) == 1
    # Renovate removes exactly one delimiter at each end, not every slash.
    file_pattern = manager["managerFilePatterns"][0][1:-1]
    assert re.fullmatch(file_pattern, VALIDATOR)
    assert not re.fullmatch(file_pattern, ".github/workflows/ci.yml")
    # The regex manager uses JS named groups; adapt only the group syntax for Python.
    pin_pattern = manager["matchStrings"][0].replace("(?<currentValue>", "(?P<currentValue>")
    match = re.search(pin_pattern, (ROOT / VALIDATOR).read_text(encoding="utf-8"))
    assert match is not None
    assert match.group("currentValue") == "44.181.11"


def test_renovate_node_override_is_narrow_and_ordered_last():
    rules = load_renovate()["packageRules"]
    node_rules = [r for r in rules if r.get("matchDepNames") == ["node"]]
    assert len(node_rules) == 2
    broad, narrow = node_rules
    for rule in node_rules:
        # setup-node extraction yields depName=node, packageName=actions/node-versions.
        assert rule["matchManagers"] == ["github-actions"]
        assert rule["matchDatasources"] == ["github-releases"]
        assert "matchPackageNames" not in rule
    assert "matchFileNames" not in broad
    assert broad["allowedVersions"] == ">=26.0.0 <27"
    assert narrow["matchFileNames"] == [VALIDATOR]
    assert narrow["allowedVersions"] == ">=24.11.0 <25"
    assert rules.index(narrow) > rules.index(broad)


def test_renovate_app_and_docker_constraints_stay_on26():
    rules = load_renovate()["packageRules"]
    npm_rule = next(r for r in rules if r.get("matchPackageNames") == ["node", "@types/node"])
    assert npm_rule["matchManagers"] == ["npm"]
    assert npm_rule["allowedVersions"] == ">=26.0.0 <27"
    docker_rule = next(r for r in rules if r.get("matchPackageNames") == ["node"])
    assert docker_rule["matchManagers"] == ["dockerfile", "docker-compose"]
    pattern = docker_rule["allowedVersions"].strip("/")
    assert re.search(pattern, "26-slim")
    assert not re.search(pattern, "24-slim")
    assert not re.search(pattern, "260-slim")


def test_frontend_lock_and_docker_match_app_runtime():
    manifest = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    assert manifest["engines"] == {"node": "^26.0.0"}
    assert lock["packages"][""]["engines"] == manifest["engines"]
    types_pin = manifest["devDependencies"]["@types/node"]
    assert types_pin.startswith("26.")
    assert lock["packages"][""]["devDependencies"]["@types/node"] == types_pin
    locked_types = lock["packages"]["node_modules/@types/node"]
    assert locked_types["version"] == types_pin
    assert locked_types["resolved"] == f"https://registry.npmjs.org/@types/node/-/node-{types_pin}.tgz"
    assert locked_types["integrity"].startswith("sha512-")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^ARG NODE_IMAGE=node:26-slim@sha256:[0-9a-f]{64}$", dockerfile, re.MULTILINE)


def test_all_node26_setup_paths_provision_linux_runtime_first():
    helper_run = "bash scripts/ci_node26_prerequisites.sh"
    covered = set()
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        relative = path.relative_to(ROOT).as_posix()
        workflow = load_workflow(relative)
        for job_name, job in workflow["jobs"].items():
            steps = job.get("steps", [])
            for index, step in enumerate(steps):
                if not step.get("uses", "").startswith("actions/setup-node@"):
                    continue
                version = step["with"]["node-version"]
                if version == "${{ env.NODE_VERSION }}":
                    version = workflow["env"]["NODE_VERSION"]
                if version != "26":
                    assert not any(s.get("run") == helper_run for s in steps), relative
                    continue
                # All current app setup sites bear Linux (including the native matrix).
                covered.add((path.name, job_name))
                prerequisites = [i for i, s in enumerate(steps) if s.get("run") == helper_run]
                assert len(prerequisites) == 1, (relative, job_name)
                prerequisite_index = prerequisites[0]
                assert prerequisite_index < index, (relative, job_name)
                assert any(
                    s.get("uses", "").startswith("actions/checkout@")
                    for s in steps[:prerequisite_index]
                ), (relative, job_name)
                prerequisite = steps[prerequisite_index]
                assert prerequisite["shell"] == "bash"
                expected_guard = "runner.os == 'Linux'"
                if step.get("if"):
                    expected_guard += f" && {step['if']}"
                assert prerequisite["if"] == expected_guard, (relative, job_name)
                assert not prerequisite.get("continue-on-error", False)
    assert covered == {
        ("ci-ui.yml", "frontend-lint"),
        ("ci-ui.yml", "e2e"),
        ("ci-packaging.yml", "package"),
        ("desktop-build.yml", "build-wheel"),
        ("release-launcher.yml", "build-wheel"),
    }


def test_node26_prerequisite_changes_trigger_relevant_path_gates():
    helper = "scripts/ci_node26_prerequisites.sh"
    packaging = load_workflow(".github/workflows/ci-packaging.yml")
    triggers = packaging.get("on", packaging.get(True))
    assert helper in triggers["pull_request"]["paths"]
    assert helper in triggers["push"]["paths"]
    ui = load_workflow(".github/workflows/ci-ui.yml")
    filters_step = next(s for s in ui["jobs"]["paths-filter"]["steps"] if s.get("id") == "filter")
    filters = yaml.safe_load(filters_step["with"]["filters"])
    assert helper in filters["code"]
    assert helper in filters["frontend"]

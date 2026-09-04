"""Compose-path contract test (docs/plans/20260829-no_more_docker_architecture.md §4).

Parses ``docker compose config --format json`` — never regexes compose.yml — so this fails
loudly if a future edit to compose.yml or an env default drifts from the exact container-side
runtime paths that persona_forge.paths' resolvers treat as highest-precedence overrides.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available")

EXPECTED_PATHS = {
    "MODEL_CACHE_CONTAINER_PATH": "/root/.cache/huggingface/hub",
    "OV_DATA_DIR": "/ov",
    "VOICE_LIBRARY_DIR": "/voices",
    "SEGMENT_LIBRARY_DIR": "/segments",
    "REF_AUDIO": "/voice/reference.wav",
    "HF_TOKEN_FILE": "/app/.hf_token",
    "OV_CACHE_DIR": "/ov/cache",
}


def _compose_config(*args: str) -> dict:
    result = subprocess.run(
        ["docker", "compose", *args, "config", "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.skip(f"docker compose config failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


class TestComposeContainerPaths:
    def test_persona_forge_service_paths(self):
        config = _compose_config()
        env = config["services"]["persona-forge"]["environment"]
        for key, expected in EXPECTED_PATHS.items():
            assert env[key] == expected, f"{key}: expected {expected!r}, got {env.get(key)!r}"

    def test_export_service_paths(self):
        config = _compose_config("--profile", "export")
        env = config["services"]["export"]["environment"]
        for key, expected in EXPECTED_PATHS.items():
            assert env[key] == expected, f"{key}: expected {expected!r}, got {env.get(key)!r}"
        # export.py's own output-root knob, distinct from the shared OV_DATA_DIR above —
        # both must point at the same container path.
        assert env["OV_OUTPUT_ROOT"] == "/ov"

    def test_volume_mount_targets_match_env_defaults(self):
        config = _compose_config()
        volumes = config["services"]["persona-forge"]["volumes"]
        targets = {v["target"]: v for v in volumes}
        assert targets["/root/.cache/huggingface/hub"]["type"] == "bind"
        assert targets["/ov"]["type"] == "bind"
        assert targets["/voices"]["type"] == "bind"
        assert targets["/segments"]["type"] == "bind"
        assert targets["/voice/reference.wav"]["type"] == "bind"

"""Tests for the Phase 8 semantic doc validator (scripts/validate_docs_semantics.py)."""

from __future__ import annotations

import pytest

from scripts.validate_docs_semantics import (
    BANNED_PATTERNS,
    check_accelerator_manifest_parity,
    check_console_entry_point,
    check_docker_container_contract,
    check_env_name_parity,
    check_release_workflow_contract,
    load_pyproject,
    main,
)


class TestAgainstRealRepo:
    """The validator's whole point is to check real repo state — run it for real."""

    def test_main_passes_clean_against_current_repo(self):
        assert main([]) == 0

    def test_console_entry_point_check_passes(self):
        failures: list[str] = []
        check_console_entry_point(load_pyproject(), failures)
        assert failures == []

    def test_docker_container_contract_check_passes(self):
        failures: list[str] = []
        check_docker_container_contract(failures)
        assert failures == []

    def test_accelerator_manifest_parity_check_passes(self):
        failures: list[str] = []
        check_accelerator_manifest_parity(failures)
        assert failures == []

    def test_release_workflow_contract_check_passes(self):
        failures: list[str] = []
        check_release_workflow_contract(failures)
        assert failures == []

    def test_env_name_parity_check_passes(self):
        failures: list[str] = []
        check_env_name_parity(failures)
        assert failures == []


class TestBannedPatterns:
    """Unit-level: the patterns themselves catch the stale claims they were written for."""

    @pytest.mark.parametrize(
        "text",
        [
            "Standalone install isn't planned unless there's real demand for it.",
            "A native install is not planned unless someone asks.",
            "**`TTS_BACKEND`** (default `openvino`)",
            "Docker is required to run Persona Forge.",
            "Docker required for any deployment.",
            "The container is the only way to run this project.",
            "the only supported way to run the service is via Docker",
        ],
    )
    def test_flags_known_stale_claims(self, text: str):
        assert any(pattern.search(text) for pattern, _ in BANNED_PATTERNS)

    @pytest.mark.parametrize(
        "text",
        [
            "Persona Forge also installs and runs natively via a source checkout.",
            "**`TTS_BACKEND`** (default `pocket_tts`)",
            "The container remains the canonical, most-tested deployment path.",
            "See RUN_LOCAL.md for the native alternative to Docker.",
        ],
    )
    def test_does_not_flag_accurate_current_claims(self, text: str):
        assert not any(pattern.search(text) for pattern, _ in BANNED_PATTERNS)

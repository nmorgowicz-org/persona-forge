"""Test validate_repo Release Please override parser."""

from __future__ import annotations

import pytest

from scripts.validate_repo import validate_pr_override_body


class TestReleasePleaseOverride:
    def test_accepts_single_type_entries_and_scopes(self):
        validate_pr_override_body(
            """Summary
BEGIN_COMMIT_OVERRIDE
feat(runtime): add generation RSS profiling

docs(handoff): record the M9 command

ci(deps): pin the cleanup action
END_COMMIT_OVERRIDE
"""
        )

    def test_rejects_composite_headers(self):
        with pytest.raises(RuntimeError, match="invalid entries"):
            validate_pr_override_body(
                """BEGIN_COMMIT_OVERRIDE
docs+export: describe and implement the export change

feat(bench)+docs: add benchmark results
END_COMMIT_OVERRIDE
"""
            )

    def test_accepts_entries_without_blank_line_separators(self):
        validate_pr_override_body(
            """BEGIN_COMMIT_OVERRIDE
feat(runtime): add generation RSS profiling
docs(handoff): record the M9 command
END_COMMIT_OVERRIDE
"""
        )

    def test_rejects_markdown_list_markers(self):
        with pytest.raises(RuntimeError, match="without a Markdown list marker"):
            validate_pr_override_body(
                """BEGIN_COMMIT_OVERRIDE
- fix(runtime): do not pass a list item to the commit parser
END_COMMIT_OVERRIDE
"""
            )

    def test_ignores_bodies_without_an_override(self):
        validate_pr_override_body("Renovate dependency update")

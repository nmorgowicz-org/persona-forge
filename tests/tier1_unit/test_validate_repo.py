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

    def test_accepts_a_single_line_breaking_change_footer(self):
        validate_pr_override_body(
            """BEGIN_COMMIT_OVERRIDE
feat(ui)!: redesign the deck

BREAKING CHANGE: the deck payload changed shape.
END_COMMIT_OVERRIDE
"""
        )

    def test_accepts_a_multi_line_breaking_change_note(self):
        """The form that failed CI: a footer paragraph is valid, and honoured.

        Release Please reads the block as the commit message and extracts
        BREAKING CHANGE notes from the summary, body, or footer, so rejecting a
        paragraph rejected a working way to declare a major bump.
        """
        validate_pr_override_body(
            """Some prose before the block.
BEGIN_COMMIT_OVERRIDE
feat(ui)!: redesign the deck

fix(runtime): stop dropping the tail
chore: archive the plan

BREAKING CHANGE: the deck payload changed shape, and the planning documents
moved. No HTTP contract changed.
END_COMMIT_OVERRIDE
"""
        )

    def test_accepts_an_entry_after_a_note(self):
        validate_pr_override_body(
            """BEGIN_COMMIT_OVERRIDE
feat(ui): first

BREAKING CHANGE: the first entry breaks.
docs: record it
END_COMMIT_OVERRIDE
"""
        )

    def test_rejects_prose_that_is_not_a_note(self):
        with pytest.raises(RuntimeError, match="invalid entries"):
            validate_pr_override_body(
                """BEGIN_COMMIT_OVERRIDE
feat(ui): redesign the deck

This paragraph is not an entry and not a note, so it would be dropped.
END_COMMIT_OVERRIDE
"""
            )

    def test_rejects_markdown_lists_inside_a_note(self):
        with pytest.raises(RuntimeError, match="invalid entries"):
            validate_pr_override_body(
                """BEGIN_COMMIT_OVERRIDE
feat(ui)!: redesign the deck

BREAKING CHANGE: the deck payload changed shape.
- deck.foo is now an object
END_COMMIT_OVERRIDE
"""
            )

    def test_ignores_bodies_without_an_override(self):
        validate_pr_override_body("Renovate dependency update")

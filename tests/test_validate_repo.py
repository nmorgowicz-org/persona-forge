import unittest

from scripts.validate_repo import validate_pr_override_body


class ReleasePleaseOverrideTests(unittest.TestCase):
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
        with self.assertRaisesRegex(RuntimeError, "invalid entries"):
            validate_pr_override_body(
                """BEGIN_COMMIT_OVERRIDE
docs+export: describe and implement the export change

feat(bench)+docs: add benchmark results
END_COMMIT_OVERRIDE
"""
            )

    def test_rejects_entries_without_blank_line_separators(self):
        with self.assertRaisesRegex(RuntimeError, "separated by blank lines"):
            validate_pr_override_body(
                """BEGIN_COMMIT_OVERRIDE
feat(runtime): add generation RSS profiling
docs(handoff): record the M9 command
END_COMMIT_OVERRIDE
"""
            )

    def test_ignores_bodies_without_an_override(self):
        validate_pr_override_body("Renovate dependency update")


if __name__ == "__main__":
    unittest.main()

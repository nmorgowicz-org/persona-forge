"""Test persona_forge.compat_patch: the Phase 5 unified qwen_tts/transformers site-package
patcher. Uses synthetic fixture files under tmp_path that mirror the shape of the six real
patches (never the real installed environment — matching the plan's "disposable environment,
never the shared dev environment" rule)."""

from __future__ import annotations

from pathlib import Path

import pytest

from persona_forge.compat_patch import (
    PATCHES,
    DeleteLines,
    Patch,
    Substitution,
    apply_qwen_patches,
    verify_qwen_patches,
)


def _write_tree(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


class TestApplyAndVerify:
    def test_apply_rewrites_matching_files_for_every_real_patch(self, tmp_path):
        for patch in PATCHES:
            text = ""
            for sub in patch.substitutions:
                text += sub.old * sub.expected_matches + "\n"
            if patch.delete_lines is not None:
                dl = patch.delete_lines
                text += (dl.contains + " marker\n") * dl.expected_matches
            _write_tree(tmp_path, patch.relative_path, text)

        report = apply_qwen_patches(tmp_path)

        assert report["status"] == "applied"
        assert {p["status"] for p in report["patches"]} == {"applied"}

    def test_second_apply_is_byte_identical_and_reports_already_applied(self, tmp_path):
        for patch in PATCHES:
            text = ""
            for sub in patch.substitutions:
                text += sub.old * sub.expected_matches + "\n"
            if patch.delete_lines is not None:
                dl = patch.delete_lines
                text += (dl.contains + " marker\n") * dl.expected_matches
            _write_tree(tmp_path, patch.relative_path, text)

        apply_qwen_patches(tmp_path)
        after_first = {
            patch.relative_path: (tmp_path / patch.relative_path).read_text() for patch in PATCHES
        }

        second = apply_qwen_patches(tmp_path)

        assert second["status"] == "already_applied"
        assert {p["status"] for p in second["patches"]} == {"already_applied"}
        for patch in PATCHES:
            assert (tmp_path / patch.relative_path).read_text() == after_first[patch.relative_path]

    def test_verify_never_writes(self, tmp_path):
        for patch in PATCHES:
            text = ""
            for sub in patch.substitutions:
                text += sub.old * sub.expected_matches + "\n"
            if patch.delete_lines is not None:
                dl = patch.delete_lines
                text += (dl.contains + " marker\n") * dl.expected_matches
            _write_tree(tmp_path, patch.relative_path, text)

        before = {
            patch.relative_path: (tmp_path / patch.relative_path).read_text() for patch in PATCHES
        }
        report = verify_qwen_patches(tmp_path)

        assert report["status"] == "applied"
        assert report["fully_applied"] is False
        for patch in PATCHES:
            assert (tmp_path / patch.relative_path).read_text() == before[patch.relative_path]

    def test_verify_reports_fully_applied_after_apply(self, tmp_path):
        for patch in PATCHES:
            text = ""
            for sub in patch.substitutions:
                text += sub.old * sub.expected_matches + "\n"
            if patch.delete_lines is not None:
                dl = patch.delete_lines
                text += (dl.contains + " marker\n") * dl.expected_matches
            _write_tree(tmp_path, patch.relative_path, text)

        apply_qwen_patches(tmp_path)
        report = verify_qwen_patches(tmp_path)

        assert report["status"] == "already_applied"
        assert report["fully_applied"] is True


class TestVersionDrift:
    def test_unexpected_match_count_is_reported_as_failed(self, tmp_path):
        patch = Patch(
            name="synthetic",
            relative_path="pkg/mod.py",
            substitutions=(Substitution("old_text", "new_text", expected_matches=1),),
        )
        # Two occurrences where exactly one (or zero) was expected: a genuine drift signal.
        _write_tree(tmp_path, patch.relative_path, "old_text\nold_text\n")

        from persona_forge import compat_patch as cp

        report = cp._process_patch(tmp_path, patch, dry_run=False)

        assert report["status"] == "failed"
        assert (tmp_path / patch.relative_path).read_text() == "old_text\nold_text\n"

    def test_zero_matches_means_already_applied_not_failed(self, tmp_path):
        patch = Patch(
            name="synthetic",
            relative_path="pkg/mod.py",
            substitutions=(Substitution("old_text", "new_text", expected_matches=1),),
        )
        _write_tree(tmp_path, patch.relative_path, "already patched, no target string present\n")

        from persona_forge import compat_patch as cp

        report = cp._process_patch(tmp_path, patch, dry_run=False)

        assert report["status"] == "already_applied"

    def test_delete_lines_unexpected_count_fails(self, tmp_path):
        patch = Patch(
            name="synthetic",
            relative_path="pkg/mod.py",
            delete_lines=DeleteLines("@decorator", expected_matches=1),
        )
        _write_tree(tmp_path, patch.relative_path, "@decorator\ndef f(): pass\n@decorator\n")

        from persona_forge import compat_patch as cp

        report = cp._process_patch(tmp_path, patch, dry_run=False)

        assert report["status"] == "failed"


class TestMissingFile:
    def test_missing_file_is_reported_as_failed(self, tmp_path):
        patch = Patch(
            name="synthetic",
            relative_path="pkg/does_not_exist.py",
            substitutions=(Substitution("old", "new", expected_matches=1),),
        )

        from persona_forge import compat_patch as cp

        report = cp._process_patch(tmp_path, patch, dry_run=False)

        assert report["status"] == "failed"
        assert report["detail"] == "file not found"

    def test_apply_qwen_patches_overall_status_is_failed_when_a_file_is_missing(self, tmp_path):
        # tmp_path has none of the real target files; every patch is a missing-file failure.
        report = apply_qwen_patches(tmp_path)
        assert report["status"] == "failed"


class TestRopeInsertionIdempotency:
    """Regression coverage for Task 4: three real substitutions (in PATCHES) insert text that
    contains their own `old` pattern as a substring, so a naive count-based re-check would find
    the same count post-patch and insert the function a second time."""

    def test_self_referential_substitution_does_not_duplicate_on_second_apply(self, tmp_path):
        marker = "already-applied-marker"
        sub = Substitution(
            old="ANCHOR:",
            new=f"inserted-block-with-{marker}\nANCHOR:",
            expected_matches=1,
            already_applied_marker=marker,
        )
        patch = Patch(name="synthetic-self-referential", relative_path="pkg/mod.py", substitutions=(sub,))
        _write_tree(tmp_path, patch.relative_path, "before\nANCHOR:\nafter\n")

        from persona_forge import compat_patch as cp

        r1 = cp._process_patch(tmp_path, patch, dry_run=False)
        assert r1["status"] == "applied"
        text_after_first = (tmp_path / patch.relative_path).read_text()
        assert text_after_first.count("inserted-block-with-" + marker) == 1

        r2 = cp._process_patch(tmp_path, patch, dry_run=False)
        assert r2["status"] == "already_applied"
        text_after_second = (tmp_path / patch.relative_path).read_text()
        assert text_after_second == text_after_first
        assert text_after_second.count("inserted-block-with-" + marker) == 1

    def test_without_marker_naive_reapply_would_duplicate(self, tmp_path):
        """Sanity check that the hazard is real: the same shape without a marker duplicates."""
        sub = Substitution(old="ANCHOR:", new="inserted-block\nANCHOR:", expected_matches=1)
        patch = Patch(name="synthetic-no-marker", relative_path="pkg/mod.py", substitutions=(sub,))
        _write_tree(tmp_path, patch.relative_path, "before\nANCHOR:\nafter\n")

        from persona_forge import compat_patch as cp

        cp._process_patch(tmp_path, patch, dry_run=False)
        r2 = cp._process_patch(tmp_path, patch, dry_run=False)

        # Without a marker, `old` ("ANCHOR:") still occurs exactly once post-patch, so this
        # correctly reports "applied" again and would duplicate the insertion — proving why the
        # real rope-parameters patches in PATCHES require already_applied_marker.
        assert r2["status"] == "applied"

    def test_real_rope_patches_all_carry_already_applied_markers(self):
        rope_patch = next(p for p in PATCHES if p.name == "rope_utils_default_rope_parameters")
        for sub in rope_patch.substitutions:
            assert sub.old in sub.new, "expected the self-referential shape this test documents"
            assert sub.already_applied_marker is not None

    def test_real_modeling_patch_marker_substitution_is_self_referential(self):
        modeling_patch = next(p for p in PATCHES if p.name == "modeling_qwen3_tts_transformers5_api")
        markered = [s for s in modeling_patch.substitutions if s.already_applied_marker is not None]
        assert markered, "expected at least one marker-carrying substitution"
        for sub in markered:
            assert sub.old in sub.new


class TestTransformersCompatDistinction:
    """Task 1: transformers_compat.py is a different, unrelated kind of patch (runtime
    monkey-patching of in-memory classes) and must not be covered/removed by this module."""

    def test_transformers_compat_still_importable_and_unrelated(self):
        from persona_forge import transformers_compat

        assert hasattr(transformers_compat, "repair_rotary_buffers")
        assert hasattr(transformers_compat, "patch_talker_prepare_inputs")
        assert hasattr(transformers_compat, "patch_eager_attention_mask_broadcast")
        # None of PATCHES touch transformers_compat.py itself.
        assert all("transformers_compat" not in p.relative_path for p in PATCHES)


@pytest.mark.parametrize("patch", PATCHES, ids=lambda p: p.name)
def test_every_real_patch_has_positive_expected_matches(patch: Patch):
    for sub in patch.substitutions:
        assert sub.expected_matches >= 1
    if patch.delete_lines is not None:
        assert patch.delete_lines.expected_matches >= 1

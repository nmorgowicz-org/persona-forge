"""Test asr_check text normalization, matching, and validation helpers (no real ASR)."""

from __future__ import annotations

import pytest

from qwen3_tts.asr_check import (
    _normalize_for_match,
    compute_transcript_match_score,
)


class TestNormalizeForMatch:
    def test_basic(self):
        assert _normalize_for_match("Hello, world!") == ["hello", "world"]

    def test_removes_bracketed_nonverbals(self):
        assert _normalize_for_match("Hi [laughter] there") == ["hi", "there"]

    def test_preserves_contractions(self):
        assert _normalize_for_match("it's fine") == ["it's", "fine"]

    def test_empty_input(self):
        assert _normalize_for_match("") == []

    def test_numeric_tokens(self):
        assert _normalize_for_match("step 1 and 2") == ["step", "1", "and", "2"]


class TestComputeTranscriptMatchScore:
    def test_perfect_match(self):
        score = compute_transcript_match_score(
            "hello world", "hello world"
        )
        assert score == 1.0

    def test_extra_words_accepted(self):
        score = compute_transcript_match_score(
            "hello world", "hello beautiful world today"
        )
        assert score == 1.0

    def test_no_match(self):
        score = compute_transcript_match_score(
            "foo bar", "abc def"
        )
        assert score == 0.0

    def test_partial_match(self):
        score = compute_transcript_match_score(
            "one two three", "one three"
        )
        assert pytest.approx(score, abs=1e-9) == 1 / 3

    def test_empty_reference_passes(self):
        assert compute_transcript_match_score("", "anything") == 1.0

    def test_order_matters(self):
        score = compute_transcript_match_score(
            "one two", "two one"
        )
        assert score < 1.0

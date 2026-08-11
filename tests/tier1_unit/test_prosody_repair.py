import threading
from unittest.mock import patch

import numpy as np
import pytest

from persona_forge.forced_alignment import Boundary
from persona_forge.prosody_repair import (
    build_alignment_pause_edits,
    repair_segment_audio,
    suggest_stitch_gap_targets,
)


def _voiced(seconds: float = 2.0, sr: int = 1000) -> np.ndarray:
    t = np.arange(int(seconds * sr), dtype=np.float32) / sr
    return (0.2 * np.sin(2 * np.pi * 80 * t)).astype(np.float32)


def test_stitch_gap_targets_use_terminal_punctuation_and_style():
    assert suggest_stitch_gap_targets(
        ["First sentence.", "Wait…", "last"], "Storyteller"
    ) == [1000.0, 1500.0]


def test_clause_pause_is_expand_only():
    # "togs," ran straight into the next word (no natural gap): the comma must be
    # skipped, never fabricated. The sentence-end owner is still manufactured.
    boundaries = [
        Boundary("togs", 0.0, 0.5, 0.99, "word", owns_clause=True).to_dict(),
        Boundary("heading", 0.5, 1.0, 0.99, "word").to_dict(),
        Boundary("arvo", 1.0, 1.5, 0.99, "sentence_split").to_dict(),
        Boundary("its", 1.6, 2.0, 0.99, "word").to_dict(),
    ]
    edits = build_alignment_pause_edits(boundaries, "Neutral", 1.0, 0.0)
    ats = {round(e["at_ms"]) for e in edits}
    assert 500 not in ats  # zero-gap comma skipped
    assert 1500 in ats  # sentence-end still manufactured


def test_clause_pause_kept_when_gap_exists():
    # A comma the speaker *did* pause at (100 ms gap) is expanded toward target.
    boundaries = [
        Boundary("first", 0.0, 0.5, 0.99, "word", owns_clause=True).to_dict(),
        Boundary("second", 0.6, 1.0, 0.99, "word").to_dict(),
    ]
    edits = build_alignment_pause_edits(boundaries, "Neutral", 1.0, 0.0)
    assert [round(e["at_ms"]) for e in edits] == [500]
    assert edits[0]["existing_ms"] == pytest.approx(100.0)


def test_target_override_adjusts_only_the_matching_boundary():
    # A per-boundary delta keyed by rounded at_ms (end*1000) is added on top of the preset
    # target for that one boundary; the others are untouched.
    boundaries = [
        Boundary("first", 0.0, 1.0, 0.99, "sentence_split").to_dict(),
        Boundary("second", 1.4, 2.0, 0.99, "sentence_split").to_dict(),
    ]
    base = build_alignment_pause_edits(boundaries, "Neutral", 1.0, 0.0)
    bumped = build_alignment_pause_edits(boundaries, "Neutral", 1.0, 0.0, {"1000": 250.0})
    base_by_at = {round(e["at_ms"]): e["target_ms"] for e in base}
    bumped_by_at = {round(e["at_ms"]): e["target_ms"] for e in bumped}
    assert bumped_by_at[1000] == pytest.approx(base_by_at[1000] + 250.0)
    assert bumped_by_at[2000] == pytest.approx(base_by_at[2000])  # untouched


def test_target_override_clamps_negative_to_zero():
    boundaries = [
        Boundary("only", 0.0, 1.0, 0.99, "sentence_split").to_dict(),
        Boundary("next", 1.4, 2.0, 0.99, "word").to_dict(),
    ]
    edits = build_alignment_pause_edits(boundaries, "Neutral", 1.0, 0.0, {"1000": -99999.0})
    assert edits[0]["target_ms"] == 0.0


def test_no_overrides_is_identical_to_none():
    boundaries = [
        Boundary("first", 0.0, 1.0, 0.99, "sentence_split").to_dict(),
        Boundary("second", 1.4, 2.0, 0.99, "sentence_split").to_dict(),
    ]
    assert build_alignment_pause_edits(boundaries, "Neutral", 1.0, 0.0, {}) == (
        build_alignment_pause_edits(boundaries, "Neutral", 1.0, 0.0)
    )


def test_auto_clean_segment_stays_sample_equivalent():
    sr = 24000
    first = _voiced(0.4, sr)
    gap = np.zeros(int(0.6 * sr), dtype=np.float32)
    wav = np.concatenate([first, gap, first])
    with patch("persona_forge.prosody_repair.forced_alignment.align") as align:
        repaired, plan, metadata = repair_segment_audio(
            wav, sr, "First sentence. Second sentence.", mode="auto"
        )
    align.assert_not_called()
    np.testing.assert_array_equal(repaired, wav)
    assert plan == []
    assert metadata["triage"]["mode"] == "natural"


def test_precise_segment_repairs_internal_boundary_with_shared_plan():
    sr = 1000
    wav = _voiced(2.0, sr)
    boundaries = [
        Boundary("first", 0.1, 0.8, 0.99, "sentence_split"),
        Boundary("second", 0.8, 1.8, 0.99, "word"),
    ]
    with patch("persona_forge.prosody_repair.forced_alignment.align", return_value=boundaries):
        repaired, plan, metadata = repair_segment_audio(
            wav,
            sr,
            "First. Second.",
            mode="precise",
            style_preset="Storyteller",
        )
    assert repaired.size == wav.size + 1000
    assert plan[0]["insert_ms"] == 1000.0
    assert plan[0]["origin"] == "alignment"
    assert metadata["resolved_mode"] == "precise"


def test_alignment_failure_falls_back_to_vad_safe_cut():
    wav = _voiced(2.0, 1000)
    with patch(
        "persona_forge.prosody_repair.forced_alignment.align",
        side_effect=RuntimeError("unavailable"),
    ):
        repaired, plan, metadata = repair_segment_audio(
            wav, 1000, "First. Second.", mode="precise"
        )
    assert repaired.size > wav.size
    assert plan[0]["origin"] == "vad"
    assert metadata["fallback"] == "vad"


def test_cancelled_alignment_never_renders_late_result():
    wav = _voiced(2.0, 1000)
    cancel = threading.Event()
    boundaries = [
        Boundary("first", 0.1, 0.8, 0.99, "sentence_split"),
        Boundary("second", 0.8, 1.8, 0.99, "word"),
    ]

    def finish_after_deadline(*args, **kwargs):
        cancel.set()
        return boundaries

    with patch(
        "persona_forge.prosody_repair.forced_alignment.align",
        side_effect=finish_after_deadline,
    ):
        repaired, plan, metadata = repair_segment_audio(
            wav,
            1000,
            "First. Second.",
            mode="precise",
            cancel_event=cancel,
        )

    np.testing.assert_array_equal(repaired, wav)
    assert plan == []
    assert metadata["fallback"] == "cancelled"

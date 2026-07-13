import threading
from unittest.mock import patch

import numpy as np

from qwen3_tts.forced_alignment import Boundary
from qwen3_tts.prosody_repair import repair_segment_audio, suggest_stitch_gap_targets


def _voiced(seconds: float = 2.0, sr: int = 1000) -> np.ndarray:
    t = np.arange(int(seconds * sr), dtype=np.float32) / sr
    return (0.2 * np.sin(2 * np.pi * 80 * t)).astype(np.float32)


def test_stitch_gap_targets_use_terminal_punctuation_and_style():
    assert suggest_stitch_gap_targets(
        ["First sentence.", "Wait…", "last"], "Storyteller"
    ) == [1000.0, 1500.0]


def test_auto_clean_segment_stays_sample_equivalent():
    sr = 24000
    first = _voiced(0.4, sr)
    gap = np.zeros(int(0.6 * sr), dtype=np.float32)
    wav = np.concatenate([first, gap, first])
    with patch("qwen3_tts.prosody_repair.forced_alignment.align") as align:
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
    with patch("qwen3_tts.prosody_repair.forced_alignment.align", return_value=boundaries):
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
        "qwen3_tts.prosody_repair.forced_alignment.align",
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
        "qwen3_tts.prosody_repair.forced_alignment.align",
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

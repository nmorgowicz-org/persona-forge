"""Phase 1 gate: prosody triage classifier + labeled fixture matrix.

Triage is a calibrated classifier, not a correctness oracle (plan §5.1). This
suite exercises a labeled matrix of synthetic clips spanning the cases the gate
calls out — clean gaps, blended (missing) gaps plus unrelated breaths,
abbreviations, decimals, ellipses, quoted punctuation, short sentences,
commas/clauses, and mismatched/missing transcripts — and records the resulting
false-negative / false-positive rates against the agreed thresholds.

Labels use the reference-side convention: PRECISE = "should escalate to
alignment" (blended); NATURAL = "fast energy path is fine."
"""

from __future__ import annotations

import numpy as np
import pytest

from qwen3_tts.prosody_triage import (
    MODE_NATURAL,
    MODE_PRECISE,
    count_expected_boundaries,
    triage,
)

SR = 16000


def _voiced(seconds: float, rng: np.random.Generator) -> np.ndarray:
    """A voiced-like block loud enough to survive librosa's top_db=30 split."""
    n = int(seconds * SR)
    t = np.linspace(0.0, seconds, n, endpoint=False, dtype=np.float32)
    tone = 0.2 * np.sin(2 * np.pi * 180.0 * t)
    tone += 0.05 * rng.standard_normal(n).astype(np.float32)
    return tone.astype(np.float32)


def _clip(segment_secs: list[float], gap_secs: list[float]) -> np.ndarray:
    """Build a clip from voiced segments separated by explicit silence gaps."""
    rng = np.random.default_rng(0)
    parts: list[np.ndarray] = []
    for i, seg in enumerate(segment_secs):
        parts.append(_voiced(seg, rng))
        if i < len(gap_secs):
            parts.append(np.zeros(int(gap_secs[i] * SR), dtype=np.float32))
    return np.concatenate(parts).astype(np.float32)


# name, transcript, segment_secs, gap_secs, expected_mode
MATRIX = [
    # --- Clean, well-gapped: fast path should stay natural ---
    ("clean_two", "Hello there. How are you today?", [0.7, 0.7], [0.45], MODE_NATURAL),
    ("clean_three", "One thing. Then another. And a third one.",
     [0.6, 0.6, 0.6], [0.4, 0.4], MODE_NATURAL),
    ("clean_comma_ok", "Well, I think so. Yes indeed.", [0.7, 0.7], [0.4], MODE_NATURAL),
    # --- Blended: sentence boundary with no gap → escalate ---
    ("blended_two", "She's right, no worries. We'll sort it out later.",
     [3.5], [], MODE_PRECISE),
    ("blended_three", "First point here. Second follows on. Third wraps up.",
     [4.0], [], MODE_PRECISE),
    ("blended_partial", "A. B here. C follows. D at the end now.",
     [1.0, 1.0], [0.4], MODE_PRECISE),  # 3 interior boundaries, only 1 gap
    # --- Missing gap masked by an unrelated breath elsewhere ---
    ("breath_masks", "This runs on. It really does keep going.",
     [1.2, 1.2], [0.35], MODE_NATURAL),  # 1 interior boundary, 1 gap → covered
    # --- Short sentences ---
    ("short_ok", "Go. Now.", [0.5, 0.5], [0.4], MODE_NATURAL),
    ("short_blended", "Go. Now. Move.", [1.5], [], MODE_PRECISE),
    # --- Abbreviations / decimals / non-terminal dots (no false PRECISE) ---
    # Single sentences: the "." in "Dr." / "3.5" is not a boundary.
    ("abbrev", "Dr. Smith arrived on time and said hello.", [2.0], [], MODE_NATURAL),
    ("decimal", "It costs 3.5 dollars in total today.", [2.0], [], MODE_NATURAL),
    # Abbreviation mid-clip must not mask a real blended boundary after it.
    ("abbrev_blended", "Dr. Smith arrived. He said hello to everyone.",
     [2.5], [], MODE_PRECISE),
    # --- Ellipsis ---
    ("ellipsis_blended", "Well... I suppose we could try it.", [2.0], [], MODE_PRECISE),
    # --- Quoted punctuation ---
    ("quoted", 'He said "stop." Then he left quickly.', [2.5], [], MODE_PRECISE),
    # --- Degenerate: mismatched / missing transcripts default to natural ---
    ("no_transcript", None, [1.0, 1.0], [0.4], MODE_NATURAL),
    ("no_punct", "just a plain phrase with no enders", [2.0], [], MODE_NATURAL),
]


@pytest.mark.parametrize("name,transcript,segs,gaps,expected", MATRIX,
                         ids=[row[0] for row in MATRIX])
def test_triage_matrix_case(name, transcript, segs, gaps, expected):
    result = triage(_clip(segs, gaps), SR, transcript)
    assert result.mode in (MODE_NATURAL, MODE_PRECISE)
    assert result.reasons, f"{name}: every verdict must carry an explanation"
    assert result.mode == expected, (
        f"{name}: got {result.mode} (coverage={result.coverage}, "
        f"expected_boundaries={result.boundaries_expected}, gaps={result.gaps_detected})"
    )


def test_triage_matrix_error_rates_recorded():
    """Record and bound the confusion matrix over the labeled fixture set.

    PRECISE is the positive class ("blended, needs alignment"). A false negative
    (blended clip left on the fast path) is the costly error the re-architecture
    exists to prevent; a false positive (clean clip escalated) only wastes an
    alignment pass. We bound both, holding FN to zero on this matrix.
    """
    tp = fp = tn = fn = 0
    for name, transcript, segs, gaps, expected in MATRIX:
        got = triage(_clip(segs, gaps), SR, transcript).mode
        if expected == MODE_PRECISE and got == MODE_PRECISE:
            tp += 1
        elif expected == MODE_NATURAL and got == MODE_PRECISE:
            fp += 1
        elif expected == MODE_NATURAL and got == MODE_NATURAL:
            tn += 1
        else:
            fn += 1

    total = tp + fp + tn + fn
    fn_rate = fn / max(1, tp + fn)  # blended clips missed
    fp_rate = fp / max(1, fp + tn)  # clean clips over-escalated
    print(
        f"\ntriage matrix (n={total}): TP={tp} FP={fp} TN={tn} FN={fn} "
        f"| FN_rate={fn_rate:.2f} FP_rate={fp_rate:.2f}"
    )

    # Gate: never miss a blended clip; keep clean-clip escalation acceptable.
    assert fn_rate == 0.0, f"blended clips misrouted to fast path: FN={fn}"
    assert fp_rate <= 0.2, f"too many clean clips escalated: FP_rate={fp_rate:.2f}"


def test_count_expected_boundaries_excludes_terminal_mark():
    # Terminal period has no interior gap; only the middle one counts.
    assert count_expected_boundaries("A here. B there. C last.") == 2.0
    assert count_expected_boundaries("Only one sentence here.") == 0.0
    assert count_expected_boundaries("") == 0.0


def test_count_expected_boundaries_comma_weight_tunable():
    text = "Well, then, we go. And stop."
    assert count_expected_boundaries(text, comma_weight=0.0) == 1.0
    assert count_expected_boundaries(text, comma_weight=0.5) == 2.0  # 1 interior period + 2*0.5 commas


def test_triage_no_transcript_is_natural_with_note():
    result = triage(_clip([1.0, 1.0], [0.4]), SR, None)
    assert result.mode == MODE_NATURAL
    assert result.coverage is None
    assert any("transcript" in r.lower() for r in result.reasons)


def test_triage_result_is_json_safe():
    import json

    result = triage(_clip([3.0], []), SR, "One. Two blended together here.")
    json.dumps(result.to_dict(), allow_nan=False)

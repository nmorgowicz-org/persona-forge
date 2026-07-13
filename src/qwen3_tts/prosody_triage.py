"""
Prosody triage (Phase 1 of the boundary-aware pause re-architecture).

Decide whether a reference clip can keep today's cheap energy-based pause path
(NATURAL) or needs the heavy forced-alignment pass (PRECISE). The signal is a
cheap comparison of *acoustic evidence* (silence gaps) against *linguistic
expectation* (sentence-ending punctuation in the stored transcript).

This module is deliberately dependency-light: it never loads a model, never
mutates audio, and only reuses `detect_pause_intervals` from `audio_style`.
Alignment itself arrives in Phase 2 — here PRECISE is only a *recommendation*
surfaced to the UI, with Natural/Precise available as manual overrides.

Triage is a calibrated classifier, not a correctness oracle: a detected breath
does not prove a particular punctuation mark was honored, and unrelated breaths
can mask a genuinely missing sentence gap. Its thresholds are tuned on the
labeled fixture matrix in `tests/tier1_unit/test_prosody_triage.py`, which also
records its false-negative / false-positive rates (the Phase 1 gate).
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, List, Optional, Tuple

import numpy as np
import librosa

from .audio_style import detect_pause_intervals

logger = logging.getLogger(__name__)

# --- Tunables (calibrated on the Phase 1 labeled matrix) ---

# Interior gaps shorter than this are breaths / co-articulation, not sentence
# boundaries, and must not count toward coverage.
MIN_GAP_MS = 120.0
# coverage >= COVERAGE_OK keeps the fast path; below it we escalate to PRECISE.
COVERAGE_OK = 0.8
# How strongly clause-level marks (commas/semicolons/colons/dashes) count toward
# expectation. Open question §10.1: start at sentence-enders only (0.0).
COMMA_WEIGHT = 0.0
# SNR below this only *annotates* the result (CTC degrades); it never gates.
LOW_SNR_DB = 15.0

MODE_NATURAL = "natural"
MODE_PRECISE = "precise"

SCHEMA_VERSION = 1

# Sentence-ending + strong punctuation, mirroring `get_pause_targets`' groups so
# triage and shaping agree on what a "boundary" is. Group 1: ellipsis, group 2:
# sentence enders, group 3: clause-level marks.
_PUNCT = re.compile(r"(\.{3,}|…)|([.!?])|([,;:]|—|–)")

# Common English abbreviations whose trailing period is not a sentence boundary.
# A cheap deterministic guard against triage over-escalating on abbreviations;
# it is not a substitute for the alignment-time normalization in Phase 2.
_ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "mt", "vs", "etc",
    "inc", "ltd", "co", "corp", "no", "vol", "fig", "e.g", "i.e", "a.m", "p.m",
})
_TRAILING_WORD = re.compile(r"([A-Za-z][A-Za-z.]*)$")


@dataclass
class TriageResult:
    """Structured triage verdict, persisted into `metrics["triage"]`."""

    mode: str
    coverage: Optional[float]
    boundaries_expected: float
    gaps_detected: int
    reasons: List[str] = field(default_factory=list)
    # Secondary signals — recorded to refine thresholds and explain the verdict;
    # they do not gate the Phase 1 decision (which is coverage-only for
    # deterministic calibration).
    median_gap_ms: float = 0.0
    speech_rate_cv: float = 0.0
    snr_db: Optional[float] = None
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def count_expected_boundaries(transcript: str, comma_weight: float = COMMA_WEIGHT) -> float:
    """Count *interior* sentence-ending punctuation, weighting clause marks separately.

    We deliberately diverge from the plan's raw punctuation count (§5.1): a
    terminal sentence-ender sits at the end of the clip and has no interior gap
    to detect, so counting it would systematically drag coverage down (a clean
    two-sentence clip would score 0.5 and misclassify as PRECISE). Only marks
    followed by further text are "interior boundaries" that a gap should cover.
    """
    trimmed = transcript.rstrip()
    strong = 0
    weak = 0
    for match in _PUNCT.finditer(trimmed):
        # Skip a mark with no following non-space text — it is terminal, not interior.
        if match.end() >= len(trimmed):
            continue
        if match.group(1):
            strong += 1
        elif match.group(2):
            if match.group(2) == "." and _is_non_boundary_dot(trimmed, match.start()):
                continue
            strong += 1
        elif match.group(3):
            weak += 1
    return float(strong) + comma_weight * float(weak)


def _is_non_boundary_dot(text: str, pos: int) -> bool:
    """True when the '.' at `pos` is a decimal point or a known abbreviation."""
    # Decimal: digit on both sides (e.g. "3.5").
    if 0 < pos < len(text) - 1 and text[pos - 1].isdigit() and text[pos + 1].isdigit():
        return True
    # Abbreviation: preceding alpha token is a known abbreviation (e.g. "Dr.").
    word_match = _TRAILING_WORD.search(text[:pos])
    if word_match:
        word = word_match.group(1).rstrip(".").lower()
        if word in _ABBREVIATIONS:
            return True
    return False


def _interior_gaps_ms(wav: np.ndarray, sr: int) -> List[float]:
    """Interior gap durations in ms (excludes leading/trailing boundary silence)."""
    intervals: List[Tuple[float, float]] = detect_pause_intervals(wav, sr)
    interior = intervals[1:-1] if len(intervals) > 2 else []
    return [(end - start) * 1000.0 for start, end in interior]


def _speech_rate_cv(wav: np.ndarray, sr: int) -> float:
    """Coefficient of variation of voiced-segment durations.

    A cheap proxy for delivery-rate variance across the clip: when it is high,
    proportional (character/time) gap mapping is unreliable, which is exactly
    when PRECISE alignment pays off. Recorded as a secondary signal only.
    """
    try:
        segments = librosa.effects.split(wav, top_db=30)
    except Exception:
        return 0.0
    if len(segments) < 2:
        return 0.0
    durations = np.array([(end - start) / sr for start, end in segments], dtype=np.float64)
    mean = float(durations.mean())
    if mean <= 0.0:
        return 0.0
    return float(durations.std() / mean)


def triage(
    wav: np.ndarray,
    sr: int,
    transcript: Optional[str] = None,
    *,
    snr_db: Optional[float] = None,
    min_gap_ms: float = MIN_GAP_MS,
    coverage_ok: float = COVERAGE_OK,
    comma_weight: float = COMMA_WEIGHT,
) -> TriageResult:
    """Classify a reference clip as NATURAL or PRECISE.

    Decision is coverage-only for deterministic calibration. Secondary signals
    (median gap, speech-rate CV, SNR) are recorded and surfaced but do not gate.
    """
    wav = np.asarray(wav, dtype=np.float32).ravel()
    reasons: List[str] = []

    interior_ms = _interior_gaps_ms(wav, sr)
    kept = [dur for dur in interior_ms if dur >= min_gap_ms]
    gaps_detected = len(kept)
    median_gap_ms = float(np.median(kept)) if kept else 0.0
    speech_rate_cv = _speech_rate_cv(wav, sr)

    def _finish(mode: str, coverage: Optional[float], expected: float) -> TriageResult:
        if snr_db is not None and snr_db < LOW_SNR_DB:
            reasons.append(
                f"Low SNR ({snr_db:.1f} dB) may degrade alignment accuracy."
            )
        return TriageResult(
            mode=mode,
            coverage=coverage,
            boundaries_expected=expected,
            gaps_detected=gaps_detected,
            reasons=reasons,
            median_gap_ms=median_gap_ms,
            speech_rate_cv=speech_rate_cv,
            snr_db=snr_db,
        )

    text = (transcript or "").strip()
    if not text:
        # Alignment needs text; without a transcript coverage is undefined.
        reasons.append("No transcript — alignment needs text; using Natural.")
        return _finish(MODE_NATURAL, None, 0.0)

    boundaries_expected = count_expected_boundaries(text, comma_weight)
    if boundaries_expected <= 0.0:
        reasons.append(
            "No sentence-ending punctuation — nothing to segment; using Natural."
        )
        return _finish(MODE_NATURAL, None, boundaries_expected)

    coverage = gaps_detected / max(1.0, boundaries_expected)
    if coverage >= coverage_ok:
        reasons.append(
            f"{gaps_detected} gap(s) cover {boundaries_expected:g} expected "
            f"boundary(ies) (coverage {coverage:.2f}); fast path."
        )
        return _finish(MODE_NATURAL, coverage, boundaries_expected)

    reasons.append(
        f"{gaps_detected} gap(s) detected, {boundaries_expected:g} sentence "
        f"boundary(ies) expected (coverage {coverage:.2f}) → blended speech."
    )
    return _finish(MODE_PRECISE, coverage, boundaries_expected)

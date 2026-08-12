"""
Automated take diagnostics: turns the metrics already computed by
audio_style.analyze_reference() into plain-language warnings a non-expert user can act on.

Each Diagnosis carries a `kb_entry_id` matching a key in
frontend/src/lib/glossary.ts's TROUBLESHOOTING map, so the UI can deep-link a chip
straight to its fix (see docs/plans/20260720-post_merge_initiatives.md §8, C4).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

# Thresholds are intentionally centralized here — one place to tune as we get real
# user feedback, rather than scattered magic numbers.
CLIPPING_PEAK_DBFS = -1.0  # matches audio_style.PEAK_CEILING_DB
FLAT_CADENCE_SPEECH_RATE_CV_MAX = 0.15  # below this, delivery pacing reads as mechanically even
FLAT_CADENCE_MIN_DURATION_SECONDS = 1.5  # too short to judge cadence reliably below this
ACCENT_DRIFT_MIN_GUIDANCE_SCALE = 1.8  # below this + a longer clip, accent adherence loosens
ACCENT_DRIFT_MIN_DURATION_SECONDS = 6.0


@dataclass
class Diagnosis:
    id: str
    severity: str  # 'info' | 'warning'
    message: str
    kb_entry_id: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def diagnose_take(
    metrics: Dict[str, Any],
    guidance_scale: Optional[float] = None,
) -> List[Diagnosis]:
    """Best-effort diagnostics for a single generated take.

    `metrics` is the dict returned by audio_style.analyze_reference(). Missing/None
    fields are treated as "no signal" rather than raising — diagnostics are advisory
    and must never break a generation response.
    """
    diagnoses: List[Diagnosis] = []
    if not metrics or metrics.get("error"):
        return diagnoses

    peak_dbfs = metrics.get("true_peak_dbfs", metrics.get("peak_dbfs"))
    if isinstance(peak_dbfs, (int, float)) and peak_dbfs >= CLIPPING_PEAK_DBFS:
        diagnoses.append(
            Diagnosis(
                id="clipping",
                severity="warning",
                message="Peak level is at or near 0 dBFS — this take may sound distorted.",
                kb_entry_id="clipping",
            )
        )

    duration = metrics.get("duration_seconds") or 0.0
    triage = metrics.get("triage") or {}
    speech_rate_cv = triage.get("speech_rate_cv")
    if (
        duration >= FLAT_CADENCE_MIN_DURATION_SECONDS
        and isinstance(speech_rate_cv, (int, float))
        and speech_rate_cv < FLAT_CADENCE_SPEECH_RATE_CV_MAX
    ):
        diagnoses.append(
            Diagnosis(
                id="robotic-cadence",
                severity="info",
                message="Delivery pacing is very even across this take — it may read as flat or robotic.",
                kb_entry_id="robotic-cadence",
            )
        )

    if (
        duration >= ACCENT_DRIFT_MIN_DURATION_SECONDS
        and isinstance(guidance_scale, (int, float))
        and guidance_scale < ACCENT_DRIFT_MIN_GUIDANCE_SCALE
    ):
        diagnoses.append(
            Diagnosis(
                id="accent-drift",
                severity="info",
                message="Low guidance scale on a longer take can let the accent loosen partway through.",
                kb_entry_id="accent-drift",
            )
        )

    return diagnoses

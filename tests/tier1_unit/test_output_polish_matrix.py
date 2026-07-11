"""Output-polish validation matrix.

Codifies the objective loudness/peak invariants every style preset's *output* must
satisfy, so a change to the ``apply_style_preset`` pipeline can't silently drift the
delivered loudness or blow the peak ceiling. This is the executable half of
docs/dev/OUTPUT_POLISH_MATRIX.md — keep the two in sync.

The expected LUFS values below come from the same preset table that builds
``STYLE_PRESETS``. The UI metadata and delivered output must stay aligned.
"""

from __future__ import annotations

import numpy as np
import pyloudnorm as pyln
import pytest

from qwen3_tts.audio_style import PEAK_CEILING_DB, STYLE_PRESETS, apply_style_preset

SR = 24000

# preset -> integrated LUFS the pipeline's final normalize step targets.
EXPECTED_LUFS = {
    "Neutral": -20.0,
    "Clean": -20.0,
    "Broadcast": -20.0,
    "Calm": -23.0,
    "Energetic": -20.0,
    "Storyteller": -23.0,
}

# Peak ceiling is uniform across every pipeline (limit_peak ceiling_db=-1.0).
PEAK_CEILING_LINEAR = 10.0 ** (PEAK_CEILING_DB / 20.0)

LUFS_TOLERANCE = 1.5   # LU; compression + limiting perturb integrated loudness slightly
PEAK_TOLERANCE = 0.02  # linear headroom for limiter overshoot / float rounding


def _speech_like(seconds: float = 3.0, sr: int = SR) -> np.ndarray:
    """A loud, dynamic, harmonically-rich signal so loudness/limiting have real work."""
    t = np.linspace(0.0, seconds, int(sr * seconds), endpoint=False, dtype=np.float32)
    fundamental = 0.6 * np.sin(2 * np.pi * 130.0 * t)
    harmonic = 0.25 * np.sin(2 * np.pi * 260.0 * t)
    sibilance = 0.1 * np.sin(2 * np.pi * 6000.0 * t)
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * 2.5 * t)  # 2.5 Hz syllabic envelope
    wav = (fundamental + harmonic + sibilance) * envelope
    return wav.astype(np.float32)


@pytest.mark.parametrize("preset", sorted(EXPECTED_LUFS))
def test_output_never_exceeds_peak_ceiling(preset: str) -> None:
    out, sr, _info = apply_style_preset(_speech_like(), SR, preset)
    peak = float(np.max(np.abs(out)))
    assert peak <= PEAK_CEILING_LINEAR + PEAK_TOLERANCE, (
        f"{preset}: peak {peak:.4f} exceeds ceiling "
        f"{PEAK_CEILING_LINEAR:.4f} ({PEAK_CEILING_DB} dBFS)"
    )


@pytest.mark.parametrize("preset,target_lufs", sorted(EXPECTED_LUFS.items()))
def test_output_hits_target_loudness(preset: str, target_lufs: float) -> None:
    out, sr, _info = apply_style_preset(_speech_like(), SR, preset)
    meter = pyln.Meter(sr)
    measured = float(meter.integrated_loudness(out))
    assert abs(measured - target_lufs) <= LUFS_TOLERANCE, (
        f"{preset}: measured {measured:.1f} LUFS, expected {target_lufs:.1f} "
        f"(+/- {LUFS_TOLERANCE} LU)"
    )


def test_no_clipping_introduced() -> None:
    """A hot, near-full-scale input must come out below full scale for every preset."""
    hot = (_speech_like() * 3.0).astype(np.float32)  # deliberately over-driven
    for preset in EXPECTED_LUFS:
        out, _sr, _info = apply_style_preset(hot, SR, preset)
        peak = float(np.max(np.abs(out)))
        assert peak <= 1.0, f"{preset}: output clips at {peak:.4f}"


def test_off_is_true_bypass() -> None:
    wav = _speech_like()

    out, sr, info = apply_style_preset(wav, SR, "off")

    assert sr == SR
    assert np.array_equal(out, wav)
    assert info["applied_steps"] == []
    assert info["bypassed"] is True
    assert STYLE_PRESETS["off"]["lufs"] is None
    assert STYLE_PRESETS["off"]["peak"] is None


@pytest.mark.parametrize("preset,target_lufs", sorted(EXPECTED_LUFS.items()))
def test_advertised_targets_match_delivered_targets(preset: str, target_lufs: float) -> None:
    assert STYLE_PRESETS[preset]["lufs"] == target_lufs
    assert STYLE_PRESETS[preset]["peak"] == PEAK_CEILING_DB

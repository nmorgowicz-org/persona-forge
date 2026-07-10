"""Tests for the richer audio style layer."""

from __future__ import annotations

import json

import numpy as np
import pyloudnorm as pyln
import pytest

from qwen3_tts.audio_style import analyze_reference, apply_style_preset, detect_pause_intervals


def _speech_like(sr: int = 24000) -> np.ndarray:
    t = np.linspace(0.0, 2.0, sr * 2, endpoint=False, dtype=np.float32)
    tone = 0.08 * np.sin(2 * np.pi * 220.0 * t)
    envelope = np.linspace(0.35, 1.0, tone.size, dtype=np.float32)
    return (tone * envelope).astype(np.float32)


def test_analyze_reference_returns_json_safe_lufs_for_silence() -> None:
    metrics = analyze_reference(np.zeros(24000, dtype=np.float32), 24000)

    assert metrics["lufs_integrated"] is None
    assert metrics["rms_dbfs"] == -100.0
    assert metrics["true_peak_dbtp"] == -100.0
    json.dumps(metrics, allow_nan=False)


def test_pause_metrics_use_shared_detector() -> None:
    sr = 24000
    wav = np.concatenate(
        [
            _speech_like(sr)[: sr // 2],
            np.zeros(int(sr * 0.2), dtype=np.float32),
            _speech_like(sr)[: sr // 2],
        ],
    )

    metrics = analyze_reference(wav, sr)
    pauses = detect_pause_intervals(wav, sr)

    assert metrics["pause_count"] == len(pauses["internal_pause_intervals"])
    assert metrics["pause_count"] >= 1
    assert metrics["pause_intervals"] == pauses["pause_intervals"]


@pytest.mark.parametrize("preset,target_lufs", [("Neutral", -20.0), ("Clean", -20.0), ("Calm", -23.0)])
def test_apply_style_preset_normalizes_toward_lufs(preset: str, target_lufs: float) -> None:
    sr = 24000
    wav = _speech_like(sr)

    polished, out_sr, metadata = apply_style_preset(wav, sr, preset)

    assert out_sr == sr
    assert any(step.startswith("normalize_lufs") for step in metadata["applied_steps"])
    measured = pyln.Meter(sr).integrated_loudness(polished)
    assert measured == pytest.approx(target_lufs, abs=1.5)

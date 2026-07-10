"""
Reference audio quality analysis and gating (Plan R1).
Calculates a 0-100 quality score based on duration, clipping, and SNR.
"""

from __future__ import annotations

import logging
import numpy as np
import librosa
from pathlib import Path
from typing import Any

from src.qwen3_tts.audio_style import analyze_reference

logger = logging.getLogger(__name__)

def calculate_snr(wav: np.ndarray, sr: int) -> float:
    """
    Estimate Signal-to-Noise Ratio (SNR).
    Uses a simple approach: compare energy of top 50% peaks (signal)
    vs bottom 10% (noise floor).
    """
    abs_wav = np.abs(wav)
    sorted_wav = np.sort(abs_wav)

    # Noise floor: bottom 10% of samples
    noise_floor = np.mean(sorted_wav[:int(len(sorted_wav) * 0.1)])
    # Signal: top 50% of samples
    signal_level = np.mean(sorted_wav[int(len(sorted_wav) * 0.5):])

    if noise_floor < 1e-7:
        return 100.0 # Perfect signal

    snr_db = 20.0 * np.log10(signal_level / noise_floor)
    return float(np.clip(snr_db, 0.0, 100.0))

def calculate_quality_score(wav_path: Path, transcript: str | None = None) -> tuple[float, list[str], dict[str, Any]]:
    """
    Analyze a reference WAV file and return a quality score (0-100), warnings, and full metrics.

    Criteria:
    - Duration: 3-15s (Ideal). <3s or >15s penalizes.
    - Clipping: peak_dbfs > -0.5dB is a failure.
    - SNR: > 20dB is good.
    """
    try:
        wav, sr = librosa.load(wav_path, sr=None)
        sr = int(sr)
        wav = np.asarray(wav, dtype=np.float32).ravel()
    except Exception as e:
        logger.error(f"Failed to load wav for analysis {wav_path}: {e}")
        return 0.0, ["Could not load audio file"], {}

    duration = wav.size / sr
    metrics = analyze_reference(wav, sr, transcript)

    score = 100.0
    warnings = []


    # 1. Duration Check (3-15s)
    if duration < 3.0:
        penalty = (3.0 - duration) * 10.0
        score -= penalty
        warnings.append(f"Too short ({duration:.1f}s). Min 3s recommended.")
    elif duration > 15.0:
        penalty = (duration - 15.0) * 5.0
        score -= penalty
        warnings.append(f"Too long ({duration:.1f}s). Max 15s recommended.")

    # 2. Clipping Check
    peak_dbfs = metrics.get("peak_dbfs", -100.0)
    if peak_dbfs > -0.5:
        score -= 30.0
        warnings.append(f"Audio is clipping (peak {peak_dbfs:.1f} dBFS).")

    # 3. SNR Check
    snr = calculate_snr(wav, int(sr))
    if snr < 15.0:

        score -= 20.0
        warnings.append(f"Low SNR ({snr:.1f} dB). Background noise may affect quality.")
    elif snr < 25.0:
        score -= 10.0
        warnings.append(f"Moderate SNR ({snr:.1f} dB).")

    score = float(np.clip(score, 0.0, 100.0))
    return score, warnings, metrics

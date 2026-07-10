"""
Audio style analysis and orchestration layer.
Delegates low-level DSP to audio_post.py.
"""

from __future__ import annotations

import logging
import numpy as np
import librosa
import pyloudnorm as pyln
from scipy import signal
from typing import Any

from . import audio_post

logger = logging.getLogger(__name__)


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _normalize_lufs(wav: np.ndarray, sr: int, target_lufs: float = -20.0) -> np.ndarray:
    """Scale audio toward integrated LUFS. No-op when loudness cannot be measured."""
    x = np.asarray(wav, dtype=np.float32).ravel()
    if x.size == 0:
        return x
    try:
        meter = pyln.Meter(sr)
        current_lufs = _finite_float(meter.integrated_loudness(x))
    except Exception as e:
        logger.warning(f"LUFS normalization failed: {e}")
        return x
    if current_lufs is None:
        return x
    gain_db = float(target_lufs) - current_lufs
    return (x * (10.0 ** (gain_db / 20.0))).astype(np.float32)


def analyze_reference(wav: np.ndarray, sr: int, transcript: str | None = None) -> dict[str, Any]:
    """
    Perform reference analysis on a voice sample.

    Args:
        wav: Audio signal as a float32 numpy array.
        sr: Sample rate.
        transcript: Optional text transcript for speech rate calculation.

    Returns:
        Dictionary of audio style metrics.
    """
    wav = np.asarray(wav, dtype=np.float32).ravel()
    duration = wav.size / sr

    if duration <= 0:
        return {}

    # 1. Basic Metrics
    peak_val = np.max(np.abs(wav))
    peak_dbfs = 20.0 * np.log10(peak_val / 1.0) if peak_val > 1e-9 else -100.0

    # 2. Loudness (LUFS)
    try:
        meter = pyln.Meter(sr)
        lufs_integrated = _finite_float(meter.integrated_loudness(wav))
    except Exception as e:
        logger.warning(f"Loudness analysis failed: {e}")
        lufs_integrated = None

    # 3. Pause Analysis (Energy-based)
    # librosa.effects.split returns intervals of non-silent audio
    try:
        # Use default top_db=60 for speech
        non_silent_intervals = librosa.effects.split(wav, top_db=60)

        if len(non_silent_intervals) == 0:
            pause_count = 0
            pause_total_seconds = duration
            pause_ratio = 1.0
            median_pause_ms = 0.0
            longest_pause_ms = 0.0
            pause_intervals = []
        else:
            # Calculate gaps between non-silent intervals
            gaps = []
            # Gap before first segment
            gaps.append((0.0, non_silent_intervals[0][0] / sr))
            # Gaps between segments
            for i in range(1, len(non_silent_intervals)):
                gap_start = non_silent_intervals[i-1][1] / sr
                gap_end = non_silent_intervals[i][0] / sr
                gaps.append((gap_start, gap_end))
            # Gap after last segment
            gaps.append((non_silent_intervals[-1][1] / sr, duration))

            pause_intervals = gaps
            gap_seconds = np.array([g[1] - g[0] for g in gaps])

            # Separate internal gaps from boundary silences for metrics
            internal_gap_seconds = gap_seconds[1:-1] if len(gaps) > 2 else np.array([])

            pause_count = len(internal_gap_seconds)
            pause_total_seconds = np.sum(gap_seconds) # Keep total including boundaries
            pause_ratio = pause_total_seconds / duration
            median_pause_ms = np.median(internal_gap_seconds) * 1000.0 if internal_gap_seconds.size > 0 else 0.0
            longest_pause_ms = np.max(internal_gap_seconds) * 1000.0 if internal_gap_seconds.size > 0 else 0.0
    except Exception as e:
        logger.warning(f"Pause analysis failed: {e}")
        pause_count = pause_ratio = pause_total_seconds = median_pause_ms = longest_pause_ms = 0.0
        pause_intervals = []


    # 4. Speech Rate Proxy
    if transcript:
        # Simple word count / duration
        word_count = len(transcript.split())
        speech_rate = word_count / duration if duration > 0 else 0.0
    else:
        # Voiced frames / total duration
        voiced_frames = np.sum(np.abs(wav) > 1e-4) # crude proxy for voiced energy
        speech_rate = (voiced_frames / sr) / duration if duration > 0 else 0.0

    return {
        "duration_seconds": float(duration),
        "sample_rate": int(sr),
        "lufs_integrated": lufs_integrated,
        "peak_dbfs": float(peak_dbfs),
        "speech_rate_proxy": float(speech_rate),
        "pause_count": int(pause_count),
        "pause_total_seconds": float(pause_total_seconds),
        "pause_ratio": float(pause_ratio),
        "median_pause_ms": float(median_pause_ms),
        "longest_pause_ms": float(longest_pause_ms),
        "pause_intervals": pause_intervals,
    }

def _apply_time_stretch(wav: np.ndarray, sr: int, factor: float) -> tuple[np.ndarray, float]:
    """
    Apply pitch-preserving time-stretch.
    factor > 1.0: Slower (longer duration)
    factor < 1.0: Faster (shorter duration)
    """
    # Guardrail: stretch factor must be within +/- 10%
    factor = np.clip(factor, 0.9, 1.1)

    # librosa.effects.time_stretch takes 'rate' where rate > 1.0 is faster.
    # rate = 1 / factor
    rate = 1.0 / factor

    # librosa returns float32
    return librosa.effects.time_stretch(wav, rate=rate).astype(np.float32), float(factor)

def _shape_pauses(wav: np.ndarray, sr: int, factor: float) -> tuple[np.ndarray, float]:
    """
    Modify internal pauses based on energy threshold.
    factor > 1.0: Lengthen pauses
    factor < 1.0: Shorten pauses
    """
    if np.abs(factor - 1.0) < 1e-4:
        return wav, 1.0

    try:
        # Detect non-silent intervals (top_db=60 is standard for speech)
        non_silent = librosa.effects.split(wav, top_db=60)
        if len(non_silent) <= 1:
            return wav, 1.0

        # We only modify INTERNAL pauses (gaps between non-silent intervals)
        # Gaps are (non_silent[i][1], non_silent[i+1][0])

        new_wav_parts = []
        last_end = 0

        # Minimum pause duration to bother modifying (e.g., 50ms)
        min_pause_samples = int(sr * 0.05)

        for i in range(len(non_silent)):
            start, end = non_silent[i]

            # Gap before this segment
            gap_start = last_end
            gap_end = start
            gap_len = gap_end - gap_start

            if gap_len > 0:
                # If it's an internal gap (not the very first gap) and above threshold
                if i > 0 and gap_len > min_pause_samples:
                    # Modify gap length
                    new_gap_len = int(gap_len * factor)
                    # Ensure we don't shrink to 0 if it was significant
                    new_gap_len = max(1, new_gap_len)

                    # Replace the gap with new length of zeros (or slice if shortening)
                    # Since we are building new_wav_parts, we just add the new gap
                    new_wav_parts.append(np.zeros(new_gap_len, dtype=np.float32))
                else:
                    # Keep gap as is
                    new_wav_parts.append(wav[gap_start:gap_end])

            # Add the speech segment
            new_wav_parts.append(wav[start:end])
            last_end = end

        # Add trailing silence as-is
        if last_end < wav.size:
            new_wav_parts.append(wav[last_end:])

        return np.concatenate(new_wav_parts).astype(np.float32), float(factor)

    except Exception as e:
        logger.warning(f"Pause shaping failed: {e}")
        return wav, 1.0

def _apply_warm_eq(wav: np.ndarray, sr: int) -> np.ndarray:
    """
    Apply a warm EQ (mild boost in lower-mids around 250Hz).
    """
    freq = 250.0
    gain_db = 3.0
    q = 1.0

    A = 10.0**(gain_db / 40.0)
    omega = 2.0 * np.pi * freq / sr
    alpha = np.sin(omega) / (2.0 * q)

    b = [1 + alpha * A, -2 * np.cos(omega), 1 - alpha * A]
    a = [1 + alpha / A, -2 * np.cos(omega), 1 - alpha / A]

    return signal.lfilter(b, a, wav).astype(np.float32)

def _apply_presence_boost(wav: np.ndarray, sr: int) -> np.ndarray:
    """
    Apply a presence boost (mild high-shelf around 3-5kHz).
    """
    # Simple high-shelf: high-pass filter at 3kHz, boost, and add back to original.
    try:
        # 1st order Butterworth high-pass at 3000Hz
        b, a = signal.butter(1, 3000 / (sr / 2), btype='high')
        presence = signal.lfilter(b, a, wav)
        # Add back with mild gain (approx +3dB boost in the high end)
        return (wav + 0.4 * presence).astype(np.float32)
    except Exception as e:
        logger.warning(f"Presence boost failed: {e}")
        return wav

def apply_style_preset(wav: np.ndarray, sr: int, preset: str, options: dict | None = None) -> tuple[np.ndarray, int, dict[str, Any]]:
    """
    Apply a named audio style preset using a sequence of audio_post operations.

    Presets:
        "Neutral": Standard normalization and limiting.
        "Clean": Compression and normalization for a more consistent, "studio" feel.
        "Broadcast": Stronger compression, normalization, and a presence boost.
        "Calm": Slower tempo, longer pauses, and warm EQ.
        "Energetic": Faster tempo, shorter pauses, and light compression.
        "Storyteller": Warm EQ, gentle compression, and longer pauses.
    """
    wav = np.asarray(wav, dtype=np.float32).ravel()
    applied_steps = []

    # Define preset pipelines
    # Each entry is (name, function, kwargs)
    pipelines = {
        "Neutral": [
            ("normalize_lufs", _normalize_lufs, {"target_lufs": -20.0}),
            ("limit_peak", audio_post.limit_peak, {"ceiling_db": -1.0}),
        ],
        "Clean": [
            ("compress", audio_post.compress, {"threshold_db": -24.0, "ratio": 2.5}),
            ("normalize_lufs", _normalize_lufs, {"target_lufs": -20.0}),
            ("limit_peak", audio_post.limit_peak, {"ceiling_db": -1.0}),
        ],
        "Broadcast": [
            ("compress", audio_post.compress, {"threshold_db": -20.0, "ratio": 3.0}),
            ("normalize_lufs", _normalize_lufs, {"target_lufs": -20.0}),
            ("presence_boost", _apply_presence_boost, {}),
            ("limit_peak", audio_post.limit_peak, {"ceiling_db": -1.0}),
        ],
        "Calm": [
            ("time_stretch", _apply_time_stretch, {"factor": 1.05}),
            ("shape_pauses", _shape_pauses, {"factor": 1.10}),
            ("warm_eq", _apply_warm_eq, {}),
            ("normalize_lufs", _normalize_lufs, {"target_lufs": -23.0}),
            ("limit_peak", audio_post.limit_peak, {"ceiling_db": -1.0}),
        ],
        "Energetic": [
            ("time_stretch", _apply_time_stretch, {"factor": 0.95}),
            ("shape_pauses", _shape_pauses, {"factor": 0.90}),
            ("compress", audio_post.compress, {"threshold_db": -20.0, "ratio": 2.0}),
            ("normalize_lufs", _normalize_lufs, {"target_lufs": -20.0}),
            ("limit_peak", audio_post.limit_peak, {"ceiling_db": -1.0}),
        ],
        "Storyteller": [
            ("warm_eq", _apply_warm_eq, {}),
            ("compress", audio_post.compress, {"threshold_db": -24.0, "ratio": 2.0}),
            ("shape_pauses", _shape_pauses, {"factor": 1.10}),
            ("normalize_lufs", _normalize_lufs, {"target_lufs": -23.0}),
            ("limit_peak", audio_post.limit_peak, {"ceiling_db": -1.0}),
        ],
    }

    pipeline = pipelines.get(preset, pipelines["Neutral"])

    current_wav = wav.copy()
    for name, func, kwargs in pipeline:
        try:
            # Merge options if provided (simple override)
            step_kwargs = kwargs.copy()
            if options:
                for k, v in options.items():
                    if k in step_kwargs:
                        step_kwargs[k] = v

            # Execute step
            res = func(current_wav, sr, **step_kwargs) if "sr" in func.__code__.co_varnames else func(current_wav, **step_kwargs)

            # Handle tuple return for steps that record metadata (like time_stretch)
            if isinstance(res, tuple):
                current_wav = res[0]
                val = res[1]
                applied_steps.append(f"{name}({val})")
            else:
                current_wav = res
                applied_steps.append(name)

        except Exception as e:
            logger.warning(f"Style preset step {name} failed: {e}. Failing open.")
            applied_steps.append(f"{name}_failed")

    metadata = {"applied_steps": applied_steps, "preset": preset}
    return current_wav, sr, metadata

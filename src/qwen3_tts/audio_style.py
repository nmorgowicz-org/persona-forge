"""
Orchestration layer for voice style and reference analysis.
Delegates low-level DSP to src/qwen3_tts/audio_post.py.
"""

from __future__ import annotations

import logging
import numpy as np
import pyloudnorm as pyln
import librosa
from scipy import signal
from typing import Any, Callable, Dict, Tuple, Optional, List

from .audio_post import (
    compress,
    limit_peak,
)

logger = logging.getLogger(__name__)

# --- Constants ---

DEFAULT_SAMPLE_RATE = 24000
TARGET_LUFS = -20.0
PEAK_CEILING_DB = -1.0

StepFn = Callable[..., np.ndarray | tuple[np.ndarray, float]]
PipelineStep = tuple[str, StepFn, dict[str, Any]]


def _steps(*steps: PipelineStep) -> list[PipelineStep]:
    return list(steps)


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

def detect_pause_intervals(wav: np.ndarray, sr: int, top_db: float = 40.0) -> List[Tuple[float, float]]:
    """Returns a list of (start, end) seconds for silence intervals."""
    # librosa.effects.split returns non-silent intervals
    non_silent = librosa.effects.split(wav, top_db=top_db)
    if len(non_silent) == 0:
        return [(0.0, wav.size / sr)]
    
    duration = wav.size / sr
    gaps = []
    # Gap before first segment
    gaps.append((0.0, non_silent[0][0] / sr))
    # Gaps between segments
    for i in range(1, len(non_silent)):
        gap_start = non_silent[i-1][1] / sr
        gap_end = non_silent[i][0] / sr
        gaps.append((gap_start, gap_end))
    # Gap after last segment
    gaps.append((non_silent[-1][1] / sr, duration))
    return gaps

def analyze_reference(wav: np.ndarray, sr: int, transcript: Optional[str] = None) -> Dict[str, Any]:
    """
    Perform reference analysis on a voice sample.
    """
    wav = np.asarray(wav, dtype=np.float32).ravel()
    duration = wav.size / sr
    if duration <= 0:
        return {}

    # 1. Basic Metrics
    peak_val = np.max(np.abs(wav))
    peak_dbfs = 20.0 * np.log10(peak_val / 1.0) if peak_val > 1e-9 else -100.0
    true_peak_dbfs = peak_dbfs  # Simple proxy; full inter-sample peak requires oversampling


    # 2. Loudness (LUFS)
    try:
        meter = pyln.Meter(sr)
        lufs_integrated = _finite_float(meter.integrated_loudness(wav))
    except Exception as e:
        logger.warning(f"Loudness analysis failed: {e}")
        lufs_integrated = None

    # 3. Pause Analysis
    try:
        pause_intervals = detect_pause_intervals(wav, sr)
        gap_seconds = np.array([g[1] - g[0] for g in pause_intervals])
        # Internal gaps exclude boundary silences
        internal_gaps = gap_seconds[1:-1] if len(pause_intervals) > 2 else np.array([])

        pause_count = len(internal_gaps)
        pause_total_seconds = np.sum(gap_seconds)
        pause_ratio = pause_total_seconds / duration
        median_pause_ms = np.median(internal_gaps) * 1000.0 if internal_gaps.size > 0 else 0.0
        longest_pause_ms = np.max(internal_gaps) * 1000.0 if internal_gaps.size > 0 else 0.0
    except Exception as e:
        logger.warning(f"Pause analysis failed: {e}")
        pause_count = pause_ratio = pause_total_seconds = median_pause_ms = longest_pause_ms = 0.0
        pause_intervals = []

    # 4. Speech Rate Proxy
    if transcript:
        word_count = len(transcript.split())
        speech_rate = word_count / duration if duration > 0 else 0.0
    else:
        # Voiced frames proxy
        voiced_frames = np.sum(np.abs(wav) > 1e-4)
        speech_rate = (voiced_frames / sr) / duration if duration > 0 else 0.0

    return {
        "duration_seconds": float(duration),
        "sample_rate": int(sr),
        "lufs_integrated": lufs_integrated,
        "peak_dbfs": float(peak_dbfs),
        "true_peak_dbfs": float(true_peak_dbfs),
        "speech_rate_proxy": float(speech_rate),
        "pause_count": int(pause_count),
        "pause_total_seconds": float(pause_total_seconds),
        "pause_ratio": float(pause_ratio),
        "median_pause_ms": float(median_pause_ms),
        "longest_pause_ms": float(longest_pause_ms),
        "pause_intervals": pause_intervals,
    }

def _apply_time_stretch(wav: np.ndarray, sr: int, factor: float) -> Tuple[np.ndarray, float]:
    """
    Apply pitch-preserving time-stretch.
    factor > 1.0: Slower (longer duration)
    factor < 1.0: Faster (shorter duration)
    """
    factor = np.clip(factor, 0.9, 1.1)
    rate = 1.0 / factor
    return librosa.effects.time_stretch(wav, rate=rate).astype(np.float32), float(factor)

def _shape_pauses(wav: np.ndarray, sr: int, factor: float) -> Tuple[np.ndarray, float]:
    """
    Modify internal pauses based on energy threshold.
    factor > 1.0: Lengthen pauses
    factor < 1.0: Shorten pauses
    """
    if np.abs(factor - 1.0) < 1e-4:
        return wav, 1.0

    try:
        non_silent = librosa.effects.split(wav, top_db=60)
        if len(non_silent) <= 1:
            return wav, 1.0

        new_wav_parts = []
        last_end = 0
        min_pause_samples = int(sr * 0.05)

        for i in range(len(non_silent)):
            start, end = non_silent[i]
            gap_len = start - last_end
            if gap_len > 0:
                if i > 0 and gap_len > min_pause_samples:
                    new_gap_len = max(1, int(gap_len * factor))
                    new_wav_parts.append(np.zeros(new_gap_len, dtype=np.float32))
                else:
                    new_wav_parts.append(wav[last_end:start])
            new_wav_parts.append(wav[start:end])
            last_end = end

        if last_end < wav.size:
            new_wav_parts.append(wav[last_end:])

        return np.concatenate(new_wav_parts).astype(np.float32), float(factor)
    except Exception as e:
        logger.warning(f"Pause shaping failed: {e}")
        return wav, 1.0

def _apply_warm_eq(wav: np.ndarray, sr: int) -> np.ndarray:
    """Apply a warm EQ (mild boost in lower-mids around 250Hz)."""
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
    """Apply a presence boost (mild high-shelf around 3-5kHz)."""
    try:
        b, a = signal.butter(1, 3000 / (sr / 2), btype='high')
        presence = signal.lfilter(b, a, wav)
        return (wav + 0.4 * presence).astype(np.float32)
    except Exception as e:
        logger.warning(f"Presence boost failed: {e}")
        return wav


# Single source of truth for both advertised metadata and delivered DSP behavior.
# "off" is a real bypass; all other presets derive STYLE_PRESETS and execution
# from the same rows so UI copy cannot drift away from the pipeline.
STYLE_PIPELINES: dict[str, dict[str, Any]] = {
    "off": {
        "lufs": None,
        "peak": None,
        "compress": None,
        "steps": _steps(),
    },
    "Neutral": {
        "lufs": TARGET_LUFS,
        "peak": PEAK_CEILING_DB,
        "compress": None,
        "steps": _steps(
            ("normalize_lufs", _normalize_lufs, {"target_lufs": TARGET_LUFS}),
            ("limit_peak", limit_peak, {"ceiling_db": PEAK_CEILING_DB}),
        ),
    },
    "Clean": {
        "lufs": TARGET_LUFS,
        "peak": PEAK_CEILING_DB,
        "compress": {"threshold_db": -24.0, "ratio": 2.5},
        "steps": _steps(
            ("compress", compress, {"threshold_db": -24.0, "ratio": 2.5}),
            ("normalize_lufs", _normalize_lufs, {"target_lufs": TARGET_LUFS}),
            ("limit_peak", limit_peak, {"ceiling_db": PEAK_CEILING_DB}),
        ),
    },
    "Broadcast": {
        "lufs": TARGET_LUFS,
        "peak": PEAK_CEILING_DB,
        "compress": {"threshold_db": -20.0, "ratio": 3.0},
        "steps": _steps(
            ("compress", compress, {"threshold_db": -20.0, "ratio": 3.0}),
            ("normalize_lufs", _normalize_lufs, {"target_lufs": TARGET_LUFS}),
            ("presence_boost", _apply_presence_boost, {}),
            ("limit_peak", limit_peak, {"ceiling_db": PEAK_CEILING_DB}),
        ),
    },
    "Calm": {
        "lufs": -23.0,
        "peak": PEAK_CEILING_DB,
        "compress": None,
        "steps": _steps(
            ("time_stretch", _apply_time_stretch, {"factor": 1.05}),
            ("shape_pauses", _shape_pauses, {"factor": 1.10}),
            ("warm_eq", _apply_warm_eq, {}),
            ("normalize_lufs", _normalize_lufs, {"target_lufs": -23.0}),
            ("limit_peak", limit_peak, {"ceiling_db": PEAK_CEILING_DB}),
        ),
    },
    "Energetic": {
        "lufs": TARGET_LUFS,
        "peak": PEAK_CEILING_DB,
        "compress": {"threshold_db": -20.0, "ratio": 2.0},
        "steps": _steps(
            ("time_stretch", _apply_time_stretch, {"factor": 0.95}),
            ("shape_pauses", _shape_pauses, {"factor": 0.90}),
            ("compress", compress, {"threshold_db": -20.0, "ratio": 2.0}),
            ("normalize_lufs", _normalize_lufs, {"target_lufs": TARGET_LUFS}),
            ("limit_peak", limit_peak, {"ceiling_db": PEAK_CEILING_DB}),
        ),
    },
    "Storyteller": {
        "lufs": -23.0,
        "peak": PEAK_CEILING_DB,
        "compress": {"threshold_db": -24.0, "ratio": 2.0},
        "steps": _steps(
            ("warm_eq", _apply_warm_eq, {}),
            ("compress", compress, {"threshold_db": -24.0, "ratio": 2.0}),
            ("shape_pauses", _shape_pauses, {"factor": 1.10}),
            ("normalize_lufs", _normalize_lufs, {"target_lufs": -23.0}),
            ("limit_peak", limit_peak, {"ceiling_db": PEAK_CEILING_DB}),
        ),
    },
}

STYLE_PRESETS = {
    name: {key: value for key, value in config.items() if key != "steps"}
    for name, config in STYLE_PIPELINES.items()
}


def apply_style_preset(wav: np.ndarray, sr: int, preset: str, options: Optional[Dict[str, Any]] = None) -> Tuple[np.ndarray, int, Dict[str, Any]]:
    """
    Apply a named audio style preset using a sequence of audio_post operations.
    """
    wav = np.asarray(wav, dtype=np.float32).ravel()
    preset_config = STYLE_PIPELINES.get(preset, STYLE_PIPELINES["Neutral"])
    resolved_preset = preset if preset in STYLE_PIPELINES else "Neutral"
    pipeline = preset_config["steps"]
    current_wav = wav.copy()

    if not pipeline:
        return current_wav, sr, {
            "applied_steps": [],
            "preset": preset,
            "resolved_preset": resolved_preset,
            "bypassed": True,
        }

    applied_steps = []
    for name, func, kwargs in pipeline:
        try:
            step_kwargs = kwargs.copy()
            if options:
                for k, v in options.items():
                    if k in step_kwargs:
                        step_kwargs[k] = v
            res = func(current_wav, sr, **step_kwargs) if "sr" in func.__code__.co_varnames else func(current_wav, **step_kwargs)
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

    return current_wav, sr, {
        "applied_steps": applied_steps,
        "preset": preset,
        "resolved_preset": resolved_preset,
        "target_lufs": preset_config["lufs"],
        "peak_ceiling_db": preset_config["peak"],
    }

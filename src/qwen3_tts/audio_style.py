"""
Orchestration layer for voice style and reference analysis.
Delegates low-level DSP to src/qwen3_tts/audio_post.py.
"""

from __future__ import annotations

import logging
import numpy as np
import pyloudnorm as pyln
import librosa
import re
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

def detect_pause_intervals(wav: np.ndarray, sr: int, top_db: float = 30.0) -> List[Tuple[float, float]]:
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

def get_pause_targets(
    prompt: str,
    style_preset: str,
    pace_multiplier: float,
    gap_starts: List[float],
    audio_duration: float,
    pause_offset_ms: float = 0.0
) -> Dict[int, Tuple[float, str]]:
    """
    Calculate target durations (in seconds) and trigger types for a sequence of gaps based on
    punctuation in the prompt and a style preset, using temporal proportional mapping.
    """
    prosody = PROSODY_MAPS.get(style_preset, PROSODY_MAPS["Neutral"])

    # 1. Identify punctuation triggers and their character positions in the prompt.
    # Group 3 is the comma-class: commas plus other clause-level breaks (semicolon, colon,
    # em/en dash) all read as a comma-length pause. `!`/`?` collapse to sentence_end — the
    # perceived pause after them matches a period.
    pattern = r"(\.{3,}|…|\u2026)|([.!?])|([,;:]|—|–)"
    triggers = []
    for match in re.finditer(pattern, prompt):
        if match.group(1):
            t_type = "ellipsis"
        elif match.group(2):
            t_type = "sentence_end"
        elif match.group(3):
            t_type = "comma"
        else:
            continue

        triggers.append({
            "type": t_type,
            "pos": match.start() / len(prompt) if len(prompt) > 0 else 0.0
        })

    # Initialize all gaps to natural target
    targets = {}
    natural_dur = (prosody["natural"] * pace_multiplier + pause_offset_ms) / 1000.0
    for i in range(len(gap_starts)):
        targets[i] = (natural_dur, "natural")

    # 2. For each punctuation trigger, find the audio gap closest to the proportional time.
    for trigger in triggers:
        t_pos = trigger["pos"]
        best_gap_idx = -1
        min_diff = float('inf')

        for gap_idx, gap_start in enumerate(gap_starts):
            g_pos = gap_start / audio_duration if audio_duration > 0 else 0.0
            diff = abs(g_pos - t_pos)
            if diff < min_diff:
                min_diff = diff
                best_gap_idx = gap_idx

        # Threshold: Only map if the gap is within 5% of the total duration from the expected position.
        # This prevents "pause drift" where distant punctuation hijacks random gaps.
        if best_gap_idx != -1 and min_diff < 0.05:
            target_key = trigger["type"]
            target_ms = prosody.get(target_key, prosody["natural"])
            duration = (target_ms * pace_multiplier + pause_offset_ms) / 1000.0
            targets[best_gap_idx] = (duration, target_key)

    return targets


def _shape_pauses(wav: np.ndarray, sr: int, prompt: str = "", style_preset: str = "Neutral", pace_multiplier: float = 1.0, pause_offset_ms: float = 0.0, **kwargs) -> Tuple[np.ndarray, float]:
    """
    Modify internal pauses based on punctuation in the prompt and a style map.
    """
    if np.abs(pace_multiplier - 1.0) < 1e-4 and not prompt and np.abs(pause_offset_ms) < 1e-4:
        return wav, 1.0

    try:
        # 1. Identify all gaps in the audio
        non_silent = librosa.effects.split(wav, top_db=30)
        if len(non_silent) <= 1:
            return wav, 1.0

        # 2. Get punctuation-aware targets using temporal proportional mapping
        audio_duration = wav.size / sr
        gap_starts = [non_silent[i][1] / sr for i in range(len(non_silent) - 1)]
        targets = get_pause_targets(prompt, style_preset, pace_multiplier, gap_starts, audio_duration, pause_offset_ms)

        new_wav_parts = []
        last_end = 0

        for i in range(len(non_silent)):
            start, end = non_silent[i]
            gap_len = start - last_end

            if gap_len > 0:
                if i > 0:
                    # Match this gap to its target duration
                    target_sec, trigger_type = targets.get(i-1, (0.0, "natural"))

                    if trigger_type == "natural":
                        # Unmatched gap (breath/hesitation): scale by pace to preserve the
                        # speaker's own delivery character. Never snap a breath to a fixed
                        # constant — that mechanizes the pacing. (gap_len is in samples, so
                        # scale it directly; no seconds conversion needed.)
                        new_gap_len = max(1, int(gap_len * pace_multiplier))
                    else:
                        # Punctuation-driven structural pause: resize to the absolute target.
                        new_gap_len = max(1, int(target_sec * sr))
                    new_wav_parts.append(np.zeros(new_gap_len, dtype=np.float32))
                else:
                    # Boundary silence: leave as is
                    new_wav_parts.append(wav[last_end:start])

            new_wav_parts.append(wav[start:end])
            last_end = end

        if last_end < wav.size:
            new_wav_parts.append(wav[last_end:])

        return np.concatenate(new_wav_parts).astype(np.float32), float(pace_multiplier)
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


PROSODY_DESCRIPTIONS: dict[str, str] = {
    "Neutral": "Standard natural pacing and pauses.",
    "Storyteller": "Slower, dramatic pacing with emphasized pauses.",
    "Calm": "Relaxed, steady pace with longer, soothing gaps.",
    "Energetic": "Fast-paced, tight gaps for a high-energy feel.",
    "Broadcast": "Professional, clear pacing typical of news or radio.",
    "Clean": "Tight, efficient pacing with minimal unnecessary gaps.",
}

# Target pause durations (ms) per delivery preset. Ordering within a preset is intentional:
# ellipsis > sentence_end > comma. `natural` is the seed/fallback target for gaps that do NOT
# map to any punctuation (breaths, hesitations); those gaps are pace-scaled to preserve the
# speaker's own delivery rather than snapped to this constant (see get_pause_targets /
# _shape_pauses), so `natural` should stay <= comma and rarely applies verbatim.
PROSODY_MAPS: dict[str, dict[str, float]] = {
    "Neutral": {"comma": 300.0, "ellipsis": 700.0, "sentence_end": 500.0, "natural": 300.0},
    "Storyteller": {"comma": 500.0, "ellipsis": 1500.0, "sentence_end": 1000.0, "natural": 500.0},
    "Calm": {"comma": 400.0, "ellipsis": 900.0, "sentence_end": 700.0, "natural": 400.0},
    "Energetic": {"comma": 200.0, "ellipsis": 400.0, "sentence_end": 300.0, "natural": 200.0},
    "Broadcast": {"comma": 300.0, "ellipsis": 600.0, "sentence_end": 500.0, "natural": 300.0},
    "Clean": {"comma": 150.0, "ellipsis": 400.0, "sentence_end": 300.0, "natural": 150.0},
}


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


def apply_style_preset(wav: np.ndarray, sr: int, preset: str, prompt: str = "", pace_multiplier: float = 1.0, options: Optional[Dict[str, Any]] = None) -> Tuple[np.ndarray, int, Dict[str, Any]]:
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

            # Pass prompt and pace_multiplier to functions that support them
            if name == "shape_pauses":
                res = func(current_wav, sr, prompt=prompt, style_preset=resolved_preset, pace_multiplier=pace_multiplier, **step_kwargs)
            elif "sr" in func.__code__.co_varnames:
                res = func(current_wav, sr, **step_kwargs)
            else:
                res = func(current_wav, **step_kwargs)

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

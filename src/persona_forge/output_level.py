"""Serving-layer loudness normalisation for ``/v1/audio/speech``.

Engines hand back very different levels (Kitten TTS 2 is peak-normalised to RMS 0.16-0.22, Pocket
sits near 0.09), so switching the active engine would otherwise change the volume every client
hears and bias any A/B comparison toward the louder engine. :func:`normalize` applies one RMS
target to the final float audio, for every engine, just before it is encoded.

Design:

* **Level** is the RMS of the *active* part of the clip: 20 ms frames quieter than ``GATE_DBFS``
  are ignored, so leading/trailing silence and long pauses do not make a clip look quiet and get
  boosted. A clip with no active frame (silence, hiss) is returned untouched.
* **Gain** moves that level to ``TARGET_RMS_DBFS`` (-23 dBFS, the EBU R128 reference), boosting by
  at most ``MAX_BOOST_DB`` so a clip that is mostly noise is never inflated to speech level.
* **Peak limiter** is a static soft-knee saturator: samples under the knee are scaled linearly and
  anything above it is rounded off smoothly toward ``PEAK_CEILING_DBFS`` (-1 dBFS), so the output
  never clips and never has a flat-topped run of hard-clipped samples. Speech at the target level
  has a peak well under the ceiling, so the limiter is a safety net, not part of the sound.

Streaming PCM is deliberately **not** normalised: a stream cannot know the whole clip's level, and
a fixed per-engine gain would be a guess because cloned voices vary by several dB. See
``docs/api/HTTP_API_REFERENCE.md`` (``POST /v1/audio/speech``) for the documented behaviour.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

import numpy as np

ENV_VAR = "TTS_NORMALIZE_LOUDNESS"

TARGET_RMS_DBFS = -23.0
PEAK_CEILING_DBFS = -1.0
MAX_BOOST_DB = 12.0
GATE_DBFS = -55.0
FRAME_SECONDS = 0.02
# Fraction of the ceiling below which the limiter leaves samples alone (slope 1 up to the knee).
_KNEE_FRACTION = 0.8

_FALSE_VALUES = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class LevelResult:
    """Outcome of :func:`normalize`. ``audio`` is the input object itself when nothing applied."""

    audio: Any
    applied: bool
    gain_db: float = 0.0


def enabled() -> bool:
    """Normalisation is on unless ``TTS_NORMALIZE_LOUDNESS`` is set to a false value."""
    return os.environ.get(ENV_VAR, "1").strip().lower() not in _FALSE_VALUES


def resolve_enabled(request_value: bool | None) -> bool:
    """A request's ``normalize_loudness`` overrides the server default when it is present."""
    return enabled() if request_value is None else bool(request_value)


def _active_rms(samples: np.ndarray, sample_rate: int) -> float | None:
    """RMS (linear) of frames above the gate, or ``None`` when no frame is active."""
    energy = np.square(samples)
    if energy.ndim > 1:  # (time, channels): mean over channels so frames stay time-aligned
        energy = energy.mean(axis=tuple(range(1, energy.ndim)))
    frame = max(1, int(round(sample_rate * FRAME_SECONDS)))
    count = energy.shape[0] // frame
    if count == 0:  # shorter than one frame: measure the whole clip as a single frame
        frame_energy = np.array([energy.mean()])
    else:
        frame_energy = energy[: count * frame].reshape(count, frame).mean(axis=1)
    active = frame_energy[frame_energy > 10 ** (GATE_DBFS / 10)]
    if active.size == 0:
        return None
    return float(math.sqrt(active.mean()))


def _soft_limit(samples: np.ndarray, ceiling: float) -> np.ndarray:
    knee = ceiling * _KNEE_FRACTION
    magnitude = np.abs(samples)
    over = magnitude > knee
    if not over.any():
        return samples
    headroom = ceiling - knee
    limited = samples.copy()
    limited[over] = np.sign(samples[over]) * (knee + headroom * np.tanh((magnitude[over] - knee) / headroom))
    return limited


def normalize(audio: Any, sample_rate: int, *, enabled: bool = True) -> LevelResult:
    """Bring ``audio`` (float or int16, mono or ``(time, channels)``) to the target level.

    Never raises on odd input: empty, silent, non-finite or unmeasurable audio comes back unchanged
    with ``applied=False``. The input array is never modified in place.
    """
    if not enabled:
        return LevelResult(audio=audio, applied=False)
    samples = np.asarray(audio)
    if samples.size == 0:
        return LevelResult(audio=audio, applied=False)
    if samples.dtype == np.int16:
        samples = samples.astype(np.float32) / 32768.0
    else:
        samples = samples.astype(np.float32, copy=False)
    if not np.isfinite(samples).all():
        samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)

    level = _active_rms(samples, sample_rate)
    if level is None:
        return LevelResult(audio=audio, applied=False)

    gain_db = min(TARGET_RMS_DBFS - 20.0 * math.log10(level), MAX_BOOST_DB)
    boosted = samples * np.float32(10 ** (gain_db / 20.0))
    limited = _soft_limit(boosted, 10 ** (PEAK_CEILING_DBFS / 20.0))
    return LevelResult(audio=limited.astype(np.float32, copy=False), applied=True, gain_db=gain_db)

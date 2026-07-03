"""Audio post-processing for stitched multi-segment OmniVoice reference clips.

See docs/plans/PLAN_persona_forge_studio.md §2. Each segment is an independent model draw
with its own internal dynamics; naively concatenating them leaves the result "all over the
place" (nick, 2026-07-03). Order matters: per-segment compression, then per-segment loudness
normalization, THEN crossfade concatenation, THEN a final limiter/normalization pass on the
whole clip. Normalizing only the final concatenated clip does nothing to fix uneven *internal*
dynamics of individual segments, which is the actual complaint this pipeline addresses.

Hand-rolled numpy, no new audio-DSP dependency (locked decision, PLAN_persona_forge_studio.md
§5) — quality is good enough for short speech clips; revisit only if it isn't.
"""

from __future__ import annotations

import numpy as np

_EPS = 1e-9


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)) + _EPS))


def compress(
    audio: np.ndarray,
    sr: int,
    threshold_db: float = -24.0,
    ratio: float = 2.5,
    attack_ms: float = 5.0,
    release_ms: float = 80.0,
) -> np.ndarray:
    """Soft-knee downward compressor tuned for speech, not music.

    Simple envelope-follower + gain-computer (no lookahead, no knee-width param) — the goal
    is evening out delivery within one short generated segment, not mastering-grade dynamics.
    """
    x = np.asarray(audio, dtype=np.float32).ravel()
    if x.size == 0:
        return x

    attack = float(np.exp(-1.0 / (sr * attack_ms / 1000.0)))
    release = float(np.exp(-1.0 / (sr * release_ms / 1000.0)))

    abs_x = np.abs(x)
    envelope = np.empty_like(x)
    env = 0.0
    for i in range(x.size):
        target = abs_x[i]
        coeff = attack if target > env else release
        env = coeff * env + (1.0 - coeff) * target
        envelope[i] = env

    env_db = 20.0 * np.log10(np.maximum(envelope, _EPS))
    over_db = np.maximum(env_db - threshold_db, 0.0)
    gain_reduction_db = over_db * (1.0 - 1.0 / ratio)
    gain = 10.0 ** (-gain_reduction_db / 20.0)
    return (x * gain).astype(np.float32)


def normalize_rms(audio: np.ndarray, target_dbfs: float = -20.0) -> np.ndarray:
    """Scale audio so its RMS level matches target_dbfs. No-op on silence."""
    x = np.asarray(audio, dtype=np.float32).ravel()
    if x.size == 0:
        return x
    current_rms = _rms(x)
    if current_rms <= _EPS:
        return x
    target_rms = 10.0 ** (target_dbfs / 20.0)
    gain = target_rms / current_rms
    return (x * gain).astype(np.float32)


def limit_peak(audio: np.ndarray, ceiling_db: float = -1.0) -> np.ndarray:
    """Scale down (never up) so the peak sample never exceeds ceiling_db."""
    x = np.asarray(audio, dtype=np.float32).ravel()
    if x.size == 0:
        return x
    peak = float(np.max(np.abs(x)))
    ceiling = 10.0 ** (ceiling_db / 20.0)
    if peak <= ceiling or peak <= _EPS:
        return x
    return (x * (ceiling / peak)).astype(np.float32)


def crossfade_concat(
    segments: list[np.ndarray], sr: int, crossfade_ms: float = 100.0
) -> np.ndarray:
    """Concatenate segments with an equal-power crossfade at each join.

    Replaces the flat-silence-gap approach from the original stitching prototype
    (PLAN_persona_forge_studio.md §2) — a crossfade masks the seam better than a hard cut
    or a silent gap between independently-drawn segments.
    """
    if not segments:
        return np.zeros(0, dtype=np.float32)
    segs = [np.asarray(s, dtype=np.float32).ravel() for s in segments]
    if len(segs) == 1:
        return segs[0]

    fade_len = int(sr * crossfade_ms / 1000.0)
    result = segs[0]
    for seg in segs[1:]:
        fade = min(fade_len, result.size, seg.size)
        if fade <= 0:
            result = np.concatenate([result, seg])
            continue
        t = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        fade_out = np.cos(t * np.pi / 2.0) ** 2
        fade_in = np.sin(t * np.pi / 2.0) ** 2
        head = result[:-fade]
        overlap = result[-fade:] * fade_out + seg[:fade] * fade_in
        tail = seg[fade:]
        result = np.concatenate([head, overlap, tail])
    return result


def stitch_segments(
    segments: list[np.ndarray],
    sr: int,
    *,
    segment_target_dbfs: float = -20.0,
    final_target_dbfs: float = -18.0,
    crossfade_ms: float = 100.0,
    final_ceiling_db: float = -1.0,
) -> np.ndarray:
    """Full pipeline: compress+normalize each segment, crossfade-join, then final limit+normalize."""
    processed = [
        normalize_rms(compress(seg, sr), segment_target_dbfs) for seg in segments
    ]
    combined = crossfade_concat(processed, sr, crossfade_ms)
    combined = limit_peak(combined, final_ceiling_db)
    final = normalize_rms(combined, final_target_dbfs)
    final = limit_peak(final, final_ceiling_db)
    return final

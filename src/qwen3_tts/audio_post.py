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


def trim(audio: np.ndarray, sr: int, start_ms: float = 0.0, end_ms: float = 0.0) -> np.ndarray:
    """Cut start_ms off the head and end_ms off the tail.

    Clamped so it never produces a negative-length result (falls back to a single
    remaining sample) — callers at the API boundary should also clamp against the
    clip's actual duration, this is defense in depth, not the primary validation.
    """
    x = np.asarray(audio, dtype=np.float32).ravel()
    if x.size == 0:
        return x
    start = max(0, int(sr * start_ms / 1000.0))
    end = max(0, int(sr * end_ms / 1000.0))
    start = min(start, x.size - 1)
    end = min(end, x.size - 1 - start)
    return x[start : x.size - end]


def apply_fades(
    audio: np.ndarray, sr: int, fade_in_ms: float = 0.0, fade_out_ms: float = 0.0
) -> np.ndarray:
    """Per-clip user-controlled fade in/out at the clip's own head/tail.

    Distinct from crossfade_concat's join-fades (which blend two adjacent clips into each
    other) — this shapes a single clip's own edges, applied before any joining happens.
    Uses the same equal-power curve as crossfade_concat for consistent character.
    """
    x = np.asarray(audio, dtype=np.float32).ravel()
    if x.size == 0:
        return x
    x = x.copy()
    fade_in_len = min(int(sr * fade_in_ms / 1000.0), x.size)
    if fade_in_len > 0:
        t = np.linspace(0.0, 1.0, fade_in_len, dtype=np.float32)
        x[:fade_in_len] *= np.sin(t * np.pi / 2.0) ** 2
    fade_out_len = min(int(sr * fade_out_ms / 1000.0), x.size)
    if fade_out_len > 0:
        t = np.linspace(0.0, 1.0, fade_out_len, dtype=np.float32)
        x[x.size - fade_out_len :] *= np.cos(t * np.pi / 2.0) ** 2
    return x


def concat_with_padding(
    segments: list[np.ndarray],
    sr: int,
    *,
    padding_ms: list[float] | None = None,
    crossfade_ms: float = 100.0,
) -> np.ndarray:
    """Join segments; for gap i, insert silence if padding_ms[i] > 0, else crossfade.

    padding_ms must have len(segments) - 1 entries (one per gap) when provided; None (or
    all-zero) reproduces crossfade_concat's today's-default all-crossfade behavior exactly.
    A short equal-power fade is applied into and out of each inserted silence gap (distinct
    from any user-set per-clip fade) so a padded gap doesn't introduce a click at its own
    boundaries — this is not a hard butt join.
    """
    if not segments:
        return np.zeros(0, dtype=np.float32)
    segs = [np.asarray(s, dtype=np.float32).ravel() for s in segments]
    if len(segs) == 1:
        return segs[0]

    gaps = list(padding_ms) if padding_ms is not None else [0.0] * (len(segs) - 1)
    if len(gaps) != len(segs) - 1:
        raise ValueError("padding_ms must have len(segments) - 1 entries")

    seam_fade_ms = min(crossfade_ms, 20.0)
    seam_fade_len_default = max(1, int(sr * seam_fade_ms / 1000.0))

    result = segs[0]
    for seg, pad_ms in zip(segs[1:], gaps):
        if pad_ms and pad_ms > 0:
            pad_len = int(sr * pad_ms / 1000.0)
            gap = np.zeros(pad_len, dtype=np.float32)
            fade_len = min(seam_fade_len_default, result.size, pad_len // 2 if pad_len > 1 else 0)
            if fade_len > 0:
                t = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
                fade_out = np.cos(t * np.pi / 2.0) ** 2
                result = result.copy()
                result[-fade_len:] *= fade_out
            fade_len_in = min(seam_fade_len_default, seg.size, pad_len // 2 if pad_len > 1 else 0)
            if fade_len_in > 0:
                t = np.linspace(0.0, 1.0, fade_len_in, dtype=np.float32)
                fade_in = np.sin(t * np.pi / 2.0) ** 2
                seg = seg.copy()
                seg[:fade_len_in] *= fade_in
            result = np.concatenate([result, gap, seg])
        else:
            result = crossfade_concat([result, seg], sr, crossfade_ms)
    return result


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


_SILENT_RMS_DBFS = -45.0
# Frame-level spectral flatness (geometric mean / arithmetic mean of the magnitude
# spectrum) is near 0 for a pure tone/drone and much higher, and highly *variable*, for
# speech (voiced/unvoiced/silence alternate constantly). A "bad take" — drone, SFX, or a
# stuck tone — shows up as almost every frame sitting in the tonal band with very little
# frame-to-frame variance, which normal speech essentially never does even in a 2-3s clip.
_DRONE_FLATNESS_THRESHOLD = 0.15
_DRONE_LOW_FLATNESS_FRACTION = 0.85
_DRONE_FLATNESS_STD_MAX = 0.05
_FRAME_MS = 50.0


def analyze_take(audio: np.ndarray, sr: int) -> tuple[bool, str]:
    """Best-effort heuristic flag for a broken OmniVoice take (dead air / drone / SFX).

    Not a real speech-quality classifier — just two cheap numpy-only checks (locked
    decision: no new DSP dependency, see module docstring) good enough to catch the
    failure modes observed in practice (nick, 2026-07-03: candidates that are "just dead
    air/drones/sfx"). False negatives are expected; genuine speech should essentially
    never trip the drone check because it flattens/varies too much frame to frame.
    Returns (flagged, reason) — reason is "ok" when not flagged.
    """
    x = np.asarray(audio, dtype=np.float32).ravel()
    if x.size == 0:
        return True, "empty"
    if _rms(x) <= 10.0 ** (_SILENT_RMS_DBFS / 20.0):
        return True, "near-silent"

    win = max(1, int(sr * _FRAME_MS / 1000.0))
    hop = max(1, win // 2)
    window = np.hanning(win) if win > 1 else np.ones(1, dtype=np.float32)
    flatness_vals: list[float] = []
    for start in range(0, x.size - win + 1, hop):
        frame = x[start : start + win] * window
        spec = np.abs(np.fft.rfft(frame)) + _EPS
        gmean = np.exp(np.mean(np.log(spec)))
        amean = np.mean(spec)
        flatness_vals.append(float(gmean / amean))

    if not flatness_vals:
        return False, "ok"
    flatness = np.array(flatness_vals)
    low_flat_frac = float(np.mean(flatness < _DRONE_FLATNESS_THRESHOLD))
    flat_std = float(np.std(flatness))
    if low_flat_frac > _DRONE_LOW_FLATNESS_FRACTION and flat_std < _DRONE_FLATNESS_STD_MAX:
        return True, "tonal/drone-like"
    return False, "ok"


def stitch_segments(
    segments: list[np.ndarray],
    sr: int,
    *,
    segment_target_dbfs: float = -20.0,
    final_target_dbfs: float = -18.0,
    crossfade_ms: float = 100.0,
    final_ceiling_db: float = -1.0,
    padding_ms: list[float] | None = None,
    trims: list[tuple[float, float]] | None = None,
    fades: list[tuple[float, float]] | None = None,
    compress_params: dict | None = None,
) -> np.ndarray:
    """Full pipeline: trim, compress+normalize, fade each segment, then join and final limit+normalize.

    New optional kwargs (stitch-editor support, PLAN_stitch_editor.md §3) all default to
    None, which reproduces the original behavior exactly:
      - trims: per-segment (start_ms, end_ms) applied before compress/normalize.
      - compress_params: kwargs forwarded to compress(); None uses its own defaults, same
        as calling compress(seg, sr) did before this parameter existed.
      - fades: per-segment (fade_in_ms, fade_out_ms) applied after normalize, before joining.
      - padding_ms: per-gap silence override; None reproduces crossfade_concat's all-crossfade
        default via concat_with_padding (which falls back to crossfade_concat per-gap).
    """
    n = len(segments)
    trims = trims or [(0.0, 0.0)] * n
    fades = fades or [(0.0, 0.0)] * n
    compress_kwargs = compress_params or {}

    processed = []
    for seg, (start_ms, end_ms), (fade_in_ms, fade_out_ms) in zip(segments, trims, fades):
        clip = trim(seg, sr, start_ms, end_ms) if (start_ms or end_ms) else seg
        clip = normalize_rms(compress(clip, sr, **compress_kwargs), segment_target_dbfs)
        if fade_in_ms or fade_out_ms:
            clip = apply_fades(clip, sr, fade_in_ms, fade_out_ms)
        processed.append(clip)

    combined = concat_with_padding(processed, sr, padding_ms=padding_ms, crossfade_ms=crossfade_ms)
    combined = limit_peak(combined, final_ceiling_db)
    final = normalize_rms(combined, final_target_dbfs)
    final = limit_peak(final, final_ceiling_db)
    return final

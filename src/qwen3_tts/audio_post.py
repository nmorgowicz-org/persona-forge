"""Audio post-processing for stitched multi-segment OmniVoice reference clips.

See docs/dev/features/persona_forge_studio.md §2. Each segment is an independent model draw
with its own internal dynamics; naively concatenating them leaves the result "all over the
place" (nick, 2026-07-03). Order matters: per-segment compression, then per-segment loudness
normalization, THEN crossfade concatenation, THEN a final limiter/normalization pass on the
whole clip. Normalizing only the final concatenated clip does nothing to fix uneven *internal*
dynamics of individual segments, which is the actual complaint this pipeline addresses.

Hand-rolled numpy, no new audio-DSP dependency (locked decision, docs/dev/features/persona_forge_studio.md
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


def _region_bounds(sr: int, size: int, start_ms: float, end_ms: float) -> tuple[int, int]:
    start = max(0, min(int(round(sr * start_ms / 1000.0)), size))
    end = max(start, min(int(round(sr * end_ms / 1000.0)), size))
    return start, end


def apply_region_envelope(
    audio: np.ndarray,
    sr: int,
    start_ms: float,
    end_ms: float,
    target_gain: float,
    fade_in_ms: float = 0.0,
    fade_out_ms: float = 0.0,
) -> np.ndarray:
    """Blend an interior region toward target_gain (0.0 for mute), ramping in/out at its edges.

    Mirrors the frontend's `applyEnvelope` for the 'gain'/'mute' RegionEdit types
    (StitchTimeline.tsx) exactly: outside any fade window the region sits flat at
    target_gain; within a fade window it blends linearly from the original level (1.0)
    toward target_gain. If a region edit's node applies during both a matching operation, the
    fade-out computation applies last, matching the frontend's sequential (not exclusive) ifs.
    """
    x = np.asarray(audio, dtype=np.float32).ravel().copy()
    start, end = _region_bounds(sr, x.size, start_ms, end_ms)
    if end <= start:
        return x
    region_len = end - start
    fade_in_len = int(round(sr * fade_in_ms / 1000.0))
    fade_out_len = int(round(sr * fade_out_ms / 1000.0))
    factor = np.full(region_len, target_gain, dtype=np.float32)
    pos = np.arange(region_len)
    if fade_in_len > 0:
        mask = pos < fade_in_len
        factor[mask] = 1.0 + (target_gain - 1.0) * (pos[mask] / fade_in_len)
    if fade_out_len > 0:
        mask = (region_len - pos) < fade_out_len
        factor[mask] = 1.0 + (target_gain - 1.0) * ((region_len - pos[mask]) / fade_out_len)
    x[start:end] *= factor
    return x


def apply_region_fade(
    audio: np.ndarray,
    sr: int,
    start_ms: float,
    end_ms: float,
    fade_in_ms: float = 0.0,
    fade_out_ms: float = 0.0,
) -> np.ndarray:
    """Ramp an interior region up from / down to silence at its own edges (the 'fade' RegionEdit type).

    Unlike apply_region_envelope, this never targets a gain level — it is a pure fade-in/
    fade-out shape confined to the region, matching the frontend's linear ramp exactly.
    """
    x = np.asarray(audio, dtype=np.float32).ravel().copy()
    start, end = _region_bounds(sr, x.size, start_ms, end_ms)
    if end <= start:
        return x
    region_len = end - start
    fade_in_len = int(round(sr * fade_in_ms / 1000.0))
    fade_out_len = int(round(sr * fade_out_ms / 1000.0))
    factor = np.ones(region_len, dtype=np.float32)
    pos = np.arange(region_len)
    if fade_in_len > 0:
        mask = pos < fade_in_len
        factor[mask] = np.minimum(factor[mask], pos[mask] / fade_in_len)
    if fade_out_len > 0:
        mask = (region_len - pos) < fade_out_len
        factor[mask] = np.minimum(factor[mask], (region_len - pos[mask]) / fade_out_len)
    x[start:end] *= factor
    return x


def _remove_range_samples(x: np.ndarray, start: int, end: int) -> np.ndarray:
    start = max(0, min(int(start), x.size))
    end = max(start, min(int(end), x.size))
    if end <= start:
        return x
    return np.concatenate([x[:start], x[end:]])


def remove_range(audio: np.ndarray, sr: int, start_ms: float, end_ms: float) -> np.ndarray:
    """Delete an interior region, matching the frontend's 'delete' RegionEdit type."""
    x = np.asarray(audio, dtype=np.float32).ravel()
    start = int(round(sr * start_ms / 1000.0))
    end = int(round(sr * end_ms / 1000.0))
    return _remove_range_samples(x, start, end)


def _insert_silence_samples(x: np.ndarray, at: int, duration_samples: int) -> np.ndarray:
    if duration_samples <= 0:
        return x
    at = max(0, min(int(at), x.size))
    silence = np.zeros(duration_samples, dtype=np.float32)
    return np.concatenate([x[:at], silence, x[at:]])


def insert_silence(audio: np.ndarray, sr: int, at_ms: float, duration_ms: float) -> np.ndarray:
    """Insert a block of silence at at_ms, matching the frontend's 'insert_silence' RegionEdit type."""
    x = np.asarray(audio, dtype=np.float32).ravel()
    at = int(round(sr * at_ms / 1000.0))
    duration_samples = int(round(sr * duration_ms / 1000.0))
    return _insert_silence_samples(x, at, duration_samples)


def apply_region_edits(audio: np.ndarray, sr: int, edits: list[dict] | None) -> np.ndarray:
    """Apply one clip's ordered RegionEdit list (docs/plans/20260709-voice_style_foundation.md).

    Order mirrors the frontend's `processClipAudio` exactly so preview and final render
    stay in sync: gain/mute/fade envelopes apply first, in their original list order
    (they may overlap and compose); deletes apply next, longest-offset-first so earlier
    indices stay valid; insert_silence applies last, in ascending position order, tracking
    a running sample offset so multiple inserts land at their intended positions.
    """
    x = np.asarray(audio, dtype=np.float32).ravel()
    if not edits:
        return x
    for edit in edits:
        edit_type = edit.get("type")
        if edit_type == "insert_silence" or edit_type == "delete":
            continue
        start_ms = float(edit.get("start_ms", 0.0))
        end_ms = float(edit.get("end_ms", 0.0))
        if end_ms <= start_ms:
            continue
        fade_in_ms = float(edit.get("fade_in_ms", 0.0))
        fade_out_ms = float(edit.get("fade_out_ms", 0.0))
        if edit_type == "gain":
            gain = 10.0 ** (float(edit.get("gain_db", 0.0)) / 20.0)
            x = apply_region_envelope(x, sr, start_ms, end_ms, gain, fade_in_ms, fade_out_ms)
        elif edit_type == "mute":
            x = apply_region_envelope(x, sr, start_ms, end_ms, 0.0, fade_in_ms, fade_out_ms)
        elif edit_type == "fade":
            x = apply_region_fade(x, sr, start_ms, end_ms, fade_in_ms, fade_out_ms)

    deletes = sorted(
        (e for e in edits if e.get("type") == "delete"),
        key=lambda e: float(e.get("start_ms", 0.0)),
        reverse=True,
    )
    for edit in deletes:
        start_ms = float(edit.get("start_ms", 0.0))
        end_ms = float(edit.get("end_ms", 0.0))
        if end_ms > start_ms:
            x = remove_range(x, sr, start_ms, end_ms)

    inserts = sorted(
        (e for e in edits if e.get("type") == "insert_silence"),
        key=lambda e: float(e.get("at_ms", 0.0)),
    )
    inserted_samples = 0
    for edit in inserts:
        at_ms = float(edit.get("at_ms", 0.0))
        duration_ms = float(edit.get("duration_ms", 0.0))
        duration_samples = int(round(sr * duration_ms / 1000.0))
        at = min(x.size, int(round(sr * at_ms / 1000.0)) + inserted_samples)
        x = _insert_silence_samples(x, at, duration_samples)
        inserted_samples += duration_samples
    return x


def resolve_safe_cut(
    audio: np.ndarray, sr: int, center_sample: int, *, search_ms: float = 50.0
) -> tuple[int, str]:
    """Snap an aligned word boundary to the safest nearby splice point.

    Cutting into voiced audio to insert a pause clicks — and, worse, splits a word —
    unless the cut lands in the genuine inter-word gap, which the INT8 aligner routinely
    misses by tens of milliseconds. We therefore search a *wide* window around the
    aligned boundary (plan §5.3 step 1) and lock onto the deepest short-time energy
    trough in it rather than the nearest incidental low sample: the trough is the real
    pause. Zero-cross proximity is a secondary tie-break. Returns (cut_sample,
    provenance) where provenance is one of ``"zero_cross"``, ``"energy_min"``, or
    ``"boundary"`` (no room to search).
    """
    x = np.asarray(audio, dtype=np.float32).ravel()
    n = x.size
    center = max(0, min(int(round(center_sample)), n))
    search = int(round(sr * search_ms / 1000.0))
    if search <= 0 or n == 0:
        return center, "boundary"
    lo = max(0, center - search)
    hi = min(n, center + search + 1)
    if hi - lo <= 1:
        return center, "boundary"

    window = x[lo:hi]
    amp = np.abs(window)
    # Smooth |amp| into a short-time energy envelope (~1 ms box) so we lock onto the
    # sustained inter-word trough, not a single incidental zero inside voiced audio.
    kernel = max(1, int(round(sr * 0.001)))
    env = (
        np.convolve(amp, np.ones(kernel, dtype=np.float32) / kernel, mode="same")
        if kernel > 1
        else amp
    )
    trough = int(np.argmin(env))
    # Among samples at (or a hair above) the trough floor, prefer a genuine
    # zero-crossing near the trough (sign flip vs the previous sample).
    floor = float(env[trough]) + 1e-4
    near = np.flatnonzero(env <= floor)
    sign = np.signbit(window)
    zero_cross = [int(i) for i in near if i > 0 and sign[i] != sign[i - 1]]
    if zero_cross:
        best = min(zero_cross, key=lambda i: abs(i - trough))
        return lo + best, "zero_cross"
    return lo + trough, "energy_min"


def _splice_padded_gap(
    x: np.ndarray, at: int, gap_samples: int, fade_len: int
) -> np.ndarray:
    """Insert `gap_samples` of silence at `at`, micro-fading the voiced audio into and
    out of the gap so the cut is inaudible. Reuses the equal-power curve of `apply_fades`
    (cos^2 ramp-down before the gap, sin^2 ramp-up after it)."""
    at = max(0, min(int(at), x.size))
    left = x[:at].copy()
    right = x[at:].copy()
    fade_out = min(max(0, fade_len), left.size)
    if fade_out > 0:
        t = np.linspace(0.0, 1.0, fade_out, dtype=np.float32)
        left[left.size - fade_out:] *= np.cos(t * np.pi / 2.0) ** 2
    fade_in = min(max(0, fade_len), right.size)
    if fade_in > 0:
        t = np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
        right[:fade_in] *= np.sin(t * np.pi / 2.0) ** 2
    gap = np.zeros(max(0, int(gap_samples)), dtype=np.float32)
    return np.concatenate([left, gap, right])


def plan_boundary_pauses(
    audio: np.ndarray, sr: int, pause_edits: list[dict], *, search_ms: float = 50.0
) -> list[dict]:
    """Resolve each alignment-owned pause edit to a concrete, sample-exact splice.

    Separated from `apply_boundary_pause_plan` so the resolved plan (cut position, snap
    provenance, inserted duration, fade semantics) is a serializable contract the frontend
    waveform preview can render identically to the backend render (plan §5.3 step 4). Each
    input edit is ``{"at_ms": <aligned boundary>, "target_ms": <final pause>,
    "existing_ms": <natural gap already present, default 0>}``; net inserted silence is
    ``max(0, target_ms - existing_ms)``. Output is sorted by cut position.
    """
    x = np.asarray(audio, dtype=np.float32).ravel()
    edits = list(pause_edits or [])
    # Resolve in temporal order so each cut's (now wide) search window can be clamped to
    # half the distance to its nearer neighbour — two close boundaries must never snap to
    # the same trough or reorder past each other.
    order = sorted(range(len(edits)), key=lambda i: float(edits[i].get("at_ms", 0.0)))
    at_ms_sorted = [float(edits[i].get("at_ms", 0.0)) for i in order]
    source_resolved: list[dict] = []
    for pos, idx in enumerate(order):
        edit = edits[idx]
        at_ms = at_ms_sorted[pos]
        target_ms = float(edit.get("target_ms", 0.0))
        existing_ms = float(edit.get("existing_ms", 0.0))
        insert_ms = max(0.0, target_ms - existing_ms)
        half_ms = search_ms
        if pos > 0:
            half_ms = min(half_ms, (at_ms - at_ms_sorted[pos - 1]) / 2.0)
        if pos < len(order) - 1:
            half_ms = min(half_ms, (at_ms_sorted[pos + 1] - at_ms) / 2.0)
        cut, provenance = resolve_safe_cut(
            x, sr, int(round(sr * at_ms / 1000.0)), search_ms=max(0.0, half_ms)
        )
        source_resolved.append({
            "at_ms": at_ms,
            "cut_sample": cut,
            "insert_ms": round(insert_ms, 3),
            "target_ms": target_ms,
            "existing_ms": existing_ms,
            "provenance": provenance,
            "origin": edit.get("origin", "alignment"),
        })
    source_resolved.sort(key=lambda r: r["cut_sample"])

    # The public cut coordinate is in the rendered preview's sample space. This folds in
    # earlier insertions on the server so waveform consumers never need to reproduce gap
    # offset math (and later markers cannot drift after an earlier manufactured pause).
    resolved: list[dict] = []
    inserted_samples = 0
    for item in source_resolved:
        rendered_cut = int(item["cut_sample"]) + inserted_samples
        item["cut_sample"] = rendered_cut
        item["cut_ms"] = round(rendered_cut * 1000.0 / sr, 3) if sr else 0.0
        resolved.append(item)
        inserted_samples += int(round(sr * float(item["insert_ms"]) / 1000.0))
    return resolved


def apply_resolved_boundary_pause_plan(
    audio: np.ndarray, sr: int, resolved_plan: list[dict], *, fade_ms: float = 8.0
) -> np.ndarray:
    """Apply a sample-exact plan returned by :func:`plan_boundary_pauses`."""
    out = np.asarray(audio, dtype=np.float32).ravel()
    if out.size == 0 or not resolved_plan:
        return out
    fade_len = max(0, int(round(sr * fade_ms / 1000.0)))
    for edit in resolved_plan:
        insert_samples = int(round(sr * float(edit["insert_ms"]) / 1000.0))
        if insert_samples <= 0:
            continue
        out = _splice_padded_gap(out, int(edit["cut_sample"]), insert_samples, fade_len)
    return out


def apply_boundary_pause_plan(
    audio: np.ndarray,
    sr: int,
    pause_edits: list[dict],
    *,
    search_ms: float = 50.0,
    fade_ms: float = 8.0,
) -> np.ndarray:
    """Insert alignment-owned pauses at aligned word boundaries without an audible click.

    For each punctuation-owned boundary (plan §5.3): snap to a safe low-energy/zero-cross
    cut near the aligned position, micro-fade the voiced audio into and out of the cut, and
    splice in the final target-duration silence directly — no second pass through
    `get_pause_targets`, the preset's target is already resolved. This is the *cut-into-
    voiced-audio* path; the raw-`np.zeros` gap *replacement* path in audio_style stays
    distinct (it edits already-silent regions and needs no anti-click).
    """
    x = np.asarray(audio, dtype=np.float32).ravel()
    if x.size == 0 or not pause_edits:
        return x
    resolved = plan_boundary_pauses(x, sr, pause_edits, search_ms=search_ms)
    return apply_resolved_boundary_pause_plan(x, sr, resolved, fade_ms=fade_ms)


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
    (docs/dev/features/persona_forge_studio.md §2) — a crossfade masks the seam better than a hard cut
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
    edits: list[list[dict]] | None = None,
) -> np.ndarray:
    """Full pipeline: trim, compress+normalize, fade each segment, then join and final limit+normalize.

    New optional kwargs (stitch-editor support, docs/dev/features/stitch_editor.md §3) all default to
    None, which reproduces the original behavior exactly:
      - trims: per-segment (start_ms, end_ms) applied before compress/normalize.
      - compress_params: kwargs forwarded to compress(); None uses its own defaults, same
        as calling compress(seg, sr) did before this parameter existed.
      - fades: per-segment (fade_in_ms, fade_out_ms) applied after normalize, before joining.
      - padding_ms: per-gap silence override; None reproduces crossfade_concat's all-crossfade
        default via concat_with_padding (which falls back to crossfade_concat per-gap).
      - edits: per-segment RegionEdit lists (gain/mute/fade/delete/insert_silence), applied
        right after trim and before compress/normalize — see apply_region_edits(). This is the
        durable counterpart to StitchTimeline.tsx's client-side preview-only region edits.
    """
    n = len(segments)
    trims = trims or [(0.0, 0.0)] * n
    fades = fades or [(0.0, 0.0)] * n
    edits = edits or [[] for _ in range(n)]
    compress_kwargs = compress_params or {}

    processed = []
    for seg, (start_ms, end_ms), (fade_in_ms, fade_out_ms), seg_edits in zip(segments, trims, fades, edits):
        clip = trim(seg, sr, start_ms, end_ms) if (start_ms or end_ms) else seg
        if seg_edits:
            clip = apply_region_edits(clip, sr, seg_edits)
        clip = normalize_rms(compress(clip, sr, **compress_kwargs), segment_target_dbfs)
        if fade_in_ms or fade_out_ms:
            clip = apply_fades(clip, sr, fade_in_ms, fade_out_ms)
        processed.append(clip)

    combined = concat_with_padding(processed, sr, padding_ms=padding_ms, crossfade_ms=crossfade_ms)
    combined = limit_peak(combined, final_ceiling_db)
    final = normalize_rms(combined, final_target_dbfs)
    final = limit_peak(final, final_ceiling_db)
    return final

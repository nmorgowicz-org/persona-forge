"""Shared per-segment prosody repair for Stitch Studio and OmniVoice.

Unlike the Voice Library wrappers, this module operates on an in-memory clip plus its
transcript.  That makes the Phase 3 alignment/VAD/safe-cut engine reusable before segments
are stitched or persisted, without manufacturing temporary voice-library entries.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from collections import OrderedDict
from typing import Any

import numpy as np

from qwen3_tts import forced_alignment
from qwen3_tts.audio_post import (
    apply_resolved_boundary_pause_plan,
    plan_boundary_pauses,
)
from qwen3_tts.audio_style import PROSODY_MAPS, detect_pause_intervals
from qwen3_tts.prosody_triage import MODE_PRECISE, triage

logger = logging.getLogger(__name__)

VALID_REPAIR_MODES = frozenset({"off", "auto", "precise"})
_PUNCT_TRIGGER = re.compile(r"(\.{3,}|…)|([.!?])|([,;:]|—|–)")
_CACHE_MAX = 128
_CACHE_LOCK = threading.Lock()
_REPAIR_WORKER_LOCK = threading.Lock()
_REPAIR_CACHE: OrderedDict[
    tuple[str, int, str, str, str, float, float],
    tuple[np.ndarray, list[dict[str, Any]], dict[str, Any]],
] = OrderedDict()


def _target_ms(
    style_preset: str, key: str, pace_multiplier: float, pause_offset_ms: float
) -> float:
    prosody = PROSODY_MAPS.get(style_preset, PROSODY_MAPS["Neutral"])
    return max(
        0.0,
        float(prosody.get(key, prosody["natural"])) * pace_multiplier + pause_offset_ms,
    )


def suggest_stitch_gap_targets(
    transcripts: list[str],
    style_preset: str = "Neutral",
    pace_multiplier: float = 1.0,
    pause_offset_ms: float = 0.0,
) -> list[float]:
    """Return the controlled seam pause after every clip except the last.

    Stitch seams are known exactly, so no alignment is necessary: the terminal punctuation
    of the preceding clip selects the same target table used by reference prosody repair.
    """
    targets: list[float] = []
    for text in transcripts[:-1]:
        trimmed = (text or "").rstrip()
        key = "natural"
        if re.search(r"(?:\.{3,}|…|…)\s*$", trimmed):
            key = "ellipsis"
        elif re.search(r"[.!?]\s*$", trimmed):
            key = "sentence_end"
        elif re.search(r"[,;:—–]\s*$", trimmed):
            key = "comma"
        targets.append(round(_target_ms(style_preset, key, pace_multiplier, pause_offset_ms), 3))
    return targets


def build_alignment_pause_edits(
    boundaries: list[dict[str, Any]],
    style_preset: str,
    pace_multiplier: float,
    pause_offset_ms: float,
) -> list[dict[str, Any]]:
    edits: list[dict[str, Any]] = []
    for index, boundary in enumerate(boundaries):
        kind = boundary.get("kind")
        if kind == "uncertain":
            continue
        if kind == "sentence_split":
            key = "sentence_end"
        elif boundary.get("owns_clause"):
            key = "comma"
        else:
            continue
        end = float(boundary.get("end", 0.0))
        existing_ms = 0.0
        if index + 1 < len(boundaries):
            existing_ms = max(
                0.0,
                (float(boundaries[index + 1].get("start", end)) - end) * 1000.0,
            )
        edits.append(
            {
                "at_ms": end * 1000.0,
                "target_ms": _target_ms(
                    style_preset, key, pace_multiplier, pause_offset_ms
                ),
                "existing_ms": existing_ms,
                "origin": "alignment",
            }
        )
    return edits


def build_vad_pause_edits(
    wav: np.ndarray,
    sr: int,
    transcript: str,
    style_preset: str,
    pace_multiplier: float,
    pause_offset_ms: float,
) -> list[dict[str, Any]]:
    text = transcript or ""
    trimmed_len = len(text.rstrip())
    if not trimmed_len or not sr:
        return []
    duration = wav.size / float(sr)
    gaps = detect_pause_intervals(wav, sr)
    edits: list[dict[str, Any]] = []
    for match in _PUNCT_TRIGGER.finditer(text):
        if match.end() >= trimmed_len:
            continue
        key = "ellipsis" if match.group(1) else "sentence_end" if match.group(2) else "comma"
        at_sec = (match.start() / len(text)) * duration
        existing_ms = 0.0
        for gap_start, gap_end in gaps:
            if gap_start <= at_sec <= gap_end:
                existing_ms = (gap_end - gap_start) * 1000.0
                break
        edits.append(
            {
                "at_ms": at_sec * 1000.0,
                "target_ms": _target_ms(
                    style_preset, key, pace_multiplier, pause_offset_ms
                ),
                "existing_ms": existing_ms,
                "origin": "vad",
            }
        )
    return edits


def repair_segment_audio(
    wav: np.ndarray,
    sr: int,
    transcript: str,
    *,
    mode: str = "auto",
    style_preset: str = "Neutral",
    pace_multiplier: float = 1.0,
    pause_offset_ms: float = 0.0,
    emit: Any = None,
    cancel_event: threading.Event | None = None,
) -> tuple[np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    """Triage and repair one segment's internal blended boundaries.

    Returns ``(audio, resolved_plan, metadata)``. Alignment is attempted first, then the
    alignment-free VAD safe-cut path. A clean Auto segment or a clip without usable text is
    returned byte-for-byte unchanged.
    """
    if mode not in VALID_REPAIR_MODES:
        raise ValueError(f"invalid prosody repair mode: {mode}")
    audio = np.asarray(wav, dtype=np.float32).ravel()
    cache_key = (
        hashlib.sha256(audio.tobytes()).hexdigest(),
        int(sr),
        transcript,
        mode,
        style_preset,
        float(pace_multiplier),
        float(pause_offset_ms),
    )
    use_cache = emit is None and cancel_event is None
    if use_cache:
        with _CACHE_LOCK:
            if cache_key in _REPAIR_CACHE:
                cached_audio, cached_plan, cached_metadata = _REPAIR_CACHE.pop(cache_key)
                _REPAIR_CACHE[cache_key] = (cached_audio, cached_plan, cached_metadata)
                return cached_audio.copy(), [dict(item) for item in cached_plan], dict(cached_metadata)

    verdict = triage(audio, sr, transcript)
    metadata: dict[str, Any] = {
        "requested_mode": mode,
        "triage": verdict.to_dict(),
        "resolved_mode": "off" if mode == "off" else verdict.mode,
        "fallback": None,
    }
    if mode == "off" or not (transcript or "").strip():
        result = (audio, [], metadata)
        if use_cache:
            _cache_result(cache_key, result)
        return result
    if mode == "auto" and verdict.mode != MODE_PRECISE:
        result = (audio, [], metadata)
        if use_cache:
            _cache_result(cache_key, result)
        return result

    # ONNX Runtime cannot interrupt an in-flight session.run call. Serialize the heavy
    # section and honor cancellation immediately before and after it, so a generation
    # request that exhausts its latency budget never renders or caches the late result.
    with _REPAIR_WORKER_LOCK:
        if cancel_event is not None and cancel_event.is_set():
            metadata["fallback"] = "cancelled"
            return audio, [], metadata
        try:
            boundaries = [
                boundary.to_dict()
                for boundary in forced_alignment.align(audio, int(sr), transcript, emit=emit)
            ]
            if cancel_event is not None and cancel_event.is_set():
                metadata["fallback"] = "cancelled"
                return audio, [], metadata
            edits = build_alignment_pause_edits(
                boundaries, style_preset, pace_multiplier, pause_offset_ms
            )
            if edits:
                plan = plan_boundary_pauses(audio, int(sr), edits)
                metadata["resolved_mode"] = "precise"
                result = (
                    apply_resolved_boundary_pause_plan(audio, int(sr), plan),
                    plan,
                    metadata,
                )
                if use_cache:
                    _cache_result(cache_key, result)
                return result
        except Exception:
            logger.exception("Per-segment forced alignment failed; using VAD safe-cut fallback")

        if cancel_event is not None and cancel_event.is_set():
            metadata["fallback"] = "cancelled"
            return audio, [], metadata
        edits = build_vad_pause_edits(
            audio, int(sr), transcript, style_preset, pace_multiplier, pause_offset_ms
        )
        if edits:
            plan = plan_boundary_pauses(audio, int(sr), edits)
            metadata["resolved_mode"] = "precise"
            metadata["fallback"] = "vad"
            result = (apply_resolved_boundary_pause_plan(audio, int(sr), plan), plan, metadata)
            if use_cache:
                _cache_result(cache_key, result)
            return result

    metadata["fallback"] = "unchanged"
    result = (audio, [], metadata)
    if use_cache:
        _cache_result(cache_key, result)
    return result


def _cache_result(
    key: tuple[str, int, str, str, str, float, float],
    result: tuple[np.ndarray, list[dict[str, Any]], dict[str, Any]],
) -> None:
    audio, plan, metadata = result
    with _CACHE_LOCK:
        _REPAIR_CACHE[key] = (audio.copy(), [dict(item) for item in plan], dict(metadata))
        _REPAIR_CACHE.move_to_end(key)
        while len(_REPAIR_CACHE) > _CACHE_MAX:
            _REPAIR_CACHE.popitem(last=False)

"""Filesystem-backed voice library (docs/architecture/VOICE_DESIGN.md §7).

Maps voice_id -> {wav_path, description, sample_text, language, created_at}. No database —
consistent with the project's existing "no database, bind-mounted host directories" pattern
(MODEL_CACHE_PATH, OV_DATA_PATH). No auth on top of this: the whole service is meant to sit
behind a trusted network / authenticated reverse proxy (see SECURITY.md).

Layout: <VOICE_LIBRARY_DIR>/<voice_id>/reference.wav + <VOICE_LIBRARY_DIR>/<voice_id>/meta.json
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import secrets
import tempfile
import time
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from persona_forge.audio_post import (
    apply_region_edits,
    apply_resolved_boundary_pause_plan,
    plan_boundary_pauses,
)
from persona_forge.audio_style import (
    analyze_reference,
    apply_style_preset,
    detect_pause_intervals,
    get_pause_targets,
    PROSODY_MAPS,
)
from persona_forge.reference_analysis import calculate_quality_score


# Fixed container-side mount point, same pattern as persona_forge.config.REF_AUDIO_PATH.
# compose.yml binds ${VOICE_LIBRARY_PATH:-./data/voices} (host) -> this path (container).
VOICE_LIBRARY_DIR = Path(os.getenv("VOICE_LIBRARY_DIR", "/voices"))
ACTIVE_DEFAULT_FILE = VOICE_LIBRARY_DIR / ".active_default"
# The mounted REF_AUDIO is materialized under this stable ID so diagnostics and UI
# actions can refer to the same library record across restarts.
MOUNTED_REF_VOICE_ID = "vd_000000000001"

logger = logging.getLogger(__name__)

_VOICE_ID_RE = re.compile(r"^vd_[0-9a-f]{12}$")
# Lineage-preserving variant sub-ID: vd_<parent_hex>.<slug>. Slug is a strict allowlist
# (no '.', '/', or leading dash/dot) so it can never contain a path separator or traversal
# sequence, and cannot itself contain another '.' (no nested sub-IDs).
_VARIANT_ID_RE = re.compile(r"^vd_([0-9a-f]{12})\.([a-z0-9][a-z0-9_-]{0,63})$")


def get_active_default_voice_id() -> str | None:
    """Return the persisted voice used by no-voice API requests, if any."""
    try:
        voice_id = ACTIVE_DEFAULT_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return voice_id or None


def set_active_default_voice_id(voice_id: str) -> None:
    """Persist the voice used by no-voice API requests."""
    if not _is_valid_voice_id(voice_id):
        raise ValueError(f"invalid voice_id: {voice_id!r}")
    ACTIVE_DEFAULT_FILE.write_text(voice_id, encoding="utf-8")


def clear_active_default_voice_id() -> None:
    """Clear the persisted no-voice API default, if present."""
    try:
        ACTIVE_DEFAULT_FILE.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not clear active API default %s", ACTIVE_DEFAULT_FILE)


def new_voice_id() -> str:
    return f"vd_{secrets.token_hex(6)}"


def parse_voice_id(voice_id: str) -> tuple[str, str | None]:
    """Split a voice_id into (parent_voice_id, slug). slug is None for a plain vd_<hex> id."""
    match = _VARIANT_ID_RE.match(voice_id or "")
    if match:
        return f"vd_{match.group(1)}", match.group(2)
    return voice_id, None


def _is_valid_voice_id(voice_id: str) -> bool:
    # Endpoint input travels straight into a filesystem path (get_voice/_voice_dir), so this
    # doubles as path-traversal defense, not just a format check.
    if not voice_id:
        return False
    return bool(_VOICE_ID_RE.match(voice_id)) or bool(_VARIANT_ID_RE.match(voice_id))


def set_active_variant(voice_id: str, variant_filename: str | None = None) -> bool:
    """Set the active reference audio for a voice — this is what the API (and every
    other reader of this voice_id) will serve going forward, so it's a "promote to
    primary" operation, not just a UI preview toggle.
    If variant_filename is None, reset to original.wav.
    """
    if not _is_valid_voice_id(voice_id):
        return False
    voice_dir = _voice_dir(voice_id)
    current_wav = voice_dir / "current.wav"
    original_wav = voice_dir / "original.wav"

    try:
        if current_wav.exists() or current_wav.is_symlink():
            current_wav.unlink()

        if variant_filename:
            target = voice_dir / variant_filename
            if not target.is_file():
                return False
            current_wav.symlink_to(target)
        else:
            current_wav.symlink_to(original_wav)
    except OSError:
        return False

    try:
        # Refresh persisted metrics/quality fields to describe whichever audio is now
        # active, so the fingerprint/waveform UI reflects the promoted variant instead
        # of stale numbers from the master reference.
        analyze_reference(voice_id)
    except Exception:
        logger.exception("Failed to refresh metrics after activating variant for %s", voice_id)
    return True


def _load_master_wav(voice_id: str) -> tuple[np.ndarray, int, bytes] | None:
    """Resolve and read a voice's master reference (original.wav, legacy reference.wav).

    Returns ``(wav, sr, wav_bytes)`` or ``None`` if the voice or its master is missing.
    Centralizes the master-resolution the prosody engines share.
    """
    voice_dir = _voice_dir(voice_id)
    master_path = voice_dir / "original.wav"
    if not master_path.is_file():
        master_path = voice_dir / "reference.wav"
    if not master_path.is_file():
        return None
    wav_bytes = master_path.read_bytes()
    wav, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
    return np.asarray(wav, dtype=np.float32).ravel(), int(sr), wav_bytes


def build_vad_pause_edits(
    wav: np.ndarray,
    sr: int,
    transcript: str,
    style_preset: str,
    pace_multiplier: float,
    pause_offset_ms: float = 0.0,
    target_overrides: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Alignment-free surgical pause edits (plan §5.5 step 3).

    Used when forced alignment is unavailable or low-confidence but the clip is blended.
    Each interior punctuation mark is placed at its *proportional* time position in the
    audio (character offset / length), given the preset target, and the residual silence
    already present at that spot is measured from detected gaps so we resize rather than
    double-pad. ``apply_boundary_pause_plan`` then snaps each to a VAD-safe low-energy cut
    and inserts with anti-click micro-fades — the same contract as the aligned path, minus
    the model. Less precise than alignment (proportional, not acoustic), but strictly
    better than the energy path on a zero-gap clip, which has no interior gap to edit.
    """
    from persona_forge.prosody_repair import build_vad_pause_edits as shared_builder

    return shared_builder(
        wav, sr, transcript, style_preset, pace_multiplier, pause_offset_ms, target_overrides
    )


def get_vad_directed_wav(
    voice_id: str,
    style_preset: str,
    pace_multiplier: float,
    pause_offset_ms: float = 0.0,
    *,
    mode: str = "precise",
    return_plan: bool = False,
    target_overrides: dict[str, float] | None = None,
) -> tuple[np.ndarray, int] | tuple[np.ndarray, int, list[dict[str, Any]]] | None:
    """Alignment-free surgical insertion (plan §5.5 step 3): proportional punctuation
    placement + VAD-safe anti-click cut. Returns ``(wav, sr)`` or ``None`` to fall through
    (no transcript, ``auto`` where triage says not blended, or no interior punctuation)."""
    meta = get_voice(voice_id)
    if meta is None:
        return None
    transcript = (meta.get("sample_text") or "").strip()
    if not transcript:
        return None
    loaded = _load_master_wav(voice_id)
    if loaded is None:
        return None
    wav, sr, _ = loaded

    if mode == "auto":
        from persona_forge.prosody_triage import MODE_PRECISE, triage
        if triage(wav, sr, transcript).mode != MODE_PRECISE:
            return None

    edits = build_vad_pause_edits(
        wav, sr, transcript, style_preset, pace_multiplier, pause_offset_ms, target_overrides
    )
    if not edits:
        return None
    plan = plan_boundary_pauses(wav, sr, edits)
    adjusted = apply_resolved_boundary_pause_plan(wav, sr, plan)
    return (adjusted, sr, plan) if return_plan else (adjusted, sr)


def build_alignment_pause_edits(
    boundaries: list[dict[str, Any]],
    style_preset: str,
    pace_multiplier: float,
    pause_offset_ms: float = 0.0,
    target_overrides: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Map punctuation-owned aligned boundaries to alignment-owned pause edits (plan §5.3).

    Each ``sentence_split`` boundary gets the preset's ``sentence_end`` target; each
    clause-owning boundary the ``comma`` target — using the same absolute duration
    formula as ``get_pause_targets`` (``preset * pace + offset``), emitted directly with
    no second expansion pass. ``uncertain`` boundaries (transcript/audio divergence) are
    skipped so we never cut blindly. ``existing_ms`` is derived from the aligned gap to the
    next word, so a partially-blended boundary is resized rather than double-padded; a
    boundary that already has enough silence yields a net no-op insert.
    """
    from persona_forge.prosody_repair import build_alignment_pause_edits as shared_builder

    return shared_builder(
        boundaries, style_preset, pace_multiplier, pause_offset_ms, target_overrides
    )


def get_alignment_directed_wav(
    voice_id: str,
    style_preset: str,
    pace_multiplier: float,
    pause_offset_ms: float = 0.0,
    *,
    mode: str = "precise",
    emit: Any = None,
    return_plan: bool = False,
    target_overrides: dict[str, float] | None = None,
) -> tuple[np.ndarray, int] | tuple[np.ndarray, int, list[dict[str, Any]]] | None:
    """Alignment-directed surgical pause insertion for blended speech (plan §5.3/§5.5).

    Aligns the master reference to its transcript (reusing the ``meta["alignment"]`` cache
    when its identity still matches) and inserts each punctuation-owned pause at the aligned
    word boundary via the anti-click ``apply_boundary_pause_plan``. Returns ``(wav, sr)`` on
    success, or ``None`` to signal the caller to fall back to the energy path — no transcript,
    ``auto`` mode where triage says the clip is not blended, alignment yielding no confident
    owned boundaries, or any alignment error. This keeps the chain "never worse than status
    quo" (plan §5.5 step 4).
    """
    from persona_forge import forced_alignment as _fa

    meta = get_voice(voice_id)
    if meta is None:
        return None
    transcript = (meta.get("sample_text") or "").strip()
    if not transcript:
        return None
    loaded = _load_master_wav(voice_id)
    if loaded is None:
        return None
    wav, sr, wav_bytes = loaded
    voice_dir = _voice_dir(voice_id)

    # auto escalates to alignment only when triage classifies the clip as blended.
    if mode == "auto":
        from persona_forge.prosody_triage import MODE_PRECISE, triage
        if triage(wav, sr, transcript).mode != MODE_PRECISE:
            return None

    identity = _fa.cache_identity(_fa.sha256_bytes(wav_bytes), _fa.sha256_text(transcript))
    cached = meta.get("alignment")
    if _fa.identity_matches(cached, identity):
        boundaries = list(cached.get("boundaries", []))
    else:
        try:
            aligned = _fa.align(wav, int(sr), transcript, emit=emit)
        except Exception:
            logger.exception("Forced alignment failed for %s; falling back to energy path", voice_id)
            return None
        boundaries = [b.to_dict() for b in aligned]
        # Persist the fresh alignment so later adjusts and the triage badge reuse it.
        fresh = get_voice(voice_id)
        if fresh is not None:
            fresh.pop("wav_path", None)
            fresh.pop("undo_available", None)
            fresh["alignment"] = _fa.build_alignment_record(aligned, identity)
            (voice_dir / "meta.json").write_text(json.dumps(fresh, indent=2), encoding="utf-8")

    edits = build_alignment_pause_edits(
        boundaries, style_preset, pace_multiplier, pause_offset_ms, target_overrides
    )
    if not edits:
        return None
    plan = plan_boundary_pauses(wav, int(sr), edits)
    adjusted = apply_resolved_boundary_pause_plan(wav, int(sr), plan)
    return (adjusted, int(sr), plan) if return_plan else (adjusted, int(sr))


def get_prosody_adjusted_wav(
    voice_id: str,
    style_preset: str,
    pace_multiplier: float,
    pause_offset_ms: float = 0.0,
    mode: str = "natural",
    return_plan: bool = False,
    target_overrides: dict[str, float] | None = None,
) -> tuple[np.ndarray, int] | tuple[np.ndarray, int, list[dict[str, Any]]] | None:
    """Calculate prosody-adjusted audio for a voice without persisting it.
    Returns (wav, sr) or None on error.

    ``mode`` selects the pause engine (plan §5.5 fallback chain):
      - ``natural`` (default): today's energy/gap-based path only.
      - ``precise`` / ``auto``: try alignment-directed surgical insertion first (1/2), then
        alignment-free VAD-directed surgical insertion (3), then the energy path (4) — each
        step strictly no worse than the next. ``auto`` gates the surgical steps on triage
        (blended only); ``precise`` forces them.
    """
    if mode in ("auto", "precise"):
        directed = get_alignment_directed_wav(
            voice_id, style_preset, pace_multiplier, pause_offset_ms, mode=mode,
            return_plan=return_plan, target_overrides=target_overrides,
        )
        if directed is not None:
            return directed
        # Step 3: alignment unusable — alignment-free VAD-directed surgical insertion.
        vad = get_vad_directed_wav(
            voice_id, style_preset, pace_multiplier, pause_offset_ms, mode=mode,
            return_plan=return_plan, target_overrides=target_overrides,
        )
        if vad is not None:
            return vad
        # Step 4: fall through to the energy path (never worse than status quo).

    meta = get_voice(voice_id)
    if meta is None:
        return None

    loaded = _load_master_wav(voice_id)
    if loaded is None:
        print(f"[DEBUG] master audio for {voice_id} is not a file")
        return None
    wav, sr, _ = loaded

    gaps = detect_pause_intervals(wav, sr)
    duration_sec = wav.size / float(sr)
    edge_tolerance = 1.0 / float(sr)

    interior = [
        (start_sec, end_sec)
        for start_sec, end_sec in gaps
        if start_sec > edge_tolerance and end_sec < duration_sec - edge_tolerance
    ]

    if not interior:
        return (wav, sr, []) if return_plan else (wav, sr)

    sample_text = meta.get("sample_text", "")
    gap_starts = [start for start, end in interior]
    targets = get_pause_targets(sample_text, style_preset, pace_multiplier, gap_starts, duration_sec, pause_offset_ms)

    edits: list[dict[str, Any]] = []
    for i, (start_sec, end_sec) in enumerate(interior):
        dur_sec = end_sec - start_sec
        mid_sec = (start_sec + end_sec) / 2.0
        
        target_sec, trigger_type = targets.get(i, (0.0, "natural"))

        if trigger_type == "natural":
            # Unmatched gap (breath/hesitation): scale by pace to preserve the speaker's own
            # delivery character rather than snapping every breath to the natural constant
            # (which mechanizes the pacing). Punctuation gaps below get an absolute target.
            new_dur = dur_sec * pace_multiplier
            diff = new_dur - dur_sec
            if abs(diff) > 0.001:
                if diff > 0:
                    edits.append({
                        "type": "insert_silence",
                        "at_ms": mid_sec * 1000.0,
                        "duration_ms": diff * 1000.0,
                    })
                else:
                    edits.append({
                        "type": "delete",
                        "start_ms": (mid_sec - abs(diff) / 2.0) * 1000.0,
                        "end_ms": (mid_sec + abs(diff) / 2.0) * 1000.0,
                    })
            continue

        if dur_sec > target_sec + 0.01:
            cut_sec = dur_sec - target_sec
            edits.append({
                "type": "delete",
                "start_ms": (mid_sec - cut_sec / 2.0) * 1000.0,
                "end_ms": (mid_sec + cut_sec / 2.0) * 1000.0,
            })
        elif dur_sec < target_sec - 0.01:
            edits.append({
                "type": "insert_silence",
                "at_ms": mid_sec * 1000.0,
                "duration_ms": (target_sec - dur_sec) * 1000.0,
            })

    if not edits:
        return (wav, sr, []) if return_plan else (wav, sr)

    adjusted = apply_region_edits(wav, sr, edits)
    return (adjusted, sr, []) if return_plan else (adjusted, sr)

def create_prosody_variant(
    voice_id: str, style_preset: str, pace_multiplier: float, pause_offset_ms: float = 0.0,
    mode: str = "natural", target_overrides: dict[str, float] | None = None,
    source: str = "preset",
) -> tuple[str, str] | None:
    """Create a prosody-adjusted variant of the master reference and register it in
    variants.json under a unique slug (lineage-preserving vd_<parent_hex>.<slug> sub-ID).
    Returns (variant_filename, slug), or None on error.
    """
    result = get_prosody_adjusted_wav(
        voice_id, style_preset, pace_multiplier, pause_offset_ms, mode,
        target_overrides=target_overrides,
    )
    if result is None:
        return None

    adjusted, sr = result

    slug = _slugify_variant(style_preset, pace_multiplier, voice_id)
    variant_filename = f"prosody_{slug}.wav"
    voice_dir = _voice_dir(voice_id)
    buf = io.BytesIO()
    sf.write(buf, adjusted, sr, format="WAV", subtype="PCM_16")
    (voice_dir / variant_filename).write_bytes(buf.getvalue())

    variants = _load_variants_meta(voice_id)
    variants[slug] = {
        "filename": variant_filename,
        "label": f"{style_preset} {pace_multiplier}x",
        "created_at": time.time(),
        "source": source,
        "style_preset": style_preset,
        "pace_multiplier": pace_multiplier,
        "pause_offset_ms": pause_offset_ms,
        "target_overrides": target_overrides,
    }
    _save_variants_meta(voice_id, variants)

    return variant_filename, slug


def save_prosody_variant(
    voice_id: str, style_preset: str, pace_multiplier: float, pause_offset_ms: float = 0.0,
    mode: str = "natural", target_overrides: dict[str, float] | None = None,
) -> dict[str, Any] | None:
    """Bake and save a prosody variant WITHOUT promoting it to active/served audio.

    Distinct from adjust_reference_pauses (save + promote, atomic) — this is the
    save-only half of the split, so a variant can be created and independently
    addressed (vd_<parent_hex>.<slug>) without changing what's currently served.
    Returns the voice metadata plus the new variant's slug/id.
    """
    source = "precise-edit" if target_overrides else "preset"
    created = create_prosody_variant(
        voice_id, style_preset, pace_multiplier, pause_offset_ms, mode,
        target_overrides=target_overrides, source=source,
    )
    if created is None:
        return None
    _variant_filename, slug = created

    meta = get_voice(voice_id)
    if meta is None:
        return None
    meta["variant_id"] = f"{voice_id}.{slug}"
    meta["variant_slug"] = slug
    return meta

def preview_prosody_variant(
    voice_id: str, style_preset: str, pace_multiplier: float, pause_offset_ms: float = 0.0
) -> bytes | None:
    """Return the prosody-adjusted audio bytes for a voice without saving.
    """
    result = get_prosody_adjusted_wav(voice_id, style_preset, pace_multiplier, pause_offset_ms)
    if result is None:
        return None

    adjusted, sr = result
    buf = io.BytesIO()
    sf.write(buf, adjusted, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()



def _voice_dir(voice_id: str) -> Path:
    parent_id, _slug = parse_voice_id(voice_id)
    # Validate parent_id against the expected hex pattern to prevent path traversal.
    # Both plain vd_<hex> IDs and variant vd_<hex>/<slug> IDs resolve here.
    if not _VOICE_ID_RE.match(parent_id):
        raise ValueError(f"Invalid voice_id format: {voice_id!r}")
    return VOICE_LIBRARY_DIR / parent_id


def _load_variants_meta(voice_id: str) -> dict[str, dict[str, Any]]:
    """Load <voice_dir>/variants.json: {slug: {filename, label, created_at, source, ...}}."""
    path = _voice_dir(voice_id) / "variants.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_variants_meta(voice_id: str, variants: dict[str, dict[str, Any]]) -> None:
    path = _voice_dir(voice_id) / "variants.json"
    path.write_text(json.dumps(variants, indent=2), encoding="utf-8")


def _slugify_variant(style_preset: str, pace_multiplier: float, voice_id: str) -> str:
    """Derive a unique, filesystem/URL-safe slug for a new variant of voice_id."""
    base = re.sub(r"[^a-z0-9]+", "-", f"{style_preset}-{pace_multiplier}x".lower()).strip("-") or "variant"
    existing = _load_variants_meta(voice_id)
    slug = base
    suffix = 2
    while slug in existing:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def _has_clipping_failure(quality_warnings: list[str], metrics: dict[str, Any]) -> bool:
    true_peak_dbtp = metrics.get("true_peak_dbtp")
    if isinstance(true_peak_dbtp, (int, float)) and true_peak_dbtp > -0.5:
        return True
    peak_dbfs = metrics.get("peak_dbfs")
    if isinstance(peak_dbfs, (int, float)) and peak_dbfs > -0.5:
        return True
    return any("clipping" in warning.lower() for warning in quality_warnings)


def _analyze_wav_bytes(wav_bytes: bytes, transcript: str | None) -> tuple[float, list[str], dict[str, Any]]:
    with tempfile.NamedTemporaryFile(dir=VOICE_LIBRARY_DIR, suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        tmp_path = Path(tmp.name)
    try:
        return calculate_quality_score(tmp_path, transcript=transcript)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def _auto_fix_clipping(wav_bytes: bytes) -> bytes:
    """Run the same peak-limit/loudness pass as normalize_reference() on raw upload bytes.

    Applied once, before the quality gate, so a clipped reference doesn't need a round trip
    through a rejected save just to get the same fix normalize_reference() would apply anyway.
    """
    wav, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
    wav = np.asarray(wav, dtype=np.float32).ravel()
    fixed_wav, sr, _ = apply_style_preset(wav, sr, "Neutral")
    buf = io.BytesIO()
    sf.write(buf, fixed_wav, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def save_voice(
    wav_bytes: bytes,
    *,
    description: str,
    sample_text: str,
    language: str,
    seed: int | None = None,
    selections: dict[str, Any] | None = None,
    family_id: str | None = None,
    variant_name: str | None = None,
    variant_kind: str | None = None,
    source: str | None = None,
    project_id: str | None = None,
    project_name: str | None = None,
) -> dict[str, Any]:
    """Persist a newly captured VoiceDesign reference sample; returns its metadata.

    ``seed`` is the exact seed used to generate this reference (see voice_design.py —
    always a concrete resolved value, never None, so every voice is reproducible).
    ``selections`` is the chip state that composed ``description``, stored so the voice can
    later be reopened and tweaked in the VoiceDesign panel instead of only re-typed from
    scratch (docs/architecture/VOICE_DESIGN.md §8.3 tune/tweak workflow).
    """
    VOICE_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

    # Perform reference analysis and quality gating before the clip enters the library
    # (Plan R1). A clipping failure gets one automatic peak-limit/normalize pass — the same
    # fix normalize_reference() offers post-save — before hard-blocking the save.
    quality_score, quality_warnings, metrics = _analyze_wav_bytes(wav_bytes, sample_text)
    auto_fixed = False
    if _has_clipping_failure(quality_warnings, metrics):
        fixed_bytes = _auto_fix_clipping(wav_bytes)
        fixed_score, fixed_warnings, fixed_metrics = _analyze_wav_bytes(fixed_bytes, sample_text)
        if _has_clipping_failure(fixed_warnings, fixed_metrics):
            raise ValueError("Reference audio failed quality gate: clipping detected.")
        wav_bytes, quality_score, quality_warnings, metrics = (
            fixed_bytes,
            fixed_score,
            fixed_warnings,
            fixed_metrics,
        )
        auto_fixed = True

    voice_id = new_voice_id()
    voice_dir = _voice_dir(voice_id)
    voice_dir.mkdir(parents=True, exist_ok=True)
    wav_path = voice_dir / "original.wav"
    wav_path.write_bytes(wav_bytes)

    meta = {
        "voice_id": voice_id,
        "description": description,
        "sample_text": sample_text,
        "language": language,
        "seed": seed,
        "selections": selections,
        "created_at": time.time(),
        "family_id": family_id,
        "variant_name": variant_name,
        "variant_kind": variant_kind,
        "source": source,
        "metrics": metrics,
        "quality_score": quality_score,
        "quality_warnings": quality_warnings,
        "needs_review": bool(quality_warnings),
        "auto_fixed": auto_fixed,
        "project_id": project_id,
        "project_name": project_name,
    }
    (voice_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def is_mounted_or_readonly_reference(voice_id: str) -> bool:
    """True if editing this voice in place is risky: its original.wav is a symlink
    resolving outside the voice library tree (e.g. a container bind-mount), which is
    often mounted read-only by the deployment. Generalizes beyond the hardcoded
    "vd_000000000001" mounted-reference voice to any future mounted/read-only source.
    """
    if not _is_valid_voice_id(voice_id):
        return False
    original_wav = _voice_dir(voice_id) / "original.wav"
    if not original_wav.is_symlink():
        return False
    try:
        target = original_wav.resolve()
    except OSError:
        return True
    try:
        target.relative_to(VOICE_LIBRARY_DIR.resolve())
        return False
    except ValueError:
        return True


def get_voice(voice_id: str) -> dict[str, Any] | None:
    """Return metadata + wav_path for voice_id, or None if it doesn't exist.

    A dotted sub-ID (vd_<parent_hex>.<slug>) resolves directly to that specific saved
    variant file via variants.json, bypassing the current.wav promotion chain entirely —
    a sub-ID always means "this exact take," independent of whatever is currently promoted.
    """
    if not _is_valid_voice_id(voice_id):
        return None
    parent_id, slug = parse_voice_id(voice_id)
    voice_dir = _voice_dir(voice_id)
    meta_path = voice_dir / "meta.json"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if slug is not None:
        variants = _load_variants_meta(parent_id)
        entry = variants.get(slug)
        if entry is None:
            return None
        variant_wav = voice_dir / entry["filename"]
        if not variant_wav.is_file():
            return None
        meta["wav_path"] = str(variant_wav)
        meta["voice_id"] = voice_id
        meta["parent_voice_id"] = parent_id
        meta["undo_available"] = False
        meta["mounted_reference"] = False
        return meta

    # Resolution Priority Chain: current -> original -> legacy (reference)
    current_wav = voice_dir / "current.wav"
    original_wav = voice_dir / "original.wav"
    legacy_wav = voice_dir / "reference.wav"

    if current_wav.is_symlink() or current_wav.is_file():
        resolved_wav = current_wav
    elif original_wav.is_symlink() or original_wav.is_file():
        resolved_wav = original_wav
    elif legacy_wav.is_symlink() or legacy_wav.is_file():
        resolved_wav = legacy_wav
    else:
        resolved_wav = original_wav

    meta["wav_path"] = str(resolved_wav)
    history_dir = voice_dir / ".history"
    meta["undo_available"] = history_dir.is_dir() and any(history_dir.iterdir())
    meta["mounted_reference"] = is_mounted_or_readonly_reference(voice_id)
    return meta


def get_voice_wav_bytes(voice_id: str) -> bytes | None:
    meta = get_voice(voice_id)
    if meta is None:
        return None
    wav_path = Path(meta["wav_path"])
    # Resolve symlinks to ensure we get the actual file
    if wav_path.is_symlink():
        wav_path = wav_path.resolve()
    if not wav_path.is_file():
        return None
    return wav_path.read_bytes()


def set_voice_project(
    voice_id: str, project_id: str | None, project_name: str | None = None,
) -> dict[str, Any] | None:
    """Assign or clear the Accent Design Project this voice belongs to (§4)."""
    meta = get_voice(voice_id)
    if meta is None:
        return None
    meta.pop("wav_path", None)
    meta["project_id"] = project_id
    meta["project_name"] = project_name
    voice_dir = _voice_dir(voice_id)
    (voice_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def update_voice(
    voice_id: str,
    *,
    sample_text: str,
    sample_text_source: str | None = None,
    asr: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Patch a saved voice's reference transcript and optional ASR metadata in place.

    Reference text must match what's actually spoken in reference.wav for cloning quality
    (see app.py's omnivoice_save), so users need to fix typos/spacing/accent-spelling here
    without forking a whole new voice — unlike the chip-based "tune/tweak" flow below, which
    always forks (docs/architecture/VOICE_DESIGN.md §8.3) because it re-generates the reference audio too.
    """
    meta = get_voice(voice_id)
    if meta is None:
        return None
    meta.pop("wav_path", None)
    meta["sample_text"] = sample_text
    meta["sample_text_source"] = sample_text_source or "user"
    meta["needs_review"] = False if asr is None else asr.get("severity") not in (None, "ok")
    if asr is not None:
        meta["asr"] = asr
    voice_dir = _voice_dir(voice_id)
    (voice_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def delete_voice(voice_id: str) -> bool:
    """Remove a voice's directory. Returns False if it doesn't exist (not an error) — the
    tune/tweak workflow forks a new voice on every edit, so this exists to prune superseded
    forks (docs/architecture/VOICE_DESIGN.md §8.3).
    """
    if not _is_valid_voice_id(voice_id):
        return False
    voice_dir = _voice_dir(voice_id)
    if not voice_dir.is_dir():
        return False
    shutil.rmtree(voice_dir)
    return True


def _snapshot_reference(voice_id: str) -> None:
    voice_dir = _voice_dir(voice_id)
    wav_path = voice_dir / "original.wav"
    meta_path = voice_dir / "meta.json"
    if not wav_path.is_file() or not meta_path.is_file():
        return
    history_dir = voice_dir / ".history"
    history_dir.mkdir(exist_ok=True)
    snapshot = history_dir / f"{time.time_ns()}"
    snapshot.mkdir()
    shutil.copy2(wav_path, snapshot / "original.wav")
    shutil.copy2(meta_path, snapshot / "meta.json")
    for stale in sorted((entry for entry in history_dir.iterdir() if entry.is_dir()), reverse=True)[10:]:
        shutil.rmtree(stale)


def undo_reference_edit(voice_id: str) -> dict[str, Any] | None:
    """Restore the most recent reference-audio snapshot for a saved voice."""
    voice_dir = _voice_dir(voice_id)
    history_dir = voice_dir / ".history"
    snapshots = sorted((entry for entry in history_dir.iterdir() if entry.is_dir()), reverse=True) if history_dir.is_dir() else []
    if not snapshots:
        return None
    latest = snapshots[0]
    shutil.copy2(latest / "original.wav", voice_dir / "original.wav")
    shutil.copy2(latest / "meta.json", voice_dir / "meta.json")
    shutil.rmtree(latest)
    return get_voice(voice_id)


def analyze_reference(voice_id: str) -> dict[str, Any] | None:
    """Analyze an existing reference and persist metrics without rewriting its audio."""
    meta = get_voice(voice_id)
    if meta is None:
        return None
    wav_path = Path(meta["wav_path"])
    if not wav_path.is_file():
        return None
    quality_score, quality_warnings, metrics = calculate_quality_score(
        wav_path, transcript=meta.get("sample_text")
    )
    meta.pop("wav_path", None)
    meta["metrics"] = metrics
    meta["quality_score"] = quality_score
    meta["quality_warnings"] = quality_warnings
    asr_severity = (meta.get("asr") or {}).get("severity")
    meta["needs_review"] = bool(quality_warnings) or asr_severity not in (None, "ok")
    (_voice_dir(voice_id) / "meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return meta


def get_or_compute_alignment(
    voice_id: str,
    *,
    emit: Any = None,
    force: bool = False,
    language: str = "en",
    granularity: str = "word",
    cancel: Any = None,
) -> dict[str, Any] | None:
    """Return a cached forced alignment or compute + persist a fresh one.

    The cache lives in ``meta["alignment"]`` and is keyed by the full identity
    (audio + transcript hashes, language, immutable model/tokenizer revision,
    preprocess + schema versions, sample rate, granularity). Any difference —
    including an edited ``sample_text`` with unchanged audio — invalidates it.
    We hash the *actual resolved master* used by the voice (current/original),
    not an assumed ``original.wav``. Raises ``ValueError`` if there is no
    transcript, since alignment needs text.
    """
    from persona_forge import forced_alignment as _fa

    meta = get_voice(voice_id)
    if meta is None:
        return None
    transcript = (meta.get("sample_text") or "").strip()
    if not transcript:
        raise ValueError("Reference has no transcript; forced alignment needs text.")
    wav_bytes = get_voice_wav_bytes(voice_id)
    if wav_bytes is None:
        return None

    identity = _fa.cache_identity(
        _fa.sha256_bytes(wav_bytes),
        _fa.sha256_text(transcript),
        language=language,
        granularity=granularity,
    )
    cached = meta.get("alignment")
    if not force and _fa.identity_matches(cached, identity):
        return cached
    if cancel is not None and getattr(cancel, "is_set", lambda: False)():
        return None

    wav, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32", always_2d=False)
    boundaries = _fa.align(
        np.asarray(wav, dtype=np.float32), int(sr), transcript,
        emit=emit, language=language, granularity=granularity,
    )
    record = _fa.build_alignment_record(boundaries, identity)

    meta.pop("wav_path", None)
    meta.pop("undo_available", None)
    meta["alignment"] = record
    (_voice_dir(voice_id) / "meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return record


def list_voices() -> list[dict[str, Any]]:
    """Return all voice metadata, backfilling analysis for legacy entries once."""
    if not VOICE_LIBRARY_DIR.is_dir():
        return []
    voices: list[dict[str, Any]] = []
    for entry in VOICE_LIBRARY_DIR.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(meta.get("metrics"), dict):
            try:
                meta = analyze_reference(entry.name) or meta
            except Exception:
                # Keep the voice usable and let the UI expose a manual retry action.
                pass
        history_dir = entry / ".history"
        meta["undo_available"] = history_dir.is_dir() and any(history_dir.iterdir())
        meta["mounted_reference"] = is_mounted_or_readonly_reference(entry.name)
        voices.append(meta)
    voices.sort(key=lambda m: m.get("created_at", 0), reverse=True)
    return voices


def get_voices_by_family(family_id: str) -> list[dict[str, Any]]:
    """Return all voices belonging to a specific family, sorted by creation date."""
    return [v for v in list_voices() if v.get("family_id") == family_id]


def create_voice_variant(
    source_voice_id: str,
    variant_name: str,
    variant_kind: str,
    description: str | None = None,
) -> dict[str, Any] | None:
    """Fork an existing voice into a new variant with updated metadata.
    Shares the same reference audio.
    """
    source = get_voice(source_voice_id)
    if source is None:
        return None

    # Copy metadata, update variant details
    meta = source.copy()
    meta.pop("voice_id", None) # new ID will be generated by save_voice
    meta["variant_name"] = variant_name
    meta["variant_kind"] = variant_kind
    if description:
        meta["description"] = description

    # To save as a variant, we use the same wav_bytes.
    wav_bytes = get_voice_wav_bytes(source_voice_id)
    if wav_bytes is None:
        return None

    # save_voice generates a new voice_id and persists to disk.
    return save_voice(
        wav_bytes=wav_bytes,
        description=meta["description"],
        sample_text=meta["sample_text"],
        language=meta["language"],
        seed=meta.get("seed"),
        selections=meta.get("selections"),
        family_id=meta.get("family_id"),
        variant_name=variant_name,
        variant_kind=variant_kind,
        source="variant_fork",
    )


def duplicate_voice(source_voice_id: str, variant_filename: str | None = None) -> dict[str, Any] | None:
    """Fork a saved voice into an independent, byte-for-byte copy.

    This intentionally bypasses save_voice(): duplication is a safety operation before destructive
    editing, so it must not re-run normalization or otherwise change the reference audio.

    By default forks whichever audio ``current.wav`` resolves to (the active variant, or
    ``original.wav`` if none is set). Pass ``variant_filename`` to fork a *specific* variant
    regardless of which one is currently active — this is the "Fork to independent voice_id"
    per-variant action, which must not disturb the source voice's active variant as a side effect.
    """
    source = get_voice(source_voice_id)
    if source is None:
        return None
    if variant_filename:
        voice_dir = _voice_dir(source_voice_id)
        variant_path = voice_dir / variant_filename
        if not variant_path.is_file():
            return None
        wav_bytes = variant_path.read_bytes()
    else:
        wav_bytes = get_voice_wav_bytes(source_voice_id)
    if wav_bytes is None:
        return None

    voice_id = new_voice_id()
    new_voice_dir = _voice_dir(voice_id)
    new_voice_dir.mkdir(parents=True, exist_ok=False)
    (new_voice_dir / "original.wav").write_bytes(wav_bytes)

    meta = dict(source)
    meta.pop("wav_path", None)
    meta.pop("api_active", None)
    meta.pop("is_default", None)
    meta["voice_id"] = voice_id
    meta["created_at"] = time.time()
    suffix = f" ({variant_filename})" if variant_filename else ""
    meta["description"] = f"{source.get('description') or source_voice_id} (copy{suffix})"
    meta["source"] = "duplicate"
    meta["duplicated_from"] = source_voice_id
    (new_voice_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def delete_variant(voice_id: str, variant_filename: str) -> bool:
    """Delete a prosody variant file. If it was the active variant, fall back to original.wav."""
    if not _is_valid_voice_id(voice_id) or not variant_filename.startswith("prosody_") or not variant_filename.endswith(".wav"):
        return False
    voice_dir = _voice_dir(voice_id)
    variant_path = voice_dir / variant_filename
    if not variant_path.is_file():
        return False

    current_wav = voice_dir / "current.wav"
    if current_wav.is_symlink() and current_wav.resolve().name == variant_filename:
        set_active_variant(voice_id, None)
    variant_path.unlink()

    variants = _load_variants_meta(voice_id)
    stale_slugs = [slug for slug, entry in variants.items() if entry.get("filename") == variant_filename]
    if stale_slugs:
        for slug in stale_slugs:
            del variants[slug]
        _save_variants_meta(voice_id, variants)

    return True


def get_variant_wav_bytes(voice_id: str, variant_filename: str) -> bytes | None:
    """Read a specific variant's audio bytes, for per-variant preview.

    Also allows the literal "original.wav" (an exact-match allowlist entry, not a pattern
    loosening) so the master reference can be previewed directly regardless of whichever
    variant is currently promoted to current.wav.
    """
    is_original = variant_filename == "original.wav"
    if not _is_valid_voice_id(voice_id) or not (
        is_original or (variant_filename.startswith("prosody_") and variant_filename.endswith(".wav"))
    ):
        return None
    variant_path = _voice_dir(voice_id) / variant_filename
    if not variant_path.is_file():
        return None
    return variant_path.read_bytes()


def compute_variant_metrics(voice_id: str, variant_filename: str) -> dict[str, Any] | None:
    """Compute quality metrics for a specific variant file without persisting to meta.json.

    Unlike ``analyze_reference`` (which writes into the parent voice's ``meta.json``), this is
    safe to call on every preview click for any variant/Original file, since previewing a
    non-promoted variant must never mutate the parent's canonical stored metrics.
    """
    meta = get_voice(voice_id)
    if meta is None:
        return None
    is_original = variant_filename == "original.wav"
    if not _is_valid_voice_id(voice_id) or not (
        is_original or (variant_filename.startswith("prosody_") and variant_filename.endswith(".wav"))
    ):
        return None
    variant_path = _voice_dir(voice_id) / variant_filename
    if not variant_path.is_file():
        return None
    quality_score, quality_warnings, metrics = calculate_quality_score(
        variant_path, transcript=meta.get("sample_text")
    )
    return {
        "metrics": metrics,
        "quality_score": quality_score,
        "quality_warnings": quality_warnings,
    }


def ensure_mounted_ref_voice(
    ref_audio_path: str,
    sample_text: str | None = None,
    sample_text_source: str = "env",
    asr: dict[str, Any] | None = None,
) -> str | None:
    """Register the mounted REF_AUDIO as a first-class 'Mounted reference' voice.

    Creates/updates voice vd_000000000001 backed by the same WAV.
    Idempotent: skips if hash matches; updates WAV+meta if hash changed.
    Returns voice_id if created/updated, else None on any error (non-fatal).
    """
    MOUNTED_VOICE_ID = MOUNTED_REF_VOICE_ID
    if not ref_audio_path or not os.path.isfile(ref_audio_path):
        return None
    try:
        import hashlib
        data = Path(ref_audio_path).read_bytes()
        if len(data) == 0:
            return None
        file_hash = hashlib.sha256(data).hexdigest()
        voice_dir = _voice_dir(MOUNTED_VOICE_ID)
        meta_path = voice_dir / "meta.json"
        existing = None
        if meta_path.is_file():
            try:
                existing = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = None
        if existing and existing.get("source") == "mounted_ref_audio" and existing.get("sha256") == file_hash:
            updated = dict(existing)
            updated["sample_text"] = (sample_text or "").rstrip()
            updated["sample_text_source"] = sample_text_source
            if asr is not None:
                updated["asr"] = asr
                updated["needs_review"] = asr.get("severity") not in (None, "ok")
            meta_path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
            return MOUNTED_VOICE_ID
        voice_dir.mkdir(parents=True, exist_ok=True)
        # Bridge to the actual mounted physical file
        (voice_dir / "original.wav").symlink_to(ref_audio_path)
        # Also set the current pointer to original
        (voice_dir / "current.wav").symlink_to(voice_dir / "original.wav")

        # Perform reference analysis and quality gating
        quality_score, quality_warnings, metrics = calculate_quality_score(voice_dir / "original.wav", transcript=sample_text)

        meta = {
            "voice_id": MOUNTED_VOICE_ID,
            "description": "Mounted reference (Default)",
            "sample_text": (sample_text or "").rstrip(),
            "sample_text_source": sample_text_source,
            "language": "en",
            "source": "mounted_ref_audio",
            "sha256": file_hash,
            "created_at": time.time(),
            "metrics": metrics,
            "quality_score": quality_score,
            "quality_warnings": quality_warnings,
            "needs_review": bool(quality_warnings),
        }
        if asr is not None:
            meta["asr"] = asr
            meta["needs_review"] = asr.get("severity") not in (None, "ok")
        (voice_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return MOUNTED_VOICE_ID
    except Exception:
        return None


def _rewrite_reference_wav(voice_id: str, wav: np.ndarray, sr: int) -> dict[str, Any] | None:
    """Overwrite original.wav in place and refresh derived metrics/quality gate.

    Raises PermissionError up front — before touching the file — if original.wav is a
    symlink to a mounted/read-only source (§2.3): writing through it would either fail
    with a raw filesystem permission error or silently corrupt the mounted host file,
    neither of which is acceptable. Callers (normalize/trim/pause-adjust/region-edits)
    should route through "edit on a copy" instead.
    """
    if is_mounted_or_readonly_reference(voice_id):
        raise PermissionError(
            f"{voice_id} is backed by a mounted, read-only reference file — in-place edits are "
            "blocked to avoid corrupting or failing against the mounted source. Use 'Edit on a "
            "copy' (or 'Fork to independent voice_id') and edit the copy instead."
        )
    meta = get_voice(voice_id)
    if meta is None:
        return None
    voice_dir = _voice_dir(voice_id)
    wav_path = voice_dir / "original.wav"
    _snapshot_reference(voice_id)
    sf.write(wav_path, wav, sr, format="WAV", subtype="PCM_16")
    quality_score, quality_warnings, metrics = calculate_quality_score(wav_path, transcript=meta.get("sample_text"))

    meta.pop("wav_path", None)
    meta["metrics"] = metrics
    meta["quality_score"] = quality_score
    meta["quality_warnings"] = quality_warnings
    meta["needs_review"] = bool(quality_warnings)
    (voice_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def normalize_reference(voice_id: str) -> dict[str, Any] | None:
    """Re-normalize a saved reference clip's loudness/peak in place (-20 LUFS, -1dBTP ceiling).

    Reuses the "Neutral" style preset pipeline so a voice's stored reference — not just its
    generated output — gets the same normalization other clips get at generation time.
    """
    meta = get_voice(voice_id)
    if meta is None:
        return None
    wav_bytes = get_voice_wav_bytes(voice_id)
    if wav_bytes is None:
        return None
    wav, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
    wav = np.asarray(wav, dtype=np.float32).ravel()
    normalized, sr, _ = apply_style_preset(wav, sr, "Neutral")
    return _rewrite_reference_wav(voice_id, normalized, sr)


def trim_reference_silence(voice_id: str, padding_ms: float = 80.0) -> dict[str, Any] | None:
    """Trim leading/trailing silence from a saved reference clip, keeping a small padding.

    Uses the same top_db threshold as detect_pause_intervals() elsewhere in the pipeline, so
    what gets trimmed here matches what the UI already marks as a pause.
    """
    meta = get_voice(voice_id)
    if meta is None:
        return None
    wav_bytes = get_voice_wav_bytes(voice_id)
    if wav_bytes is None:
        return None
    wav, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
    wav = np.asarray(wav, dtype=np.float32).ravel()
    gaps = detect_pause_intervals(wav, sr)
    if not gaps:
        return meta

    speech_start_sec = gaps[0][1]
    speech_end_sec = gaps[-1][0]

    if speech_start_sec >= speech_end_sec:
        return meta

    pad = int(sr * padding_ms / 1000.0)
    start = max(0, int(speech_start_sec * sr) - pad)
    end = min(wav.size, int(speech_end_sec * sr) + pad)
    if start <= 0 and end >= wav.size:
        return meta
    return _rewrite_reference_wav(voice_id, wav[start:end], sr)


def adjust_reference_pauses(
    voice_id: str, style_preset: str = "Neutral", pace_multiplier: float = 1.0, pause_offset_ms: float = 0.0,
    mode: str = "natural",
) -> dict[str, Any] | None:
    """Create a prosody variant and set it as active.
    Returns the voice metadata.
    """
    created = create_prosody_variant(voice_id, style_preset, pace_multiplier, pause_offset_ms, mode)
    if not created:
        return None
    variant_filename, _slug = created

    if not set_active_variant(voice_id, variant_filename):
        return None

    return get_voice(voice_id)




def apply_reference_region_edits(
    voice_id: str, edits: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Apply a manual RegionEdit list to a saved reference clip in place.

    Backs the hand-editing UI (drag-select -> delete a mid-clip pause / insert silence / fade).
    Edits are the same validated shape used for stitch clips, applied through the shared
    audio_post.apply_region_edits engine, then written back via _rewrite_reference_wav.
    """
    meta = get_voice(voice_id)
    if meta is None:
        return None
    if not edits:
        return meta
    wav_bytes = get_voice_wav_bytes(voice_id)
    if wav_bytes is None:
        return None
    wav, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
    wav = np.asarray(wav, dtype=np.float32).ravel()
    edited = apply_region_edits(wav, sr, edits)
    return _rewrite_reference_wav(voice_id, edited, sr)


def set_default_variant(voice_id: str) -> dict[str, Any] | None:
    """Mark voice_id as the default variant within its family, unmarking any siblings.

    Voices without a family_id are treated as a single-member family of themselves.
    """
    meta = get_voice(voice_id)
    if meta is None:
        return None
    family_id = meta.get("family_id")
    siblings = get_voices_by_family(family_id) if family_id else [meta]
    for sibling in siblings:
        sibling_id = sibling["voice_id"]
        is_default = sibling_id == voice_id
        if sibling.get("is_default", False) == is_default:
            continue
        sibling_meta = get_voice(sibling_id)
        if sibling_meta is None:
            continue
        sibling_meta.pop("wav_path", None)
        sibling_meta["is_default"] = is_default
        (_voice_dir(sibling_id) / "meta.json").write_text(
            json.dumps(sibling_meta, indent=2), encoding="utf-8"
        )
    return get_voice(voice_id)

"""Filesystem-backed voice library (docs/dev/architecture/voice_design.md §7).

Maps voice_id -> {wav_path, description, sample_text, language, created_at}. No database —
consistent with the project's existing "no database, bind-mounted host directories" pattern
(MODEL_CACHE_PATH, OV_DATA_PATH). No auth on top of this: the whole service is meant to sit
behind a trusted network / authenticated reverse proxy (see SECURITY.md).

Layout: <VOICE_LIBRARY_DIR>/<voice_id>/reference.wav + <VOICE_LIBRARY_DIR>/<voice_id>/meta.json
"""

from __future__ import annotations

import io
import json
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

from qwen3_tts.audio_post import apply_region_edits
from qwen3_tts.audio_style import (
    analyze_reference,
    apply_style_preset,
    detect_pause_intervals,
    get_pause_targets,
    PROSODY_MAPS,
)
from qwen3_tts.reference_analysis import calculate_quality_score


# Fixed container-side mount point, same pattern as qwen3_tts.config.REF_AUDIO_PATH.
# compose.yml binds ${VOICE_LIBRARY_PATH:-./data/voices} (host) -> this path (container).
VOICE_LIBRARY_DIR = Path(os.getenv("VOICE_LIBRARY_DIR", "/voices"))

_VOICE_ID_RE = re.compile(r"^vd_[0-9a-f]{12}$")


def new_voice_id() -> str:
    return f"vd_{secrets.token_hex(6)}"


def _is_valid_voice_id(voice_id: str) -> bool:
    # Endpoint input travels straight into a filesystem path (get_voice/_voice_dir), so this
    # doubles as path-traversal defense, not just a format check.
    return bool(voice_id) and bool(_VOICE_ID_RE.match(voice_id))


def set_active_variant(voice_id: str, variant_filename: str | None = None) -> bool:
    """Set the active reference audio for a voice.
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
        return True
    except OSError:
        return False


def get_prosody_adjusted_wav(
    voice_id: str, style_preset: str, pace_multiplier: float
) -> tuple[np.ndarray, int] | None:
    """Calculate prosody-adjusted audio for a voice without persisting it.
    Returns (wav, sr) or None on error.
    """
    meta = get_voice(voice_id)
    if meta is None:
        return None

    voice_dir = _voice_dir(voice_id)
    master_path = voice_dir / "original.wav"
    if not master_path.is_file():
        return None

    wav_bytes = master_path.read_bytes()
    wav, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
    wav = np.asarray(wav, dtype=np.float32).ravel()

    gaps = detect_pause_intervals(wav, sr)
    duration_sec = wav.size / float(sr)
    edge_tolerance = 1.0 / float(sr)

    interior = [
        (start_sec, end_sec)
        for start_sec, end_sec in gaps
        if start_sec > edge_tolerance and end_sec < duration_sec - edge_tolerance
    ]

    if not interior:
        return wav, sr

    sample_text = meta.get("sample_text", "")
    targets = get_pause_targets(sample_text, style_preset, pace_multiplier, len(interior))

    edits: list[dict[str, Any]] = []
    for i, (start_sec, end_sec) in enumerate(interior):
        dur_sec = end_sec - start_sec
        mid_sec = (start_sec + end_sec) / 2.0
        target_sec = targets[i] if i < len(targets) else targets[-1]

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
        return wav, sr

    return apply_region_edits(wav, sr, edits), sr

def create_prosody_variant(
    voice_id: str, style_preset: str, pace_multiplier: float
) -> str | None:
    """Create a prosody-adjusted variant of the master reference.
    Returns the filename of the created variant.
    """
    result = get_prosody_adjusted_wav(voice_id, style_preset, pace_multiplier)
    if result is None:
        return None

    adjusted, sr = result

    # If no changes were made, we can just return the original
    # (Note: this is slightly simplified as apply_region_edits might return same wav)
    # We'll just always save it to be sure it's a distinct file if the user expects a variant.
    # Actually, if adjusted is identical to original, we can return "original.wav".
    # But for simplicity, let's always save the variant.

    variant_filename = f"prosody_{style_preset}_{pace_multiplier}x.wav"
    voice_dir = _voice_dir(voice_id)
    buf = io.BytesIO()
    sf.write(buf, adjusted, sr, format="WAV", subtype="PCM_16")
    (voice_dir / variant_filename).write_bytes(buf.getvalue())
    return variant_filename

def preview_prosody_variant(
    voice_id: str, style_preset: str, pace_multiplier: float
) -> bytes | None:
    """Return the prosody-adjusted audio bytes for a voice without saving.
    """
    result = get_prosody_adjusted_wav(voice_id, style_preset, pace_multiplier)
    if result is None:
        return None

    adjusted, sr = result
    buf = io.BytesIO()
    sf.write(buf, adjusted, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()



def _voice_dir(voice_id: str) -> Path:
    return VOICE_LIBRARY_DIR / voice_id


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
) -> dict[str, Any]:
    """Persist a newly captured VoiceDesign reference sample; returns its metadata.

    ``seed`` is the exact seed used to generate this reference (see voice_design.py —
    always a concrete resolved value, never None, so every voice is reproducible).
    ``selections`` is the chip state that composed ``description``, stored so the voice can
    later be reopened and tweaked in the VoiceDesign panel instead of only re-typed from
    scratch (docs/dev/architecture/voice_design.md §8.3 tune/tweak workflow).
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
    }
    (voice_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def get_voice(voice_id: str) -> dict[str, Any] | None:
    """Return metadata + wav_path for voice_id, or None if it doesn't exist."""
    if not _is_valid_voice_id(voice_id):
        return None
    voice_dir = _voice_dir(voice_id)
    meta_path = voice_dir / "meta.json"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

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


def update_voice(voice_id: str, *, sample_text: str) -> dict[str, Any] | None:
    """Patch a saved voice's reference transcript in place (metadata only, no re-clone).

    Reference text must match what's actually spoken in reference.wav for cloning quality
    (see app.py's omnivoice_save), so users need to fix typos/spacing/accent-spelling here
    without forking a whole new voice — unlike the chip-based "tune/tweak" flow below, which
    always forks (docs/dev/architecture/voice_design.md §8.3) because it re-generates the reference audio too.
    """
    meta = get_voice(voice_id)
    if meta is None:
        return None
    meta.pop("wav_path", None)
    meta["sample_text"] = sample_text
    meta["sample_text_source"] = "user"
    meta["needs_review"] = False
    voice_dir = _voice_dir(voice_id)
    (voice_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def delete_voice(voice_id: str) -> bool:
    """Remove a voice's directory. Returns False if it doesn't exist (not an error) — the
    tune/tweak workflow forks a new voice on every edit, so this exists to prune superseded
    forks (docs/dev/architecture/voice_design.md §8.3).
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


def duplicate_voice(source_voice_id: str) -> dict[str, Any] | None:
    """Create an independent, byte-for-byte copy of a saved voice.

    This intentionally bypasses save_voice(): duplication is a safety operation before destructive
    editing, so it must not re-run normalization or otherwise change the reference audio.
    """
    source = get_voice(source_voice_id)
    wav_bytes = get_voice_wav_bytes(source_voice_id)
    if source is None or wav_bytes is None:
        return None

    voice_id = new_voice_id()
    voice_dir = _voice_dir(voice_id)
    voice_dir.mkdir(parents=True, exist_ok=False)
    (voice_dir / "original.wav").write_bytes(wav_bytes)

    meta = dict(source)
    meta.pop("wav_path", None)
    meta.pop("api_active", None)
    meta.pop("is_default", None)
    meta["voice_id"] = voice_id
    meta["created_at"] = time.time()
    meta["description"] = f"{source.get('description') or source_voice_id} (copy)"
    meta["source"] = "duplicate"
    meta["duplicated_from"] = source_voice_id
    (voice_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


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
    MOUNTED_VOICE_ID = "vd_000000000001"
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
    """
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
    voice_id: str, style_preset: str = "Neutral", pace_multiplier: float = 1.0
) -> dict[str, Any] | None:
    """Create a prosody variant and set it as active.
    Returns the voice metadata.
    """
    variant_filename = create_prosody_variant(voice_id, style_preset, pace_multiplier)
    if not variant_filename:
        return None

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

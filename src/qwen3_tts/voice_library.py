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
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from qwen3_tts.audio_style import analyze_reference, apply_style_preset, detect_pause_intervals
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
    with tempfile.NamedTemporaryFile(dir=VOICE_LIBRARY_DIR, suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        tmp_path = Path(tmp.name)
    try:
        # Perform reference analysis and quality gating before the clip enters the library.
        quality_score, quality_warnings, metrics = calculate_quality_score(tmp_path, transcript=sample_text)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    if _has_clipping_failure(quality_warnings, metrics):
        raise ValueError("Reference audio failed quality gate: clipping detected.")

    voice_id = new_voice_id()
    voice_dir = _voice_dir(voice_id)
    voice_dir.mkdir(parents=True, exist_ok=True)
    wav_path = voice_dir / "reference.wav"
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
    meta["wav_path"] = str(voice_dir / "reference.wav")
    return meta


def get_voice_wav_bytes(voice_id: str) -> bytes | None:
    meta = get_voice(voice_id)
    if meta is None:
        return None
    wav_path = Path(meta["wav_path"])
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
    import shutil

    shutil.rmtree(voice_dir)
    return True


def list_voices() -> list[dict[str, Any]]:
    """Return all voice metadata, newest first. Skips entries with missing/corrupt meta.json."""
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
        (voice_dir / "reference.wav").write_bytes(data)

        # Perform reference analysis and quality gating
        quality_score, quality_warnings, metrics = calculate_quality_score(voice_dir / "reference.wav", transcript=sample_text)

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
    """Overwrite reference.wav in place and refresh derived metrics/quality gate.

    Shared by any operation that edits the stored reference audio itself (normalize, trim),
    as opposed to update_voice(), which only patches metadata.
    """
    meta = get_voice(voice_id)
    if meta is None:
        return None
    voice_dir = _voice_dir(voice_id)
    wav_path = voice_dir / "reference.wav"
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

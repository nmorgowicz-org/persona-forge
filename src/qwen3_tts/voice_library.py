"""Filesystem-backed voice library (docs/plans/PLAN_voice_design.md §7).

Maps voice_id -> {wav_path, description, sample_text, language, created_at}. No database —
consistent with the project's existing "no database, bind-mounted host directories" pattern
(MODEL_CACHE_PATH, OV_DATA_PATH). No auth on top of this: the whole service is meant to sit
behind a trusted network / authenticated reverse proxy (see SECURITY.md).

Layout: <VOICE_LIBRARY_DIR>/<voice_id>/reference.wav + <VOICE_LIBRARY_DIR>/<voice_id>/meta.json
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

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


def save_voice(
    wav_bytes: bytes, *, description: str, sample_text: str, language: str
) -> dict[str, Any]:
    """Persist a newly captured VoiceDesign reference sample; returns its metadata."""
    voice_id = new_voice_id()
    voice_dir = _voice_dir(voice_id)
    voice_dir.mkdir(parents=True, exist_ok=True)
    (voice_dir / "reference.wav").write_bytes(wav_bytes)
    meta = {
        "voice_id": voice_id,
        "description": description,
        "sample_text": sample_text,
        "language": language,
        "created_at": time.time(),
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

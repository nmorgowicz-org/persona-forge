"""Filesystem-backed OmniVoice segment library.

Persists individually locked-in candidate takes (not full stitched voices — see
voice_library.py for that) so good sentence/accent combinations accumulate across sessions
instead of only existing for the lifetime of one design session's in-memory candidate cache.
Enables flexible stitching: a final reference voice can be assembled from any subset of the
library, not just the segments locked in during one sitting.

Same "no database, bind-mounted host directory" pattern as voice_library.py.

Layout: <SEGMENT_LIBRARY_DIR>/<segment_id>/clip.wav + <SEGMENT_LIBRARY_DIR>/<segment_id>/meta.json
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

# compose.yml binds ${SEGMENT_LIBRARY_PATH:-./data/segments} (host) -> this path (container).
SEGMENT_LIBRARY_DIR = Path(os.getenv("SEGMENT_LIBRARY_DIR", "/segments"))

_SEGMENT_ID_RE = re.compile(r"^seg_[0-9a-f]{12}$")


def new_segment_id() -> str:
    return f"seg_{secrets.token_hex(6)}"


def _is_valid_segment_id(segment_id: str) -> bool:
    # Endpoint input travels straight into a filesystem path, so this doubles as
    # path-traversal defense, not just a format check.
    return bool(segment_id) and bool(_SEGMENT_ID_RE.match(segment_id))


def _segment_dir(segment_id: str) -> Path:
    # Validate segment_id to prevent path traversal from user input.
    if not _SEGMENT_ID_RE.match(segment_id):
        raise ValueError(f"Invalid segment_id format: {segment_id!r}")
    return SEGMENT_LIBRARY_DIR / segment_id


def _tags_from_instruct(instruct: str) -> list[str]:
    return [tag.strip() for tag in instruct.split(",") if tag.strip()]


def save_segment(
    wav_bytes: bytes,
    *,
    text: str,
    instruct: str,
    engine: str,
    sample_rate: int,
    accent_id: str | None = None,
    language: str | None = None,
    seed: int | None = None,
    num_step: int | None = None,
    speed: float | None = None,
    guidance_scale: float | None = None,
    diverse_candidates: bool | None = None,
    postprocess_output: bool | None = None,
    duration_target: float | None = None,
    candidate_id: str | None = None,
    job_id: str | None = None,
    whisper_transcript: str | None = None,
    match_score: float | None = None,
    duration_sec: float | None = None,
    feature_tags: list[str] | None = None,
    project_id: str | None = None,
    project_name: str | None = None,
) -> dict[str, Any]:
    """Persist one locked-in candidate take; returns its metadata.

    ``instruct`` is parsed into ``tags`` (split on comma) so the library can be browsed/
    filtered by trait ("australian accent", "high pitch", ...) without re-parsing on every
    read.
    """
    segment_id = new_segment_id()
    segment_dir = _segment_dir(segment_id)
    segment_dir.mkdir(parents=True, exist_ok=True)
    (segment_dir / "clip.wav").write_bytes(wav_bytes)
    meta = {
        "segment_id": segment_id,
        "text": text,
        "instruct": instruct,
        "tags": _tags_from_instruct(instruct),
        "engine": engine,
        "accent_id": accent_id,
        "sample_rate": sample_rate,
        "language": language,
        "seed": seed,
        "num_step": num_step,
        "speed": speed,
        "guidance_scale": guidance_scale,
        "diverse_candidates": diverse_candidates,
        "postprocess_output": postprocess_output,
        "duration_target": duration_target,
        "candidate_id": candidate_id,
        "job_id": job_id,
        "whisper_transcript": whisper_transcript,
        "match_score": match_score,
        "duration_sec": duration_sec,
        "feature_tags": feature_tags or [],
        "project_id": project_id,
        "project_name": project_name,
        "created_at": time.time(),
    }
    (segment_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def get_segment(segment_id: str) -> dict[str, Any] | None:
    """Return metadata + wav_path for segment_id, or None if it doesn't exist."""
    if not _is_valid_segment_id(segment_id):
        return None
    segment_dir = _segment_dir(segment_id)
    meta_path = segment_dir / "meta.json"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    meta["wav_path"] = str(segment_dir / "clip.wav")
    return meta


def set_segment_project(
    segment_id: str, project_id: str | None, project_name: str | None = None,
) -> dict[str, Any] | None:
    """Assign or clear the Accent Design Project this segment belongs to (§4)."""
    meta = get_segment(segment_id)
    if meta is None:
        return None
    meta.pop("wav_path", None)
    meta["project_id"] = project_id
    meta["project_name"] = project_name
    segment_dir = _segment_dir(segment_id)
    (segment_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def get_segment_wav_bytes(segment_id: str) -> bytes | None:
    meta = get_segment(segment_id)
    if meta is None:
        return None
    wav_path = Path(meta["wav_path"])
    if not wav_path.is_file():
        return None
    return wav_path.read_bytes()


def delete_segment(segment_id: str) -> bool:
    if not _is_valid_segment_id(segment_id):
        return False
    segment_dir = _segment_dir(segment_id)
    if not segment_dir.is_dir():
        return False
    import shutil

    shutil.rmtree(segment_dir)
    return True


def list_segments() -> list[dict[str, Any]]:
    """Return all segment metadata, newest first. Skips entries with missing/corrupt meta.json."""
    if not SEGMENT_LIBRARY_DIR.is_dir():
        return []
    segments: list[dict[str, Any]] = []
    for entry in SEGMENT_LIBRARY_DIR.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        segments.append(meta)
    segments.sort(key=lambda m: m.get("created_at", 0), reverse=True)
    return segments

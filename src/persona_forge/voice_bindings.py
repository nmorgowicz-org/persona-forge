"""Binding status: whether a saved voice is prepared for a cloning engine (plan §4.1, §5.4).

A *binding* is one (saved voice x engine) pair. Its state is ``ready`` | ``needs_preparation`` |
``preparing`` | ``failed`` | ``unsupported``, and ``ready`` is only ever claimed for the exact
inputs that were prepared: the reference audio's hash, the transcript's hash (for engines that
clone with one) and the engine's revision. Change any of them and the marker no longer matches,
so the binding reads ``needs_preparation`` again with no invalidation hook to forget.

Markers are written by the adapters after a successful worker ``prepare`` (lazily at first
synthesis or from the explicit Prepare action) and live in the voice's own directory, so
deleting the voice deletes them. Reading status never starts a worker: it is a few small JSON
reads plus a cached file hash per voice.

What a marker means: the engine accepted this reference (and transcript) once, so a request
needs nothing further at request time (no transcript lookup, no Whisper download). The prepared
state itself lives in the worker's memory and is rebuilt on demand after an engine unload.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from persona_forge import speech_engines, voice_library

MARKER_FILE = "engine_bindings.json"
BASELINE_ENGINE = "pocket-tts"
NO_CLONING = "no local cloning"

_lock = threading.RLock()
_hashes: dict[str, tuple[tuple[int, ...], str]] = {}
_jobs: dict[tuple[str, str], dict[str, Any]] = {}


# -- inputs -----------------------------------------------------------------------------------


def _is_installed(engine_id: str) -> bool:
    from persona_forge import provisioned_engines

    provisioned = provisioned_engines.get(engine_id)
    return provisioned is not None and bool(provisioned.engine.is_installed())


def _needs_transcript(engine_id: str) -> bool:
    from persona_forge import provisioned_engines

    provisioned = provisioned_engines.get(engine_id)
    return provisioned is not None and bool(getattr(provisioned.engine, "CLONE_NEEDS_TRANSCRIPT", False))


def engine_revision(engine_id: str) -> str:
    """Identity of what a pack was built from; a repair or upgrade that changes it re-prepares."""
    from persona_forge import engine_packs

    return engine_packs.binding_revision(engine_id)


def file_sha256(path: str | os.PathLike[str]) -> str:
    """SHA-256 cached by file identity, size, mtime and ctime (including timestamp-preserving edits)."""
    resolved = Path(path).resolve()
    stat = resolved.stat()
    stamp = (stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    cached = _hashes.get(str(resolved))
    if cached is not None and cached[0] == stamp:
        return cached[1]
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    _hashes[str(resolved)] = (stamp, digest.hexdigest())
    return digest.hexdigest()


def text_sha256(text: str | None) -> str:
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


def current_key(meta: dict[str, Any], engine_id: str) -> dict[str, str]:
    """What a marker must equal for ``engine_id`` to be ready for this voice right now."""
    key = {
        "reference_sha256": file_sha256(meta["wav_path"]),
        "revision": engine_revision(engine_id),
    }
    if _needs_transcript(engine_id):
        key["transcript_sha256"] = text_sha256(meta.get("sample_text"))
    return key


# -- markers ----------------------------------------------------------------------------------


def _marker_path(voice_id: str) -> Path:
    return voice_library._voice_dir(voice_id) / MARKER_FILE


def _read_markers(voice_id: str) -> dict[str, Any]:
    try:
        data = json.loads(_marker_path(voice_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):  # ValueError covers bad JSON and a non-library voice id
        return {}
    return data if isinstance(data, dict) else {}


def read_marker(voice_id: str, engine_id: str) -> dict[str, Any] | None:
    voice_entry = _read_markers(voice_id).get(voice_id)
    entry = voice_entry.get(engine_id) if isinstance(voice_entry, dict) else None
    return entry if isinstance(entry, dict) else None


def write_marker(voice_id: str, engine_id: str, key: dict[str, str]) -> None:
    """Record that ``engine_id`` prepared ``voice_id`` with exactly ``key`` (and clear any job)."""
    try:
        path = _marker_path(voice_id)
    except ValueError:
        return  # not a library voice id, so there is no directory to keep a marker in
    if not path.parent.is_dir():
        return  # the voice was deleted while it was being prepared
    with _lock:
        markers = _read_markers(voice_id)
        voice_entry = markers.get(voice_id)
        if not isinstance(voice_entry, dict):
            voice_entry = markers[voice_id] = {}
        voice_entry[engine_id] = {**key, "prepared_at": time.time()}
        try:
            voice_library._write_text_atomic(path, json.dumps(markers, indent=2))
        except OSError:
            return  # a read-only library still serves; the voice just reads as unprepared
        if (_jobs.get((voice_id, engine_id)) or {}).get("state") != "preparing":
            _jobs.pop((voice_id, engine_id), None)


# -- in-flight and failed preparations (memory only) --------------------------------------------


def reset_jobs() -> None:
    with _lock:
        _jobs.clear()


def set_job(
    voice_id: str, engine_id: str, state: str, *, key: dict[str, str] | None, error: str | None = None
) -> None:
    with _lock:
        _jobs[(voice_id, engine_id)] = {
            "state": state,
            "key": key,
            "error": error,
            "at": time.time(),
        }


def get_job(voice_id: str, engine_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get((voice_id, engine_id))
        return dict(job) if job is not None else None


def clear_job(voice_id: str, engine_id: str) -> None:
    with _lock:
        _jobs.pop((voice_id, engine_id), None)


# -- status -----------------------------------------------------------------------------------


def _blocker(meta: dict[str, Any], needs_transcript: bool) -> str | None:
    if not needs_transcript:
        return None
    if not (meta.get("sample_text") or "").strip():
        return "transcript_missing"
    if transcript_unreviewed(meta):
        return "transcript_unreviewed"
    return None


# ASR severities the Voice Library already shows as "Review text". ``needs_review`` is not used:
# it also flags audio-quality warnings (clipping, noise), which say nothing about the words.
_ASR_REVIEW_SEVERITIES = {"warn", "fail", "no_speech", "error"}


def transcript_unreviewed(meta: dict[str, Any]) -> bool:
    """True when the speech check disagreed with the stored words and nobody has confirmed them.

    Typing or confirming the transcript (``sample_text_source`` becomes ``user``) is the review.
    """
    asr = meta.get("asr")
    severity = asr.get("severity") if isinstance(asr, dict) else None
    return severity in _ASR_REVIEW_SEVERITIES and meta.get("sample_text_source") != "user"


_BLOCKER_REASON = {
    "engine_not_installed": "Install the engine to use it.",
    "transcript_missing": "Needs a transcript: add or generate one, then prepare.",
    "transcript_unreviewed": "Review the transcript before preparing; it must match the audio.",
}


def _binding(meta: dict[str, Any], engine: speech_engines.EngineInfo) -> dict[str, Any]:
    voice_id = meta["voice_id"]
    base: dict[str, Any] = {
        "engine": engine.id,
        "label": engine.label,
        "status": "needs_preparation",
        "supported": engine.capabilities.clone,
        "installed": True,
        "needs_transcript": False,
        "blocker": None,
        "reason": None,
        "error": None,
        "prepared_at": None,
        "can_prepare": False,
    }
    if not engine.capabilities.clone:
        return {**base, "status": "unsupported", "reason": NO_CLONING}
    if engine.id == BASELINE_ENGINE:
        # Pocket clones per request through the app's own runtime; there is nothing to prepare.
        return {**base, "status": "ready"}

    installed = _is_installed(engine.id)
    needs_transcript = _needs_transcript(engine.id)
    base.update(installed=installed, needs_transcript=needs_transcript)
    if not installed:
        return {**base, "blocker": "engine_not_installed", "reason": _BLOCKER_REASON["engine_not_installed"]}

    blocker = _blocker(meta, needs_transcript)
    if blocker:
        return {**base, "blocker": blocker, "reason": _BLOCKER_REASON[blocker], "can_prepare": True}

    key = current_key(meta, engine.id)
    job = get_job(voice_id, engine.id)
    if job is not None and job["state"] == "preparing":
        return {**base, "status": "preparing", "reason": "Preparing…"}
    marker = read_marker(voice_id, engine.id)
    if marker is not None and all(marker.get(name) == value for name, value in key.items()):
        return {**base, "status": "ready", "prepared_at": marker.get("prepared_at")}

    if job is not None and job["state"] == "failed" and job["key"] == key:
        return {
            **base,
            "status": "failed",
            "error": job["error"],
            "reason": job["error"],
            "can_prepare": True,
        }
    blocker = _blocker(meta, needs_transcript)
    return {
        **base,
        "blocker": blocker,
        "reason": _BLOCKER_REASON.get(blocker or ""),
        "can_prepare": True,  # preparing is also how a missing transcript gets resolved
    }


def meta_with_path(voice_id: str) -> dict[str, Any] | None:
    meta = voice_library.get_voice(voice_id)
    if meta is None:
        return None
    path = Path(meta.get("wav_path") or "")
    return meta if path.is_file() else None


def bindings_for_meta(meta: dict[str, Any]) -> list[dict[str, Any]]:
    return [_binding(meta, engine) for engine in speech_engines.list_engines()]


def bindings_for_voice(voice_id: str) -> list[dict[str, Any]]:
    """One binding per registered engine, in registry order; ``[]`` for an unknown voice."""
    meta = meta_with_path(voice_id)
    return bindings_for_meta(meta) if meta is not None else []


def all_bindings() -> dict[str, list[dict[str, Any]]]:
    """Bindings for every saved voice in one pass (no worker is contacted)."""
    result: dict[str, list[dict[str, Any]]] = {}
    for listed in voice_library.list_voices():
        meta = meta_with_path(listed["voice_id"])
        if meta is not None:
            result[listed["voice_id"]] = bindings_for_meta(meta)
    return result

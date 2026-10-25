"""Saved Compare-tab listening sessions, kept next to ``ui_preferences.json``.

Ratings follow the install, not the browser. Each session is one comparison: the text, and per
slot the engine, voice, generation time, audio length and the user's ratings. The per-engine
summary is computed here so the engine cards and the Compare tab show the same numbers.
"""

from __future__ import annotations

import json
import os
import statistics
import tempfile
import threading
from pathlib import Path
from typing import Any

from persona_forge import paths

_FILENAME = "compare_results.json"
MAX_SESSIONS = 500
MAX_SLOTS = 8
_lock = threading.Lock()


class SessionInvalid(ValueError):
    def __init__(self, reason: str) -> None:
        self.safe_message = reason
        super().__init__(reason)


def _path() -> Path:
    return Path(paths.runtime_data_dir()) / _FILENAME


def load(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or _path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    sessions = data.get("sessions") if isinstance(data, dict) else None
    return [s for s in sessions if isinstance(s, dict)] if isinstance(sessions, list) else []


def _write(sessions: list[dict[str, Any]], p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{_FILENAME}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "sessions": sessions}, handle)
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _number(value: Any, low: float, high: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if low <= value <= high else None


def _clean_slot(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SessionInvalid("each slot must be an object")
    engine = raw.get("engine")
    if not isinstance(engine, str) or not 0 < len(engine) <= 64:
        raise SessionInvalid("slot engine must be a short string")
    slot: dict[str, Any] = {"engine": engine}
    for key in ("voice", "voiceName"):
        if isinstance(raw.get(key), str):
            slot[key] = raw[key][:200]
    for key, high in (("ms", 3_600_000), ("seconds", 3600)):
        number = _number(raw.get(key), 0, high)
        if number is not None:
            slot[key] = number
    for key in ("naturalness", "artifacts", "similarity"):
        number = _number(raw.get(key), 1, 5)
        if number is not None:
            slot[key] = int(number)
    if isinstance(raw.get("favourite"), bool):
        slot["favourite"] = raw["favourite"]
    return slot


def clean_session(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SessionInvalid("session must be an object")
    slots = raw.get("slots")
    if not isinstance(slots, list) or not 1 <= len(slots) <= MAX_SLOTS:
        raise SessionInvalid(f"slots must be a list of 1-{MAX_SLOTS} items")
    text = raw.get("text")
    at = raw.get("at")
    return {
        "at": at[:40] if isinstance(at, str) else "",
        "text": text[:2000] if isinstance(text, str) else "",
        "slots": [_clean_slot(s) for s in slots],
    }


def append(raw_sessions: list[Any], path: Path | None = None) -> int:
    """Validate and append sessions (newest kept). Returns the stored count."""
    cleaned = [clean_session(s) for s in raw_sessions]
    p = path or _path()
    with _lock:
        merged = (load(p) + cleaned)[-MAX_SESSIONS:]
        _write(merged, p)
    return len(merged)


def clear(path: Path | None = None) -> None:
    p = path or _path()
    with _lock:
        p.unlink(missing_ok=True)


def summarise(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-engine means, favourites, and generation time per second of audio (median and worst)."""
    rated: dict[str, list[dict[str, Any]]] = {}
    for session in sessions:
        for slot in session.get("slots", []):
            if "naturalness" in slot and "artifacts" in slot:
                rated.setdefault(slot["engine"], []).append(slot)
    rows = []
    for engine, clips in rated.items():
        speeds = [c["ms"] / 1000 / c["seconds"] for c in clips if c.get("ms") and c.get("seconds")]
        similarity = [c["similarity"] for c in clips if "similarity" in c]
        rows.append(
            {
                "engine": engine,
                "clips": len(clips),
                "natural": round(statistics.fmean(c["naturalness"] for c in clips), 2),
                "clean": round(statistics.fmean(c["artifacts"] for c in clips), 2),
                "similarity": round(statistics.fmean(similarity), 2) if similarity else None,
                "favourites": sum(1 for c in clips if c.get("favourite")),
                "speed_median": round(statistics.median(speeds), 3) if speeds else None,
                "speed_worst": round(max(speeds), 3) if speeds else None,
            }
        )
    return sorted(rows, key=lambda r: -(r["natural"] + r["clean"]))

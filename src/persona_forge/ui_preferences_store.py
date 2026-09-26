"""Server-side UI preferences (contract D17 / §6.11).

Persisted to ``ui_preferences.json`` in ``paths.runtime_data_dir()``, next to ``runtime.json``
(same pattern as ``runtime_store.py``), so preferences follow the install rather than the browser
origin: they survive port changes and are shared by every browser that uses this server.

Only the allowlisted keys below are accepted. The theme and experience-level lists live in the
frontend (the source of truth), so the server stores any short string for those two keys and the
frontend falls back to its default when it reads a value it does not know.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import warnings
from pathlib import Path
from typing import Any, Callable, Mapping

from persona_forge import paths

_SCHEMA_VERSION = 1
_FILENAME = "ui_preferences.json"

# Returns None when the value is acceptable, else a short reason for the 400 message.
Validator = Callable[[Any], str | None]


class PreferencesInvalid(ValueError):
    """A preference update was rejected.

    Raised with the key and a validator reason only, so the message is safe to return
    to API clients (CodeQL py/information-exposure-through-exception: routes must use
    ``safe_message``, never ``str(exc)``).
    """

    def __init__(self, key: str, reason: str) -> None:
        self.safe_message = f"{key}: {reason}"
        super().__init__(self.safe_message)


def _string(max_length: int) -> Validator:
    def validate(value: Any) -> str | None:
        if not isinstance(value, str):
            return "must be a string"
        if len(value) > max_length:
            return f"must be at most {max_length} characters"
        return None

    return validate


def _one_of(*choices: str) -> Validator:
    def validate(value: Any) -> str | None:
        if value not in choices:
            return f"must be one of {', '.join(repr(c) for c in choices)}"
        return None

    return validate


def _boolean(value: Any) -> str | None:
    return None if isinstance(value, bool) else "must be a boolean"


ALLOWED_KEYS: dict[str, Validator] = {
    "theme": _string(32),
    "experienceLevel": _string(32),
    "voiceLibrary.tab": _one_of("voices", "segments"),
    "voiceLibrary.layout": _string(32),
    "voiceLibrary.analysisExpanded": _boolean,
    "updates.dismissedVersion": _string(64),
}

# Serializes read-merge-write so two concurrent POSTs cannot drop each other's keys.
_write_lock = threading.Lock()


def _ui_preferences_path() -> Path:
    return paths.runtime_data_dir() / _FILENAME


def load(path: Path | None = None) -> dict[str, Any]:
    """Load persisted preferences. A missing file is ``{}``; a corrupt or malformed one is
    ``{}`` plus a warning, never a boot failure."""
    p = path or _ui_preferences_path()
    if not p.is_file():
        return {}

    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        warnings.warn(
            f"{_FILENAME} at {p} is unreadable/corrupt ({exc}); ignoring saved UI preferences.",
            stacklevel=2,
        )
        return {}

    if not isinstance(data, dict) or not isinstance(data.get("values"), dict):
        warnings.warn(
            f"{_FILENAME} at {p} has an unexpected shape; ignoring saved UI preferences.",
            stacklevel=2,
        )
        return {}

    return dict(data["values"])


def _validate(update: Mapping[str, Any]) -> None:
    for key, value in update.items():
        validator = ALLOWED_KEYS.get(key)
        if validator is None:
            raise PreferencesInvalid(key, "unknown preference")
        reason = validator(value)
        if reason is not None:
            raise PreferencesInvalid(key, reason)


def _write(values: Mapping[str, Any], p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": _SCHEMA_VERSION, "values": dict(values)}
    fd, tmp_name = tempfile.mkstemp(dir=p.parent, prefix=f".{_FILENAME}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f)
        os.replace(tmp_name, p)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def merge_and_save(update: Mapping[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Validate ``update``, merge it over the saved preferences, write atomically, and return
    the full merged map. Raises ``ValueError("<key>: <reason>")`` for an unknown key or an
    invalid value before anything is written."""
    _validate(update)
    p = path or _ui_preferences_path()
    with _write_lock:
        values = load(p)
        values.update(update)
        _write(values, p)
    return values

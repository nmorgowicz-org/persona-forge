"""Phase A7a: persist runtime config to ``${DATA_DIR}/runtime.json`` and layer it over
image/preset defaults at startup (D11 precedence: env-locked > file > default).

Reuses whatever data root is already mounted for the voice library (no new required volume):
``DATA_DIR`` if set, else ``VOICE_LIBRARY_DIR``/``VOICE_LIBRARY_PATH_CONTAINER``, else ``/voices``.
"""

from __future__ import annotations

import json
import os
import tempfile
import warnings
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from persona_forge import paths

_SCHEMA_VERSION = 1
_FILENAME = "runtime.json"


def _data_dir() -> Path:
    return paths.runtime_data_dir()


def _runtime_json_path() -> Path:
    return _data_dir() / _FILENAME


def load_persisted_config(path: Path | None = None) -> dict[str, Any]:
    """Load persisted runtime values. Missing, corrupt, or malformed files are ignored
    (warn, return ``{}``) rather than crashing boot."""
    p = path or _runtime_json_path()
    if not p.is_file():
        return {}

    try:
        raw = p.read_text()
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        warnings.warn(
            f"runtime.json at {p} is unreadable/corrupt ({exc}); ignoring persisted config.",
            stacklevel=2,
        )
        return {}

    if not isinstance(data, dict) or not isinstance(data.get("values"), dict):
        warnings.warn(
            f"runtime.json at {p} has an unexpected shape; ignoring persisted config.",
            stacklevel=2,
        )
        return {}

    return dict(data["values"])


def save_persisted_config(values: Mapping[str, Any], path: Path | None = None) -> None:
    """Atomically write ``values`` to disk (temp file + rename)."""
    p = path or _runtime_json_path()
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


def locked_keys(environ: MutableMapping[str, str] = os.environ) -> set[str]:
    """Keys an operator has explicitly locked via ``RUNTIME_LOCKED_KEYS`` (csv) and/or
    ``RUNTIME_LOCK_<KEY>=1``. Locked keys always win over a persisted file value."""
    keys = {k.strip() for k in (environ.get("RUNTIME_LOCKED_KEYS", "") or "").split(",") if k.strip()}
    prefix = "RUNTIME_LOCK_"
    for env_key, env_value in environ.items():
        if env_key.startswith(prefix) and str(env_value).strip() == "1":
            keys.add(env_key[len(prefix) :])
    return keys


def is_locked(key: str, environ: MutableMapping[str, str] = os.environ) -> bool:
    return key in locked_keys(environ)


def apply_persisted_config(environ: MutableMapping[str, str] = os.environ) -> dict[str, Any]:
    """Layer persisted ``runtime.json`` values over ``environ``, skipping locked keys.

    Must run after ``apply_preset_env`` (which only ``setdefault``s) and before any
    torch/OV import, mirroring the import-time ordering ``model.py`` already uses.
    File values *override* whatever ``environ`` currently holds (preset default or a
    plain, unlocked explicit value) — only an explicit lock outranks the file (D11).
    """
    values = load_persisted_config()
    locked = locked_keys(environ)
    applied: dict[str, Any] = {}
    for key, value in values.items():
        if key in locked:
            continue
        environ[key] = str(value)
        applied[key] = value
    return applied

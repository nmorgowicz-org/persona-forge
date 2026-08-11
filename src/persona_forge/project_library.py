"""Accent Design Project registry (docs/plans/20260714-voice-lifecycle-and-library-architecture.md §4).

A Project is just a name/description tag: voices and segments carry their own
`project_id`/`project_name` fields (set via voice_library.set_voice_project /
segment_library.set_segment_project), so membership is derived by scanning those
existing meta.json files rather than duplicated here. This file only tracks the
project registry itself (id -> name/description/created_at) — deleting a project
does not touch any voice/segment; they simply fall back to "Ungrouped" once their
project_id no longer resolves to a live project.

Stored inside VOICE_LIBRARY_DIR so it rides along on the same bind mount already
used by voice_library.py — no new volume wiring needed.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from typing import Any

from persona_forge.voice_library import VOICE_LIBRARY_DIR

_PROJECTS_FILE = VOICE_LIBRARY_DIR / "projects.json"
_PROJECT_ID_RE = re.compile(r"^proj_[0-9a-f]{12}$")


def _is_valid_project_id(project_id: str) -> bool:
    return bool(project_id) and bool(_PROJECT_ID_RE.match(project_id))


def _load() -> dict[str, dict[str, Any]]:
    if not _PROJECTS_FILE.is_file():
        return {}
    try:
        return json.loads(_PROJECTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(projects: dict[str, dict[str, Any]]) -> None:
    VOICE_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    _PROJECTS_FILE.write_text(json.dumps(projects, indent=2), encoding="utf-8")


def create_project(name: str, description: str | None = None) -> dict[str, Any]:
    projects = _load()
    project_id = f"proj_{secrets.token_hex(6)}"
    entry = {
        "project_id": project_id,
        "name": name,
        "description": description,
        "created_at": time.time(),
    }
    projects[project_id] = entry
    _save(projects)
    return entry


def list_projects() -> list[dict[str, Any]]:
    return sorted(_load().values(), key=lambda p: p.get("created_at", 0), reverse=True)


def get_project(project_id: str) -> dict[str, Any] | None:
    if not _is_valid_project_id(project_id):
        return None
    return _load().get(project_id)


def rename_project(project_id: str, name: str, description: str | None = None) -> dict[str, Any] | None:
    projects = _load()
    entry = projects.get(project_id)
    if entry is None:
        return None
    entry["name"] = name
    if description is not None:
        entry["description"] = description
    _save(projects)
    return entry


def delete_project(project_id: str) -> bool:
    projects = _load()
    if project_id not in projects:
        return False
    del projects[project_id]
    _save(projects)
    return True

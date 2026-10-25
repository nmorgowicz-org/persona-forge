"""Phonon 31M adapter: English preset voices from a pack child process.

Phonon cannot clone from a recording, so it serves only its built-in catalog. A request that names
a saved library voice gets a clear 400 instead of a silent fallback to some other voice.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


from persona_forge import engine_packs, phonon_pack, phonon_worker
from persona_forge.kitten2_engine import EngineUnavailable, InvalidVoice
from persona_forge.pack_preset_engine import PackPresetEngine

ENGINE_ID = phonon_pack.ENGINE_ID
PRESET_PREFIX = "phonon:"

__all__ = ["EngineUnavailable", "InvalidVoice", "PhononEngine", "is_installed", "list_presets"]


def pack_directory(root: Path | None = None) -> Path | None:
    return engine_packs.find_pack_dir(ENGINE_ID, root)


def pack_python(root: Path | None = None) -> Path | None:
    """Interpreter of the installed pack, or the ``PHONON_PYTHON`` development override."""
    override = os.environ.get("PHONON_PYTHON")
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    directory = pack_directory(root)
    if directory is None or engine_packs.inspect_pack(directory).status != "verified":
        return None
    python = phonon_pack.venv_python(directory)
    return python if python.is_file() else None


def is_installed(root: Path | None = None) -> bool:
    return pack_python(root) is not None


def list_presets(root: Path | None = None) -> list[str]:
    """English voice names from the downloaded catalog (no model load needed)."""
    directory = pack_directory(root)
    if directory is None or not is_installed(root):
        return []
    for catalog in sorted((directory / "hf").glob("**/models--*phonon-voices/snapshots/*/voices.jsonl")):
        names: list[str] = []
        try:
            for line in catalog.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                if entry.get("language") == "en" and entry.get("name"):
                    names.append(str(entry["name"]))
        except (OSError, ValueError):
            continue
        if names:
            return sorted(names)
    return []


def preset_language(name: str, root: Path | None = None) -> str:
    return "en"  # only English voices are listed


class PhononEngine(PackPresetEngine):
    id = ENGINE_ID
    label = "Phonon 31M"
    idle_env = "PHONON_IDLE_UNLOAD_S"
    worker_file = str(Path(phonon_worker.__file__).resolve())
    preset_prefix = PRESET_PREFIX
    streams = True

    def _pack_python(self) -> Path | None:
        return pack_python()

    def _load_request(self) -> tuple[dict[str, Any], dict[str, str]]:
        env: dict[str, str] = {}
        directory = None if os.environ.get("PHONON_PYTHON") else pack_directory()
        if directory is not None:
            # Serve from the pack's own files and never download mid-request.
            env = {"HF_HOME": str(phonon_pack.weights_dir(directory)), "HF_HUB_OFFLINE": "1"}
        return {"op": "load"}, env

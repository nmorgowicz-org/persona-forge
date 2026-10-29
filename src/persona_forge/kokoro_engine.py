"""Kokoro 82M adapter: multilingual preset voices from a pack child process.

Kokoro cannot clone from a recording, so it serves only its built-in catalog. A request that names
a saved library voice gets a clear 400 instead of a silent fallback to some other voice. The voice
name decides the language (``ff_siwis`` speaks French), so ``language`` in the request is ignored.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np

from persona_forge import engine_packs, kokoro_pack, kokoro_worker
from persona_forge.kitten2_engine import EngineUnavailable, InvalidVoice
from persona_forge.pack_preset_engine import PackPresetEngine

ENGINE_ID = kokoro_pack.ENGINE_ID
PRESET_PREFIX = "kokoro:"

__all__ = ["EngineUnavailable", "InvalidVoice", "KokoroEngine", "is_installed", "list_presets"]


def pack_directory(root: Path | None = None) -> Path | None:
    return engine_packs.find_pack_dir(ENGINE_ID, root)


def pack_python(root: Path | None = None) -> Path | None:
    """Interpreter of the installed pack, or the ``KOKORO_PYTHON`` development override."""
    override = os.environ.get("KOKORO_PYTHON")
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    directory = pack_directory(root)
    if directory is None or engine_packs.inspect_pack(directory).status != "verified":
        return None
    python = kokoro_pack.venv_python(directory)
    return python if python.is_file() else None


def is_installed(root: Path | None = None) -> bool:
    return pack_python(root) is not None


def list_presets(root: Path | None = None) -> list[str]:
    """Voice names the worker can serve, read from the voices file (no model load needed)."""
    directory = pack_directory(root)
    if directory is None or not is_installed(root):
        return []
    try:
        with np.load(kokoro_pack.voices_path(directory)) as data:
            names = [str(name) for name in data.files]
    except (OSError, ValueError):
        return []
    return sorted(name for name in names if kokoro_worker.language_for(name))


def preset_language(name: str, root: Path | None = None) -> str:
    """Language code of a voice (``a``/``b`` prefixes are US/UK English)."""
    return "en" if name[:1] in {"a", "b"} else (kokoro_worker.language_for(name) or "??")[:2]


class KokoroEngine(PackPresetEngine):
    id = ENGINE_ID
    label = "Kokoro 82M"
    idle_env = "KOKORO_IDLE_UNLOAD_S"
    idle_default_s = kokoro_pack.IDLE_UNLOAD_AFTER_S
    worker_file = str(Path(kokoro_worker.__file__).resolve())
    preset_prefix = PRESET_PREFIX

    def _pack_python(self) -> Path | None:
        return pack_python()

    def _seed(self, request: dict[str, Any], seed_value: int | None) -> None:
        del request, seed_value  # Kokoro is deterministic; there is nothing to seed

    def _load_request(self) -> tuple[dict[str, Any], dict[str, str]]:
        directory = pack_directory()
        if directory is None:
            raise EngineUnavailable(
                "The Kokoro 82M engine pack is not installed; install it in Runtime → Speech engines."
            )
        return {
            "op": "load",
            "model_path": str(kokoro_pack.model_path(directory)),
            "voices_path": str(kokoro_pack.voices_path(directory)),
        }, {}

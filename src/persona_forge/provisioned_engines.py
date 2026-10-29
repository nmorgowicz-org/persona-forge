"""Registry of engines that are provisioned as packs (their own environment, child process).

Each entry names two modules by dotted path, imported lazily so the web process never pays for an
engine nobody uses:

- the engine module exposes ``ENGINE_ID``, ``PRESET_PREFIX``, ``is_installed()`` and
  ``list_presets()``; its adapter exposes ``status()`` and ``recheck()``.
- the pack module exposes ``start_install()`` and ``job_status()``.

Adding an engine means adding one line here; the routes, the engine cards and the voice catalog
pick it up without further changes.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType

_REGISTRY: dict[str, tuple[str, str]] = {
    "kitten2": ("persona_forge.kitten2_engine", "persona_forge.kitten2_pack"),
    "phonon-31m": ("persona_forge.phonon_engine", "persona_forge.phonon_pack"),
    "kokoro": ("persona_forge.kokoro_engine", "persona_forge.kokoro_pack"),
    "pocket-lite": ("persona_forge.pocket_lite_engine", "persona_forge.pocket_lite_pack"),
}


@dataclass(frozen=True)
class Provisioned:
    engine_id: str
    engine: ModuleType
    pack: ModuleType


def ids() -> tuple[str, ...]:
    return tuple(_REGISTRY)


def get(engine_id: str) -> Provisioned | None:
    names = _REGISTRY.get(engine_id)
    if names is None:
        return None
    return Provisioned(
        engine_id,
        importlib.import_module(names[0]),
        importlib.import_module(names[1]),
    )


def all_engines() -> list[Provisioned]:
    return [item for engine_id in _REGISTRY if (item := get(engine_id)) is not None]

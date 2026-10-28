"""Voice names of the pack engines, bundled so they can be browsed before an engine is installed.

An installed engine reports its own voices (that is authoritative). This file only answers "what
would I get?" for an engine that is not installed yet, so the Built-in voices tab can list it with
a "needs install" badge. ``engine_voice_catalog.json`` is generated from installed packs
(``python -m persona_forge.voice_catalog``) and a test compares it to any pack that is installed,
so it cannot quietly go stale.
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOG_FILE = Path(__file__).with_name("engine_voice_catalog.json")

# Engines whose voice list is generated from an installed pack. Pocket Lite's is fixed in its
# worker, so it needs no file.
GENERATED_ENGINES = ("kitten2", "phonon-31m", "kokoro")


@lru_cache(maxsize=1)
def _load() -> dict[str, list[dict[str, str]]]:
    try:
        data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def bundled_voices(engine_id: str) -> list[dict[str, str]]:
    """``[{"name", "language"}]`` for an engine, or ``[]`` when none is bundled."""
    if engine_id == "pocket-lite":
        from persona_forge import pocket_lite_worker

        return [{"name": name, "language": "en"} for name in pocket_lite_worker.ENGLISH_PRESETS]
    return [dict(entry) for entry in _load().get(engine_id, [])]


def installed_voices(provisioned: Any) -> list[dict[str, str]]:
    """Voices an installed engine reports, in the same shape as :func:`bundled_voices`."""
    engine = provisioned.engine
    return [
        {"name": name, "language": engine.preset_language(name) or "en"}
        for name in engine.list_presets()
    ]


def refresh(path: Path = CATALOG_FILE) -> dict[str, list[dict[str, str]]]:
    """Rewrite the bundled file from the packs installed on this machine."""
    from persona_forge import provisioned_engines

    catalog = dict(_load())
    for engine_id in GENERATED_ENGINES:
        provisioned = provisioned_engines.get(engine_id)
        if provisioned is None or not provisioned.engine.is_installed():
            print(f"skipped {engine_id}: not installed here (kept the existing entry)", file=sys.stderr)
            continue
        catalog[engine_id] = installed_voices(provisioned)
    path.write_text(json.dumps(catalog, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    _load.cache_clear()
    return catalog


if __name__ == "__main__":
    result = refresh()
    for key, value in sorted(result.items()):
        print(f"{key}: {len(value)} voices")

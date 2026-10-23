"""Speech-engine registry (Phase C foundation).

One place describes every engine the server can offer: identity, capabilities, runtime and
licence. The API and UI derive model routing, controls and readiness from this; adding an engine
means adding an entry here plus an adapter, not another special case in the routes.

Phase C1 registers Pocket only. Entries for Kitten 2 / Kokoro / Phonon / KokoClone land once
their technical screening (Phase B) has picked the order, without changing this contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EngineCapabilities:
    clone: bool
    presets: bool
    import_prepared_voice: bool
    streaming: str  # "frame" | "sentence" | "none"
    languages: tuple[str, ...]
    speed: bool
    expression_tags: bool
    seed: bool
    instructions: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "clone": self.clone,
            "presets": self.presets,
            "import_prepared_voice": self.import_prepared_voice,
            "streaming": self.streaming,
            "languages": list(self.languages),
            "speed": self.speed,
            "expression_tags": self.expression_tags,
            "seed": self.seed,
            "instructions": self.instructions,
        }


@dataclass(frozen=True)
class EngineInfo:
    id: str
    label: str
    description: str
    backend: str
    runtime: str
    source: str
    license: str
    capabilities: EngineCapabilities
    installed: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "object": "model",
            "label": self.label,
            "description": self.description,
            "backend": self.backend,
            "runtime": self.runtime,
            "source": self.source,
            "license": self.license,
            "installed": self.installed,
            "capabilities": self.capabilities.as_dict(),
        }


POCKET_CAPABILITIES = EngineCapabilities(
    clone=True,
    presets=True,
    import_prepared_voice=False,
    streaming="frame",
    languages=("en", "fr", "de", "es", "it", "pt"),
    speed=False,
    expression_tags=False,
    seed=True,
    instructions=True,
)

ENGINES: dict[str, EngineInfo] = {
    "pocket-tts": EngineInfo(
        id="pocket-tts",
        label="Pocket TTS",
        description="Low-resource CPU engine with local cloning and a curated built-in catalog.",
        backend="pocket_tts",
        runtime="python-cpu",
        source="kyutai/pocket-tts",
        license="see upstream",
        capabilities=POCKET_CAPABILITIES,
    ),
}

# Model names OpenAI clients already send, plus conventional aliases. `None` means "the active
# engine", so old callers that omit `model` keep their current behaviour.
MODEL_ALIASES: dict[str, str | None] = {
    "": None,
    "default": None,
    "persona-forge": None,
    "persona_forge": None,
    # OpenAI SDK examples and older clients send these names; a drop-in endpoint must not
    # reject them just because the engine is local.
    "tts-1": None,
    "tts-1-hd": None,
    "gpt-4o-mini-tts": None,
    "pocket": "pocket-tts",
    "pocket-tts": "pocket-tts",
    "pocket_tts": "pocket-tts",
}


def engine_for_backend(backend: str | None) -> EngineInfo | None:
    """Return the engine currently served by ``model.TTS_BACKEND``."""
    for engine in ENGINES.values():
        if engine.backend == backend:
            return engine
    return None


def active_engine(backend: str | None) -> EngineInfo | None:
    """Return the active engine, falling back to Pocket for unknown legacy backends."""
    return engine_for_backend(backend) or ENGINES.get("pocket-tts")


def list_engines() -> list[EngineInfo]:
    """All registered engines, in registration order."""
    return list(ENGINES.values())


def resolve_model(
    model_name: str | None, current_backend: str | None
) -> tuple[EngineInfo | None, bool]:
    """Resolve an API ``model`` value to ``(engine, recognized)``.

    Known engine ids/backends and aliases resolve to that engine; an omitted model resolves to
    the active engine. Unrecognised names fall back to the active engine with ``recognized=False``
    — existing OpenAI clients send arbitrary labels (``custom``, ``tts-1``), and rejecting them
    would break the drop-in contract. The speech route reports recognition in a header.
    """
    key = (model_name or "").strip().lower()
    if key in MODEL_ALIASES:
        alias = MODEL_ALIASES[key]
        if alias is None:
            return active_engine(current_backend), True
        return ENGINES.get(alias), True
    for engine in ENGINES.values():
        if key in (engine.id, engine.backend):
            return engine, True
    return active_engine(current_backend), False

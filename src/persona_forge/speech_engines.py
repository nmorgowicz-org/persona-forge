"""Speech-engine registry (Phase C foundation).

One place describes every engine the server can offer: identity, capabilities, runtime and
licence. The API and UI derive model routing, controls and readiness from this; adding an engine
means adding an entry here plus an adapter, not another special case in the routes.

Phase C1 registers Pocket only. Entries for Kitten 2 / Kokoro / Phonon / KokoClone land once
their technical screening (Phase B) has picked the order, without changing this contract.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable


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
    pack_only: bool = False

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
            "pack_only": self.pack_only,
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

KITTEN2_CAPABILITIES = EngineCapabilities(
    clone=True,
    presets=True,
    import_prepared_voice=False,
    streaming="none",
    languages=("en",),
    speed=False,
    expression_tags=False,
    seed=True,
    instructions=False,
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
    "kitten2": EngineInfo(
        id="kitten2",
        label="Kitten TTS 2",
        description=(
            "Cloning and 115 built-in voices on Apple silicon (MLX) or an NVIDIA GPU. "
            "Installed as an engine pack; not usable on CPU-only machines."
        ),
        backend="kitten2",
        runtime="python-mlx-or-cuda",
        source="KittenML/kitten-tts-2",
        license="Stellon Labs Community License",
        capabilities=KITTEN2_CAPABILITIES,
        installed=False,
        pack_only=True,
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
    "kitten2": "kitten2",
    "kitten-2": "kitten2",
    "kitten-tts-2": "kitten2",
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


@runtime_checkable
class SpeechEngine(Protocol):
    """Behaviour a serving engine must provide (plan §4.2).

    C2 implements the synthesis surface; pack install/verify/prepare and unload join this
    contract in C3 without changing how the API calls it.
    """

    id: str

    def describe(self) -> dict[str, Any]:
        """Return the engine descriptor shown by /v1/models and the UI."""
        ...

    def synthesize(
        self,
        text: str,
        language: str,
        *,
        voice_id: str | None = None,
        voice_variant_id: str | None = None,
        style_preset: str | None = None,
        postprocess: bool | dict[str, Any] | None = None,
        prosody_repair: bool = False,
        seed_value: int | None = None,
        instruct: str | None = None,
    ) -> tuple[Any, int, str | None]:
        """Return ``(wav, sample_rate, job_id)`` for one complete request."""
        ...

    def stream_pcm(
        self,
        text: str,
        language: str,
        *,
        voice_id: str | None = None,
        seed_value: int | None = None,
    ) -> Iterator[bytes]:
        """Yield raw int16 LE mono PCM chunks."""
        ...


class PocketTtsEngine:
    """Pocket adapter over the existing runtime.

    C2 is deliberately a delegation layer: the model module stays the implementation, so the
    endpoint's behaviour, timeouts, repair metadata and cancellation semantics are unchanged.
    C3 moves the implementation behind a pack child process.
    """

    id = "pocket-tts"

    def describe(self) -> dict[str, Any]:
        return ENGINES[self.id].as_dict()

    def synthesize(
        self,
        text: str,
        language: str,
        *,
        voice_id: str | None = None,
        voice_variant_id: str | None = None,
        style_preset: str | None = None,
        postprocess: bool | dict[str, Any] | None = None,
        prosody_repair: bool = False,
        seed_value: int | None = None,
        instruct: str | None = None,
    ) -> tuple[Any, int, str | None]:
        from persona_forge import model

        return model.executor.submit(
            model._run_generate,
            text,
            language,
            voice_id=voice_id,
            voice_variant_id=voice_variant_id,
            style_preset=style_preset,
            postprocess=postprocess,
            prosody_repair=prosody_repair,
            seed_value=seed_value,
            instruct=instruct,
        ).result(timeout=480)

    def stream_pcm(
        self,
        text: str,
        language: str,
        *,
        voice_id: str | None = None,
        seed_value: int | None = None,
    ) -> Iterator[bytes]:
        from persona_forge import model

        yield from model._run_generate_pocket_tts_stream(
            text, language, voice_id=voice_id, seed_value=seed_value
        )


ADAPTERS: dict[str, SpeechEngine] = {"pocket-tts": PocketTtsEngine()}


def _make_kitten2() -> SpeechEngine:
    # Imported on first use: the adapter imports this module's registry, so building it at import
    # time would make the import order matter.
    from persona_forge.kitten2_engine import Kitten2Engine

    return Kitten2Engine()


_ADAPTER_FACTORIES: dict[str, Callable[[], SpeechEngine]] = {"kitten2": _make_kitten2}


def get_adapter(engine_id: str) -> SpeechEngine | None:
    """Return the adapter for ``engine_id``, creating lazily built ones on first use."""
    adapter = ADAPTERS.get(engine_id)
    if adapter is None and engine_id in _ADAPTER_FACTORIES:
        adapter = ADAPTERS.setdefault(engine_id, _ADAPTER_FACTORIES[engine_id]())
    return adapter


def adapter_for(engine: EngineInfo) -> SpeechEngine:
    """Return the serving adapter for ``engine``; raises LookupError when none is registered."""
    adapter = get_adapter(engine.id)
    if adapter is None:
        raise LookupError(f"No adapter registered for engine {engine.id!r}")
    return adapter


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

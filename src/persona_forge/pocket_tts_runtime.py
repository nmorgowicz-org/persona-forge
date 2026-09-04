"""Pocket TTS runtime adapter (kyutai-labs/pocket-tts).

Provides a thin, self-contained interface for loading Pocket TTS models, building
voice states from reference audio, and generating speech. Designed to plug into
the repo's existing hotswap/executor infrastructure without pulling in heavy Qwen3-TTS
or OpenVINO symbols at import time.

Public API:
    - load_pocket_tts_model(...)
    - build_default_voice_state(...)
    - get_pocket_tts_voice_state(...)
    - generate_pocket_tts(...)
    - generate_pocket_tts_stream(...)
    - warm_up_pocket_tts(...)
    - invalidate_voice_state(...)
    - unload_pocket_tts()
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import TYPE_CHECKING, Any
from pathlib import Path
from persona_forge import paths
from persona_forge.voice_library import VOICE_LIBRARY_DIR, get_voice
from persona_forge.pocket_artifact_resolver import (
    KYUTAI_WITHOUT_CLONING_REPO,
    KYUTAI_WITHOUT_CLONING_REVISION,
    PocketArtifactError,
    PocketArtifactResolver,
    VOICE_EMBEDDING_PINS,
)
from persona_forge.pocket_english_config import write_pocket_english_config

# Cache directory for persisted voice states (.safetensors)
STATE_CACHE_DIR = VOICE_LIBRARY_DIR / ".state_cache"
STATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_SAFE_CACHE_KEY_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _state_cache_path(resolved_id: str) -> Path:
    safe_stem = _SAFE_CACHE_KEY_RE.sub("_", resolved_id).strip("._")
    if not safe_stem or safe_stem != resolved_id:
        digest = hashlib.sha256(resolved_id.encode("utf-8")).hexdigest()[:16]
        safe_stem = f"{safe_stem[:80] or 'voice'}-{digest}"
    return STATE_CACHE_DIR / f"{safe_stem}.safetensors"

from pocket_tts import TTSModel

if TYPE_CHECKING:
    # Imported inside functions at runtime to avoid drag-in.
    import torch


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

pocket_tts_model: TTSModel | None = None
pocket_tts_default_voice_state: dict[str, Any] | None = None
pocket_tts_voice_state_cache: dict[str, Any] = {}

pocket_tts_cloning_available: bool = False
pocket_tts_cloning_status_message: str = ""

# Artifact provenance for the current (or most recent) load: engine, model
# source/revision/sha256, cloning status. Persists across idle-unload so /health
# keeps reporting the verified identity of the cached artifacts.
pocket_tts_provenance: dict[str, Any] = {}
pocket_tts_artifact_dir: str | None = None

# Extra audio frames to keep after the last speech frame (post-EOS tail control).
# 1 frame = 1/12.5 s of audio at 24 kHz (1920 samples), matching the Mimi codec's frame rate.
# Controlled by POCKET_TTS_FRAMES_AFTER_EOS env var (default 8).
pocket_tts_frames_after_eos: int = 8


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

# POCKET_TTS_MODEL_SOURCE -> allowed catalog source names for the cloning model.
# An empty tuple means "cache only, no network". Gated sources are additionally
# skipped when no HF token is configured (never probed unauthenticated).
_MODEL_SOURCE_ALLOWED: dict[str, tuple[str, ...]] = {
    "auto": ("lunahr", "kyutai"),
    "lunahr": ("lunahr",),
    "official": ("kyutai",),
    "local": (),
}

# Public read-only view of the valid modes (validated before any unload by
# model.apply_runtime_config so an invalid value never triggers a reload).
MODEL_SOURCE_MODES: tuple[str, ...] = tuple(_MODEL_SOURCE_ALLOWED)

# Modes that may degrade to the separately pinned non-cloning (built-in-only)
# model when the cloning model cannot be resolved.
_DEGRADABLE_MODES = ("auto", "official")


def _default_artifact_dir() -> Path:
    return paths.pocket_tts_artifact_dir()


def _load_via_resolved_artifacts(
    language: str,
    temp: float,
    sampler_decode_steps: int,
    eos_threshold: float,
    *,
    quantize: bool,
    noise_clamp: float | None,
    model_source: str,
    artifact_dir: str | Path | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve pinned Pocket-TTS artifacts and build the load kwargs + provenance.

    Returns ``(load_kwargs, provenance)`` where ``load_kwargs`` uses a
    project-owned local config file (no ``language=``). Raises RuntimeError for
    fail-closed mode failures; degraded loads (built-in-only model) are encoded
    in the returned provenance and applied post-load by the caller.
    """
    if model_source not in _MODEL_SOURCE_ALLOWED:
        raise ValueError(
            f"POCKET_TTS_MODEL_SOURCE must be one of {sorted(_MODEL_SOURCE_ALLOWED)}, "
            f"got {model_source!r}"
        )

    dir_path = Path(artifact_dir) if artifact_dir else _default_artifact_dir()
    resolver = PocketArtifactResolver(dir_path, token=os.environ.get("HF_TOKEN") or None)
    allowed = _MODEL_SOURCE_ALLOWED[model_source]

    # 1) Cloning model (preferred). In auto/official modes a failure degrades to
    #    the separately pinned non-cloning model (built-in voices only).
    cloning: Any = None
    cloning_error: PocketArtifactError | None = None
    try:
        cloning = resolver.resolve("model_cloning_english", allowed_sources=allowed)
    except PocketArtifactError as exc:
        cloning_error = exc

    degraded = False
    integrity_failure = False
    if cloning is None:
        integrity_failure = "integrity_mismatch" in (cloning_error.kinds() if cloning_error else [])
        if model_source not in _DEGRADABLE_MODES:
            detail = str(cloning_error) if cloning_error else "no sources allowed"
            raise RuntimeError(
                f"[pocket_tts] POCKET_TTS_MODEL_SOURCE={model_source!r} requires the "
                f"voice-cloning model, which could not be resolved ({detail}). "
                "Fix network/token access or set POCKET_TTS_MODEL_SOURCE=auto."
            ) from cloning_error
        print(f"[pocket_tts] Cloning model unavailable ({cloning_error}); degrading to built-in-only model.")
        try:
            noncloning = resolver.resolve("model_noncloning_english")
        except PocketArtifactError as exc:
            raise RuntimeError(
                "[pocket_tts] Neither the voice-cloning model nor the built-in-only "
                f"model could be resolved (cloning: {cloning_error}; "
                f"built-in-only: {exc}). Check network access or pre-populate "
                "POCKET_TTS_ARTIFACT_DIR and use POCKET_TTS_MODEL_SOURCE=local."
            ) from exc
        weights_path = str(noncloning.path)
        source_name = noncloning.source_name
        repo_id = noncloning.repo_id
        revision = noncloning.revision
        sha256 = noncloning.sha256
        degraded = True
    else:
        weights_path = str(cloning.path)
        source_name = cloning.source_name
        repo_id = cloning.repo_id
        revision = cloning.revision
        sha256 = cloning.sha256

    # 2) Tokenizer. In local mode this is required from the cache; elsewhere a
    #    failure falls back to the package's own public pinned download.
    tokenizer = None
    tokenizer_error: PocketArtifactError | None = None
    try:
        tokenizer = resolver.resolve("tokenizer_english", allowed_sources=allowed)
    except PocketArtifactError as exc:
        tokenizer_error = exc
    if tokenizer is None:
        if model_source == "local":
            raise RuntimeError(
                "[pocket_tts] POCKET_TTS_MODEL_SOURCE=local requires the tokenizer in the "
                f"artifact cache ({tokenizer_error})."
            ) from tokenizer_error
        print(
            f"[pocket_tts] Tokenizer not in artifact cache ({tokenizer_error}); "
            "falling back to the package's pinned public download."
        )
        tokenizer_path = (
            f"hf://{KYUTAI_WITHOUT_CLONING_REPO}/languages/english/tokenizer.model"
            f"@{KYUTAI_WITHOUT_CLONING_REVISION}"
        )
    else:
        tokenizer_path = str(tokenizer.path)

    # 3) Non-cloning fallback weights: prefer the verified local file, else the
    #    package's public pin (only reachable if the package's internal fallback
    #    ever triggers, which it should not once weights_path is a local file).
    noncloning_weights_path: str | None = None
    try:
        noncloning_weights_path = str(
            resolver.resolve(
                "model_noncloning_english",
                allowed_sources=[] if model_source == "local" else None,
            ).path
        )
    except PocketArtifactError:
        noncloning_weights_path = None

    provenance: dict[str, Any] = {
        "engine": "torch",
        "language": language,
        "model_source": source_name,
        "model_source_requested": model_source,
        "model_repo": repo_id,
        "model_revision": revision,
        "model_sha256": sha256,
        "model_verified": True,
        "model_file": Path(weights_path).name,
        "artifact_dir": str(dir_path),
        "cloning_available": not degraded,
        "cloning_status": (
            "integrity_error" if integrity_failure else ("degraded" if degraded else "ready")
        ),
        "message": (
            "Voice cloning weights failed integrity verification and were not loaded; "
            "running with built-in voices only. Delete the affected files in "
            "POCKET_TTS_ARTIFACT_DIR to re-download them."
            if integrity_failure
            else (
                "Voice cloning model could not be downloaded; running with built-in "
                "voices only. Set an HF_TOKEN (for the official kyutai source) or "
                "restore network access to enable cloning."
                if degraded
                else ""
            )
        ),
        "allowed_sources": list(allowed),
        # Built-in voice embeddings come from the public non-cloning repo; only
        # local mode is strictly network-free for them.
        "voice_allowed_sources": [] if model_source == "local" else None,
    }

    config_path = write_pocket_english_config(
        dir_path,
        weights_path=weights_path,
        noncloning_weights_path=noncloning_weights_path,
        tokenizer_path=tokenizer_path,
        provenance=f"{source_name} {repo_id}@{revision} sha256={sha256[:16]}…",
    )

    load_kwargs: dict[str, Any] = dict(
        config=str(config_path),
        temp=temp,
        sampler_decode_steps=sampler_decode_steps,
        eos_threshold=eos_threshold,
        quantize=quantize,
    )
    # noise_clamp defaults to TTSModel's own DEFAULT_NOISE_CLAMP when omitted; only override
    # it when the caller explicitly set one.
    if noise_clamp is not None:
        load_kwargs["noise_clamp"] = noise_clamp

    return load_kwargs, provenance


def load_pocket_tts_model(
    language: str,
    temp: float,
    sampler_decode_steps: int,
    eos_threshold: float,
    *,
    quantize: bool = False,
    noise_clamp: float | None = None,
    frames_after_eos: int | None = None,
    model_source: str = "auto",
    artifact_dir: str | Path | None = None,
) -> TTSModel:
    """Load (or reload) the Pocket TTS model into the global handle.

    Args:
        language: Pocket TTS language config (e.g. "english", "french_24l").
        temp: Sampling temperature.
        sampler_decode_steps: Number of LSD refinement steps per audio frame.
        eos_threshold: Logits-based EOS threshold.
        quantize: Whether to enable int8 quantization.
        noise_clamp: Optional noise magnitude cap.
        frames_after_eos: Optional extra frames to keep after EOS.
        model_source: Artifact source mode: "auto" (cache -> LunaHR -> official
            gated -> built-in-only degradation), "lunahr" (cache or LunaHR
            ungated), "official" (cache or authenticated kyutai), or "local"
            (verified cache only, network-free).
        artifact_dir: Persistent directory for verified artifacts; defaults to
            <MODEL_CACHE_CONTAINER_PATH>/pocket-tts.

    Returns:
        The loaded TTSModel instance.

    Raises:
        RuntimeError: If the model fails to load.
        ValueError: If ``model_source`` is not a known mode.
    """
    global pocket_tts_model, pocket_tts_provenance, pocket_tts_artifact_dir
    global pocket_tts_cloning_available, pocket_tts_cloning_status_message

    # Unload any previous instance first (hotswap-safe).
    unload_pocket_tts()

    print(
        f"[pocket_tts] Loading model — language={language!r}, "
        f"temp={temp}, sampler_decode_steps={sampler_decode_steps}, "
        f"eos_threshold={eos_threshold}, quantize={quantize}, noise_clamp={noise_clamp}, "
        f"model_source={model_source!r}"
    )

    degraded = False
    if language == "english":
        load_kwargs, provenance = _load_via_resolved_artifacts(
            language,
            temp,
            sampler_decode_steps,
            eos_threshold,
            quantize=quantize,
            noise_clamp=noise_clamp,
            model_source=model_source,
            artifact_dir=artifact_dir,
        )
        degraded = provenance["cloning_status"] in ("degraded", "integrity_error")
        pocket_tts_provenance = provenance
        pocket_tts_artifact_dir = provenance["artifact_dir"]
    else:
        load_kwargs: dict[str, Any] = dict(
            language=language,
            temp=temp,
            sampler_decode_steps=sampler_decode_steps,
            eos_threshold=eos_threshold,
            quantize=quantize,
        )
        if noise_clamp is not None:
            load_kwargs["noise_clamp"] = noise_clamp
        # Non-English languages keep the legacy package-config loading path
        # (no artifact resolution yet); provenance stays minimal.
        pocket_tts_provenance = {
            "engine": "torch",
            "language": language,
            "model_source": None,
            "model_source_requested": None,
            "model_repo": None,
            "model_revision": None,
            "model_sha256": None,
            "model_verified": False,
            "model_file": None,
            "artifact_dir": None,
            "cloning_available": None,
            "cloning_status": "unavailable",
            "message": "",
            "allowed_sources": None,
            "voice_allowed_sources": None,
        }
        pocket_tts_artifact_dir = None

    try:
        pocket_tts_model = TTSModel.load_model(**load_kwargs)
    except Exception as exc:
        pocket_tts_model = None
        raise RuntimeError(f"[pocket_tts] Failed to load TTSModel: {exc}") from exc

    if degraded and pocket_tts_model is not None:
        # The loaded weights are the built-in-only checkpoint: the package's
        # audio-prompt path raises VOICE_CLONING_UNSUPPORTED for it.
        pocket_tts_model.has_voice_cloning = False
        pocket_tts_cloning_available = False
        pocket_tts_cloning_status_message = pocket_tts_provenance["message"]
        print(
            f"[pocket_tts] Loaded in {pocket_tts_provenance['cloning_status']} mode: "
            "built-in voices only, voice cloning disabled."
        )

    # Store advanced knobs for use during generation.
    global pocket_tts_frames_after_eos
    if frames_after_eos is not None:
        pocket_tts_frames_after_eos = max(0, frames_after_eos)
        print(f"[pocket_tts] frames_after_eos set to {pocket_tts_frames_after_eos}")
    else:
        pocket_tts_frames_after_eos = 8
        print(f"[pocket_tts] frames_after_eos defaulted to {pocket_tts_frames_after_eos}")

    print("[pocket_tts] Model loaded and ready.")
    return pocket_tts_model


# ---------------------------------------------------------------------------
# Default voice state from REF_AUDIO
# ---------------------------------------------------------------------------

def build_default_voice_state(
    model: TTSModel,
    ref_audio_path: str | None,
) -> dict[str, Any] | None:
    """Build a Pocket TTS voice_state from the configured reference audio.

    This voice_state becomes the default when no voice_id is requested.

    Args:
        model: Loaded Pocket TTS TTSModel.
        ref_audio_path: Absolute path to a reference WAV.

    Returns:
        voice_state dict, or None if no valid ref_audio_path.
    """
    global pocket_tts_default_voice_state, pocket_tts_cloning_available, pocket_tts_cloning_status_message

    # A saved voice "Activated for API" persists across restarts: prefer it over REF_AUDIO so the
    # OpenAI endpoint keeps cloning from the user's chosen default instead of the mounted reference.
    active_id = get_active_default_voice_id()
    if active_id:
        active_wav = _library_reference_wav(active_id)
        if active_wav is not None:
            print(f"[pocket_tts] Using persisted active default voice {active_id!r}")
            ref_audio_path = str(active_wav)
        else:
            print(
                f"[pocket_tts] Persisted active default {active_id!r} has no reference.wav "
                "(voice likely deleted); clearing the stale default and falling back."
            )
            try:
                ACTIVE_DEFAULT_FILE.unlink(missing_ok=True)
            except OSError as exc:
                print(f"[pocket_tts] Could not clear stale active default file: {exc}")

    if not ref_audio_path:
        print("[pocket_tts] No REF_AUDIO_PATH configured; default voice_state = None.")
        pocket_tts_default_voice_state = None
        return None

    if not os.path.isfile(ref_audio_path):
        print(
            f"[pocket_tts] REF_AUDIO_PATH exists but is not a file: {ref_audio_path!r}; "
            "default voice_state = None."
        )
        pocket_tts_default_voice_state = None
        return None

    print(f"[pocket_tts] Building default voice_state from {ref_audio_path!r}")
    try:
        pocket_tts_default_voice_state = model.get_state_for_audio_prompt(ref_audio_path)
        pocket_tts_cloning_available = True
        pocket_tts_cloning_status_message = ""
        print("[pocket_tts] Default voice_state built successfully.")
        return pocket_tts_default_voice_state
    except Exception as exc:
        pocket_tts_default_voice_state = None
        pocket_tts_cloning_available = False
        msg = str(exc)
        if not (pocket_tts_provenance.get("message") or "").strip():
            if "We could not download the weights for the model with voice cloning" in msg:
                pocket_tts_cloning_status_message = (
                    "Voice cloning model unavailable. "
                    "Accept the terms at https://huggingface.co/kyutai/pocket-tts with the account "
                    "used for HF_TOKEN, then restart the container."
                )
            else:
                pocket_tts_cloning_status_message = f"Voice cloning unavailable: {msg}"

        print(
            f"[pocket_tts] Failed to build default voice_state: {exc}. "
            "Continuing without a default voice_state."
        )
        return None


# ---------------------------------------------------------------------------
# Runtime "Activate for API" default (hot-swap, persisted)
# ---------------------------------------------------------------------------

# Records which library voice the OpenAI endpoint should clone from when no voice is passed.
ACTIVE_DEFAULT_FILE = VOICE_LIBRARY_DIR / ".active_default"


def get_active_default_voice_id() -> str | None:
    """Return the persisted "Activated for API" voice_id, or None if unset."""
    try:
        vid = ACTIVE_DEFAULT_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return vid or None


def _library_reference_wav(voice_id: str) -> Path | None:
    meta = get_voice(voice_id)
    if meta is None:
        return None
    wav_path = Path(meta["wav_path"])
    if wav_path.is_symlink():
        wav_path = wav_path.resolve()
    return wav_path if wav_path.is_file() else None
    return wav_path if wav_path.is_file() else None


def set_default_voice_state_from_library(
    voice_id: str, model: TTSModel | None = None
) -> dict[str, Any]:
    """Hot-swap the API default voice_state to a saved library voice and persist the choice.

    Rebuilds the module-level ``pocket_tts_default_voice_state`` from the voice's reference.wav so
    subsequent no-voice requests (incl. the OpenAI endpoint) clone from it immediately -- no restart
    -- and writes the id to ACTIVE_DEFAULT_FILE so build_default_voice_state() restores it on boot.
    """
    global pocket_tts_default_voice_state, pocket_tts_cloning_available, pocket_tts_cloning_status_message
    model = model or pocket_tts_model
    if model is None:
        raise RuntimeError("[pocket_tts] Model is not loaded; cannot activate a voice.")
    wav_path = _library_reference_wav(voice_id)
    if wav_path is None:
        raise FileNotFoundError(f"No reference.wav for voice_id {voice_id!r}")
    pocket_tts_default_voice_state = model.get_state_for_audio_prompt(str(wav_path))
    pocket_tts_cloning_available = True
    pocket_tts_cloning_status_message = ""
    try:
        ACTIVE_DEFAULT_FILE.write_text(voice_id, encoding="utf-8")
    except OSError as exc:
        print(f"[pocket_tts] Could not persist active default {voice_id!r}: {exc}")
    print(f"[pocket_tts] Activated library voice {voice_id!r} as the API default.")
    return pocket_tts_default_voice_state


# ---------------------------------------------------------------------------
# Voice selection (default, library, or custom)
# ---------------------------------------------------------------------------

def _resolve_builtin_voice_artifact(name: str) -> Path | None:
    """Resolve a built-in voice name to a resolver-verified local .safetensors.

    Loading through a project-owned config changes the model's ``origin``, so the
    package's own predefined-voice lookup (which requires the origin to be inside
    the package's config directory) is unavailable. Instead, pinned built-in
    voices are resolved through the artifact resolver and passed to
    ``get_state_for_audio_prompt`` as an explicit .safetensors path (a branch that
    performs no origin check).

    Returns None when artifact resolution is not active (non-English loads) or
    the name has no pin, in which case the caller falls back to the package's
    own resolution.
    """
    artifact_dir = pocket_tts_artifact_dir
    if not artifact_dir:
        return None
    if name not in VOICE_EMBEDDING_PINS:
        return None
    resolver = PocketArtifactResolver(
        Path(artifact_dir), token=os.environ.get("HF_TOKEN") or None
    )
    try:
        result = resolver.resolve(
            f"voice_embed_english_{name}",
            allowed_sources=pocket_tts_provenance.get("voice_allowed_sources"),
        )
    except PocketArtifactError as exc:
        raise RuntimeError(
            f"[pocket_tts] Could not resolve built-in voice {name!r} from the "
            f"artifact cache: {exc}"
        ) from exc
    return result.path


def get_pocket_tts_voice_state(
    model: TTSModel,
    voice_id: str | None,
    default_voice_state: dict[str, Any] | None,
    ref_audio_path: str | None,
) -> dict[str, Any]:
    """Resolve the Pocket TTS voice_state for a generation request.

    Priority:
        1. If voice_id is None or empty -> use default_voice_state.
        2. If voice_id is in cache -> use cached state.
        3. If voice_id is a built-in preset or hf:// path -> load and cache.
        4. If voice_id matches a library voice -> load from its WAV, cache it.
        5. If none of the above -> raise RuntimeError.

    Args:
        model: Loaded Pocket TTS TTSModel.
        voice_id: Optional voice identifier (preset name, hf:// path, or library ID).
        default_voice_state: The default state derived from REF_AUDIO.
        ref_audio_path: Fallback reference audio path.

    Returns:
        A voice_state dict for use with generate_audio.

    Raises:
        RuntimeError: If no valid voice_state can be resolved.
    """
    # 1) No specific voice requested -> default.
    if not voice_id:
        if default_voice_state is not None:
            print("[pocket_tts] voice_state resolution: default (in-memory)")
            return default_voice_state
        # Last-ditch: try to rebuild from ref_audio_path.
        if ref_audio_path and os.path.isfile(ref_audio_path):
            print(
                f"[pocket_tts] No default_voice_state; falling back to ref_audio_path={ref_audio_path!r}"
            )
            print("[pocket_tts] voice_state resolution: default (rebuilt from ref_audio_path)")
            state = model.get_state_for_audio_prompt(ref_audio_path)
            global pocket_tts_default_voice_state
            pocket_tts_default_voice_state = state
            return state
        raise RuntimeError(
            "[pocket_tts] Voice cloning model not available (likely missing or gated HF token). "
            "Set an HF_TOKEN with access to kyutai/pocket-tts via Runtime → HF_TOKEN "
            "or in your startup config."
        )

    # Normalize "pocket:name" to "name"
    resolved_id = voice_id
    if voice_id.startswith("pocket:"):
        resolved_id = voice_id[7:]

    is_library_voice = resolved_id.startswith("vd_")
    library_meta = None
    if is_library_voice:
        from persona_forge import voice_library

        library_meta = voice_library.get_voice(resolved_id)
        if library_meta is None:
            raise ValueError(
                f"[pocket_tts] voice_id {resolved_id!r} not found in voice_library"
            )

    # 2) In-memory cache.
    cached = pocket_tts_voice_state_cache.get(resolved_id)
    if cached is not None:
        print(f"[pocket_tts] voice_state resolution: {resolved_id!r} (in-memory cache)")
        return cached

    # 3) Disk cache (.safetensors).
    cache_path = _state_cache_path(resolved_id)
    cache_is_current = True
    if cache_path.is_file() and library_meta is not None:
        dependency_mtimes = []
        wav_path = library_meta.get("wav_path")
        if wav_path and os.path.isfile(wav_path):
            dependency_mtimes.append(os.path.getmtime(wav_path))
        meta_path = VOICE_LIBRARY_DIR / resolved_id / "meta.json"
        if meta_path.is_file():
            dependency_mtimes.append(meta_path.stat().st_mtime)
        if dependency_mtimes and cache_path.stat().st_mtime < max(dependency_mtimes):
            cache_is_current = False

    if cache_path.is_file() and cache_is_current:
        try:
            print(f"[pocket_tts] Loading cached voice state from disk: {cache_path.name}")
            state = model.import_model_state(str(cache_path))
            pocket_tts_voice_state_cache[resolved_id] = state
            print(f"[pocket_tts] voice_state resolution: {resolved_id!r} (disk cache import)")
            return state
        except Exception as exc:
            print(f"[pocket_tts] Failed to load cached state {cache_path.name}: {exc}. Falling back.")

    # 3) Try built-in preset or hf:// path.
    # If it doesn't look like a library ID (starts with 'vd_'), try treating it as a preset/path.
    if not resolved_id.startswith("vd_"):
        # With a project-owned config the package can't honor predefined names
        # (origin check), so pinned built-in voices are resolved to verified
        # local .safetensors first; unpinned names and hf:// paths pass through.
        state_input = resolved_id
        local_voice_file = _resolve_builtin_voice_artifact(resolved_id)
        if local_voice_file is not None:
            state_input = str(local_voice_file)
        try:
            print(f"[pocket_tts] Attempting to load built-in voice: {resolved_id!r}")
            state = model.get_state_for_audio_prompt(state_input)
            pocket_tts_voice_state_cache[resolved_id] = state
            model.export_model_state(state, str(cache_path))
            print(f"[pocket_tts] voice_state resolution: {resolved_id!r} (built-in preset, rebuilt)")
            return state
        except Exception as exc:
            # Not a valid preset/path, fall through to library lookup.
            print(f"[pocket_tts] {resolved_id!r} is not a built-in preset: {exc}")

    # 4) Look up in voice_library.
    if library_meta is None:
        from persona_forge import voice_library

        library_meta = voice_library.get_voice(resolved_id)
    if library_meta is None:
        raise ValueError(
            f"[pocket_tts] voice_id {resolved_id!r} not found in voice_library"
        )

    wav_path = library_meta.get("wav_path")
    if not wav_path or not os.path.isfile(wav_path):
        raise RuntimeError(
            f"[pocket_tts] voice_id={resolved_id!r} exists but wav_path is invalid: "
            f"{wav_path!r}"
        )

    state = model.get_state_for_audio_prompt(wav_path)
    pocket_tts_voice_state_cache[resolved_id] = state
    model.export_model_state(state, str(cache_path))
    print(f"[pocket_tts] voice_state resolution: {resolved_id!r} (library, rebuilt from wav)")
    return state


def invalidate_voice_state(voice_id: str) -> None:
    """Drop a cached voice_state so the next request rebuilds it from the voice library.

    Must be called whenever a voice's reference audio changes or is deleted on disk (see
    voice_library.delete_voice) — the cache in get_pocket_tts_voice_state is keyed by
    voice_id only and never re-checks the library once built, so a deleted voice would
    otherwise stay generatable from the stale cached state.
    """
    pocket_tts_voice_state_cache.pop(voice_id, None)


# ---------------------------------------------------------------------------
# Audio generation
# ---------------------------------------------------------------------------

def _trim_post_eos_tail(audio: torch.Tensor, sr: int, frames_after_eos: int) -> torch.Tensor:
    """Trim trailing dead air after the last speech frame, respecting frames_after_eos.

    Uses a per-frame energy heuristic:
    - 1 frame = 1/12.5 s, matching the Mimi codec's actual frame rate.
    - Finds the last frame whose energy is above a floor that combines an absolute RMS
      threshold with a gentle *trailing-window* relative term (median of recent above-floor
      frames), rather than a fraction of the whole clip's peak. A single loud early sentence
      must not be able to gate a quiet closing sentence.
    - Keeps up to frames_after_eos extra frames after that point.
    - On any error, returns the original audio unchanged.
    """
    try:
        if frames_after_eos < 0 or audio.numel() == 0:
            return audio

        # Work on CPU float
        x = audio.float().cpu().flatten()
        frame_samples = max(1, round(sr / 12.5))
        if len(x) <= frame_samples:
            return audio

        # Per-frame energy (L2 norm) via unfold
        frames = x.unfold(0, frame_samples, frame_samples)
        energies = (frames * frames).sum(dim=1).sqrt()

        # Absolute floor: speech decay lives well above this; room tone/codec noise below it.
        abs_floor = 1e-3 * (frame_samples**0.5)
        above_floor = energies[energies >= abs_floor]
        # Trailing-window relative term: median of the frames that already clear the floor,
        # scaled down, so a loud sentence elsewhere in the clip can't mask a quiet ending.
        rel_floor = float(above_floor.median()) * 0.1 if above_floor.numel() else 0.0
        thresh = max(abs_floor, rel_floor)

        # Last speech frame index (energy above threshold)
        speech_mask = (energies >= thresh).nonzero(as_tuple=True)[0]
        if speech_mask.numel() == 0:
            return audio
        last_speech_frame = int(speech_mask[-1])

        # Effective endpoint: allow extra frames_after_eos beyond last speech frame
        limit_frame = last_speech_frame + frames_after_eos
        limit_sample = min(len(x), (limit_frame + 1) * frame_samples)

        if limit_sample < len(x):
            return x[:limit_sample]
        return audio
    except Exception:
        # Defensive: never break generation on trimming issues
        return audio


def generate_pocket_tts(
    model: TTSModel,
    voice_state: dict[str, Any],
    text: str,
) -> tuple[Any, int]:
    """Generate speech audio from text using the loaded Pocket TTS model.

    Args:
        model: Loaded Pocket TTS TTSModel.
        voice_state: Voice state dict (from get_state_for_audio_prompt).
        text: Input text to synthesize.

    Returns:
        (audio_tensor, sample_rate)
            - audio_tensor: 1D torch.Tensor (PCM float, 24 kHz).
            - sample_rate: int (24000).
    """
    import torch

    if not model:
        raise RuntimeError("[pocket_tts] Model is not loaded; call load_pocket_tts_model first.")
    if not voice_state:
        raise RuntimeError("[pocket_tts] voice_state is missing; cannot generate.")
    if not text:
        raise ValueError("[pocket_tts] Input text is empty.")

    audio = model.generate_audio(voice_state, text)

    # Normalize to expected shape.
    if isinstance(audio, torch.Tensor):
        if audio.dim() == 1:
            audio = audio  # already mono 1D
        else:
            audio = audio.squeeze()
    else:
        audio = torch.tensor(audio, dtype=torch.float32)

    sample_rate = getattr(model, "sample_rate", 24000)

    # Apply post-EOS tail trim if configured
    audio = _trim_post_eos_tail(audio, int(sample_rate), pocket_tts_frames_after_eos)

    return audio, int(sample_rate)


def generate_pocket_tts_stream(
    model: TTSModel,
    voice_state: dict[str, Any],
    text: str,
) -> Any:
    """Generate speech audio incrementally, yielding float32 PCM chunks.

    Used for HTTP streaming endpoints (Hermes TTS streaming integration).
    Each yielded chunk is a 1D array of float32 samples at 24 kHz.

    Note: Post-EOS tail trimming is skipped in streaming mode since it requires
    seeing the complete audio first. Streaming trades latency for quality.

    Args:
        model: Loaded Pocket TTS TTSModel.
        voice_state: Voice state dict.
        text: Input text to synthesize.

    Yields:
        1D float32 arrays (PCM samples).
    """
    import numpy as np

    if not model:
        raise RuntimeError("[pocket_tts] Model is not loaded; call load_pocket_tts_model first.")
    if not voice_state:
        raise RuntimeError("[pocket_tts] voice_state is missing; cannot generate.")
    if not text:
        raise ValueError("[pocket_tts] Input text is empty.")

    for audio_chunk in model.generate_audio_stream(voice_state, text):
        arr = np.asarray(audio_chunk, dtype=np.float32)
        if arr.ndim > 1:
            arr = arr.squeeze()
        yield arr


def warm_up_pocket_tts(model: TTSModel, voice_state: dict[str, Any] | None) -> None:
    """Run one throwaway generation right after load to pay the first-call cost here.

    The first real inference through a freshly loaded TTSModel appears to carry a
    one-time cost (lazy kernel/graph setup, first-run allocation spike) that has
    shown up as a silent, untraceable crash (no Python exception, no traceback) on
    the very first user-triggered generate call after every model load/reload —
    never on subsequent calls against the same loaded model. Running a trivial
    generation here, synchronously, on the same serialized executor thread that
    loads the model, means that cost (and any resulting failure) is paid and logged
    at load time instead of silently swallowing a user's first request.

    No-ops quietly if there's no voice_state to warm up with (e.g. cloning
    unavailable) — the warm-up isn't the source of truth for readiness, just a
    best-effort mitigation.
    """
    if model is None or not voice_state:
        return
    import time as _time

    t0 = _time.monotonic()
    try:
        print("[pocket_tts] Warming up model with a throwaway generation...", flush=True)
        generate_pocket_tts(model, voice_state, "Warming up.")
        print(f"[pocket_tts] Warm-up complete ({_time.monotonic() - t0:.1f}s).", flush=True)
    except Exception as exc:
        # Surface loudly but don't block boot -- a warm-up failure here is strictly
        # more useful (visible, attributable to load) than the same failure hitting
        # a real user's first request silently.
        import traceback

        print(
            f"[pocket_tts] Warm-up generation failed after {_time.monotonic() - t0:.1f}s: {exc}",
            flush=True,
        )
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def unload_pocket_tts() -> None:
    """Unload Pocket TTS model and clear all cached voice states."""
    global pocket_tts_model, pocket_tts_default_voice_state, pocket_tts_voice_state_cache

    if pocket_tts_model is None and not pocket_tts_voice_state_cache:
        return

    print("[pocket_tts] Unloading Pocket TTS model and clearing cache...")

    pocket_tts_model = None
    pocket_tts_default_voice_state = None
    pocket_tts_voice_state_cache.clear()

    print("[pocket_tts] Unloaded.")

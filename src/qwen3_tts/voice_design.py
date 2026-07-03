"""VoiceDesign checkpoint model-swap manager.

See docs/plans/PLAN_voice_design.md §3/§4.2. VoiceDesign is a separate HF checkpoint from
Base — this service holds exactly one checkpoint in memory at a time (model.py's
module-level globals assume it), so using VoiceDesign means: unload Base, load VoiceDesign,
run generate_voice_design(). All of that must run serialized inside model.executor (the
service's single inference thread), same as every other model operation, so no in-flight
/generate call can race the swap.

Unlike an earlier version of this module, VoiceDesign is deliberately *not* swapped back to
Base when the request finishes — iterating on a design (several generate calls in a row) is
the common case, and reloading Base after every single one just to immediately unload it
again on the next call wastes the swap cost. Base is reloaded lazily, on demand, by
model._ensure_base_loaded() the next time /generate or /v1/audio/speech actually needs it
(or when the Persona Forge UI explicitly swaps engines, or on idle timeout).
"""

from __future__ import annotations

import time
from typing import Any

from qwen3_tts import model

# ~130-150 words/min speech rate heuristic (PLAN_voice_design.md §8.4). VoiceDesign's IR
# capacity (§4.1) is larger to leave headroom for testing; this is the API-level cap on the
# *stored* reference sample, kept intentionally short because shorter, clearer reference
# samples clone better.
MAX_SAMPLE_TEXT_SECONDS = 15.0
_WORDS_PER_SECOND = 140.0 / 60.0
MAX_SAMPLE_TEXT_WORDS = int(MAX_SAMPLE_TEXT_SECONDS * _WORDS_PER_SECOND)

_swap_in_progress = False


def swap_in_progress() -> bool:
    return _swap_in_progress


def validate_sample_text(sample_text: str) -> None:
    """Raise ValueError if sample_text exceeds the ~15s speech heuristic."""
    word_count = len(sample_text.split())
    if word_count > MAX_SAMPLE_TEXT_WORDS:
        raise ValueError(
            "Sample text is too long; keep it under 15 seconds of speech "
            f"(~{MAX_SAMPLE_TEXT_WORDS} words max, got {word_count})."
        )


def run_voice_design_request(
    description: str, sample_text: str, language: str, seed: int | None = None
) -> tuple[Any, int, int]:
    """Swap to VoiceDesign and synthesize the sample. Leaves VoiceDesign loaded on success —
    see this module's docstring for why. On failure, the checkpoint is left unloaded rather
    than force-restoring Base; the next real /generate or /v1/audio/speech call reloads Base
    on demand via model._ensure_base_loaded(), so an error here can't leave the service
    permanently stuck without a usable model.

    Must run inside model.executor — callers submit this via
    ``model.executor.submit(run_voice_design_request, ...)``, never call it directly
    off-thread.

    A concrete seed is always resolved and applied (random when the caller doesn't supply
    one) and returned to the caller, so every saved voice has a reproducible, inspectable
    seed rather than depending on whatever ambient RNG state happened to exist — required
    for the tune/tweak workflow (PLAN_voice_design.md §8.3) to mean anything: re-rolling a
    voice needs a real new random draw, and locking onto a good take needs its exact seed.
    """
    global _swap_in_progress
    _swap_in_progress = True
    model._touch_last_request()
    resolved_seed = model.resolve_seed(seed)
    t0 = time.monotonic()
    try:
        print("[voice_design] swapping to VoiceDesign checkpoint...", flush=True)
        model.unload_foreign_models()
        model.force_unload()
        model.load_model(model.VOICE_DESIGN_PROFILE)

        if getattr(model.model.model, "tts_model_type", None) != "voice_design":
            raise RuntimeError(
                "Loaded checkpoint is not a VoiceDesign checkpoint "
                f"(tts_model_type={getattr(model.model.model, 'tts_model_type', None)!r}); "
                "check VOICE_DESIGN_MODEL_REPO / VOICE_DESIGN_MODEL_SIZE."
            )

        model._apply_optional_seed(resolved_seed)
        print(
            f"[voice_design] generating sample (lang={language!r}, seed={resolved_seed})...",
            flush=True,
        )
        wavs, sr = model.model.generate_voice_design(
            text=sample_text,
            language=language,
            instruct=description,
        )
        wav = model._trim_silence(wavs[0], sr)
        elapsed = time.monotonic() - t0
        print(f"[voice_design] sample generated in {elapsed:.1f}s", flush=True)
        return wav, sr, resolved_seed
    except Exception:
        print("[voice_design] request failed; unloading VoiceDesign checkpoint...", flush=True)
        model.force_unload()
        raise
    finally:
        _swap_in_progress = False
        print(
            f"[voice_design] done, total elapsed={time.monotonic() - t0:.1f}s",
            flush=True,
        )

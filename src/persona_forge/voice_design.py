"""VoiceDesign checkpoint model-swap manager.

See docs/architecture/VOICE_DESIGN.md §3/§4.2. VoiceDesign is a separate HF checkpoint from
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

from persona_forge import model

# Mirrors omnivoice_engine._progress (GET /omnivoice/progress) — nick's feedback, 2026-07-03:
# "you did not add that [progress/ETA] in for the persona-forge voice design". This checkpoint's
# generate_voice_design() is a single blocking autoregressive call (no per-candidate loop to
# report mid-flight progress on, unlike OmniVoice's diffusion-style per-step model), so
# "progress" here is phase (loading the checkpoint vs. generating) plus an ETA derived from a
# running average of past request durations, rather than a true completed/total counter.
_progress: dict[str, Any] = {
    "phase": "idle",
    "avg_seconds": None,
    "estimated_remaining_seconds": None,
}
_phase_started_at: float | None = None
_completed_requests = 0


def get_progress() -> dict[str, Any]:
    snapshot = dict(_progress)
    if snapshot["phase"] == "generating" and snapshot["avg_seconds"] is not None and _phase_started_at is not None:
        elapsed = time.monotonic() - _phase_started_at
        snapshot["estimated_remaining_seconds"] = max(0.0, snapshot["avg_seconds"] - elapsed)
    return snapshot

# ~130-150 words/min speech rate heuristic (docs/architecture/VOICE_DESIGN.md §8.4). VoiceDesign's IR
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
    for the tune/tweak workflow (docs/architecture/VOICE_DESIGN.md §8.3) to mean anything: re-rolling a
    voice needs a real new random draw, and locking onto a good take needs its exact seed.
    """
    global _swap_in_progress, _phase_started_at, _completed_requests
    _swap_in_progress = True
    model._touch_last_request()
    resolved_seed = model.resolve_seed(seed)
    t0 = time.monotonic()
    _progress.update(phase="loading", estimated_remaining_seconds=_progress["avg_seconds"])
    _phase_started_at = t0
    try:
        print("[voice_design] swapping to VoiceDesign checkpoint...", flush=True)
        model.unload_foreign_models()
        model.force_unload()
        model.load_model(model.VOICE_DESIGN_PROFILE)

        # pocket_tts has no separate VoiceDesign checkpoint (pocket_tts_runtime.load_pocket_tts_model()
        # always loads the same checkpoint-agnostic TTSModel, which has no nested .model to inspect
        # and no generate_voice_design), so /voice_design rejects that backend up front with 501;
        # this identity check applies to the qwen_tts/pytorch/openvino backends, where
        # model.model is a Qwen3TTSModel wrapper exposing the loaded HF checkpoint as model.model.model.
        if model.TTS_BACKEND != "pocket_tts" and getattr(model.model.model, "tts_model_type", None) != "voice_design":
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
        _progress["phase"] = "generating"
        _phase_started_at = time.monotonic()
        wavs, sr = model.model.generate_voice_design(
            text=sample_text,
            language=language,
            instruct=description,
        )
        wav = model._trim_silence(wavs[0], sr)
        elapsed = time.monotonic() - t0
        print(f"[voice_design] sample generated in {elapsed:.1f}s", flush=True)

        _completed_requests += 1
        prev_avg = _progress["avg_seconds"]
        _progress["avg_seconds"] = (
            elapsed if prev_avg is None else prev_avg + (elapsed - prev_avg) / _completed_requests
        )
        return wav, sr, resolved_seed
    except Exception:
        print("[voice_design] request failed; unloading VoiceDesign checkpoint...", flush=True)
        model.force_unload()
        raise
    finally:
        _swap_in_progress = False
        _progress["phase"] = "idle"
        _progress["estimated_remaining_seconds"] = None
        _phase_started_at = None
        print(
            f"[voice_design] done, total elapsed={time.monotonic() - t0:.1f}s",
            flush=True,
        )

"""VoiceDesign checkpoint model-swap manager.

See docs/plans/PLAN_voice_design.md §3/§4.2. VoiceDesign is a separate HF checkpoint from
the always-resident Base model — this service holds exactly one checkpoint in memory at a
time (model.py's module-level globals assume it), so using VoiceDesign means: unload Base,
load VoiceDesign, run generate_voice_design() once, then reload Base. All of that must run
serialized inside model.executor (the service's single inference thread), same as every
other model operation, so no in-flight /generate call can race the swap.
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
    description: str, sample_text: str, language: str
) -> tuple[Any, int]:
    """Swap to VoiceDesign, synthesize the sample, and swap back to Base.

    Must run inside model.executor — callers submit this via
    ``model.executor.submit(run_voice_design_request, ...)``, never call it directly
    off-thread. Always attempts to restore the Base model on the way out (``finally``),
    even on failure, so a VoiceDesign error can't leave the service permanently stuck
    without a loaded model — see PLAN_voice_design.md §4.3 step 5 for why this fail-safe
    matters more than usual here (this is the only code path that unloads the
    otherwise-always-resident Base model).
    """
    global _swap_in_progress
    _swap_in_progress = True
    t0 = time.monotonic()
    try:
        print("[voice_design] swapping to VoiceDesign checkpoint...", flush=True)
        model.force_unload()
        model.load_model(model.VOICE_DESIGN_PROFILE)

        if getattr(model.model.model, "tts_model_type", None) != "voice_design":
            raise RuntimeError(
                "Loaded checkpoint is not a VoiceDesign checkpoint "
                f"(tts_model_type={getattr(model.model.model, 'tts_model_type', None)!r}); "
                "check VOICE_DESIGN_MODEL_REPO / VOICE_DESIGN_MODEL_SIZE."
            )

        print(f"[voice_design] generating sample (lang={language!r})...", flush=True)
        wavs, sr = model.model.generate_voice_design(
            text=sample_text,
            language=language,
            instruct=description,
        )
        wav = model._trim_silence(wavs[0], sr)
        elapsed = time.monotonic() - t0
        print(f"[voice_design] sample generated in {elapsed:.1f}s", flush=True)
        return wav, sr
    finally:
        print("[voice_design] swapping back to Base checkpoint...", flush=True)
        model.force_unload()
        model.load_model(model.BASE_PROFILE)
        _swap_in_progress = False
        print(
            f"[voice_design] swap complete, total elapsed={time.monotonic() - t0:.1f}s",
            flush=True,
        )

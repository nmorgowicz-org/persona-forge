"""OmniVoice checkpoint model-swap manager (Persona Forge accent-design engine).

See docs/plans/PLAN_persona_forge_studio.md §1. OmniVoice reuses the same one-model-at-a-time
swap discipline VoiceDesign already established (qwen3_tts.voice_design): unload Base, load
OmniVoice, run a whole *job* (every reference segment, every candidate take) in one swap
window. All of that must run serialized inside model.executor (the service's single
inference thread), same as every other model operation, so no in-flight /generate call can
race the swap.

Unlike VoiceDesign, OmniVoice is a bespoke third-party checkpoint (k2-fsa/OmniVoice) that
never goes through model.load_model()/model.active_profile — it isn't wired through
OVTalkerRuntime, so its lifecycle is entirely local to this module. It registers itself with
model.register_foreign_engine() so idle-unload and the Base-priority swap-back in
model._ensure_base_loaded() (used by /generate and /v1/audio/speech) both know how to unload
it. On success the OmniVoice checkpoint is left loaded — iterating on takes for the same
accent is the common case — and is only unloaded when: the user explicitly swaps engines
(another run_voice_design_request or run_omnivoice_job call unloads it via
model.force_unload()/model.unload_foreign_models()), the idle-unload timeout fires, or a
/generate or /v1/audio/speech request needs Base back.

Unlike voice_design.run_voice_design_request, a job here produces multiple candidate takes
per segment (the reliability findings in [[voicedesign-accent-investigation]] mean single-shot
generation isn't good enough to skip auditioning) and never asks OmniVoice to generate more
than one short sentence per call — long multi-sentence single-shot generation was found to be
unreliable (0/5 to 0/6 clean across two test batches); the caller is expected to pass already
sentence-segmented text and stitch the chosen takes afterward via audio_post.stitch_segments.
"""

from __future__ import annotations

import gc
import time
from typing import Any

from qwen3_tts import model
from qwen3_tts.audio_post import stitch_segments

_swap_in_progress = False
_omnivoice_model = None

# OmniVoice's own fixed output rate (k2-fsa/OmniVoice), independent of this repo's Base
# model's vocoder rate.
OMNIVOICE_SAMPLE_RATE = 24000


def swap_in_progress() -> bool:
    return _swap_in_progress


def omnivoice_loaded() -> bool:
    return _omnivoice_model is not None


def _malloc_trim() -> None:
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def _unload_omnivoice() -> None:
    global _omnivoice_model
    if _omnivoice_model is None:
        return
    _omnivoice_model = None
    gc.collect()
    gc.collect()
    _malloc_trim()
    print("[omnivoice] checkpoint unloaded.", flush=True)


model.register_foreign_engine(omnivoice_loaded, _unload_omnivoice)


def run_omnivoice_job(
    segments: list[str],
    instruct: str,
    language: str = "english",
    candidates_per_segment: int = 3,
    seed: int | None = None,
) -> list[list[tuple[Any, int]]]:
    """Swap to OmniVoice and generate every segment x candidate. Leaves OmniVoice loaded on
    success (see this module's docstring for why). On failure, the checkpoint is unloaded
    fully rather than restoring Base; the next real /generate or /v1/audio/speech call
    reloads Base on demand via model._ensure_base_loaded().

    Must run inside model.executor — callers submit this via
    ``model.executor.submit(run_omnivoice_job, ...)``, never call it directly off-thread.

    Returns a segments x candidates_per_segment list of (wav, sample_rate) tuples.

    No manual seed by default: seeding a whole multi-segment/multi-candidate batch defeats
    the point of auditioning independent draws, and stitching validated in
    [[voicedesign-accent-investigation]] was done with no manual seed. ``seed`` exists for
    reproducing/debugging a specific prior job, not as the default UX path.
    """
    global _swap_in_progress, _omnivoice_model
    if not segments:
        raise ValueError("segments must be non-empty")
    if candidates_per_segment < 1:
        raise ValueError("candidates_per_segment must be >= 1")
    if not instruct.strip():
        raise ValueError("instruct must be non-empty")

    _swap_in_progress = True
    model._touch_last_request()
    t0 = time.monotonic()
    try:
        print("[omnivoice] swapping out Base, loading OmniVoice...", flush=True)
        model.force_unload()

        import torch
        from omnivoice import OmniVoice

        if seed is not None:
            model._apply_optional_seed(seed)

        _omnivoice_model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", dtype=torch.float32)

        results: list[list[tuple[Any, int]]] = []
        for seg_idx, text in enumerate(segments):
            candidates: list[tuple[Any, int]] = []
            for cand_idx in range(candidates_per_segment):
                print(
                    f"[omnivoice] segment {seg_idx + 1}/{len(segments)}, "
                    f"candidate {cand_idx + 1}/{candidates_per_segment}...",
                    flush=True,
                )
                audio = _omnivoice_model.generate(
                    text=text, instruct=instruct, language=language
                )[0]
                wav = model._trim_silence(audio, OMNIVOICE_SAMPLE_RATE)
                candidates.append((wav, OMNIVOICE_SAMPLE_RATE))
            results.append(candidates)
        elapsed = time.monotonic() - t0
        print(f"[omnivoice] job complete in {elapsed:.1f}s, staying loaded", flush=True)
        return results
    except Exception:
        print("[omnivoice] job failed; unloading OmniVoice checkpoint...", flush=True)
        _unload_omnivoice()
        raise
    finally:
        _swap_in_progress = False
        print(
            f"[omnivoice] done, total elapsed={time.monotonic() - t0:.1f}s",
            flush=True,
        )


def stitch_selected(selected: list[tuple[Any, int]]) -> tuple[Any, int]:
    """Combine one chosen candidate per segment into a final reference clip.

    Pure numpy post-processing (audio_post.stitch_segments) — does not touch the model,
    model.executor, or the swap machinery, so it can run outside a job/swap window.
    """
    if not selected:
        raise ValueError("selected must be non-empty")
    sample_rates = {sr for _, sr in selected}
    if len(sample_rates) != 1:
        raise ValueError(f"mixed sample rates in selection: {sample_rates}")
    sr = selected[0][1]
    final = stitch_segments([wav for wav, _ in selected], sr)
    return final, sr

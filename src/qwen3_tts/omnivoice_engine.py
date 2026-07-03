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
from qwen3_tts.asr_check import has_speech
from qwen3_tts.audio_post import analyze_take, stitch_segments

# Real bounds from the installed `omnivoice` package's OmniVoiceGenerationConfig
# (num_step default 32, guidance_scale/duration/speed unset by default) — see
# docs/plans/PLAN_omnivoice_integration.md and the 2026-07-03 upstream-docs review. Clamped
# here rather than trusting the frontend, since these reach a third-party model call.
MIN_NUM_STEP = 1
MAX_NUM_STEP = 64
MIN_SPEED = 0.25
MAX_SPEED = 4.0

# A take flagged by audio_post.analyze_take (dead air / drone / SFX — nick's report,
# 2026-07-03: "just dead air/drones/sfx") gets exactly one silent retry before being
# returned as-is; OmniVoice failures are known to be non-deterministic per-draw (see module
# docstring), so a second independent draw has a real chance of landing clean, but retrying
# indefinitely would turn one bad line into an unbounded generation loop.
MAX_ATTEMPTS_PER_CANDIDATE = 2

_swap_in_progress = False
_omnivoice_model = None

# OmniVoice's own fixed output rate (k2-fsa/OmniVoice), independent of this repo's Base
# model's vocoder rate.
OMNIVOICE_SAMPLE_RATE = 24000

# Polled by GET /omnivoice/progress (app.py) so the frontend can render a real progress bar
# with an ETA instead of an indeterminate banner — nick's feedback 2026-07-03: the prior
# top-of-page banner gave no sense of what was happening or how long it'd take. "loading"
# covers the OmniVoice checkpoint load (can take a while on first use), "generating" covers
# the per-candidate loop; ``avg_seconds`` is a running average over completed candidates in
# *this* job, used to estimate remaining time for the candidates left.
_progress: dict[str, Any] = {
    "phase": "idle",
    "total": 0,
    "completed": 0,
    "current_segment_index": 0,
    "current_candidate_index": 0,
    "segment_count": 0,
    "candidates_per_segment": 0,
    "avg_seconds": None,
    "estimated_remaining_seconds": None,
}


def swap_in_progress() -> bool:
    return _swap_in_progress


def omnivoice_loaded() -> bool:
    return _omnivoice_model is not None


def get_progress() -> dict[str, Any]:
    return dict(_progress)


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
    num_step: int | None = None,
    duration: float | None = None,
    speed: float | None = None,
) -> list[list[tuple[Any, int, bool, str]]]:
    """Swap to OmniVoice and generate every segment x candidate. Leaves OmniVoice loaded on
    success (see this module's docstring for why). On failure, the checkpoint is unloaded
    fully rather than restoring Base; the next real /generate or /v1/audio/speech call
    reloads Base on demand via model._ensure_base_loaded().

    Must run inside model.executor — callers submit this via
    ``model.executor.submit(run_omnivoice_job, ...)``, never call it directly off-thread.

    Returns a segments x candidates_per_segment list of (wav, sample_rate, flagged,
    flag_reason) tuples. ``flagged`` comes from audio_post.analyze_take's best-effort
    dead-air/drone heuristic; a flagged candidate is retried once in-loop before being
    returned (see MAX_ATTEMPTS_PER_CANDIDATE), so a flagged result already survived a retry.

    ``num_step``/``duration``/``speed`` map straight onto the real ``OmniVoice.generate()``
    kwargs (confirmed against the installed omnivoice==0.1.5 package, 2026-07-03 upstream
    review) — omitted (None) ones are left out of the call entirely so the model's own
    defaults apply rather than this repo silently overriding them.

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
    total = len(segments) * candidates_per_segment
    _progress.update(
        phase="loading",
        total=total,
        completed=0,
        current_segment_index=0,
        current_candidate_index=0,
        segment_count=len(segments),
        candidates_per_segment=candidates_per_segment,
        avg_seconds=None,
        estimated_remaining_seconds=None,
    )
    t0 = time.monotonic()
    try:
        print("[omnivoice] swapping out Base, loading OmniVoice...", flush=True)
        model.force_unload()

        import torch
        from omnivoice import OmniVoice

        if seed is not None:
            model._apply_optional_seed(seed)

        _omnivoice_model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", dtype=torch.float32)
        _progress["phase"] = "generating"

        gen_kwargs: dict[str, Any] = {}
        if num_step is not None:
            gen_kwargs["num_step"] = max(MIN_NUM_STEP, min(MAX_NUM_STEP, int(num_step)))
        if duration is not None:
            gen_kwargs["duration"] = float(duration)
        if speed is not None:
            gen_kwargs["speed"] = max(MIN_SPEED, min(MAX_SPEED, float(speed)))

        results: list[list[tuple[Any, int, bool, str]]] = []
        for seg_idx, text in enumerate(segments):
            candidates: list[tuple[Any, int, bool, str]] = []
            for cand_idx in range(candidates_per_segment):
                _progress["current_segment_index"] = seg_idx
                _progress["current_candidate_index"] = cand_idx
                print(
                    f"[omnivoice] segment {seg_idx + 1}/{len(segments)}, "
                    f"candidate {cand_idx + 1}/{candidates_per_segment}...",
                    flush=True,
                )
                cand_t0 = time.monotonic()
                wav = None
                flagged, reason = True, "empty"
                for attempt in range(1, MAX_ATTEMPTS_PER_CANDIDATE + 1):
                    audio = _omnivoice_model.generate(
                        text=text, instruct=instruct, language=language, **gen_kwargs
                    )[0]
                    wav = model._trim_silence(audio, OMNIVOICE_SAMPLE_RATE)
                    flagged, reason = analyze_take(wav, OMNIVOICE_SAMPLE_RATE)
                    if not flagged:
                        # analyze_take's spectral heuristic is a fast proxy and can miss
                        # non-tonal dead-air (broadband hiss, babble, clipped garbage) — run
                        # the more expensive but more direct Whisper no-speech gate only on
                        # takes that already passed the cheap check.
                        speech_found, _transcript = has_speech(wav, OMNIVOICE_SAMPLE_RATE)
                        if not speech_found:
                            flagged, reason = True, "no-speech-detected"
                        else:
                            break
                    if attempt < MAX_ATTEMPTS_PER_CANDIDATE:
                        print(
                            f"[omnivoice] candidate flagged ({reason}), retrying "
                            f"(attempt {attempt + 1}/{MAX_ATTEMPTS_PER_CANDIDATE})...",
                            flush=True,
                        )
                cand_elapsed = time.monotonic() - cand_t0
                candidates.append((wav, OMNIVOICE_SAMPLE_RATE, flagged, reason))

                completed = _progress["completed"] + 1
                prev_avg = _progress["avg_seconds"]
                avg = cand_elapsed if prev_avg is None else prev_avg + (cand_elapsed - prev_avg) / completed
                remaining = total - completed
                _progress.update(
                    completed=completed,
                    avg_seconds=avg,
                    estimated_remaining_seconds=remaining * avg,
                )
                print(
                    f"[omnivoice] candidate done in {cand_elapsed:.1f}s "
                    f"({completed}/{total}, ~{remaining * avg:.0f}s remaining)",
                    flush=True,
                )
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
        _progress["phase"] = "idle"
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

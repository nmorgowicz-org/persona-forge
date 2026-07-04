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
import logging
import time
from typing import Any

from qwen3_tts import model
from qwen3_tts.asr_check import has_speech, compute_transcript_match_score, _MIN_MATCH_SCORE_SHORT, _MIN_MATCH_SCORE_LONG, _MAX_WORDS_SHORT, _MAX_SOFT_MATCH_SCORE, _SOFT_REJECT_IF_LOGPROB_BELOW
from qwen3_tts.audio_post import analyze_take, stitch_segments

logger = logging.getLogger(__name__)

# Real bounds from the installed `omnivoice` package's OmniVoiceGenerationConfig
# (num_step default 32, guidance_scale/duration/speed unset by default) — see
# docs/plans/PLAN_omnivoice_integration.md and the 2026-07-03 upstream-docs review. Clamped
# here rather than trusting the frontend, since these reach a third-party model call.
MIN_NUM_STEP = 16
MAX_NUM_STEP = 32
MIN_SPEED = 0.5
MAX_SPEED = 2.5
MIN_GUIDANCE = 1.5
MAX_GUIDANCE = 3.0

# Temperature schedule for diverse candidates (when diverse_candidates=True)
DIVERSE_TEMPS = [5.0, 7.0, 10.0]

# Soft guard for segment length
WARNING_CHARS = 120
WARNING_WORDS = 15

# A take flagged by audio_post.analyze_take (dead air / drone / SFX — nick's report,
# 2026-07-03: "just dead air/drones/sfx") gets exactly one silent retry before being
# returned as-is; OmniVoice failures are known to be non-deterministic per-draw (see module
# docstring), so a second independent draw has a real chance of landing clean, but retrying
# indefinitely would turn one bad line into an unbounded generation loop.
MAX_ATTEMPTS_PER_CANDIDATE = 3

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
    durations: list[float | None] | None = None,
    speed: float | None = None,
    guidance_scale: float | None = None,
    diverse_candidates: bool = False,
    postprocess_output: bool | None = None,
    on_segment_complete=None,
) -> list[list[tuple[Any, int, bool, str, str, float | None]]]:
    """Swap to OmniVoice and generate every segment x candidate. Leaves OmniVoice loaded on
    success (see this module's docstring for why). On failure, the checkpoint is unloaded
    fully rather than restoring Base; the next real /generate or /v1/audio/speech call
    reloads Base on demand via model._ensure_base_loaded().

    Must run inside model.executor — callers submit this via
    ``model.executor.submit(run_omnivoice_job, ...)``, never call it directly off-thread.

    Returns a segments x candidates_per_segment list of (wav, sample_rate, flagged,
    flag_reason, whisper_transcript) tuples. ``flagged`` comes from audio_post.analyze_take's
    best-effort dead-air/drone heuristic; a flagged candidate is retried once in-loop before
    being returned (see MAX_ATTEMPTS_PER_CANDIDATE), so a flagged result already survived
    a retry. ``whisper_transcript`` is the transcript produced by faster-whisper when it
    ran (empty string if no speech detected or Whisper was skipped).

    ``num_step``/``durations``/``speed``/``guidance_scale`` map onto the real
    ``OmniVoice.generate()`` kwargs (confirmed against omnivoice pinned at commit
    398b6113 — past 0.1.5 on PyPI, see Dockerfile note — 2026-07-04 upstream review).

    - ``durations`` is per-segment: a list aligned with ``segments`` where each entry is
      either None (auto) or an explicit target duration in seconds (e.g. 2.4). This maps
      onto real token-level length control inside OmniVoice.generate() (target_tokens =
      duration * frame_rate), so it's not a post-hoc trim — the model itself is asked to
      decode that many frames.
    - ``postprocess_output`` controls OmniVoice’s own silence-trimming / normalization:
      - True: apply post-processing (may shorten audio).
      - False: disable (closer to exact duration, may keep trailing silence).
      - None: use model default.
      When a segment has an explicit duration, we force postprocess_output=False for
      that segment so timing is not silently altered.
    - We do NOT run our own silence-trim on top of OmniVoice's output (see history: an
      earlier version called model._trim_silence() unconditionally here, which silently
      undid postprocess_output=False and defeated duration targeting). Silence handling
      for this engine is entirely OmniVoice's own — postprocess_output plus
      pad_duration/fade_duration (also forced to 0.0/near-zero for duration-targeted
      segments, since OmniVoice unconditionally pads +0.1s per side otherwise).

    When ``diverse_candidates=True``, position_temperature cycles through [5.0, 7.0, 10.0]
    across candidates to produce prosodically different takes; when False, the first
    candidate uses 5.0 and the rest use 7.0. class_temperature is always 0.0 (greedy).

    If ``on_segment_complete`` is provided and callable, it is invoked after each segment's
    candidates are ready:
        on_segment_complete(segment_index, text, candidates_list)
    This is used to stream segment results into job state for the streaming audition API.

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

    # English-first note
    lang = language.strip().lower()
    if lang != "english":
        logger.warning(
            "OmniVoice: language='%s' — best quality is English; consider using a "
            "reference audio for other languages.",
            language,
        )

    # Soft segment length guard (warning only)
    for idx, seg in enumerate(segments):
        words = len(seg.split())
        chars = len(seg)
        if chars > WARNING_CHARS or words > WARNING_WORDS:
            logger.warning(
                "OmniVoice: segment[%d] length high (%d chars, %d words) — "
                "output may be unreliable",
                idx,
                chars,
                words,
            )

    # Clamp guidance_scale
    if guidance_scale is not None:
        guidance_scale = float(guidance_scale)
        if guidance_scale < MIN_GUIDANCE or guidance_scale > MAX_GUIDANCE:
            logger.warning(
                "OmniVoice: guidance_scale %s out of range, clamping to [%s, %s]",
                guidance_scale,
                MIN_GUIDANCE,
                MAX_GUIDANCE,
            )
        guidance_scale = float(max(MIN_GUIDANCE, min(MAX_GUIDANCE, guidance_scale)))

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

        # float32 for stable CPU performance (float16 can be slower on many CPUs)
        _omnivoice_model = OmniVoice.from_pretrained(
            "k2-fsa/OmniVoice",
            dtype=torch.float32,
        )
        _progress["phase"] = "generating"

        # Base gen_kwargs shared by all candidates
        gen_kwargs: dict[str, Any] = {}
        gen_kwargs["denoise"] = True
        if num_step is not None:
            gen_kwargs["num_step"] = max(MIN_NUM_STEP, min(MAX_NUM_STEP, int(num_step)))
        if speed is not None:
            gen_kwargs["speed"] = max(MIN_SPEED, min(MAX_SPEED, float(speed)))
        if guidance_scale is not None:
            gen_kwargs["guidance_scale"] = guidance_scale

        # Normalize durations: list aligned with segments; None means “auto”.
        durations_list: list[float | None] = durations or []
        if len(durations_list) != len(segments):
            durations_list = [None] * len(segments)

        results: list[list[tuple[Any, int, bool, str, str, float | None]]] = []
        for seg_idx, text in enumerate(segments):
            candidates: list[tuple[Any, int, bool, str, str, float | None]] = []
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

                # Temperature diversity:
                # - diverse_candidates=True: cycle [5.0, 7.0, 10.0] across candidates
                # - else: first candidate 5.0, rest 7.0
                if diverse_candidates:
                    pos_temp = DIVERSE_TEMPS[cand_idx % len(DIVERSE_TEMPS)]
                else:
                    pos_temp = 5.0 if cand_idx == 0 else 7.0

                cand_gen = dict(gen_kwargs)
                cand_gen["class_temperature"] = 0.0
                cand_gen["position_temperature"] = pos_temp

                # Per-segment duration + postprocess_output behavior:
                seg_duration = durations_list[seg_idx] if seg_idx < len(durations_list) else None
                if seg_duration is not None:
                    seg_duration = float(seg_duration)
                    cand_gen["duration"] = seg_duration
                    # When user specifies an explicit duration, disable post-processing
                    # and OmniVoice's own edge padding to avoid silent shortening/lengthening.
                    # A small fade is kept (not 0) so segment edges don't click when stitched.
                    cand_gen["postprocess_output"] = False
                    cand_gen["pad_duration"] = 0.0
                    cand_gen["fade_duration"] = 0.02
                elif postprocess_output is not None:
                    cand_gen["postprocess_output"] = bool(postprocess_output)

                last_transcript = ""
                last_match_score: float | None = None
                for attempt in range(1, MAX_ATTEMPTS_PER_CANDIDATE + 1):
                    audio = _omnivoice_model.generate(
                        text=text,
                        instruct=instruct,
                        language=language,
                        **cand_gen,
                    )[0]
                    # Silence handling is left entirely to OmniVoice's own
                    # postprocess_output/pad_duration/fade_duration above — we used to
                    # also run model._trim_silence() here, which ignored
                    # postprocess_output=False and defeated duration targeting.
                    wav = audio
                    cand_flagged, cand_reason = analyze_take(wav, OMNIVOICE_SAMPLE_RATE)
                    last_transcript = ""
                    last_logprob: float | None = None
                    last_match_score: float | None = None

                    if not cand_flagged:
                        speech_found, last_transcript, last_logprob = has_speech(
                            wav, OMNIVOICE_SAMPLE_RATE
                        )
                        if not speech_found:
                            cand_flagged, cand_reason = True, "no-speech-detected"
                        else:
                            # Compute fuzzy transcript match score
                            last_match_score = compute_transcript_match_score(
                                text,
                                last_transcript,
                            )

                            # Choose threshold based on reference word count
                            ref_words = len(text.split())
                            min_score = (
                                _MIN_MATCH_SCORE_SHORT
                                if ref_words <= _MAX_WORDS_SHORT
                                else _MIN_MATCH_SCORE_LONG
                            )

                            # Decide if this candidate is OK based on match + logprob
                            ok = True
                            if last_match_score < 0.6:
                                # Clearly wrong
                                ok = False
                            elif last_match_score < min_score:
                                # Borderline: only accept if confidence is decent
                                if (
                                    last_logprob is not None
                                    and last_logprob >= _SOFT_REJECT_IF_LOGPROB_BELOW
                                ):
                                    # Confident enough to accept borderline
                                    ok = True
                                else:
                                    # Low confidence + poor match → reject
                                    ok = False
                            else:
                                # Good match
                                ok = True

                            if not ok:
                                cand_flagged, cand_reason = True, "poor-transcript-match"
                            else:
                                # Valid candidate — override any prior flagged state
                                # from a previous attempt so we never carry "dubious" into
                                # the final candidate on a successful retry.
                                cand_flagged = False
                                cand_reason = "ok"

                    flagged, reason = cand_flagged, cand_reason

                    if not flagged:
                        break

                    if attempt < MAX_ATTEMPTS_PER_CANDIDATE:
                        print(
                            f"[omnivoice] candidate flagged ({reason}), retrying "
                            f"(attempt {attempt + 1}/{MAX_ATTEMPTS_PER_CANDIDATE})...",
                            flush=True,
                        )
                cand_elapsed = time.monotonic() - cand_t0
                candidates.append(
                    (wav, OMNIVOICE_SAMPLE_RATE, flagged, reason, last_transcript or "", last_match_score)
                )

                completed = _progress["completed"] + 1
                prev_avg = _progress["avg_seconds"]
                avg = (
                    cand_elapsed
                    if prev_avg is None
                    else prev_avg
                    + (cand_elapsed - prev_avg) / completed
                )
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
            if on_segment_complete is not None and callable(on_segment_complete):
                on_segment_complete(seg_idx, text, candidates)
            results.append(candidates)
        elapsed = time.monotonic() - t0
        print(
            f"[omnivoice] job complete in {elapsed:.1f}s, staying loaded",
            flush=True,
        )
        return results
    except Exception:
        print(
            "[omnivoice] job failed; unloading OmniVoice checkpoint...",
            flush=True,
        )
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

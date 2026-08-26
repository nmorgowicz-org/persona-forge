# Persona Forge Studio — OmniVoice engine, audio pipeline, and UI redesign

> Audience: a fresh AI coding agent with zero prior context.
> This document describes what was built. For the research and validation
> that motivated it, see `docs/archive/omnivoice/omnivoice_integration.md`.

## 0. Rationale and high-level design

Persona Forge Studio integrated OmniVoice into the existing Qwen3-TTS container as a
secondary, on-demand model used for accent-specific reference clip generation via a
"generate-N-and-pick, stitch multi-segment" workflow.

Three core design decisions were made and are treated as final:

- In-container, not a sibling service:
  - Reused the existing load/unload/swap infrastructure (`model.py`'s
    `force_unload()` / `load_model()`) already proven by VoiceDesign's
    Base↔VoiceDesign swap.
  - No new Docker service; no second persistent model.

- On-demand swap, not resident:
  - Base is unloaded, OmniVoice is loaded, the job runs, then Base is restored.
  - Never resident alongside Base; strict one-model-at-a-time.

- Full redesign for affected UI surfaces:
  - The Persona Forge UI was implemented as a VST-style studio surface
    (waveforms, meters, progress, motion) instead of a simple form/panel.

Runtime alignment:
- Existing pins (torch 2.12.1 / torchaudio 2.11.0 / transformers 5.12.1) matched
  OmniVoice's requirements.
- The only new runtime dependency introduced was `pydub`; heavier extras
  (gradio, webdataset, etc.) were not pulled into the inference path.

## 1. Backend: OmniVoice engine module

### 1.1 Core module: `src/persona_forge/omnivoice_engine.py`

Modeled on `voice_design.py` with a swap guard and an executor-based entry point,
but adapted for multi-segment, multi-candidate cherry-pick workflows.

Key aspects:

- One-time swap per job:
  - A single `run_omnivoice_job` call:
    - Swaps Base out.
    - Loads OmniVoice.
    - Generates all segments × candidates.
    - Unloads OmniVoice.
    - Restores Base.
  - Model-load cost is paid once per job, not per candidate.

- Signature:
  - `run_omnivoice_job(segments, instruct, candidates_per_segment=3, seed=None)`
    returns segments × candidates of (wav, sample_rate), with Base always
    restored on exit.

- Isolation from OpenVINO model global:
  - A module-level `_omnivoice_model` is used (plain nn.Module) instead of
    reusing `model.py`'s `model` global, which is dedicated to the OV runtime.
  - Teardown is explicit:
    - Set `_omnivoice_model = None`, run GC twice, call `malloc_trim(0)`,
      then reload Base.
  - This avoids over-abstracting a two-caller pattern.

- Seeding:
  - Default: no manual global seed (batch seeding empirically degraded
    diversity and quality).
  - Optional `seed` parameter is accepted for reproducibility and debugging,
    not used in the normal UX flow.

### 1.2 API routes in `app.py`

Two new routes were introduced, separate from `/voice_design`, to keep
request/response shapes clean.

- `POST /omnivoice/audition`:
  - Input:
    - `segments`: list[str]
    - `instruct`: str
    - `candidates_per_segment`: int (default 3)
  - Behavior:
    - Calls `omnivoice_engine.run_omnivoice_job` via
      `model.executor.submit(...)` (same concurrency pattern as VoiceDesign).
  - Output:
    - JSON with segments, each containing candidates with:
      - `candidate_id`, `audio_base64`, `sample_rate`.
    - No stitching or saving; this is the "cherry-pick options" step.

- `POST /omnivoice/stitch`:
  - Input:
    - `selections`: list[candidate_id], one per segment, referencing the
      latest `/audition` response.
  - Behavior:
    - Uses a short-lived in-memory cache keyed by `candidate_id`:
      - Cleared on each new `/audition`.
      - Suitable for a single-user local tool.
    - Runs the audio post-processing pipeline (§2) on selected segments.
    - Pure numpy-based processing; no model; runs inline without
      `model.executor`.
  - Output:
    - The final stitched WAV, fed into the existing
      `voice_library.save_voice` path like VoiceDesign outputs.

Concurrency:
- Both routes reuse the `swap_in_progress()` guard pattern and coordinate
  with VoiceDesign to avoid overlapping swaps.

## 2. Audio post-processing pipeline

A deterministic, no-model pipeline was implemented to solve the "all over the
place" loudness and consistency problem in stitched clips.

It runs fully in numpy (with existing runtime deps like librosa/soundfile as
needed), in the order below. Order is intentional; collapsing steps into only
"normalize the final output" was explicitly avoided.

- Per-segment:
  - Applied mild dynamic-range compression (soft-knee, speech-tuned, low ratio)
    before normalization to smooth internal dynamics.
  - Then normalized each segment to a common target level (RMS-based) so that
    cherry-picked candidates are fairly comparable.

- Cross-segment:
  - Used a short equal-power crossfade (80–150 ms) between segments instead of
    the earlier flat silence gaps.
  - Added minimal silence padding only where natural pacing required it.

- Final stitched clip:
  - Applied peak limiting to avoid clipping from crossfade overlap.
  - Applied a final loudness normalization to a fixed target (e.g., -16 to -18 dB
    RMS) appropriate for reference speech clips.

The pipeline is synchronous and fast enough to execute inside `/omnivoice/stitch`
without a job queue.

## 3. Frontend: "VST-level" UI redesign

The affected Persona Forge surfaces were redesigned with a studio-grade aesthetic
and behavior: waveforms, meters, live-ish progress, and spring-based motion, while
keeping the existing Tailwind + shadcn primitives for layout and chrome.

### 3.1 Design principles

- Visual, not just playable:
  - Waveforms, meters, and progress are primary; `<audio>`-only is not enough.
- High information density with progressive disclosure:
  - Studio tool feel; not a wizard or linear form.
- Motion as information:
  - Spring-physics animations for state changes, no flat linear transitions.
- Dark-first, consistent with existing theme.

### 3.2 New frontend dependencies

- `wavesurfer.js`:
  - For per-segment and stitched-clip waveforms, zoom, scrubbing,
    and region/marker support (used for crossfade regions).
- `framer-motion`:
  - Spring-based layout transitions, candidate appearance animations,
    panel expansion, and micro-interactions.
- Web Audio API:
  - Used directly for live metering and small spectrum readouts during playback.
- Tailwind + shadcn:
  - Retained as the structural base (buttons, dialogs, layout) while the new
    dependencies focus on audio-specific surfaces.

### 3.3 New components

- `EngineSelector`:
  - Top-level choice between:
    - "Qwen VoiceDesign": free-form, fast, no accent guarantee.
    - "Persona Forge Engine": OmniVoice-backed, accent-bank-driven,
      higher accent fidelity, slower/multi-step.
  - Presented like choosing an instrument/preset category, not a hidden dropdown.

- `AccentBank`:
  - Replaced raw text/sample input for OmniVoice.
  - Provides per-accent sets of curated segment sentences, each with an audition
    action before committing to a full job.
  - Implemented as a card grid/rack; uses pre-baked reference audio (committed
    to the repo) instead of live generation to avoid cost and flakiness.

- `SegmentRack`:
  - Core Persona Forge workspace:
    - One row/card per sentence segment.
    - Shows `candidates_per_segment` waveform thumbnails via wavesurfer.
    - Marks one candidate as selected (cherry-pick UX).
    - Includes per-segment "regenerate" to re-roll candidates for that segment
      without restarting the whole job.
    - Integrates with `GenerationProgress` for live-ish status.

- `StitchPreview`:
  - Displays a single combined waveform after stitching (post §2 pipeline).
  - Highlights crossfade regions.
  - Provides playhead scrub and a final loudness/peak readout (VST-style meters).

- `GenerationProgress`:
  - Replaced bare spinners with a dynamic progress surface:
    - Animated "building" waveform.
    - Per-segment status chips (pending → generating → ready).
    - Communicates that long-running jobs are advancing.

### 3.4 Motion and interaction

- Spring-based transitions for layout changes:
  - Candidate cards, status changes, panel expand/collapse.
- Stable layouts:
  - `framer-motion` layout/AnimatePresence used for candidate list updates
    to avoid janky pop-ins.
- Waveform animations:
  - New candidates animate in (draw-on style) instead of appearing statically.
- Meters:
  - Sweep to values rather than snapping; reinforce a "real-time" feel.
- Accessibility:
  - Respects `prefers-reduced-motion`.

### 3.5 Intentional non-goals

- Not a full multi-track DAW timeline:
  - Segments are sequential, not freely overlapping.
- No user-tunable compressor/limiter parameters in v1:
  - Shipped with fixed, speech-optimized defaults.
- No wholesale redesign of every settings page:
  - Focus stayed on the Persona Forge generation surface;
    other pages can adopt the motion/visual language later.

## 4. Implementation timeline (brief)

Original plan specified this order, which was largely followed:

1) `omnivoice_engine.py` swap manager and `/omnivoice/audition` + `/omnivoice/stitch`
   routes, validated via curl/Postman.
2) Audio post-processing pipeline as a standalone, unit-testable module.
3) AccentBank data curation (based on AU sentences from OmniVoice integration plan).
4) Frontend: EngineSelector + AccentBank.
5) SegmentRack, StitchPreview, GenerationProgress and the full "VST-level" surface.

## 5. Decisions made

Treated as final and reflected in the implementation:

- Compressor:
  - Hand-rolled in numpy (soft-knee envelope follower + gain computer) instead of
    adding `pedalboard` as a runtime dependency.
- `candidate_id` cache:
  - Simple in-memory dict, single-user, no persistence.
  - Cleared on the next `/omnivoice/audition`.
- AccentBank preview audio:
  - Curated and repo-committed (derived from prior OmniVoice validation artifacts)
    instead of generated at build time.
- CC-BY-NC license:
  - Deferred, not treated as a blocker; revisitable when a commercial offering
    becomes concrete.

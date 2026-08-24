# OmniVoice Reference

What it is:

- A secondary accent-fidelity engine integrated into this container for Persona Forge Studio.
- Used for generating accent-specific reference clips (e.g., Australian, British), not for general text-to-speech.
- Based on `k2-fsa/OmniVoice`, a 0.6B-parameter diffusion-style TTS model built on a Qwen3-0.6B-Base backbone.

What it is NOT:

- Not a drop-in replacement for the Base voice-clone model.
- Not wired through OpenVINO or the `model.load_model()` path.
- Not a general-purpose voice design tool: it has a very narrow, closed instruct vocabulary.
- Not guaranteed deterministic: each draw is non-deterministic by design.

## License and constraints

- Code: Apache 2.0.
- Weights: CC-BY-NC (non-commercial) because training data includes Emilia, which carries non-commercial terms.
- Prohibits: "unauthorized voice cloning, voice impersonation, fraud, scams, other illegal or unethical activities."
- You must consciously accept this before using in any commercial context. The integration does not silently waive this.

## How it loads

- Loaded via the installed `omnivoice` Python package (pinned to a PyPI release in the
  Dockerfile — `omnivoice==0.2.1`; the `pad_duration`/`fade_duration` knobs we rely on
  shipped in 0.2.0).
- Always loaded as `float32`; float16 showed ~50% broken-output rate in testing.
- Loaded with:
  - `OmniVoice.from_pretrained("k2-fsa/OmniVoice", dtype=torch.float32)`
  - No `device_map` argument — it's moved with `.to("cpu")` / `.to("mps")` / `.to("cuda")` after construction.
- Runs on CPU with no code changes; no OpenVINO export exists or is planned.
- Fixed output rate: 24 kHz.

## How it swaps with Base

Only one model may be loaded at a time.

- On every OmniVoice job:
  - Base is unloaded (`model.force_unload()`).
  - OmniVoice is loaded into `_omnivoice_model` (a private module-level var, not `model.model`).
  - The entire job (all segments × candidates) runs.
  - OmniVoice is left loaded (iterating on takes is the common case).
- OmniVoice is unloaded when:
  - Another engine is swapped in (VoiceDesign, or another OmniVoice job).
  - A `/generate` or `/v1/audio/speech` request calls `model._ensure_base_loaded()`.
  - The idle-unload timeout fires (`IDLE_UNLOAD_SECONDS`).
- The swap is serialized on `model.executor` (the single inference thread) — no concurrent generation with Base.

## How it coexists (one-model-at-a-time)

- Registers itself via `model.register_foreign_engine(omnivoice_loaded, _unload_omnivoice)` so:
  - The idle watcher can unload it.
  - `_ensure_base_loaded()` knows how to remove it before loading Base.
- Does not modify `model.model`, `model.active_profile`, or OVTalkerRuntime.
- Health endpoint exposes:
  - `omnivoice_loaded: true/false`
  - `swap_in_progress: true/false`

## End-to-end workflow

1. Audition request

   - `POST /omnivoice/audition`:
     - `segments`: list of individual sentence strings (short, 1-2 sentences each).
     - `instruct`: comma-separated tags (e.g., `"female, young adult, moderate pitch, australian accent"`).
     - `candidates_per_segment`: how many takes per segment (default 3).
     - Optional: `seed`, `num_step`, `durations` (per-segment), `speed`, `guidance_scale`, `diverse_candidates`, `postprocess_output`, `min_match_score`.
   - If model is ready: job starts immediately.
   - If not ready: job is queued until model loads.

2. Progress polling

   - `GET /omnivoice/audition/progress?job_id=<id>`:
     - Reports `status` (queued / running / completed / failed), segments completed, ETA, per-segment candidates.
   - `GET /omnivoice/progress`:
     - Low-level per-job progress: phase (idle/loading/generating), candidate counters, avg seconds, estimated remaining.

3. Select takes

   - Each candidate is returned with:
     - `candidate_id`, `audio_base64`, `flagged`, `flag_reason`, `whisper_transcript`, `match_score`.
   - Per-segment cherry-picking: user selects one candidate per segment.
   - Candidates live in an in-memory cache until:
     - Persisted via `POST /omnivoice/segments` ("keep this take").
     - Cleared on the next `/omnivoice/audition`.

4. Persist segments (optional but recommended)

   - `POST /omnivoice/segments`:
     - Inputs: `candidate_id`, `text`, `instruct`, `accent_id`.
     - Saves the selected take as a durable segment: `seg_<id>` under `/segments`, with full metadata (language, seed, parameters, etc.).
   - Segments are reusable across sessions and stitch plans.

5. Stitch (optional)

   - `POST /omnivoice/stitch`:
     - Combines selected clips from:
       - segment_ids (durable segments),
       - candidate_ids (ephemeral, current-session only),
       - or stitch_plan (structured plan with clips, trims, fades, crossfades, compression, padding, loudness targets).
     - Pure numpy DSP; no model call; no swap.

6. Save to voice library

   - `POST /omnivoice/save`:
     - Takes selected clips (via stitch_plan or selections/segment_ids), stitches them, and saves as a voice in the voice library (`/voices`).
     - Voice is then usable via `voice_id` in `/generate` and `/v1/audio/speech`.

## Key behavior

Non-deterministic per draw:

- Each generation is an independent draw.
- Multiple candidates are generated so the user can pick the cleanest / best-sounding take.

ASR gating:

- After audio_post.analyze_take passes, faster-whisper (`tiny.en`, int8, CPU) checks whether the output actually contains speech and whether it matches the input text.
- If no speech is detected or the transcript doesn't match, the candidate is flagged.
- Thresholds are tunable via ASR_ env vars (see ENV_REFERENCE.md).

Broken-take detection:

- `analyze_take()` in `audio_post.py`:
  - Checks for near-silent clips.
  - Checks for tonal/drone-like artifacts via spectral flatness.
- A flagged candidate is retried up to 3 times. If it stays flagged, it is returned as-is.

Duration control:

- Per-segment `durations` parameter: maps onto token-level length control inside OmniVoice's own generate (target_tokens = duration * frame_rate), not a post-hoc trim.
- When duration is specified, postprocess_output is forced to `False` and pad/fade durations are reduced to preserve timing.
- No external silence trim is applied to OmniVoice output — it has its own postprocess_output.

Known accent strengths:

- Australian: confirmed real and effective.
- British: sounded good in limited checks; not exhaustively validated.
- Indian: inconclusive in testing.
- Best quality is for English; for other languages, OmniVoice's own docs warn about reduced stability.

Known limits:

- Long single-shot generation (multi-sentence, 10-15s+ in one call) fails frequently. Use short segments and stitch.
- The instruct vocabulary is strict: gender, age, pitch, style (only "whisper"), and specific accent labels. No warmth/sweetness/breathiness tags.
- Category order in `instruct` is load-bearing: gender, age, pitch, style, accent last.
- Certain token patterns (e.g., "G'day!" as an opener) can trigger truncation.

## "Don't do this" list

- Don't treat OmniVoice as a direct clone replacement.
  - It doesn't understand arbitrary reference audio. Use it for accent design, not identity.
- Don't change float32 to float16.
  - float16 caused ~50% broken-output; float32 is required for stability.
- Don't bypass the swap protocol.
  - OmniVoice must run inside model.executor, with Base unloaded, via `run_omnivoice_job()`.
  - Never load OmniVoice in parallel with Base or with another OmniVoice job.
- Don't ask it for one giant generation for long scripts.
  - It will fail. Segment your text, generate per-segment, stitch later.
- Don't ignore the license.
  - CC-BY-NC weights. Any commercial use must be reviewed, not assumed OK.
- Don't invent instruct tags.
  - OmniVoice raises ValueError on unknown tags. Only use documented categories.

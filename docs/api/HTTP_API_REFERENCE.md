# Persona Forge — HTTP API Reference

Single-source reference for all HTTP endpoints exposed by Persona Forge.

- All JSON endpoints expect `application/json`.
- All audio endpoints that return files set the appropriate `Content-Type` (`audio/mpeg` for MP3, `audio/wav` for WAV).
- All endpoints are relative to the service root (default: `http://host:8318`).
- The service is single-worker (Gunicorn `-w 1`); model access is serialized via a single-thread executor.

---

## Core TTS

### POST /generate

- Purpose: Primary text-to-speech endpoint (voice-cloning).

Request body (JSON):

- `text` (string, required) — text to synthesize.
- `language` (string, optional, default "English") — language label.
- `voice_id` (string, optional) — ID of a voice from the voice library to clone.
- `instruct` (string, optional) — optional instruction/steering prompt.
- `response_format` (string, optional, default "mp3") — "mp3" or "wav".
- `seed` (integer, optional) — RNG seed for reproducibility; if present must be an integer.
- `prosody_repair` (boolean, optional, default false) — batch/offline output repair using
  the input text. The server-enforced deadline defaults to five seconds.

Response:

- 200:
  - Body: raw audio bytes (MP3 or WAV, based on `response_format`).
  - Header: `X-Seed`: the resolved integer seed used.
  - Header: `X-Prosody-Repair-Outcome`: `not_requested`, `repaired`, `unnecessary`,
    `failed`, or `budget_fallback`.
  - Repair requests also report budget, duration, and repaired-boundary count through
    `X-Prosody-Repair-Budget-Seconds`, `X-Prosody-Repair-Duration-Seconds`, and
    `X-Prosody-Repair-Boundaries`.
- 503:
  - If model not loaded or a runtime reconfiguration is in progress.
- 400:
  - If JSON invalid, `text` missing, unsupported `response_format`, or `seed` not integer.
- 500:
  - If an inference error occurs.

Important notes:

- This endpoint does not fail-fast when a VoiceDesign/OmniVoice swap is in progress; it
  queues behind it in the same executor (FIFO) and runs once Base is reloaded. This can add
  ~90–120s of latency during a swap (longer on cold OpenVINO kernel cache).
- Timeout on the executor is 480 seconds.

### POST /v1/audio/speech

- Purpose: OpenAI-compatible TTS endpoint (same underlying generation as `/generate`).

Request body (JSON):

- `input` or `text` (string, required) — text to synthesize (`input` preferred).
- `language` (string, optional, default "English") — language label.
- `voice_id` (string, optional) — ID of a voice to clone.
- `instruct` (string, optional) — instruction/steering prompt.
- `response_format` (string, optional, default "mp3") — "mp3" or "wav".
- `seed` (integer, optional) — RNG seed.
- `prosody_repair` (boolean, optional, default false) — same bounded complete-file repair
  contract as `/generate`.

Response:

- 200:
  - Body: raw audio bytes (MP3 or WAV).
  - Header: `X-Seed`: resolved integer seed.
  - Headers: the same `X-Prosody-Repair-*` outcome metadata as `/generate`.
- 503:
  - If model not loaded or a runtime reconfiguration is in progress.
- 400:
  - If JSON invalid, input text missing, unsupported `response_format`, or invalid `seed`.
- 500:
  - If an inference error occurs.

Error format:

- Always returns an OpenAI-style JSON: `{ "error": { "message": "...", "type": "...", "code": null } }`.

Important notes:

- Same FIFO queueing behind swaps as `/generate`.

### POST /generate/with_metrics and POST /generate/async

- Both accept the same boolean `prosody_repair` opt-in as `/generate`.
- `/generate/with_metrics` returns a `prosody_repair` object alongside metrics.
- `/generate/async` returns the requested/pending state immediately; `GET /generate/progress`
  reports the final structured outcome, and `GET /generate/job/<job_id>/audio` carries the
  same `X-Prosody-Repair-*` headers as the synchronous routes.
- `failed` and `budget_fallback` are successful generation outcomes: audio remains available
  and is the clean pre-repair waveform (with ordinary configured output DSP still applied).

### POST /generate/stream

- Purpose: Streaming TTS (raw PCM over a persistent connection).

Request body (JSON):

- `text` (string, required) — text to synthesize.
- `language` (string, optional, default "English").
- `voice_id` (string, optional) — voice to clone.
- `seed` (any, optional) — seed; passed through to generation.
- `prosody_repair` must remain false/omitted. Repair requires a completed waveform, so true
  is rejected with HTTP 400; use `/generate` or `/generate/async` instead.

Response:

- 200:
  - Body: a raw binary stream of PCM samples (32-bit float little-endian).
  - Headers:
    - `Content-Type: application/octet-stream`
    - `X-Audio-Format: f32le`
    - `X-Audio-Sample-Rate`: sample rate of the vocoder.
    - `X-Audio-Channels: 1`
    - `X-Stream-Error-Semantics: connection-close`
- 503:
  - If service not ready, or if the FP32 OpenVINO vocoder is not available (checked when model is loaded).
- 400:
  - If JSON invalid or `text` missing.
- On error during streaming:
  - The connection is closed; client must treat connection close as fatal.

Important notes:

- Requires OpenVINO vocoder; will 503 if it is missing while model is loaded.
- If model is idle-unloaded, it will attempt to reload; if streaming then fails, it will surface via an internal error event and a closed connection.

### POST /stream_internal (dev-only)

- Purpose: Internal endpoint to compare streaming vs batch decode; returns concatenated incremental decode as WAV.

Request body (JSON):

- `text` (string, required)
- `language` (string, optional)
- `reuse_streamed_decode` (boolean, optional, default false)
- `seed` (optional)
- Optional sampling params: `do_sample`, `temperature`, `top_p`, `top_k`, `max_new_tokens`

Response:

- 200: WAV audio with dev-oriented headers (`X-Streaming-*`, `X-Streaming-SNR-Db`, etc.)
- 503: Model not loaded or swap in progress
- 500: Inference error

### POST /batch_internal (dev-only)

- Purpose: Internal endpoint for a reference batch decode (no streaming) as WAV.

Request body (JSON):

- `text` (string, required)
- `language` (string, optional)
- `seed` (optional)
- Optional sampling params: `do_sample`, `temperature`, `top_p`, `top_k`, `max_new_tokens`

Response:

- 200: WAV with dev headers (`X-Batch-Frames`, `X-Batch-Elapsed-Seconds`, `X-Batch-Seed`)
- 503 / 500: as above

---

## Health and runtime

### GET /health

- Purpose: Health check and basic runtime status. Always returns 200.

Response (JSON):

- Fields (subset, from `model.health_state()` plus merged extras):
  - `model_loaded` — whether the Base/VoiceDesign model is currently loaded.
  - `swap_in_progress` — whether a VoiceDesign/OmniVoice swap is currently occurring.
  - `reconfig_in_progress` — whether a runtime config reload is in progress.
  - `omnivoice_loaded` — whether the OmniVoice checkpoint is resident.
  - `loading_message` — present if service is still loading (e.g. "Loading model…").

Important notes:

- Intended for container health checks; always 200, even while model loads.
- Actual readiness for work is implied by `model_loaded` and absence of swap/reconfig flags.

### GET /runtime/config

- Purpose: Get the current runtime configuration state (idle-unload, memory, etc.).

Response (JSON):

- Fields from `model.runtime_config_state()`. Specific fields depend on model.py; treat as opaque state.

### POST /runtime/config

- Purpose: Update runtime configuration dynamically (e.g. idle-unload behavior, memory settings).

Request body (JSON):

- Arbitrary key-value payload understood by `model.apply_runtime_config`; exact keys are implementation-dependent and documented in model.py.

Response:

- 200: updated config state (same shape as GET response).
- 503: if another runtime reconfiguration or VoiceDesign swap is already in progress.
- 400: if JSON invalid or config values rejected.
- 500: if an error occurs during reconfiguration.

Important notes:

- Runs on the model executor with a 300-second timeout.
- No auth gate; service is assumed to sit behind a trusted network or reverse proxy.

---

## VoiceDesign

### POST /voice_design

- Purpose: Generate a VoiceDesign preview (new voice from description) — swaps to VoiceDesign checkpoint, generates reference sample, leaves it loaded.

Request body (JSON):

- `description` (string, required) — voice description/instruction.
- `sample_text` (string, required) — text to speak in the generated sample.
  - Constrained: ~15s of speech (~34 words); longer samples cause 400.
- `language` (string, optional, default "English") — language.
- `seed` (integer, optional) — integer seed; must be int if provided.
- `selections` (any, optional) — internal chip-state for future tune/tweak; not validated by the endpoint.

Response (JSON):

- 200:
  - `preview_id` (string) — ephemeral ID; must be used with `/voice_design/preview/{preview_id}/save`.
  - `sample_rate` (int)
  - `seed` (int)
  - `audio_base64` (string) — base64-encoded WAV of the generated reference sample.
- 503:
  - If model not loaded or a VoiceDesign swap is already in progress.
- 400:
  - If JSON invalid, `description` or `sample_text` missing, `sample_text` too long, or `seed` not integer.
- 500:
  - If generation fails (e.g., wrong checkpoint type).

Important notes:

- Blocking: caller waits up to 300 seconds.
- Checkpoint swap is involved; subsequent VoiceDesign calls can iterate without swapping back.
- `preview_id` is ephemeral and in-memory only; not persisted to the voice library until explicitly saved.
- While this is running, GET `/voice_design/progress` can be polled for ETA.

### POST /voice_design/preview/{preview_id}/save

- Purpose: Persist a previously generated VoiceDesign preview into the voice library.

Path params:

- `preview_id` (string) — from `/voice_design` response.

Response (JSON):

- 200:
  - `voice_id` (string) — new persistent ID in the voice library.
- 400:
  - If `preview_id` unknown or expired.
- 500:
  - On internal error during save.
- 503:
  - If model not loaded.

Important notes:

- Consumes the preview; the same `preview_id` cannot be reused.

### GET /voice_design/progress

- Purpose: Poll progress for an in-flight VoiceDesign request.

Response (JSON):

- `phase` (string) — one of: "idle", "loading", "generating".
- `avg_seconds` (number or null) — running average generation time across recent requests.
- `estimated_remaining_seconds` (number or null) — ETA only while `phase == "generating"`.

Important notes:

- Unlike OmniVoice progress, there is no completed/total counter; this checkpoint performs a single blocking call per request.

---

## Voice library

### GET /voices

- Purpose: List all saved voices.

Response (JSON):

- `voices` (array) — each object contains voice metadata:
  - `voice_id`, `description`, `sample_text`, `language`, `seed`, `selections`, `created_at`.

### GET /voices/{voice_id}

- Purpose: Get details and audio for a specific voice.

Response (JSON):

- Same metadata fields as above, plus:
  - `audio_base64` — base64-encoded reference WAV (if file present).
- 404 if voice_id not found.

### PATCH /voices/{voice_id}

- Purpose: Update a voice's reference transcript (`sample_text`) without regenerating audio.

Request body (JSON):

- `sample_text` (string, required) — updated transcript that must match what's in reference.wav.

Response:

- 200: updated metadata (no audio field).
- 400: if `sample_text` missing.
- 404: if voice not found.

### DELETE /voices/{voice_id}

- Purpose: Delete a voice from the library.

Response:

- 200: `{ "deleted": "<voice_id>" }`.
- 404: if voice not found.

---

## OmniVoice audition

All OmniVoice audition endpoints are asynchronous via `job_id`: you start a job, then poll progress.

### POST /omnivoice/audition

- Purpose: Start a multi-segment, multi-candidate OmniVoice audition job.

Async behavior:

- Returns immediately with `job_id`; generation runs in background.
- Candidates become available incrementally via `/omnivoice/audition/progress`.
- Uses the same model executor; subject to queueing if another job/swap is in progress.

Queueing:

- If the service is started:
  - `status` is "running" immediately.
- If the service is not started:
  - `status` is "queued"; a dispatcher waits up to 900s for `_service_started`, then begins the job.
- If another swap is in progress, returns 503.

Request body (JSON):

- `segments` (string[], required) — list of short text segments (sentences). Must be non-empty; each entry non-empty.
- `instruct` (string, required) — accent/voice instruction.
- `language` (string, optional, default "english") — language; OmniVoice quality is best for English.
- `candidates_per_segment` (int, optional, default 3) — positive integer.
- `seed` (int, optional) — for reproducibility.
- `num_step` (int, optional) — must be integer; clamped to [16, 32] on the server.
- `durations` (list of number or null, optional):
  - Must match `segments` length.
  - Each value is an explicit per-segment target duration in seconds, or null for auto.
- `duration` (number, optional, legacy):
  - Applied uniformly to all segments if `durations` is absent.
- `speed` (number, optional) — clamped to [0.5, 2.5].
- `guidance_scale` (number, optional) — clamped to [1.5, 3.0].
- `diverse_candidates` (boolean, optional, default false) — if true, uses [5.0, 7.0, 10.0] temperature schedule across candidates.
- `postprocess_output` (boolean, optional) — enables/disables OmniVoice's own silence-trimming/normalization.
- `min_match_score` (number, optional) — per-candidate transcript match threshold (0.0–1.0).

Response (JSON):

- 200:
  - `job_id` (string)
  - `total_segments` (int)
- 503:
  - If another swap is in progress.
- 400:
  - If segments/instruct/params invalid.

### GET /omnivoice/audition/progress?job_id=...

- Purpose: Poll the progress and results of an audition job; returns completed candidates as they finish.

Query params:

- `job_id` (string, required) — from `/omnivoice/audition`.

Response (JSON):

- 200:
  - `status` (string) — one of: "queued", "running", "completed", "failed".
  - `job_id` (string)
  - `total_segments` (int)
  - `current_segment_index` (int or null)
  - `segments_completed` (array):
    - Each item:
      - `segment_index` (int)
      - `text` (string)
      - `candidates` (array of candidate objects):
        - `candidate_id` (string)
        - `sample_rate` (int)
        - `duration_sec` (float)
        - `audio_base64` (string) — WAV.
        - `flagged` (boolean) — whether dead-air/drone/sfx detected.
        - `flag_reason` (string or null)
        - `whisper_transcript` (string or null)
        - `match_score` (float or null)
  - `message` (string or null)
  - `eta` / `estimated_remaining_seconds` (number or null)
  - `total_candidates`, `completed_candidates`, `avg_seconds`, `current_candidate_index` (numbers or null)
- 400:
  - If `job_id` parameter missing.
- 404:
  - If job unknown or expired (TTL: 600 seconds; also evicted if >50 jobs).

Important notes:

- The `segments_completed` list grows incrementally; poll until `status == "completed"` or `"failed"`.
- Each candidate's `audio_base64` is large; responses can be several MB per segment.

### GET /omnivoice/progress

- Purpose: Low-level engine progress for the currently running OmniVoice job (for UI banners and internal use).

Response (JSON):

- `phase` (string) — "idle", "loading", "generating"
- `total`, `completed` (ints)
- `current_segment_index`, `current_candidate_index` (ints or 0)
- `segment_count`, `candidates_per_segment` (ints)
- `avg_seconds`, `estimated_remaining_seconds` (numbers or null)

No auth or per-job scoping; reflects the single in-flight OmniVoice job.

---

## OmniVoice segments (library)

Segments are individual locked-in candidate takes from an audition job, persisted for reuse.

### POST /omnivoice/segments

- Purpose: Lock in one audition candidate into the persistent segment library.

Request body (JSON):

- `candidate_id` (string, required) — from an audition job's candidate.
- `text` (string, required) — the text spoken in this segment.
- `instruct` (string, required) — accent/instruction associated with the take.
- `accent_id` (string, optional) — caller-provided accent grouping.

Response (JSON):

- 200:
  - Segment metadata:
    - `segment_id`, `text`, `instruct`, `tags`, `engine`, `accent_id`, `sample_rate`,
      `language`, `seed`, `num_step`, `speed`, `guidance_scale`, `diverse_candidates`,
      `postprocess_output`, `duration_target`, `candidate_id`, `job_id`,
      `whisper_transcript`, `match_score`, `duration_sec`, `created_at`
    - `audio_base64` — WAV of the locked-in take.
- 400:
  - If candidate unknown/expired, or `text`/`instruct` missing.

Important notes:

- Consumes candidate_id reference from ephemeral cache; segment persists on disk.
- If candidate_id was part of an existing job, additional metadata (language, seed, durations, etc.) is inferred from job params.

### GET /omnivoice/segments

- Purpose: List all persisted segments.

Response (JSON):

- `segments` (array) — each with segment metadata; no `audio_base64`, no `wav_path`.

### GET /omnivoice/segments/{segment_id}/audio

- Purpose: Download the audio for a single segment.

Response:

- 200:
  - Body: raw WAV bytes.
  - `Content-Type: audio/wav`
  - `Content-Disposition: inline; filename="<segment_id>.wav"`
- 404:
  - If segment_id not found.

### DELETE /omnivoice/segments/{segment_id}

- Purpose: Delete a segment from the library.

Response:

- 200: `{ "deleted": true }`.
- 404: if not found.

---

## OmniVoice stitch

Preview-stitch segments or candidates into a single audio clip without saving permanently.

### POST /omnivoice/stitch

- Purpose: Stitch selected segments or candidates into a single WAV.

Two modes (mutually exclusive based on payload shape):

- Simple mode:
  - `segment_ids` (string[]): list of persisted segment IDs.
  - OR `selections` (string[]): list of ephemeral `candidate_id`s.
- Stitch plan mode (advanced):
  - `stitch_plan` (object):
    - `clips` (array, required): each clip:
      - One of:
        - `segment_id` (string)
        - `candidate_id` (string)
        - `voice_id` (string)
      - Optional:
        - `trim_start_ms` (float)
        - `trim_end_ms` (float)
        - `fade_in_ms` (float)
        - `fade_out_ms` (float)
    - Optional:
      - `padding_ms` (float[]): length must be `len(clips) - 1`
      - `crossfade_ms` (float)
      - `segment_target_dbfs` (float)
      - `final_target_dbfs` (float)
      - `final_ceiling_db` (float)
      - `compress` (object):
        - `threshold_db` (float), `ratio` (float), `attack_ms` (float), `release_ms` (float)

Response:

- 200:
  - Body: WAV audio.
- 400:
  - If:
    - No `stitch_plan`, `segment_ids`, or `selections`; or
    - IDs unknown, or
    - `stitch_plan` malformed.
- 500:
  - On unexpected stitch error.

Important notes:

- `segment_id`-based clips are stable across restarts; `candidate_id`-based clips depend on in-memory audition cache and can disappear on a new audition job.
- `voice_id`-based clips pull from the voice library (useful for mixing a saved reference voice as a clip).

---

## OmniVoice save (stitch + persist)

### POST /omnivoice/save

- Purpose: Stitch selected segments/candidates and persist the result as a new voice in the library.

Request body (JSON):

- `instruct` (string, required) — description of the resulting accent/voice.
- `segments` (string[], required) — the text segments spoken in the final stitched voice (used as the reference transcript).
- `language` (string, optional, default "english")
- `accent_id` (string, optional)

Plus clips resolution (same as `/omnivoice/stitch`):

- Either:
  - `stitch_plan` (object, advanced), OR
  - `segment_ids` (string[]), OR
  - `selections` (string[]).

Response (JSON):

- 200:
  - `voice_id` (string)
  - `sample_rate` (int)
  - `audio_base64` (string) — stitched WAV.
- 400:
  - If clips cannot be resolved, or `instruct`/`segments` invalid.
- 500:
  - On internal error.

Important notes:

- The resulting voice is usable with `/generate` and `/v1/audio/speech` via its `voice_id`.
- Intern metadata (`segment_ids`, `candidate_ids`, `stitch_plan`) is stored in `selections` for later reconstruction.

# Persona Forge — HTTP API Reference

Single-source reference for all HTTP endpoints exposed by Persona Forge.

- All JSON endpoints expect `application/json`.
- All audio endpoints that return files set the appropriate `Content-Type` (`audio/mpeg` for MP3, `audio/wav` for WAV, `audio/pcm` for raw PCM).
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
- `response_format` (string, optional, default "mp3") — "mp3", "wav", or "pcm"
  (raw int16 LE mono, `audio/pcm`).
- `seed` (integer, optional) — RNG seed for reproducibility; if present must be an integer.
- `prosody_repair` (boolean, optional, default false) — batch/offline output repair using
  the input text. The server-enforced deadline defaults to five seconds.

Response:

- 200:
  - Body: raw audio bytes (MP3, WAV, or PCM, based on `response_format`).
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
- `response_format` (string, optional, default "mp3") — "mp3", "wav", or "pcm"
  (raw int16 LE mono, `audio/pcm`).
- `seed` (integer, optional) — RNG seed.
- `prosody_repair` (boolean, optional, default false) — same bounded complete-file repair
  contract as `/generate`.

Response:

- 200:
  - Body: raw audio bytes (MP3, WAV, or PCM, based on `response_format`).
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

### POST /generate/with_metrics

- Purpose: Same generation as `/generate` but returns a JSON envelope with base64 audio,
  reference metrics, and take diagnoses (used by the frontend VariantCompare).

Request body (JSON):

- Same fields as `/generate`: `text` (string, required), `language`, `voice_id`, `instruct`,
  `seed`, `prosody_repair`, plus optional pass-throughs `voice_variant_id`, `style_preset`,
  `postprocess`.

Response (JSON):

- 200:
  - `audio_base64` (string) — WAV of the generated audio.
  - `media_type` (string) — `audio/wav` (always encoded as WAV).
  - `seed` (int) — resolved seed.
  - `metrics` (object) — `analyze_reference` metrics for the generated audio; an `error` field
    if analysis failed.
  - `diagnoses` (array) — take-diagnosis objects.
  - `job_id` (string) and `prosody_repair` (object) — present when a repair outcome is tracked
    for the job.
- 503:
  - If model not loaded or a runtime reconfiguration is in progress.
- 400:
  - If JSON invalid, `text` missing, `seed` not integer, or `builtin_voice` unsupported on the
    active backend.
- 422:
  - If generation aborted (cache capacity exceeded).
- 500:
  - If an inference error occurs.

### POST /generate/async

- Purpose: Start a generation job and return immediately with a `job_id`; generation runs in a
  background thread. Poll `GET /generate/progress`, fetch the audio via
  `GET /generate/job/{job_id}/audio`, or stop early with `POST /generate/cancel`.

Request body (JSON):

- Same fields as `/generate`: `text` (string, required), `language`, `voice_id`, `instruct`,
  `seed`, `prosody_repair`, `response_format` ("mp3", "wav", or "pcm"), plus optional
  pass-throughs `voice_variant_id`, `style_preset`, `postprocess`.

Response (JSON):

- 200:
  - `job_id` (string)
  - `prosody_repair` (object): `requested` (boolean), `outcome` ("pending" if requested, else
    "not_requested").
- 503:
  - If model not loaded or a runtime reconfiguration is in progress.
- 400:
  - If JSON invalid, `text` missing, unsupported `response_format`, `seed` not integer, or
    `builtin_voice` unsupported on the active backend.

Important notes:

- Generation errors (including capacity-exceeded) do not fail this call: they surface later as
  `status: "failed"` on `GET /generate/progress`. The progress response has no dedicated `error`
  field; the failure string is stored on the job record but not exposed by this endpoint.
- `failed` and `budget_fallback` are successful generation outcomes: audio remains available
  and is the clean pre-repair waveform (with ordinary configured output DSP still applied).
- Jobs are cleaned up ~120 s after completion; fetch audio before then.

### GET /generate/progress

- Purpose: Poll live progress/ETA for an async generation job.

Query params:

- `job_id` (string, required) — from `/generate/async`.

Response (JSON):

- 200:
  - `job_id` (string)
  - `status` (string) — one of: "queued", "running", "completed", "failed", "cancelled".
  - `frames_generated`, `expected_total_frames` (ints)
  - `progress_pct` (number, 0–100)
  - `elapsed_seconds`, `audio_seconds` (numbers)
  - `rtf`, `live_rtf_estimate` (number or null)
  - `eta_seconds` (number or null)
  - `message` (string or null)
  - `style_preset`, `postprocess_applied`, `applied_steps`, `prosody_repair` — from job state.
  - `audio_available` (boolean) — true once completed; for cancelled/failed jobs, true if a
    (partial) waveform was captured.
- 400:
  - If `job_id` parameter missing.
- 404:
  - If job unknown or expired (~120 s after completion).

### POST /generate/cancel

- Purpose: Cooperatively cancel a running async generation job.

Params:

- `job_id` (string, required) — as a query parameter or in the JSON body.

Response (JSON):

- 200: `{ "cancelled": true, "job_id": "..." }`.
- 400: If `job_id` missing.
- 404: If job unknown or not running.

Important notes:

- Cooperative: generation ends at the next decode step; partial audio may remain retrievable via
  `GET /generate/job/{job_id}/audio`.

### GET /generate/job/{job_id}/audio

- Purpose: Retrieve the audio of a completed (or cancelled-with-partial-audio) async job.

Query params:

- `response_format` (string, optional, default "mp3") — "mp3", "wav", or "pcm".

Response:

- 200:
  - Body: audio bytes (MP3, WAV, or raw PCM).
  - Headers: `X-Seed`, `X-Job-Id`, the same `X-Prosody-Repair-*` headers as the synchronous
    routes, plus `X-Style-Preset`, `X-Postprocess-Applied`, `X-Audio-Seconds`, `X-RTF`, and
    `X-Applied-Steps` when present.
- 400:
  - If the job is not completed/cancelled yet, or `response_format` unsupported.
- 404:
  - If job unknown/expired, or no audio available.

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

### POST /runtime/config/reset

- Purpose: Drop the persisted runtime config (keeping locked keys) and revert unlocked keys to
  their hardcoded defaults.

Response:

- 200: updated config state (same shape as GET response).
- 503: if another runtime reconfiguration or VoiceDesign/OmniVoice swap is already in progress.
- 500: if an error occurs during reset.

Important notes:

- Runs on the model executor with a 300-second timeout.
- No auth gate; same rationale as POST `/runtime/config`.

### POST /health/validate-ref-text

- Purpose: Validate the configured default reference (`REF_AUDIO`/`REF_AUDIO_PATH` + `REF_TEXT`)
  with Whisper and return the match verdict.

Response (JSON):

- 200: validation result with at least:
  - `severity` (string) — "ok", "warn", "fail", "no_speech", or "error".
  - `match_score` (number or null)
  - `whisper_transcript` (string or null)
  - `suggestion` (string or null)
- 400:
  - If `REF_AUDIO`/`REF_AUDIO_PATH` or `REF_TEXT` is not configured.
- 503:
  - If model not loaded.
- 500:
  - If validation fails (`error` field).

### GET /alignment/performance

- Purpose: Bounded observed latency window for forced-alignment jobs (cold starts and cache hits
  included).

Response (JSON):

- `sample_count`, `window_size` (ints)
- `budget_seconds` (number) — the configured `ALIGNER_LATENCY_BUDGET_SECONDS`
- `p50_seconds`, `p95_seconds` (number or null)
- `within_budget` (boolean) — p95 under budget (true when no samples yet)
- `breach_count` (int)

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

### POST /voices/{voice_id}/transcribe

- Purpose: Generate and persist a reference transcript with the service's `faster-whisper`
  (`tiny.en`, CPU `int8`) ASR path. This is useful for mounted or imported voices whose
  audio has no saved `sample_text`.
- Response:
  - 200: updated voice metadata with `sample_text_source: "whisper"` and ASR metadata.
  - 400: if the voice has no readable reference audio.
  - 404: if voice not found.
  - 422: if Whisper detects no usable speech.
  - 503: if the model service is not ready.

### DELETE /voices/{voice_id}

- Purpose: Delete a voice from the library.

Response:

- 200: `{ "deleted": "<voice_id>" }`.
- 404: if voice not found.

### GET /voices/built-in

- Purpose: List the curated built-in voices for the Pocket TTS backend.

Response (JSON):

- `voices` (array) — each object:
  - `voice_id` (string, e.g. "pocket:amy"), `builtin_voice`, `backend` ("pocket_tts"),
    `display_name`, `source`, `license`, `language`, `language_code`, `category`, `note`,
    `prompt`, `requires_backend` ("pocket_tts").

### POST /voices/{voice_id}/duplicate

- Purpose: Fork a voice into an independent `voice_id` (also used as a safety copy before
  destructive reference-audio editing).

Request body (JSON, optional):

- `variant_filename` (string, optional) — fork this specific prosody variant rather than the
  currently active one.

Response (JSON):

- 201: new voice metadata.
- 404: if voice not found.
- 500: if the duplicate fails.

### POST /voices/{voice_id}/analyze

- Purpose: Backfill reference metrics without changing the saved WAV.

Response (JSON):

- 200: updated voice metadata (with metrics).
- 404: if voice not found.
- 500: if reference analysis fails.

### POST /voices/{voice_id}/undo-reference-edit

- Purpose: Undo the most recent reference-audio edit (restore the pre-edit audio).

Response (JSON):

- 200: updated voice metadata.
- 409: if there is no audio edit to undo.

### POST /voices/{voice_id}/normalize

- Purpose: Re-normalize the saved reference clip's loudness/peak in place (-20 LUFS, -1 dBTP).

Response (JSON):

- 200: updated voice metadata.
- 404: if voice not found.
- 409: if the reference is mounted/read-only (duplicate the voice and edit the copy instead).
- 500: if normalization fails.

### POST /voices/{voice_id}/trim-silence

- Purpose: Trim leading/trailing silence from the saved reference clip in place.

Response (JSON):

- 200: updated voice metadata.
- 404: if voice not found.
- 409: if the reference is mounted/read-only.
- 500: if trimming fails.

### POST /voices/{voice_id}/set-default

- Purpose: Mark this voice as the default variant within its family.

Response (JSON):

- 200: updated voice metadata.
- 404: if voice not found.

### POST /voices/{voice_id}/project

- Purpose: Assign or clear the Accent Design Project this voice belongs to.

Request body (JSON):

- `project_id` (string, optional) — `proj_<12 hex>`; omit/null to clear.
- `project_name` (string, optional) — denormalized name tag.

Response (JSON):

- 200: updated voice metadata.
- 404: if voice not found.

### POST /voices/{voice_id}/set-active-variant

- Purpose: Set the active prosody variant for a voice, or reset to the original.

Request body (JSON):

- `variant_filename` (string, optional) — variant to activate; omit/null to reset to original.

Response (JSON):

- 200: voice metadata plus `status` and `active_variant`.
- 400: if the voice or variant file is invalid.
- 500: if setting the variant fails.

### GET /voices/{voice_id}/variants

- Purpose: List the original reference plus all saved prosody variants for a voice.

Response (JSON):

- `entries` (array) — first entry is the original (`is_original: true`); each variant entry has
  `id` ("<voice_id>.<slug>"), `slug`, `filename`, `label`, `source`, `created_at`,
  `is_original: false`.
- `variants` (string[]) — sorted variant filenames.
- `active_variant` (string or null) — the variant currently served (null when serving original).
- `active_filename` (string) — filename currently served ("original.wav" or a variant).
- 400: if voice_id invalid.
- 404: if voice not found.

### GET /voices/{voice_id}/variants/{variant_filename}/audio

- Purpose: Fetch a single variant's raw audio for per-variant preview playback.

Response (JSON):

- 200: `{ "audio_base64": "..." }` (WAV).
- 404: if variant not found.

### GET /voices/{voice_id}/variants/{variant_filename}/metrics

- Purpose: Compute a single variant's quality metrics without persisting them (preview-only).

Response (JSON):

- 200: metrics object.
- 404: if variant not found.

### DELETE /voices/{voice_id}/variants/{variant_filename}

- Purpose: Delete a prosody variant. If it was active, the voice falls back to original.wav.

Response (JSON):

- 200: `{ "deleted": "<variant_filename>" }`.
- 404: if variant not found.

### POST /voices/{voice_id}/activate

- Purpose: Make a saved voice the no-voice runtime API default. Hot-swaps the Pocket voice
  state or Qwen clone prompt and persists the choice across restarts.

Response (JSON):

- 200: voice metadata with `api_active: true`.
- 400: if a Qwen backend voice has no reference transcript.
- 409: if the active backend does not support saved-voice API defaults.
- 404: if voice not found.
- 503: if model not loaded.
- 500: if activation fails.

### POST /voices/{voice_id}/warm

- Purpose: Ensure the voice's clone state is loaded and cached before generation (bounces the
  runtime back from an idle-unloaded state and pre-builds that voice's state).

Response (JSON):

- 200: `{ "warmed": true, "voice_id": "..." }`; or
  `{ "warmed": false, "reason": "not pocket_tts backend" }` when the backend is not `pocket_tts`.
- 404: if voice not found.
- 503: if model not loaded.
- 500: if warm-up fails.

### GET /voices/{voice_id}/preview-prosody

- Purpose: Preview prosody adjustments without saving a variant.

Query params:

- `style_preset` (string, default "Neutral")
- `pace_multiplier` (number, default 1.0)
- `pause_offset` (number, default 0.0)
- `mode` ("natural" | "precise" | "auto", default "auto")
- `target_overrides` (JSON object as a string, optional) — per-boundary target deltas (ms) keyed
  by rounded at_ms, layered on top of `pause_offset`.

Response (JSON):

- 200:
  - `audio_base64` (string) — adjusted WAV.
  - `metrics` (object) — analysis of the adjusted audio (or an `error` field).
  - `diagnoses` (array) — take diagnostics.
  - `sample_rate` (int), `sample_count` (int)
  - `plan` (object) — the prosody adjustment plan.
- 400: if params non-numeric, `mode` invalid, or `target_overrides` malformed.
- 404: if voice not found.
- 500: if preview failed.

### POST /voices/{voice_id}/adjust-pauses

- Purpose: Adjust interior pauses of the saved reference clip in place based on a prosody map
  and pace.

Request body (JSON):

- `style_preset` (string, default "Neutral")
- `pace_multiplier` (number, default 1.0)
- `pause_offset` (number, default 0.0)
- `mode` ("natural" | "precise" | "auto", default "auto")

Response (JSON):

- 200: updated voice metadata.
- 400: if params non-numeric or `mode` invalid.
- 404: if voice not found.
- 409: if the reference is mounted/read-only.
- 500: if the adjustment fails.

### POST /voices/{voice_id}/prosody-variants

- Purpose: Bake and save a prosody variant without promoting it to the active/served audio.

Request body (JSON):

- Same fields as `/adjust-pauses`, plus optional:
  - `target_overrides` (object of numbers) — precise per-boundary corrections.

Response (JSON):

- 200: saved variant metadata.
- 400: as with `/adjust-pauses`, or if `target_overrides` malformed.
- 404: if voice not found.
- 409: if the reference is mounted/read-only.
- 500: if saving fails.

### POST /voices/{voice_id}/region-edits

- Purpose: Apply a manual region-edit list (delete / insert_silence / fade / gain / mute) to the
  saved reference clip in place.

Request body (JSON):

- `edits` (array, optional) — each edit:
  - `type` (string, required): one of `gain`, `mute`, `fade`, `delete`, `insert_silence`.
  - `gain` / `mute` / `fade` / `delete`: `start_ms`, `end_ms` (required numbers); optional
    `gain_db` (gain only), `fade_in_ms`, `fade_out_ms` (where applicable).
  - `insert_silence`: `at_ms`, `duration_ms` (required numbers).

Response (JSON):

- 200: updated voice metadata.
- 400: if the edits payload is invalid.
- 404: if voice not found.
- 409: if the reference is mounted/read-only.
- 500: if the edit fails.

### POST /voices/{voice_id}/triage

- Purpose: Cheap, synchronous triage: does this reference need forced alignment?

Response (JSON):

- 200: triage result:
  - `mode` (string) — the recommended prosody mode.
  - `coverage` (number or null), `boundaries_expected` (number), `gaps_detected` (int)
  - `reasons` (string[])
  - `median_gap_ms`, `speech_rate_cv` (numbers)
- 404: if voice not found, or reference audio missing.
- 500: if triage fails.

### POST /voices/{voice_id}/align

- Purpose: Start (or reuse) a forced-alignment job. Async: returns a job to poll.

Request body (JSON, optional):

- `force` (boolean, optional) — recompute even when a cached alignment exists.

Response (JSON):

- 202: job object:
  - `job_id`, `voice_id`, `status` ("queued"/"running"/"completed"/"failed"/"cancelled"),
    `created_at`, `started_at`, `finished_at`, `duration_seconds`,
    `latency_budget_seconds`, `within_latency_budget`,
    `result` (null until completed), `error` (null unless failed).
- 400: if the voice has no transcript.
- 404: if voice not found.

Important notes:

- At most one alignment runs at a time; terminal jobs are evicted by TTL/count
  (default 600 s / 50 jobs).

### GET /voices/{voice_id}/align/{job_id}

- Purpose: Poll a forced-alignment job.

Response (JSON):

- 200: same job object as `POST /align`; `result` carries the alignment on completion.
- 404: if the job is unknown or belongs to a different voice.

### DELETE /voices/{voice_id}/align/{job_id}

- Purpose: Cancel a forced-alignment job.

Response (JSON):

- 200: job object (a cancelled job never reports "completed").
- 404: if the job is unknown or belongs to a different voice.

### POST /voices/{voice_id}/validate

- Purpose: Validate the voice's saved transcript against its reference audio with Whisper.

Response (JSON):

- 200: same validation result shape as `POST /health/validate-ref-text`.
- 400: if the voice is missing wav_path or sample_text.
- 404: if voice not found.
- 503: if model not loaded.
- 500: if validation fails.

---

## Projects

Accent Design Projects are name/description tags that group voices and segments. Membership is
derived from each voice's/segment's own `project_id`/`project_name` fields (set via
`POST /voices/{voice_id}/project` and `POST /omnivoice/segments/{segment_id}/project`); the
registry is persisted in `projects.json` inside the voice-library volume. Deleting a project does
not touch its voices/segments — they simply fall back to "Ungrouped".

### GET /projects

- Purpose: List all projects, newest first.

Response (JSON):

- Array of project objects:
  - `project_id` (string, "proj_<12 hex>"), `name` (string), `description` (string or null),
    `created_at` (number, epoch seconds).

### POST /projects

- Purpose: Create a project.

Request body (JSON):

- `name` (string, required)
- `description` (string, optional)

Response (JSON):

- 200: the created project object (shape as above).
- 400: if JSON invalid or `name` missing/empty.

### PATCH /projects/{project_id}

- Purpose: Rename a project (optionally update its description).

Request body (JSON):

- `name` (string, required)
- `description` (string, optional) — updated only when present.

Response (JSON):

- 200: the updated project object.
- 400: if JSON invalid or `name` missing/empty.
- 404: if project_id unknown.

### DELETE /projects/{project_id}

- Purpose: Delete a project from the registry (its voices/segments are not touched).

Response (JSON):

- 200: `{ "deleted": true }`.
- 404: if project_id unknown.

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

### POST /omnivoice/audition/cancel

- Purpose: Cancel a running (or queued) OmniVoice audition job.

Query params:

- `job_id` (string, required) — from `/omnivoice/audition`.

Response (JSON):

- 200: `{ "cancelled": true, "job_id": "..." }`.
- 400: if `job_id` missing, or the job is not currently running/queued.
- 404: if job unknown or expired.

Important notes:

- Cooperative: the engine stops at the next segment/candidate boundary. A still-queued job is
  finalized immediately with `status: "failed"` and message "Cancelled by user."

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

### POST /omnivoice/segments/{segment_id}/project

- Purpose: Assign or clear the Accent Design Project this segment belongs to.

Request body (JSON):

- `project_id` (string, optional) — `proj_<12 hex>`; omit/null to clear.
- `project_name` (string, optional) — denormalized name tag.

Response (JSON):

- 200: updated segment metadata.
- 404: if segment not found.

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

### POST /omnivoice/stitch/pacing-targets

- Purpose: Resolve inter-segment pause targets (stitch padding) through the canonical prosody
  target table, for the given transcripts and pacing.

Request body (JSON):

- `transcripts` (string[], required) — non-empty list of the segment texts, in stitch order.
- `pace_multiplier` (number, optional, default 1.0) — must be within [0.25, 4.0].
- `pause_offset_ms` (number, optional, default 0.0) — must be within [-2000, 5000].
- `style_preset` (string, optional, default "Neutral") — falls back to "Neutral" if not a known
  prosody preset.

Response (JSON):

- 200:
  - `padding_ms` (number[]) — suggested seam pause after every clip except the last
    (length = `len(transcripts) - 1`), derived from each preceding clip's terminal punctuation.
  - `style_preset` (string) — the preset actually used.
- 400:
  - If JSON invalid, `transcripts` is not a non-empty list of strings, pacing values are
    non-numeric, or pacing values are out of range.

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

---

## Frontend (static)

Present only when `FRONTEND_ENABLED` is on (default) and a built frontend dist is available;
otherwise the service runs API-only and these routes do not exist.

### GET /

- Purpose: Serve the web UI entry point (index.html).

### GET /assets/{filename}

- Purpose: Serve compiled frontend static assets (JS/CSS/etc.).

### GET /favicon.svg

- Purpose: Serve the favicon.

---

## Internal / test-only

### GET /_shutdown

- Purpose: Test-only hook used by the fake model server to shut down a test instance. Returns
  plain-text "ok". Not part of the product API surface.

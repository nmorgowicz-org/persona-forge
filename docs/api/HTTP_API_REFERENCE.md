# Persona Forge — HTTP API Reference

Single-source reference for all HTTP endpoints exposed by Persona Forge.

- All JSON endpoints expect `application/json`.
- All audio endpoints that return files set the appropriate `Content-Type` (`audio/mpeg` for MP3, `audio/wav` for WAV, `audio/pcm` for raw PCM).
- All endpoints are relative to the service root (default: `http://host:8318`).
- The service is single-worker (Gunicorn `-w 1`); model access is serialized via a single-thread executor.

## Connecting other tools

In Persona Forge Desktop, open **Settings** and copy the OpenAI-compatible base URL shown for
the server. It has the form `http://<host>:<port>/v1`; use the loopback address for tools on the
same machine or a listed LAN address when network access is enabled.

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
- `normalize_loudness` (boolean, optional) — `false` skips the loudness normalisation described
  below for this request; `true` forces it on even when the server default is off
  (`TTS_NORMALIZE_LOUDNESS=0`). Omitted → the server default (on). A non-boolean value returns 400.
- `prosody_repair` (boolean, optional, default false) — same bounded complete-file repair
  contract as `/generate`.
- `model` (string, optional) — engine selector. Known values: `pocket-tts` (and aliases
  `pocket`, `pocket_tts`, `persona-forge`, `tts-1`, `tts-1-hd`, `gpt-4o-mini-tts`, `default`,
  or omitted → active engine) and, once the pack is installed, `kitten2` (aliases `kitten-2`,
  `kitten-tts-2`) `phonon-31m` (aliases `phonon`, `phonon31m`) `kokoro` (aliases `kokoro-82m`, `kokoro82m`) or `pocket-lite` (aliases `pocket_lite`, `pocket-lite-18m`). Pack engines are served beside
  the active backend in a separate process (no 409); a missing pack returns 503 with an install hint. Kitten 2 holds roughly 2 GB while loaded
  and stops itself after `KITTEN2_IDLE_UNLOAD_S` of inactivity. An unknown label is treated as a client-side name and served by
  the active engine, so existing OpenAI clients keep working; the response reports
  `X-Model-Recognized: false`. A request never switches the built-in backend (see "Switching
  engines from a request" below). **Which engine serves a request:** an engine named outright in
  `model` serves it; otherwise a namespaced `voice`/`voice_id` (`kokoro:af_heart`, `phonon:Zoey`,
  `kitten2:Bruno`, `pocket-lite:jane`) is served by its own engine, even when `model` is a generic
  label such as `tts-1`; with no voice, the persisted API default (see `GET /api-default`) names the
  engine, so a Kokoro or Phonon default serves a bare request. A request that names a different
  engine does not use the default's voice. A default that cannot be served is an error, never
  another speaker (409 `api_default_unavailable`, below).

Response:

- 200:
  - Body: raw audio bytes (MP3, WAV, or PCM, based on `response_format`).
  - Header: `X-Seed`: resolved integer seed.
  - Header: `X-Model-Recognized`: `true` when `model` matched an engine/alias, `false` when an
    unknown label was accepted for compatibility.
  - Headers: the same `X-Prosody-Repair-*` outcome metadata as `/generate`.
  - Header: `X-Loudness-Normalized`: `true` when the clip was level-normalised, `false` when it was
    not (opt-out, silent audio, or a streamed response). `X-Loudness-Gain-Db`: the applied gain in
    dB, present only when normalised.
- 503:
  - If model not loaded or a runtime reconfiguration is in progress.
  - **Engine warming** (retryable): a pack engine that is still loading its worker or compiling its
    first call answers `503` with a `Retry-After` header (whole seconds) and error code
    `engine_warming`. See "Engine warm-up" below.
  - A pack that is not installed, or whose worker failed to load, also answers 503 with the reason
    in `message` but **no** `Retry-After` and no `engine_warming` code: retrying will not help.
- 400:
  - If JSON invalid, input text missing, unsupported `response_format`, invalid `seed`, or a
    non-boolean `normalize_loudness`.
- 409 (`api_default_unavailable`): the request relies on the API default (no voice, and no other
  engine named) and the default's engine was removed or its voice no longer exists. The message
  names the default, what is missing and the repair ("Install Kokoro 82M again in Runtime → Speech
  engines, or choose a different API default"). Nothing is synthesised; there is no fallback to
  another speaker or engine. `GET /api-default` reports the same `problem`. Naming a voice
  explicitly still works while the default is broken.
- 500:
  - If an inference error occurs.

Error format:

- Always returns an OpenAI-style JSON: `{ "error": { "message": "...", "type": "...", "code": null } }`.
  `code` is `null` except for `engine_warming` and `api_default_unavailable`.

Important notes:

- Same FIFO queueing behind swaps as `/generate`.
- **Loudness normalisation.** Engines differ in native level (Kitten TTS 2 is peak-normalised to
  RMS 0.16–0.22, Pocket sits near 0.09), so every complete clip is brought to one level before
  encoding, whichever engine produced it: the RMS of the active speech (frames below −55 dBFS
  are ignored, so pauses do not count) is moved to **−23 dBFS**, boosting by at most 12 dB, and a
  soft-knee peak limiter keeps samples under **−1 dBFS** so nothing clips. Silent, empty or
  unmeasurable audio is returned unchanged. It is **on by default**; opt out per request with
  `normalize_loudness: false` or server-wide with `TTS_NORMALIZE_LOUDNESS=0`. Applies to `mp3`,
  `wav` and to `pcm` from engines that return a whole clip (Kitten TTS 2, Kokoro, and any
  non-streamed request). Implementation: `src/persona_forge/output_level.py`.
- **Streamed PCM is not normalised.** `response_format: "pcm"` from an engine that streams
  (Pocket-TTS, Phonon 31M, Pocket Lite) is sent chunk by chunk as produced; a stream cannot know
  the whole clip's level, and a fixed per-engine gain would be a guess because cloned voices vary
  by several dB. Those responses carry `X-Loudness-Normalized: false`. Request `wav`/`mp3`
  (or an engine that does not stream) when level consistency matters more than first-audio
  latency.

#### Switching engines from a request (not supported)

The plan's "Allow API requests to switch engines" setting is **not built, on purpose**. Pack engines
(Kitten 2, Phonon, Kokoro, Pocket Lite) already run beside the active backend in their own worker
process, so a request for one never needs a switch. What is left is a swap among the built-in
backends (`pocket_tts`, `openvino`, `pytorch`), and the current lifecycle cannot do that safely
from a request:

- Only `pocket-tts` is a registered engine, so a request cannot name `openvino` or `pytorch`
  (`model: "openvino"` is an unknown label: served by the active backend, `X-Model-Recognized:
  false`). `active_engine()` reports `pocket-tts` for the Qwen3-TTS backends as a legacy label.
- The one existing swap, `apply_runtime_config({"TTS_BACKEND": ...})`, is a global reconfiguration,
  not a queued job: it sets `reconfig_in_progress`, which makes `/generate` and `/v1/audio/speech`
  answer 503 "Model not loaded" to every other client while it unloads and reloads (the documented
  FIFO queueing only covers VoiceDesign/OmniVoice swaps). It writes `runtime.json` unless told not
  to, flips `TTS_BACKEND` before the load succeeds, and has no rollback if the load fails. A Qwen3-TTS
  load is ~5.4–6.9 GiB, 60–120 s or more on a cold OpenVINO cache, and needs a one-time IR export;
  two clients naming different backends would thrash it.
- A safe version needs a queued swap job with a bounded wait, a rollback path and an engine id for
  each built-in backend, which is a lifecycle redesign (`MODEL_SWAP_AND_QUEUEING.md` is normative).

What clients get today: the backend is changed in Runtime (or `POST /runtime/config`), not by a
request. A request the active backend cannot serve gets a clear error instead of a swap:
`builtin_voice` on a non-Pocket backend is a 400 ("builtin_voice is only supported when
TTS_BACKEND=pocket_tts"), `PUT /api-default` with a Pocket preset while another backend is active is
a 409 ("Built-in presets require TTS_BACKEND=pocket_tts"), and an engine pack that is missing is a
503 with the install hint. The 409 "model is not active; the active engine is X" in the request
path only fires for a registered non-pack engine other than the active one; since `pocket-tts` is the
only such engine and is also the fallback label for the Qwen backends, it cannot occur today.

#### Engine warm-up (`engine_warming`)

A pack engine goes `idle` → `loading` (worker starting, weights loading) → `warming` (first call
compiling kernels; about 33 s for compiled Kitten TTS 2 on NVIDIA) → `ready`. The first request to
an idle engine starts that load in the background. Nothing blocks until a gunicorn timeout:

- The request waits for the engine for at most **`ENGINE_WARM_WAIT_S` seconds (default `5`)**.
  Engines that load in a couple of seconds therefore still answer the first request normally.
  `0` never waits. The value is read on every request.
- If the engine is still loading or warming after that, the answer is
  `503 Service Unavailable` with `Retry-After: <seconds>` and
  `{ "error": { "message": "Kitten TTS 2 is warming up (compiling its first call); retry in about 30 s.", "type": "api_error", "code": "engine_warming" } }`.
  The message names the engine and the phase (`loading` or `warming up`). `Retry-After` is the
  remaining estimate where one is measured (Kitten TTS 2 warm-up: 35 s), clamped to 1–60 s, and
  `5` otherwise or once the estimate is exceeded.
- The load keeps running after the 503, so the retry is served as soon as `ready`. Concurrent
  requests share one load. The request itself is not queued: resend it.
- OpenAI SDKs retry a 503 and honour `Retry-After`, so most clients need no change. The built-in
  UI (Speak, Compare, voice previews) retries by itself and shows the message.
- The same answer applies to `response_format: "pcm"` streaming engines, before any audio is sent.
- Poll `GET /engines` (`load_status`, below) to watch progress without sending synthesis requests.

### GET /v1/models

- Purpose: OpenAI-compatible model discovery; lists registered speech engines.
- Response 200: `{ "object": "list", "data": [ ... ] }`, each entry:
  `id` (`pocket-tts`), `object` (`model`), `label`, `description`, `backend`, `runtime`,
  `source`, `license`, `installed`, `active`, `owned_by` (`local`), and `capabilities`
  (`clone`, `presets`, `import_prepared_voice`, `streaming`, `languages`, `speed`,
  `expression_tags`, `seed`, `instructions`).
- No model load is required; safe to poll before the engine is ready.

### GET /v1/audio/voices

- Purpose: list every voice the endpoint can serve for the active engine.
- Response 200: `{ "object": "list", "data": [ ... ] }`, each entry:
  `voice_id` (`vd_...` or `pocket:<name>`), `object` (`voice`), `engine`, `kind`
  (`library`|`preset`), `display_name`, `language`, `language_code`, `servable`.
- **Language filter:** by default only English voices are listed. The setting is the UI
  preference `voiceCatalog.language` (`en` or `all`, in Speech engines or the Built-in voices tab);
  `?language=all` or `?language=en` overrides it per call. The response carries `language_filter` and
  `hidden_by_language_filter`. This only affects listing: a request may name any voice, in any
  language, and is served. Each voice has `language_code`; saved voices without one are always shown.
- Pocket presets (`pocket:<name>`) are included only when the Pocket backend is active.
- When the Kitten TTS 2 pack is installed, its 115 built-in voices are listed as `kitten2:<Name>`
  (`engine: "kitten2"`, `kind: "preset"`). Names come from the downloaded weights, so listing never
  loads the model. Saved library voices work with Kitten 2 too (cloning); an unknown preset name
  returns 400.

### GET /engines

- Purpose: engine-manager view for the UI; combines built-in engines with packs under
  `ENGINE_PACKS_DIR`.
- Response 200: `{ "engines": [ ... ] }`, each card: `id`, `label`, `description`, `kind`
  (`builtin`|`pack`|`builtin+pack`), `version`, `runtime`, `source`, `license`, `active`,
  `capabilities`, `requirements`, `pack` (manifest + artifacts) and `state`:
  `status` (`built-in`|`not-installed`|`installed`|`verified`|`invalid`),
  `artifacts_present`, `artifacts_total`, `disk_bytes`, `verified`, `errors`.
- Provisioned packs (Kitten TTS 2) also carry `install_job` (`state` `idle|running|done|error`,
  `step`, `step_index`, `step_count`, `error`) and `load_status`:
  - `state`: `idle` (installed, loads on demand, also after an idle unload) → `loading` (worker
    starting) → `warming` (worker loaded; first call compiling) → `ready`, or `error`. `ready` is
    the plan's "active": the worker can serve now. Engines whose worker has no warm-up step go
    straight from `loading` to `ready`.
  - `idle_unload_after` (seconds; `0` = never) and `idle_unload_source` (`argument|env|manifest|default`):
    the effective idle-unload period. It comes from the pack manifest's `idle_unload_after`, the
    per-engine env override wins (see `docs/ENV_REFERENCE.md`), and packs installed before the field
    existed use the engine default. After the period the worker stops and `state` returns to `idle`;
    the next request reloads it. The manifest value is also on `pack.idle_unload_after`.
  - `elapsed_s`: seconds spent in the current `loading`/`warming` phase, else `null`.
  - `estimated_s`: expected length of the current phase where it has been measured (Kitten TTS 2
    `warming`: 35), else `null`.
  - `error`, `mode` (`compiled|eager|mlx`; `null` until warm-up has finished) and `fast_mode_issue`
    with `code`, `message`, `action`, `help_url`, `detail` when fast mode is unavailable.
  While `loading` or `warming`, `POST /v1/audio/speech` for that engine answers a retryable 503
  (see "Engine warm-up").
- Provisioned packs also carry `install_check`: one short sentence synthesised through the pack's
  own worker right after its install verified, timed after the engine's warm-up (Kitten TTS 2's
  compile-heavy first call is sent as the `warmup` request and kept out of the timing; engines
  without a warm-up get one untimed priming call). `null` for built-ins and for packs installed
  before the check existed or with `ENGINE_INSTALL_SPEED_CHECK=0`. Fields:
  - `outcome`: `ok` (RTF at or under 1), `slow` (slower than real time on this machine) or
    `unavailable` (the worker could not be measured; see `error`). A slow machine is a labelled
    outcome, never an install failure, and the check never mints or changes the verification
    stamp (only the provisioner does).
  - `rtf` (compute seconds per second of audio), `compute_seconds`, `audio_seconds`,
    `warmup_seconds` (`null` when the engine had no separate warm-up), `device` (the worker's
    backend, for example `cuda` or `mlx`, else its mode, for example `cpu`), `mode`
    (`compiled|eager|mlx|cpu...`), `load_average` (1-minute, `null` where the OS has none), `note`
    (for example why fast mode is unavailable), `error`, `at` (UTC timestamp).
  The record is stored as `.install_check.json` in the pack directory and goes away with it.
  `POST /engines/{engine_id}/benchmark` is the separate, repeatable measurement (`benchmark`).
- Read-only and local: no network access, no model load.

### POST /engines/{engine_id}/verify

- Purpose: re-hash a pack's artifacts against the manifest pins and refresh its state.
- Response 200: `{ "engine": { ...card... } }` with `state.status = "verified"` when every
  artifact exists and matches, `invalid` with `state.errors` otherwise.
- Built-in engines are always verified. Unknown ids return 404.

### POST /engines/{engine_id}/install

- Purpose: download a pack's artifacts from the URLs pinned in its manifest, resume partial
  downloads, verify size and SHA-256, then publish the verification stamp.
- Response 200: `{ "engine": { ...card... }, "state": { ... } }` with `state.status = "verified"`.
- 409: no manifest, active install, not enough disk, unsupported source scheme, or verification
  failure (`{ "error": "..." }`). Partial downloads are kept as `<artifact>.part` for retry;
  unverified bytes are never published as the artifact.

### POST /engines/kitten2/install

- Purpose: provision the Kitten TTS 2 pack in the background: a private Python 3.12 environment, the
  GPU runtime on NVIDIA machines, `kittenml`, and the model weights (about 2.4 GB), then a
  verification stamp. The pack runs offline afterwards.
- 202: `{ "started": true, "job": { ... } }`. 409 (`started: false`) when an install is already
  running. Poll `GET /engines/kitten2/install` (or `GET /engines`) for `job.state`, `step`,
  `step_index` / `step_count`, and `error`. Retrying resumes: an existing environment is reused.
- Supported machines: Apple silicon (MLX) and NVIDIA GPUs with a recent driver (CUDA 12 or 13,
  chosen automatically). Linux CUDA shares the code path but is untested. Unsupported machines get
  a plain-language reason in `job.error`.

### POST /engines/phonon-31m/install

- Purpose: provision the Phonon 31M pack in the background (same job shape, polling and retry
  behaviour as `POST /engines/kitten2/install`): a private Python environment, the `ptts` native
  runtime, and the model plus the English voice catalog (about 70 MB). No GPU, torch or compiler is
  needed; it takes under a minute. A final offline synthesis proves the prefetch is complete.
- Needs a CPU with AVX2 on Intel/AMD (about 2013 or newer) or Apple silicon; otherwise
  `job.error` says so in plain language.
- Phonon cannot clone: naming a saved library voice returns 400. Its 37 English voices are listed
  as `phonon:<Name>` (names can contain spaces). `POST /engines/phonon-31m/recheck` reloads it.
- **Streaming:** `response_format: "pcm"` streams raw int16 PCM as the model produces it (first
  bytes in about 20 ms on Apple silicon); other formats return the whole clip. Disconnecting
  mid-stream stops the worker, and the next request restarts it in about 0.1 s.
- **`speed`:** a number, honoured by Phonon only, from about 0.73 to 1.5 (values outside are
  clamped). The mapping is calibrated on one sentence, so the resulting length is approximate
  (1.34 gave 1.33x, 0.82 gave about 0.90x on another). Engines without a speed control ignore it,
  as before; streaming responses carry `X-Speed-Applied: true|false`. A non-numeric `speed` is 400.

### POST /engines/kokoro/install

- Purpose: provision the Kokoro 82M pack in the background (same job shape as the other packs): a
  private Python environment, `kokoro-onnx` (its phonemizer library is bundled in the wheel, so no
  system `espeak-ng` is needed), and the int8 model plus voice file (about 120 MB) from a pinned
  release, verified by size and SHA-256. Takes about ten seconds to a minute on a good connection.
- Voices are `kokoro:<voice>` (41 listed: English US/UK, Spanish, French, Hindi, Italian,
  Portuguese). The voice name selects the language, so `language` is ignored. Japanese and Chinese
  voices exist upstream but need extra packages and are not served. No cloning: a saved-voice
  request is 400. `speed` (0.5-2.0) is honoured natively; output is not frame-streamed.
- ONNX Runtime is pinned to four threads (fewer on smaller machines): its default oversubscribes
  and was 2-3x slower on Intel.
- Network failures while downloading say so plainly and are retried by choosing Install again.

### POST /engines/pocket-lite/install

- Purpose: provision Pocket Lite, the 18M-parameter Pocket checkpoint (`english_18m_2026-10`), in the
  background (same job shape as the other packs). It runs on the application's own Python, so there is
  no virtual environment: the install downloads the model and 21 English voices (about 190 MB) into
  the pack's own `hf/` folder, then verifies them offline. About a minute and a half on a good link.
- **Needs a Hugging Face token** whose owner has accepted the terms of the gated `kyutai/pocket-tts`
  repository (cloning weights live there): `HF_TOKEN` or `huggingface-cli login`. A missing token or
  unaccepted terms fails with a message that says so; nothing is accepted on the user's behalf. The
  token goes to the download process only and is never stored or logged.
- Clones a saved voice from its reference clip (no transcript needed) and serves the English presets as
  `pocket-lite:<name>` (the standard `pocket:<name>` names also work). `seed` is honoured (repeat runs
  agree to within one 16-bit step, the same as the standard model); `speed` is not supported. With
  `response_format: "pcm"` it streams raw int16 PCM as the model produces it, like Phonon, for presets
  and cloned saved voices (first audio about 0.02 s warm on the Mac, against 0.3 s for a whole clip;
  the streamed audio matches the whole-clip render within one 16-bit step). Its voice states are
  separate from the standard Pocket runtime.

### POST /engines/kitten2/recheck

- Purpose: reload the engine in the background so a newly installed compiler is picked up (fast
  mode on NVIDIA needs a C++ compiler: Microsoft C++ Build Tools on Windows, `build-essential` on
  Linux). No restart is needed.
- 202 `{ "started": true, "status": { ... } }`; 409 when the pack is not installed or a load is
  already running.

### POST /engines/{engine_id}/remove

- Purpose: delete a pack directory (manifest and artifacts). Built-in engines have no pack.
- 200: `{ "removed": "<engine_id>" }`.
- 409: the engine is active — switch engines first.
- 409: the engine serves the API default (a pack voice, or a saved voice cloned on it). Body:
  `{ "error": "<Engine> serves the API default voice '<voice>'. Change the API default first, then
  remove the engine.", "code": "api_default_engine", "api_default": { "engine", "voice" } }`. The pack
  stays on disk. `GET /engines` cards carry `api_default: true` for that engine so a UI can say why
  Remove is unavailable.
- 404: no removable pack for that id.

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
  - `shell` — the server's host context (`"desktop"` when spawned by the desktop shell via
    `PERSONA_FORGE_SHELL=desktop`, else `null`). The SPA hides its web update banner when this
    is `"desktop"` (contract D13).
  - `ref_text_validation` — startup validation for the configured reference audio/text.
  - `ref_text_diagnostic` — when `REF_AUDIO` is a readable file, identifies the mounted
    library voice (`voice_id`), `audio_path`, text source, and persisted
    `active_api_voice_id`. This lets clients link a mismatch to the exact Voice Library
    record; the active API voice may legitimately be a different saved voice.

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

### GET /ui/preferences

- Purpose: read the saved UI preferences (contract D17 / §6.11). Works before the model loads
  (never 503).
- Response (JSON): `{"values": {...}}` — `{}` when nothing has been saved yet.
- Persisted to `ui_preferences.json` in the same directory as `runtime.json`.

### /compare/results

Saved Compare-tab listening sessions (`compare_results.json` next to `ui_preferences.json`).

- `GET`: `{count, summary}`. `summary` has one row per engine: `clips`, `natural`, `clean`,
  `similarity` (null when no cloned clip was rated), `favourites`, `speed_median` and `speed_worst`
  (generation seconds per second of audio).
- `POST {sessions: [{at, text, slots: [{engine, voice, voiceName, ms, seconds, naturalness,
  artifacts, similarity, favourite}]}]}`: appends validated sessions (ratings 1-5, at most 8 slots,
  newest 500 kept). 400 on a malformed session, 413 above 512 KB.
- `DELETE`: clears all saved sessions.

### API language enforcement

The UI preference `api.enforceLanguage` (Integrations page, "Enforce English on the API", default
off) makes `POST /v1/audio/speech` return 400 for a non-English voice or a non-English `language`,
with a message naming the voice and the setting. Off, any voice is served even when hidden from
`/v1/audio/voices`.

### POST /engines/{engine_id}/benchmark

Times one cold and three warm requests of a fixed sentence through `/v1/audio/speech` (first
preset voice, or the first saved voice for cloning engines) and saves the result to
`engine_benchmarks.json`. Returns `{engine, benchmark}` with `cold_seconds`, `rtf_median`,
`rtf_worst` (generation seconds per second of audio), `warm_runs`, `load_average`, `voice`, `at`.
The cold run waits through an engine's `loading`/`warming` phases (retrying the `engine_warming` 503), so `cold_seconds` includes the warm-up. 404 unknown engine, 400 when no voice is available, 409 when another benchmark is running or the
engine cannot serve (for example a pack that is not installed). `GET /engines` cards now carry
`hardware_fit` (`level` of `recommended`, `ok`, `unsupported`, `unknown`, and `text`) and `benchmark`
(the saved result or null). The result depends on machine load, so the card shows the load average.

### POST /ui/preferences

- Purpose: merge UI preference values (theme, experience level, voice-library layout/toggle,
  dismissed update version). Unknown keys and invalid values are rejected, so a stale client
  cannot corrupt the store.
- Request (JSON): `{"values": {<key>: <value>, ...}}`.

Allowed keys:

| Key | Value |
| --- | --- |
| `theme` | string, ≤ 32 chars |
| `experienceLevel` | string, ≤ 32 chars |
| `voiceLibrary.tab` | `"voices"` or `"segments"` |
| `voiceLibrary.layout` | string, ≤ 32 chars |
| `voiceLibrary.analysisExpanded` | boolean |
| `updates.dismissedVersion` | string, ≤ 64 chars |

- 200: full merged `{"values": {...}}`.
- 400: invalid JSON, `values` missing or not an object, unknown key, or invalid value
  (`{"error": "<message>"}`).
- 413: body larger than 16 KB.
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
- If the voice is the API default on the active backend, the default is cleared. If it is the API
  default on a pack engine, the record stays and reports `problem.code = "voice_missing"` (see
  `GET /api-default`), so requests without a voice fail with the repair message instead of using
  another speaker.

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

### GET /api-default

- Purpose: the effective no-voice API default: engine + voice + variant. Persisted separately from
  Speak's transient selection. `{ "default": null }` when none is set.
- 200 `{ "default": { ... } }` with `voice` (`vd_...` saved voice, `pocket:<name>`, or a pack voice:
  `kokoro:<voice>`, `phonon:<Name>`, `kitten2:<Name>`, `pocket-lite:<name>`), `engine` (the active
  backend such as `pocket_tts` for Pocket voices and for saved voices served by the active backend,
  or the pack engine id such as `kokoro`, `phonon-31m`), `engine_label`, `variant`, `kind`
  (`preset`|`library`), `display_name`, `language`, `language_code`, `updated_at`, `source`
  (`record`|`legacy`), `servable` and `problem`.
- `problem` is `null` when the default can be served. For a default on a pack engine it is
  `{ "code", "engine", "message", "repair" }` when it cannot: `engine_not_installed` (the pack was
  removed or is damaged) or `voice_missing` (the pack no longer offers the voice, or the saved voice
  was deleted); `servable` is then `false`. `repair` is the action to take: reinstall the engine, or
  choose another default. The record is kept so the problem stays visible; it is never replaced
  silently. Defaults served by the active backend (Pocket presets, saved voices) behave as before:
  a deleted saved voice clears the default.

### PUT /api-default

- Purpose: set the default. Body: `voice` (required), `engine` (optional), `variant` (optional).
- A pack voice (`kokoro:af_heart`) is served by that pack engine whatever `engine` says; an `engine`
  that disagrees is a 400. A saved voice (`vd_...`) stays on the active backend unless `engine` names
  an installed pack engine that clones (`kitten2`, `pocket-lite`): then requests without a voice
  clone it on that engine (it is prepared on the first request). Saved voices on the active backend
  keep their hot-swap behaviour and the legacy `.active_default` mirror; a pack-engine default clears
  that mirror because it does not change the active backend's runtime voice.
- Validated against the registry at set time: the engine must be installed and the voice offered
  (or, for a saved voice, exist, and have a transcript where the engine needs one).
- Persisted atomically (`<voice library>/.api_default.json`); if a write fails the previous default
  is restored whole and a saved-voice activation is rolled back. It survives restarts.
- 200: `{ "default": { ... } }` as in `GET`. 400: invalid body, id shape, unknown namespace, engine
  and voice disagree, an engine that cannot clone a saved voice, or a saved voice without the
  transcript the engine needs. 404: unknown voice. 409: engine not installed, or a Pocket preset
  while another backend is active. 500: the default could not be saved.

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

### GET /omnivoice/audition/progress?job_id=

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

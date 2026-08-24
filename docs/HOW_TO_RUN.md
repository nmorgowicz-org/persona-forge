# How to run Persona Forge

This document is for anyone deploying or operating this container. Internal host-specific
procedures are in [INTERNAL_OPERATIONS.md](docs/dev/INTERNAL_OPERATIONS.md).

## Quick start (pocket-tts, no export required)

Persona Forge's default backend is pocket-tts (self-contained, no export step). This section covers
the zero-friction path. For optional Qwen3-TTS with OpenVINO acceleration, see the "Export
(optional)" section below.

Requirements: Linux AMD64, Docker with Compose, at least 10 GiB for the service.

1. Copy and edit the environment:

   ```bash
   cp .env.example .env
   # Optional: set REF_AUDIO_PATH for a default voice. REF_TEXT is optional; Whisper drafts it by default.
   # MODEL_SIZE and TTS_BACKEND default to 1.7B and pocket_tts respectively.
   ```

2. Start the service. By default `docker compose up` (without `--build`) resolves
   `PERSONA_FORGE_IMAGE` (unset → `persona-forge:local`), which doesn't exist yet on a fresh clone,
   so it builds from source. To skip the build and pull the published image instead, set
   `PERSONA_FORGE_IMAGE` in `.env` first:

   ```bash
   echo 'PERSONA_FORGE_IMAGE=ghcr.io/nmorgowicz-org/persona-forge:latest' >> .env
   ```

   Then either way:

   ```bash
   docker compose up -d persona-forge
   docker compose logs -f persona-forge
   ```

    First boot loads the model; subsequent boots are fast.
    Health will report `status: "starting"` until ready.

    On first boot the Pocket-TTS English model and built-in voice embeddings are downloaded
    once and verified against pinned SHA-256 checksums; they are cached in the persistent
    artifact directory (`POCKET_TTS_ARTIFACT_DIR`, default `<MODEL_CACHE_PATH>/pocket-tts`),
    so later boots never re-download. If the voice-cloning model cannot be fetched at all,
    the service still starts with the built-in voices only — `/health` reports
    `pocket_cloning_status: "degraded"` and `pocket_model_source` shows what loaded.
    Sourcing modes are controlled by `POCKET_TTS_MODEL_SOURCE` (see
    `docs/ENV_REFERENCE.md`, "Pocket-TTS artifact sourcing").

3. Verify:

   ```bash
   curl -fsS http://localhost:8318/health

   curl -sS http://localhost:8318/v1/audio/speech \
     -H 'Content-Type: application/json' \
     -d '{"input":"This is a test.","response_format":"mp3"}' \
     -o test.mp3
   ```

## Export (optional: Qwen3-TTS engine)

Only run this section if you want to use the Qwen3-TTS engine (available in PyTorch or OpenVINO).
The default pocket-tts backend needs no export. If using Qwen3-TTS with OpenVINO acceleration,
the export is memory-intensive; refer to the instructions below.

1. Stop the serving container (export is memory-intensive):

   ```bash
   docker compose down persona-forge
   ```

2. Export IR (one time per model size / config change; uses 13–14 GiB):

   ```bash
   docker compose run --rm export
   ```

3. Start the service with OpenVINO backend:

   ```bash
   TTS_BACKEND=openvino docker compose up -d persona-forge
   docker compose logs -f persona-forge
   ```

   First boot warms the OpenVINO kernel cache (60–120s).

4. Verify:

   ```bash
   curl -fsS http://localhost:8318/health

   curl -sS http://localhost:8318/v1/audio/speech \
     -H 'Content-Type: application/json' \
     -d '{"input":"This is a test.","response_format":"mp3"}' \
     -o test.mp3
   ```

Only port 8318 is exposed. The same image is used for serving and exporting; the Compose
`export` service overrides the command.

### Using the web UI

By default, `FRONTEND_ENABLED=1` and the UI is available at `http://localhost:8318/`:

- Speak: text-to-speech with voice selection.
- Voice Design: guided creation of new voices from text descriptions.
- Voice Library: browse, preview, edit, and delete generated voices.
- Integrations: OpenAI-compatible API snippets using your voices.
- Runtime: adjust live settings (backend, idle unload, silence trim, etc.).

Set `FRONTEND_ENABLED=0` to run as an API-only service.

### Using VoiceDesign / voice library (optional)

If you want to generate new voices and use them as clone targets:

1. After exporting the Base model (Quick start, step 2), run:

   ```bash
   docker compose run --rm export-voice-design
   ```

   This writes a separate VoiceDesign IR under `/ov/1.7B-voicedesign/...` and is required before
   VoiceDesign will work.

2. Ensure `OPENVINO_KEEP_CODEC_ENCODER=1` (the default; set in `.env` or via the Runtime panel
   if it was overridden). With the codec encoder released (`0`), a new `voice_id` cannot be
   cloned on first use. Keeping it at `1` uses ~0.3 GiB more but enables full voice library
   functionality.

3. Create a new voice:
   - In the UI: open Voice Design, choose chips or write a description, generate, and save.
   - Or via curl:

     ```bash
     curl -sS http://localhost:8318/voice_design \
       -H 'Content-Type: application/json' \
       -d '{"description":"An older British man, calm and gravelly.",
            "sample_text":"The old lighthouse stood against the storm."}'
     ```

4. Use the returned `voice_id` in `/generate` or `/v1/audio/speech`, or select it from the
   Voice Library in the UI.

Note: `POST /voice_design` briefly swaps the resident model and causes 503 for a short period
(typically 5–30 seconds if the kernel cache is warm).

## Operator reference

This section is for day-to-day operators: what to change and what to leave alone.

### Essential settings

The service can start without a default reference voice. In `.env` (or your Compose environment):

- `MODEL_SIZE` — `1.7B` (recommended) or `0.6B`.
- `REF_AUDIO_PATH` — optional absolute host path to a default reference WAV. When present, it is mounted, promoted into the Voice Library, and analyzed with Whisper.
- `REF_TEXT` — optional power-user override for the mounted reference transcript. If omitted, `REF_TEXT_AUTO=whisper` drafts it automatically for Qwen backends. Pocket TTS ignores transcript text.

Normal users only need to choose a model size and optionally add or generate a voice in the app.

### Recommended settings (for most real deployments)

- `LOW_RAM_MODE=1` — enables aggressive glibc memory tuning + idle unload. Recommended on
  hosts with < 20 GiB free RAM.
- `PERSONA_FORGE_IMAGE=ghcr.io/nmorgowicz-org/persona-forge:<sha>` — pin your production image.
- `TTS_MEMORY_LIMIT`, `TTS_MEMORY_SWAP_LIMIT` — adjust for your host (defaults 10G/11G).
- For all other knobs (threading, quantization, silence trim, codec behavior, etc.), see
  Advanced settings reference below and the .env.example comments.

### Memory and sizing

Both model sizes use ~5.4–5.8 GiB steady. Export uses 13–14 GiB.

| Available RAM | Guidance |
|---|---|
| ≥ 28 GiB | Can export and serve simultaneously; can raise `TTS_MEMORY_LIMIT` to 16G. |
| 16–27 GiB | Stop serving before export. Raise `TTS_MEMORY_LIMIT` to 12–14G if desired. |
| 10–15 GiB | Stop serving before export. Keep default limits. |
| < 10 GiB | Service will not fit. |

`LOW_RAM_MODE=1` enables:
- Glibc malloc tuning (`MALLOC_MMAP_THRESHOLD_=65536`, `MALLOC_ARENA_MAX=1`).
- Idle unload after 30 minutes (override with `IDLE_UNLOAD_SECONDS`).
- Python `malloc_trim(0)` after unload.
No jemalloc / tcmalloc: allocator replacement caused SIGABRT/SIGSEGV under transformers 5.x.

`TTS_MAX_SPEECH_SECONDS` (default 300):
- qwen3-tts-engine-only (pytorch/openvino); `pocket_tts` never reads this and is unbounded.
- Controls max audio duration per request. For `openvino`, baked into IR at export time.
- Is a latency/safety cap, not a memory lever. Changing it saves/costs on the order of
  hundreds of MiB, not gigabytes.
- Must match between `export` and `persona-forge` for `openvino`; changing it requires re-exporting.
- On CPU, `QWEN3_ENGINE_CPU_MAX_NEW_TOKENS` (default 300 tokens, ~25s) is a separate,
  tighter hang-avoidance clamp applied to both `pytorch` and `openvino` — raising
  `TTS_MAX_SPEECH_SECONDS` alone won't get you longer CPU generations past that.

### Runtime control (no restart needed)

`GET/POST /runtime/config` (and the Runtime panel in the UI) let you adjust settings live:

- Live-adjustable:
  - `TTS_BACKEND` (openvino | pytorch | pocket_tts)
  - `IDLE_UNLOAD_SECONDS`
  - `SILENCE_TRIM`, `SILENCE_TRIM_THRESH`, `SILENCE_TRIM_PAD_MS`
  - `OV_DYNAMIC_QUANT_GROUP_SIZE`
- Read-only:
  - Mount modes, optional `REF_AUDIO_PATH` status, `HF_TOKEN` set?, device, dtype, reference-text/Whisper review state.
- Requires re-export (openvino only) / restart (pytorch):
  - `TTS_MAX_SPEECH_SECONDS`, quantization. (`pocket_tts` never reads this setting.)

Changing `TTS_BACKEND` or `OV_DYNAMIC_QUANT_GROUP_SIZE` briefly reloads the model (serialized,
no dropped requests).

### Advanced settings reference

Use these only if you have a reason. All other internals are preset-derived and work out of the box.

**`TTS_BACKEND`** (default `openvino`)
- Set to `pytorch` as a rollback backend when OpenVINO IR is broken or missing.
- PyTorch is slower and does not use the IR, but is useful for verification.
- Change live via Runtime panel or `.env`; triggers a model reload.

**`OV_INFERENCE_THREADS`** (default `6`)
- Number of CPU threads for OpenVINO transformer + vocoder and PyTorch glue.
- Set this to your physical core count (not hyperthreads) for best latency.
- Beyond physical cores there are no gains; too many threads can cause contention.

**`OV_DYNAMIC_QUANT_GROUP_SIZE`** (default `32`)
- OpenVINO dynamic quantization for inference:
  - `0` = disabled (baseline accuracy, slower)
  - `32` = default (slight speedup, negligible quality loss)
  - `64` = faster, slightly lower accuracy (useful only on very constrained hosts)
- Change live via Runtime panel or `.env`; triggers a model reload.

**`OV_CACHE_DIR`** (default `/ov/cache`)
- OpenVINO compiled kernel cache directory. Leaving this default eliminates 60–120s of
  JIT recompilation on every restart or idle-unload reload.
- Set to empty string (`""`) to disable (useful only for controlled testing).

**`OPENVINO_KEEP_CODEC_ENCODER`** (default `1`)
- Controls whether the ~0.3 GiB PyTorch codec encoder stays loaded after startup:
  - `1` (default): codec stays loaded; any `voice_id` can be cloned immediately. Needed for VoiceDesign and the voice library.
  - `0`: codec is released after startup; saves ~0.3 GiB. Uncached `voice_id` fails with a clear error instead of silently cloning.
- Set `0` only for single-voice deployments (e.g. Hermes) that never need voice-library/VoiceDesign cloning.

**`IDLE_UNLOAD_SECONDS`** (default `0` or `1800` with `LOW_RAM_MODE=1`)
- Unload the model after this many seconds of idle. Reload is automatic and transparent
  but adds ~5–30s of latency on first request if the kernel cache is warm.
- `LOW_RAM_MODE=1` sets this to 1800 automatically.
- Useful on shared hosts where RAM is needed for other workloads.

**`TTS_MAX_SPEECH_SECONDS`** (default `300`)
- qwen3-tts-engine-only (pytorch/openvino); `pocket_tts` never reads this and is unbounded.
- Maximum duration for a single request. For `openvino`, baked into the IR at export time.
- Is a latency/safety cap, not a memory lever. Use it to bound worst-case latency and fail
  fast on runaway or misbehaving requests.
- Must match between `export` and `persona-forge` for `openvino`. Changing it requires re-exporting.
- On CPU, see `QWEN3_ENGINE_CPU_MAX_NEW_TOKENS` below — it's a separate, tighter clamp
  that applies regardless of this setting.

**`QWEN3_ENGINE_MAX_NEW_TOKENS`** (default `800`)
- qwen3-tts-engine-only. Base per-request token ceiling, before the CPU clamp below.

**`QWEN3_ENGINE_CPU_MAX_NEW_TOKENS`** (default `300`, ~25s of audio)
- qwen3-tts-engine-only. Hang-avoidance cap forced whenever `pytorch` or `openvino` is
  running on CPU (no iGPU deployment has been validated yet — both backends run the same
  qwen3-tts engine and are too slow on CPU to safely decode without this). The tighter of
  this and `TTS_MAX_SPEECH_SECONDS`-derived capacity always wins.

**`QWEN3_ENGINE_CPU_BF16_MAX_NEW_TOKENS`** (default `160`)
- qwen3-tts-engine-only. Extra-tight cap for `pytorch` + `bfloat16` specifically — that
  combination is known to hang or diverge on many CPUs.

**`SILENCE_TRIM` / `SILENCE_TRIM_THRESH` / `SILENCE_TRIM_PAD_MS`**
- Trim leading/trailing silence from generated audio.
  - `SILENCE_TRIM=1` (default) with threshold `0.01` and `30 ms` padding.
  - Disable (`SILENCE_TRIM=0`) only if output is clipped or you need the raw waveform.
- Tunable live via Runtime panel or `.env`.

**`HF_TOKEN`** (unset by default)
- Set if the checkpoint is gated in your environment (e.g., new HF account, specific region).
- Never log or commit this. Use Docker secrets or `HF_TOKEN_FILE` in production.

**`MODEL_REVISION`** (unset by default)
- Pin a specific Hugging Face revision. If set, must match exported IR metadata.
- Useful for strict reproducibility; generally unnecessary if you pin the image.

**`VOICE_DESIGN_MODEL_SIZE`** (default `1.7B`)
- Only relevant if you're deploying VoiceDesign with a different size.
- Today only 1.7B ships a VoiceDesign checkpoint.

**`VOICE_DESIGN_MAX_SPEECH_SECONDS`** (default `20`)
- Capacity baked into the VoiceDesign IR at export time. Must match between
  `export-voice-design` and `persona-forge`. Change only if you need longer VoiceDesign samples.

## HTTP API reference

- `GET /health`
  - Health, readiness, OpenVINO status, and `swap_in_progress`.

- `POST /v1/audio/speech` (OpenAI-compatible)
  - `{ "input": "text", "language": "English", "response_format": "mp3|wav", "voice_id": "vd_...", "instruct": "...", "prosody_repair": true }`
  - `voice_id` selects a saved voice from the library.
  - `prosody_repair` is an explicit batch/offline opt-in. It uses the input text and returns
    `X-Prosody-Repair-Outcome`; timeout preserves the original output.

- `POST /generate` (native)
  - Same fields as above but `text` instead of `input`.

- `POST /generate/stream`
  - Returns headerless mono float32 LE PCM with `X-Audio-*` headers for low-latency playback.

- `POST /voice_design`
  - `{ "description": "...", "sample_text": "...", "language": "English", "seed": 123 }`
  - Returns `{ "voice_id", "sample_rate", "seed", "audio_base64" }`.
  - Briefly swaps the model; other endpoints return 503 during the swap.

- `GET /voices`
  - Lists all saved voices.

- `GET /voices/<voice_id>`
  - Metadata + sample audio (`audio_base64`).

- `DELETE /voices/<voice_id>`
  - Deletes a saved voice.

- `GET/POST /runtime/config`
  - See Runtime control section above.

`seed` is optional; `/generate` and `/v1/audio/speech` report the used seed via `X-Seed` header.
`/stream_internal` and `/batch_internal` are internal parity endpoints, not stable APIs.

## Rollback

- Fastest: restore previous immutable image and restart Compose.
- Backend fallback: set `TTS_BACKEND=pytorch` (via `.env` or Runtime panel). Slower,
  no OpenVINO IR needed.

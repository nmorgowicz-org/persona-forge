# How to run Qwen3-TTS OpenVINO

This document is for anyone deploying or operating this container. Internal host-specific
procedures are in [INTERNAL_OPERATIONS.md](docs/dev/INTERNAL_OPERATIONS.md).

## Quick start

Requirements: Linux AMD64, Docker with Compose, Intel CPU, at least 10 GiB for the service, a
reference WAV, and its exact transcript.

1. Copy and edit the environment:

   ```bash
   cp .env.example .env
   # Set REF_AUDIO_PATH and REF_TEXT.
   # MODEL_SIZE=1.7B is recommended and is the default.
   ```

2. Export IR (one time per model size / config change; uses 13–14 GiB):

   ```bash
   docker compose run --rm export
   ```

   On a constrained host (10–15 GiB), stop the serving container first:
   ```bash
   docker compose down qwen3-tts
   ```

3. Start the service:

   ```bash
   docker compose up -d qwen3-tts
   docker compose logs -f qwen3-tts
   ```

   First boot is slow: it loads the model and warms the OpenVINO kernel cache.
   Health will report `status: "starting"` until it finishes.

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

2. Ensure `OPENVINO_RELEASE_CODEC=0` (set in `.env` or via the Runtime panel). With the codec
   released (`1`), a new `voice_id` cannot be cloned on first use. Setting it to `0` uses
   ~0.3 GiB more but enables full voice library functionality.

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

### Essential settings (set these)

In `.env` (or your Compose environment):

- `REF_AUDIO_PATH` — absolute host path to your reference WAV (REQUIRED).
- `REF_TEXT` — exact transcript of the reference WAV (REQUIRED).
- `MODEL_SIZE` — `1.7B` (recommended) or `0.6B`.

These three are all you strictly need beyond the defaults.

### Recommended settings (for most real deployments)

- `LOW_RAM_MODE=1` — enables aggressive glibc memory tuning + idle unload. Recommended on
  hosts with < 20 GiB free RAM.
- `QWEN3_TTS_IMAGE=ghcr.io/nmorgowicz-org/qwen3-tts-openvino:<sha>` — pin your production image.
- `TTS_MEMORY_LIMIT`, `TTS_MEMORY_SWAP_LIMIT` — adjust for your host (defaults 10G/11G).

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

`TTS_MAX_SPEECH_SECONDS` (default 64):
- Controls max audio duration per request. Baked into IR at export time.
- Is a latency/safety cap, not a memory lever. Changing it from 64s to 15s saves ~200 MiB,
  not gigabytes.
- Must match between `export` and `qwen3-tts`; changing it requires re-exporting.

### Runtime control (no restart needed)

`GET/POST /runtime/config` (and the Runtime panel in the UI) let you adjust settings live:

- Live-adjustable:
  - `TTS_BACKEND` (openvino | pytorch)
  - `IDLE_UNLOAD_SECONDS`
  - `SILENCE_TRIM`, `SILENCE_TRIM_THRESH`, `SILENCE_TRIM_PAD_MS`
  - `OV_DYNAMIC_QUANT_GROUP_SIZE`
- Read-only:
  - Mount modes, `REF_AUDIO_PATH` set?, `HF_TOKEN` set?, device, dtype.
- Requires re-export:
  - `TTS_MAX_SPEECH_SECONDS`, quantization.

Changing `TTS_BACKEND` or `OV_DYNAMIC_QUANT_GROUP_SIZE` briefly reloads the model (serialized,
no dropped requests).

### Advanced settings

Use these only if you have a reason. All others are preset-derived and work out of the box.

| Variable | Default | When to change |
|---|---|---|
| `TTS_BACKEND` | `openvino` | `pytorch` for rollback |
| `OV_INFERENCE_THREADS` | `6` | Set to your physical core count |
| `TTS_MEMORY_LIMIT` / `TTS_MEMORY_SWAP_LIMIT` | `10G` / `11G` | Raise on hosts with more RAM |
| `EXPORT_MEMORY_LIMIT` / `EXPORT_MEMORY_SWAP_LIMIT` | `13G` / `14G` | Only if export OOMs |
| `OPENVINO_RELEASE_CODEC` | `1` | Set `0` if using voice library / VoiceDesign; see above |
| `OV_DYNAMIC_QUANT_GROUP_SIZE` | `32` | `0` = off; `64` = faster, slightly lower accuracy |
| `OV_CACHE_DIR` | `/ov/cache` | Only change if you need to isolate caches |
| `SILENCE_TRIM` / `SILENCE_TRIM_THRESH` / `SILENCE_TRIM_PAD_MS` | `1` / `0.01` / `30` | Disable if audio is clipped |
| `HF_TOKEN` | unset | Set if checkpoint is gated |
| `MODEL_REVISION` | unset | Pin a specific revision |
| `VOICE_DESIGN_MODEL_SIZE` | `1.7B` | Only relevant if shipping other sizes |
| `VOICE_DESIGN_MAX_SPEECH_SECONDS` | `20` | Only change if you need longer VoiceDesign samples |
| `TTS_MAX_SPEECH_SECONDS` | `64` | Only change if you want a different per-request cap |

## HTTP API reference

- `GET /health`
  - Health, readiness, OpenVINO status, and `swap_in_progress`.

- `POST /v1/audio/speech` (OpenAI-compatible)
  - `{ "input": "text", "language": "English", "response_format": "mp3|wav", "voice_id": "vd_...", "instruct": "..." }`
  - `voice_id` selects a saved voice from the library.

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

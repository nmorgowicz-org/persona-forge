# Qwen3-TTS OpenVINO

CPU-only Linux AMD64 container for Qwen3-TTS voice-cloning checkpoints, accelerated on Intel CPUs
with OpenVINO.

One image, one process, one model, one server-side reference voice, port 8318. The same image
contains the export tooling.

## What it does

- Synthesizes speech in a cloned voice from a single reference WAV (no training).
- Two model sizes (`MODEL_SIZE=0.6B` or `1.7B`); 1.7B is recommended (same memory, better quality).
- OpenAI-compatible `POST /v1/audio/speech`.
- Web UI with Speak, Voice Design, Voice Library, Integrations, and Runtime tabs.
- VoiceDesign: generate new voices from a text description, save them, and use them as clone
  targets. Requires a separate export (see HOW_TO_RUN).
- MP3 or WAV output; incremental PCM stream available.
- `TTS_BACKEND=pytorch` rollback if OpenVINO misbehaves.

No authentication or TLS. Keep port 8318 on a trusted network or behind an authenticated reverse
proxy (see SECURITY.md).

## Quick start

Requirements: Linux AMD64, Docker Compose, Intel CPU, at least 10 GiB RAM for the service, a
reference WAV, and its exact transcript.

```bash
cp .env.example .env
# Edit .env: set REF_AUDIO_PATH and REF_TEXT. MODEL_SIZE=1.7B is recommended.

docker compose run --rm export
docker compose up -d qwen3-tts
curl -fsS http://localhost:8318/health
```

Generate:

```bash
curl -sS http://localhost:8318/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input":"Hello from Qwen three TTS.","response_format":"mp3"}' \
  -o output.mp3
```

For full deployment details, environment variables, VoiceDesign setup, streaming, and memory
tuning, see [HOW_TO_RUN.md](docs/HOW_TO_RUN.md).

## Model profiles

| Profile | Quality | Steady serving memory | Max request length | Recommendation |
|---|---|---|---|---|
| `0.6B` | Good | ~5.4–5.8 GiB | ~64 seconds | Only if you specifically need it |
| `1.7B` | Better | ~5.4–5.8 GiB | ~64 seconds | **Default — same memory, better output** |

Max request length is an export-time setting (`TTS_MAX_SPEECH_SECONDS`), primarily a
latency/safety cap, not a memory lever.

## HTTP API (summary)

- `GET /health`
- `POST /v1/audio/speech` (OpenAI-compatible)
- `POST /generate` (native)
- `POST /voice_design`
- `GET /voices`, `GET /voices/<id>`, `DELETE /voices/<id>`
- `GET/POST /runtime/config`

Full API details, streaming, and runtime/config semantics are in
[HOW_TO_RUN.md](docs/HOW_TO_RUN.md).

## Images

Published as `ghcr.io/nmorgowicz-org/qwen3-tts-openvino:<git-sha>` plus release-version and
`latest` tags. Production must use a SHA tag or digest; never `latest`.

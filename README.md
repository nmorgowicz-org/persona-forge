# Persona Forge

Open-source voice-cloning and voice-design studio: OmniVoice + pocket-tts on a portable CPU-first
backend (Intel iGPU via torch-xpu optional). Runs as a Dockerized web app on Linux AMD64.

One image, one process, multiple cloning engines, voice library, and inference server on port 8318.
Includes accent/persona design via OmniVoice and Qwen3-TTS (opt-in) export tooling.

## What it does

- Synthesizes speech in a cloned voice from a single reference WAV (no training).
- Two cloning engines: **pocket-tts** (default, portable) and **OmniVoice** (custom accent design).
- Optional Qwen3-TTS engine (PyTorch or OpenVINO acceleration) with two model sizes (0.6B/1.7B).
- OpenAI-compatible `POST /v1/audio/speech`.
- Web UI with Speak, Voice Design, Voice Library, Integrations, and Runtime tabs.
- VoiceDesign: generate new voices from a text description via OmniVoice, save them, and use as
  cloning targets. Requires a separate export (see HOW_TO_RUN).
- MP3 or WAV output; incremental PCM stream available.
- Intel iGPU acceleration via torch-xpu (optional, see docs/dev/LOCAL_SETUP.md).

No authentication or TLS. Keep port 8318 on a trusted network or behind an authenticated reverse
proxy (see SECURITY.md).

## Getting started

Prerequisites:

- Docker and Docker Compose
- Optional: a reference WAV file for a default cloned voice

Steps:

1. Copy `.env.example` to `.env`; set `HF_TOKEN` only if your selected models are gated. Optional: set `REF_AUDIO_PATH` for a default voice; Whisper drafts its transcript automatically.
2. `docker compose up --build persona-forge`
3. Run once to generate model artifacts: `docker compose run --rm --profile export export`
4. Open `http://localhost:8318`

For advanced configuration, environment variables, and tuning, see [docs/ENV_REFERENCE.md](docs/ENV_REFERENCE.md).

Working on the backend directly (not via Docker)? See [docs/dev/LOCAL_SETUP.md](docs/dev/LOCAL_SETUP.md)
for the `uv`-managed local dev environment.

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

Published as `ghcr.io/nmorgowicz-org/persona-forge:<git-sha>` plus release-version and
`latest` tags. Production must use a SHA tag or digest; never `latest`.

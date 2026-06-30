# Qwen3-TTS OpenVINO

Linux AMD64 container for the official Qwen3-TTS Base voice-cloning checkpoints, accelerated on
Intel CPUs with OpenVINO. It exposes a small OpenAI-compatible HTTP API and supports `0.6B` and
`1.7B` through one `MODEL_SIZE` setting.

## Quick start

```bash
cp .env.example .env
# Set REF_AUDIO_PATH, REF_TEXT, and MODEL_SIZE in .env.

docker compose run --rm export
docker compose up --build -d qwen3-tts

curl -sS http://localhost:8318/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input":"Hello from Qwen three TTS.","response_format":"mp3"}' \
  -o output.mp3
```

The export is stored under `./data/ov/<MODEL_SIZE>` and reused by later starts. Change
`MODEL_SIZE`, rerun the export, then restart the service to compare 0.6B and 1.7B.

See [HOW_TO_RUN.md](docs/HOW_TO_RUN.md) for operations, A/B testing, volumes, settings, and
benchmark collection. Development contracts and measured results are under [docs/dev](docs/dev/).
Security and private-reporting guidance is in [SECURITY.md](SECURITY.md).

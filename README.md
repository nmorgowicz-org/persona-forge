# Qwen3-TTS OpenVINO

CPU-only Linux AMD64 container for the official Qwen3-TTS Base voice-cloning checkpoints. It runs
the two autoregressive transformer cores and FP32 vocoder with OpenVINO on Intel CPUs, while keeping
prompt construction, sampling, and lightweight model glue in PyTorch.

The application is intentionally small: one image, one Gunicorn process, one model, one server-side
reference voice, and port `8318`. The same image also contains the export, quantization, parity, and
benchmark tooling.

## What it does

- Synthesizes speech in a cloned voice from a single reference WAV, no training required.
- Two model sizes (`MODEL_SIZE=0.6B` or `1.7B`). Both use roughly the same memory; 1.7B sounds better.
- OpenAI-compatible `POST /v1/audio/speech` — drop-in for clients that already speak the OpenAI TTS API.
- `POST /voice_design` generates a new reference voice from a free-text description (`Qwen3-TTS-1.7B-VoiceDesign`
  checkpoint) and saves it to a filesystem-backed voice library; pass its `voice_id` to any generate
  endpoint to clone it. This briefly swaps the resident model — see [HOW_TO_RUN.md](docs/HOW_TO_RUN.md).
- MP3 or WAV output; incremental PCM stream available for low-latency playback.
- Generated IR and model weights persist on the host — restarts are fast, no re-download.
- `TTS_BACKEND=pytorch` rollback if something goes wrong with the accelerated backend.

One fixed default reference voice per container, extendable at runtime via `POST /voice_design` +
`voice_id`. Authentication and TLS are not implemented — the service must run on a trusted network or
behind an authenticated reverse proxy.

## Quick start

Requirements: Linux AMD64, Docker Compose, an Intel CPU, a reference WAV with its exact transcript,
and at least 10 GiB available to the serving container. Export needs up to 13 GiB and must not run
beside the service on a constrained host.

```bash
cp .env.example .env
# Set REF_AUDIO_PATH and REF_TEXT in .env.  MODEL_SIZE defaults to 1.7B (recommended).

docker compose run --rm export
docker compose up --build -d qwen3-tts
curl -fsS http://localhost:8318/health

curl -sS http://localhost:8318/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input":"Hello from Qwen three TTS.","response_format":"mp3"}' \
  -o output.mp3
```

The first export downloads the selected checkpoint to `./data/model` and writes reusable IR to
`./data/ov/<MODEL_SIZE>`. Change `MODEL_SIZE`, run export again, and restart to change profiles.

## Model profiles

| Profile | Quality | Steady serving memory | Max request length | Recommendation |
|---|---|---|---|---|
| `0.6B` | Good | ~5.4–5.8 GiB | ~64 seconds of audio (`TTS_MAX_SPEECH_SECONDS`) | Only if you have a specific reason to avoid 1.7B |
| `1.7B` | Better | ~5.4–5.8 GiB | ~64 seconds of audio (`TTS_MAX_SPEECH_SECONDS`) | **Default — same memory, better output** |

Both profiles use nearly identical memory because the fixed inference engine overhead dominates the
model-size difference. The default 10G/11G container limits leave headroom for longer prompts. Max
request length is export-time only, set via `TTS_MAX_SPEECH_SECONDS` — it's a latency/safety cap, not
a memory lever (lowering it saves tens of MiB, not GiB); see
[HOW_TO_RUN.md](docs/HOW_TO_RUN.md) for RAM-tiered setup guidance and details.

## HTTP API

```text
GET  /health
POST /v1/audio/speech  {"input":"...", "language":"English", "response_format":"mp3|wav", "voice_id":"...", "seed":123}
POST /generate         {"text":"...",  "language":"English", "response_format":"mp3|wav", "voice_id":"...", "seed":123}
POST /generate/stream  {"text":"...",  "language":"English", "voice_id":"...", "seed":123}  -> mono f32le PCM

POST /voice_design     {"description":"...", "sample_text":"...", "language":"English"}
                       -> {"voice_id":"...", "sample_rate":24000, "audio_base64":"..."}
GET  /voices           -> {"voices": [...]}
GET  /voices/<voice_id> -> voice metadata + audio_base64
```

`/stream_internal` and `/batch_internal` are development parity endpoints, not stable public APIs.
The public stream reports format, sample rate, and channel count in `X-Audio-*` headers. If an error
occurs after audio starts, the connection closes and the partial audio must be discarded or handled
explicitly.

## Images and artifacts

Release automation publishes one image as immutable
`ghcr.io/nmorgowicz-org/qwen3-tts-openvino:<git-sha>` and also applies release-version and moving
`latest` tags. Production must use a SHA tag or digest. Model weights, OpenVINO IR, reference audio,
and generated speech are never included in the image; Compose bind-mounts them from the host.

See [HOW_TO_RUN.md](docs/HOW_TO_RUN.md) for deployment, streaming, rollback, memory measurement,
A/B listening, and benchmark collection. The implementation contract and measured evidence are in
[docs/dev/architecture/OPENVINO_IMPLEMENTATION.md](docs/dev/architecture/OPENVINO_IMPLEMENTATION.md) and
[docs/dev/benchmarks/OPENVINO_RESULTS.md](docs/dev/benchmarks/OPENVINO_RESULTS.md). Security guidance is in
[SECURITY.md](SECURITY.md); the service has no authentication or TLS and must remain on a trusted
network or behind an authenticated TLS reverse proxy.

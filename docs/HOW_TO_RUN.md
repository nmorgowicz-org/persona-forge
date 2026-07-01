# How to run Qwen3-TTS OpenVINO

## User quick start

Requirements: Linux AMD64, Docker with Compose, an Intel CPU, at least 10 GiB available container
memory, a reference WAV, and its exact transcript.

```bash
cp .env.example .env
```

Set these three values in `.env`:

```dotenv
REF_AUDIO_PATH=/absolute/path/to/reference.wav
REF_TEXT=The exact words spoken in the reference WAV
MODEL_SIZE=1.7B
```

Export once for the selected model, then start the service:

```bash
docker compose run --rm export
docker compose up --build -d qwen3-tts
docker compose logs -f qwen3-tts
```

The first export downloads the Hugging Face checkpoint into `./data/model` and writes OpenVINO IR
under `./data/ov/0.6B` or `./data/ov/1.7B`. Both directories are host bind mounts, so image rebuilds
do not redownload or re-export them. The reference WAV is mounted read-only at
`/voice/reference.wav`; `REF_TEXT` must match it exactly.

Serving and export use the same image. Its default command starts the API; the Compose `export`
service overrides that command with `python scripts/export.py`. Released images are tagged
`ghcr.io/nmorgowicz-org/qwen3-tts-openvino:<git-sha>` (plus version and moving `latest` tags on a
release). Production must pin the SHA tag or digest.

Check readiness and generate audio:

```bash
curl -fsS http://localhost:8318/health

curl -sS http://localhost:8318/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input":"This is a test.","response_format":"mp3"}' \
  -o test.mp3

curl -sS http://localhost:8318/generate \
  -H 'Content-Type: application/json' \
  -d '{"text":"This is a WAV test.","response_format":"wav"}' \
  -o test.wav
```

Only port 8318 is exposed. One Gunicorn process owns the model and serializes inference through a
single executor, avoiding duplicate model memory.

### What the containers do

There is one image and two Compose service definitions:

- `qwen3-tts` runs the image's default Gunicorn command and serves port 8318.
- `export` uses the same image but overrides its command with `python scripts/export.py`. It
  downloads the selected checkpoint if needed, exports/compresses the transformer IR, exports the
  FP32 vocoder, creates the stateful graph(s), and writes the stable `/ov/<MODEL_SIZE>` layout.

Export is a one-time operation per model size or source/dependency change. It can use 13–14 GiB,
whereas serving defaults to 10G/11G. On a 15 GiB host, stop `qwen3-tts` before exporting and never
run two model jobs concurrently.

### Bind mounts

| Host setting | Container path | Mode | Purpose |
|---|---|---|---|
| `MODEL_CACHE_PATH` (default `./data/model`) | `/root/.cache/huggingface/hub` | read/write | Reuses downloaded checkpoint files |
| `OV_DATA_PATH` (default `./data/ov`) | `/ov` | read/write | Stores generated IR by model size |
| `REF_AUDIO_PATH` | `/voice/reference.wav` | read-only | Fixed voice-clone reference used at startup |

`REF_TEXT` is an environment value, not a mount. It must be the exact transcript of the reference
WAV; a mismatch reduces speaker and pronunciation quality. Do not place tokens, private voices,
model caches, IR, or generated audio in the Git checkout.

## Compare 0.6B and 1.7B

**Recommendation: use `1.7B`.** It is slightly preferred on listening quality and has **no memory
penalty** — both profiles are dominated by a fixed OpenVINO/vocoder floor and land at roughly
5.4–5.8 GiB steady for normal single-utterance traffic (see *Memory expectations* below). The A/B
procedure remains here for anyone who wants to re-verify on their own hardware.

Run one model at a time on a 15 GiB host. Generate the same text, reference, format, and sampling
settings for both. Save audio outside Git.

```bash
# First run with MODEL_SIZE=0.6B in .env
docker compose run --rm export
docker compose up --build -d qwen3-tts
curl -sS http://localhost:8318/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input":"Use the same benchmark sentence for both models.","response_format":"wav"}' \
  -o /tmp/qwen-0.6B.wav

docker compose down
# Change MODEL_SIZE=1.7B, then repeat.
docker compose run --rm export
docker compose up -d qwen3-tts
curl -sS http://localhost:8318/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input":"Use the same benchmark sentence for both models.","response_format":"wav"}' \
  -o /tmp/qwen-1.7B.wav
```

Listen blind if possible. Record intelligibility, speaker similarity, prosody, repetition,
truncation, and artifacts. Also capture image ID, source commit, model revision, IR metadata hash,
latency, peak container RSS, host available RAM, and swap delta. The acceptance methodology is in
`docs/dev/OPENVINO_IMPLEMENTATION.md`; historical measurements are in
`docs/dev/OPENVINO_RESULTS.md`.

## Presets and advanced settings

`MODEL_SIZE` chooses the tested serving profile:

| Setting | 0.6B | 1.7B |
|---|---|---|
| Main transformer | INT8, stateful cache capacity 768 | INT4 asymmetric group 32, stateful cache capacity 768 |
| Predictor | INT8 stateful cache capacity 32 | INT8 explicit cache |
| Vocoder | FP32 OpenVINO | FP32 OpenVINO |
| Torch glue | BF16 low-memory load | BF16 low-memory load |
| Default memory/swap | 10G / 11G | 10G / 11G |

The stateful capacity is baked into the IR. Capacity 768 is about 64 seconds at 12 Hz, including
prompt and generated positions. A request exceeding it fails closed. Changing capacity requires a
new stateful transform plus parity and memory validation; it is not a runtime tuning variable.

### Memory expectations

Both sizes run at roughly **5.4–5.8 GiB** for normal single-utterance traffic and are safe under the
default 10G/11G limit. Steady memory is a large fixed OpenVINO floor (~2.7 GiB for the FP32 vocoder
plus runtime) plus a small variable delta, which is why **0.6B is not meaningfully smaller than
1.7B**. Long paragraphs push the generation peak higher as the stateful KV cache fills toward
capacity 768. On the OpenVINO backend the service frees the ~0.3 GiB PyTorch codec after startup
(`OPENVINO_RELEASE_CODEC`, on by default) once the voice prompt is built and the OpenVINO vocoder
owns decoding; the startup log prints `released ~0.32 GiB of PyTorch codec` when it does. Measured
A/B tables are in `docs/dev/OPENVINO_RESULTS.md`.

Explicit advanced environment values override preset defaults. Common examples are:

```dotenv
TTS_BACKEND=pytorch
MODEL_CACHE_PATH=/var/data/autopirate/qwen3-tts/model
OV_DATA_PATH=/var/data/autopirate/qwen3-tts/openvino-simplify-v2
TTS_MEMORY_LIMIT=10G
TTS_MEMORY_SWAP_LIMIT=11G
MODEL_REVISION=<pinned-hugging-face-revision>
HF_TOKEN=<token-if-the-checkpoint-requires-it>
OPENVINO_RELEASE_CODEC=0
```

Operational settings:

| Variable | Default | Meaning |
|---|---|---|
| `MODEL_SIZE` | `0.6B` | Selects the complete tested 0.6B or 1.7B preset |
| `QWEN3_TTS_IMAGE` | `qwen3-tts-openvino:local` | Unified serving/export image; pin SHA or digest in production |
| `QWEN3_TTS_PORT` | `8318` | Host port mapped to container port 8318 |
| `TTS_BACKEND` | `openvino` | Set `pytorch` for the rollback backend |
| `MODEL_REVISION` | unset | Optional Hugging Face revision pin; must match IR metadata for OpenVINO |
| `HF_TOKEN` | unset | Hugging Face access token when required; do not commit it |
| `TTS_MEMORY_LIMIT` / `TTS_MEMORY_SWAP_LIMIT` | `10G` / `11G` | Serving cgroup limits |
| `EXPORT_MEMORY_LIMIT` / `EXPORT_MEMORY_SWAP_LIMIT` | `13G` / `14G` | Export cgroup limits |
| `OPENVINO_RELEASE_CODEC` | `1` for OpenVINO | Frees the PyTorch codec after startup; disable for future per-request cloning |

`TTS_BACKEND=pytorch` is the rollback path and does not require exported IR. It still needs the
checkpoint cache and reference voice. Do not set exporter serving dtype overrides: graph conversion
requires its FP32 parity path.

`OPENVINO_RELEASE_CODEC` frees the PyTorch codec after startup for a smaller footprint and defaults
on (with the OpenVINO release-torch policy). The release is fail-closed: once freed there is no
PyTorch decode fallback, so an OpenVINO vocoder failure errors the request instead of silently
switching backends. Set it to `0` to keep the codec encoder resident — required for future
per-request voice cloning, and useful if you want the PyTorch vocoder fallback available.

## Streaming and validation endpoints

`POST /generate/stream` returns headerless mono float32 little-endian PCM. Read
`X-Audio-Sample-Rate`, `X-Audio-Channels`, and `X-Audio-Format`; if generation fails after bytes are
sent, the connection closes and the partial audio must be discarded or handled explicitly.

Save a raw stream and convert it to WAV with SoX:

```bash
curl -sS http://localhost:8318/generate/stream \
  -H 'Content-Type: application/json' \
  -d '{"text":"This response can begin playing while it is decoded."}' \
  -o /tmp/qwen-stream.f32le
sox -t raw -r 24000 -e floating-point -b 32 -c 1 -L /tmp/qwen-stream.f32le stream.wav
```

Use the sample rate returned by `X-Audio-Sample-Rate` rather than assuming 24000 in client code.

`POST /stream_internal` and `POST /batch_internal` are development parity endpoints. They accept
fixed seeds and sampling controls and return timing/parity headers. They are not stable public API.

## dockermisc1

Use the persistent host paths and run commands from a checkout of this repository:

```bash
export MODEL_CACHE_PATH=/var/data/autopirate/qwen3-tts/model
export REF_AUDIO_PATH=/var/data/autopirate/qwen3-tts/voice/voice_A.wav
export REF_TEXT='Exact transcript for voice_A.wav'
export MODEL_SIZE=0.6B

docker compose run --rm export
docker compose up --build -d qwen3-tts
docker stats --no-stream qwen3-tts
```

For a released image, replace the local build with an immutable tag:

```bash
export QWEN3_TTS_IMAGE=ghcr.io/nmorgowicz-org/qwen3-tts-openvino:<git-sha>
docker compose pull qwen3-tts
docker compose up -d qwen3-tts
```

Private GHCR pulls require `read:packages` credentials passed to `docker login --password-stdin`.
Never store the token in `.env` or Compose. The application itself has no authentication or TLS;
keep port 8318 on a trusted network or place it behind an authenticated TLS reverse proxy.

### Validation and benchmark capture

After every image, model, IR, or runtime-setting change:

```bash
curl -fsS http://localhost:8318/health | python -m json.tool
docker inspect --format '{{.Image}}' qwen3-tts
docker exec qwen3-tts cat /sys/fs/cgroup/memory.current

# Generate the committed benchmark prompts or fixed comparison text, then capture the resettable
# cgroup peak. Recreate the container before each A/B configuration.
docker exec qwen3-tts cat /sys/fs/cgroup/memory.peak
docker stats --no-stream qwen3-tts
```

Record source commit, immutable image tag/digest, model revision, IR metadata hash from `/health`,
backend, compression/cache profile, prompt, sampling settings, latency, audio duration/RTF, memory
current/peak, host available RAM, swap delta, and listening notes. Use deterministic greedy runs for
code/parity comparisons and production sampling for final listening and performance decisions.

### Rollback

The fastest production rollback is restoring the previous immutable image digest and restarting
Compose. The backend rollback is `TTS_BACKEND=pytorch`; it uses the checkpoint and reference mounts
but not OpenVINO IR. Verify `/health` reports `"backend": "pytorch"`, then generate a short WAV.
PyTorch is substantially slower and is a recovery path, not the preferred steady-state backend.

Stop only this project with `docker compose stop qwen3-tts`. Never run a second full-model job at
the same time, and never use blanket Docker stop, kill, or prune commands on the shared host.

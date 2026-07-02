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

## Sizing for your host

Both model sizes use nearly the same memory (~5.4–5.8 GiB steady) because the inference engine
overhead dominates the model-size difference. Export is the memory spike.

| Available RAM | Setup |
|---|---|
| **≥ 28 GiB** | Can export and serve at the same time. Optionally raise `TTS_MEMORY_LIMIT` to 16G for long requests. |
| **16–27 GiB** | Stop serving before export. Can raise `TTS_MEMORY_LIMIT` to 12–14G for longer requests. |
| **10–15 GiB** | Stop serving before export (default dockermisc1 setup). Keep default memory limits. |
| **< 10 GiB** | Serving will not fit. This service needs at least 10 GiB for the container. |

### Low RAM mode

Set `LOW_RAM_MODE=1` on hosts where RAM is shared with other workloads (VMs, LXCs, other containers):

```dotenv
LOW_RAM_MODE=1
```

This does three things together:

1. **jemalloc allocator** — replaces glibc malloc via `LD_PRELOAD` before Gunicorn starts. PyTorch and OpenVINO hold large intermediate allocations that glibc never returns to the OS even after they are freed; jemalloc with a 1-second decay actively purges those pages back to the kernel.
2. **Aggressive memory return** — `MALLOC_CONF=background_thread:true,dirty_decay_ms:1000,muzzy_decay_ms:1000` runs a jemalloc background thread that continuously returns unused pages.
3. **Idle unload** — model weights (~5–6 GiB) are released after 30 minutes of idle. The next request reloads them automatically. With the OV kernel cache warm (default), reload takes ~5–10s; on a completely cold first boot it takes ~60–120s while OV compiles kernels and writes the cache. Override the timeout with `IDLE_UNLOAD_SECONDS=<seconds>`.

`LOW_RAM_MODE` requires the container image to have `libjemalloc2` installed. All released images built after this feature was added include it. If you built an older local image, rebuild it.

The `/health` endpoint reports `model_loaded`, `process_rss_mib`, and `idle_unload_seconds` so you can observe the effect.

### Memory limits

The default `TTS_MEMORY_LIMIT=10G` is conservative. Raising it lets the container handle longer
requests without being killed by the cgroup limit:

```dotenv
TTS_MEMORY_LIMIT=14G     # comfortable on a 20+ GiB host
TTS_MEMORY_SWAP_LIMIT=15G
```

Long requests (several paragraphs) push memory higher as the model accumulates context. The hard
ceiling is roughly 64 seconds of generated audio per request regardless of memory limit — increase
it by re-exporting with a larger `TTS_MAX_SPEECH_SECONDS` (see below), not by raising the memory
limit.

### Max speech length (`TTS_MAX_SPEECH_SECONDS`)

The exported OpenVINO graph has a fixed-size internal K/V cache, so the longest possible single
request is baked in at export time — it cannot be changed at runtime, only by re-exporting.
`TTS_MAX_SPEECH_SECONDS` (default `64`) controls that ceiling in human units instead of raw frame
counts:

```dotenv
TTS_MAX_SPEECH_SECONDS=20   # e.g. a Hermes-style tool that only ever needs short utterances
```

Set the **same value** in `.env` for both the `export` and `qwen3-tts` services before running
`docker compose run --rm export` — the value selects both which capacity-keyed IR file gets built
(`main_stateful_cap<N>.xml`) and which one gets loaded. A request that would exceed the configured
limit fails fast with `stateful cache capacity exceeded`, reported in both frames and seconds, instead
of silently truncating or (pre-fix) free-running until it crashes.

**This is a safety/latency cap, not a memory-saving knob.** Peak container RSS is dominated by fixed
OpenVINO runtime + vocoder overhead (~7.3 GiB), with capacity contributing only ~0.5 MiB per second
of headroom (measured from the 768-vs-2048-frame A/B in `docs/dev/benchmarks/OPENVINO_RESULTS.md`) — lowering it
from 64s to 15s saves roughly 200 MiB, not gigabytes. Use it to bound worst-case latency and fail
closed on runaway/misbehaving requests, not to fit a smaller memory budget.

Leave it unset (or `64`) unless you have a specific reason to change it — the default reproduces the
exact IR filename and capacity every existing deployment already has on disk, so nothing changes for
existing setups.

### Threads

Set `OV_INFERENCE_THREADS` to your CPU's physical core count (not hyperthreads):

```dotenv
OV_INFERENCE_THREADS=8   # example for an 8-core CPU
```

The default is 6, tuned for the validated host. More threads = faster generation up to the core
count; beyond that there are no gains.

## Compare 0.6B and 1.7B

**Recommendation: use `1.7B`.** It sounds better and uses the same memory. The A/B
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
`docs/dev/architecture/OPENVINO_IMPLEMENTATION.md`; historical measurements are in
`docs/dev/benchmarks/OPENVINO_RESULTS.md`.

## Presets and advanced settings

`MODEL_SIZE` is the only setting most users need to change:

| Setting | Quality | Steady memory | Max request | Notes |
|---|---|---|---|---|
| `0.6B` | Good | ~5–6 GiB | ~64 sec | Use only if you have a specific reason |
| `1.7B` | Better | ~5–6 GiB | ~64 sec | **Recommended default** |

Both profiles use the same memory. The 64-second ceiling per request is the `TTS_MAX_SPEECH_SECONDS`
default (see above) — a property of the exported model, not runtime-adjustable; re-export with a
different `TTS_MAX_SPEECH_SECONDS` if you need a different ceiling.

After startup the service releases ~0.3 GiB of load-time overhead; the startup log prints
`released ~0.32 GiB of PyTorch codec` when this happens. Measured results are in
`docs/dev/benchmarks/OPENVINO_RESULTS.md`.

Explicit advanced environment values override preset defaults. Common examples are:

```dotenv
TTS_BACKEND=pytorch
MODEL_CACHE_PATH=/var/data/autopirate/qwen3-tts/model
OV_DATA_PATH=/var/data/autopirate/qwen3-tts/openvino
TTS_MEMORY_LIMIT=10G
TTS_MEMORY_SWAP_LIMIT=11G
MODEL_REVISION=<pinned-hugging-face-revision>
HF_TOKEN=<token-if-the-checkpoint-requires-it>
OPENVINO_RELEASE_CODEC=0
```

Operational settings:

| Variable | Default | Meaning |
|---|---|---|
| `MODEL_SIZE` | `1.7B` | `0.6B` or `1.7B`; 1.7B is recommended (same memory, better quality) |
| `TTS_MAX_SPEECH_SECONDS` | `64` | Longest single request the exported IR supports. Export-time only (re-export to change); must match between `export` and `qwen3-tts`. Not a meaningful memory lever — see above |
| `QWEN3_TTS_IMAGE` | `qwen3-tts-openvino:local` | Image to run; pin a SHA or digest in production |
| `QWEN3_TTS_PORT` | `8318` | Host port mapped to container port 8318 |
| `TZ` | `America/Detroit` | Container timezone for log timestamps |
| `TTS_BACKEND` | `openvino` | Set `pytorch` for the rollback backend (slower, no IR needed) |
| `MODEL_REVISION` | unset | Pin a specific Hugging Face revision; must match exported IR |
| `HF_TOKEN` | unset | Hugging Face token when required; do not commit it |
| `TTS_MEMORY_LIMIT` / `TTS_MEMORY_SWAP_LIMIT` | `10G` / `11G` | Serving container memory limits; raise on hosts with more RAM |
| `EXPORT_MEMORY_LIMIT` / `EXPORT_MEMORY_SWAP_LIMIT` | `13G` / `14G` | Export container memory limits |
| `LOW_RAM_MODE` | `0` | Set to `1` to enable jemalloc allocator, aggressive memory return, and 30-min idle unload. Recommended on hosts with less than 20 GiB free. Requires a rebuilt or freshly pulled image (jemalloc is installed at build time). |
| `OV_INFERENCE_THREADS` | `6` | CPU threads for inference; set to your CPU's physical core count |
| `OV_CACHE_DIR` | `/ov/cache` | OpenVINO compiled kernel cache directory. Already on the persistent `OV_DATA_PATH` mount — no extra setup needed. Eliminates ~60–120s JIT recompilation on every restart or idle-unload reload. Set to empty string to disable. |
| `OV_DYNAMIC_QUANT_GROUP_SIZE` | `32` | Inference speed/accuracy knob (`0` = off, `32` = default, `64` = faster/slightly lower accuracy) |
| `IDLE_UNLOAD_SECONDS` | unset | Unload the model after this many idle seconds (e.g. `1800` = 30 min). Frees ~5–6 GiB. Reload is automatic: ~5–10s with OV cache warm, ~60–120s on first cold boot. Disabled by default. Set automatically to `1800` by `LOW_RAM_MODE=1`. |
| `SILENCE_TRIM` | `1` | Trim trailing silence from output (`0` to disable if audio seems clipped) |
| `SILENCE_TRIM_THRESH` | `0.01` | Silence threshold as a fraction of peak amplitude |
| `SILENCE_TRIM_PAD_MS` | `30` | Milliseconds of audio kept after the silence boundary |
| `OPENVINO_RELEASE_CODEC` | `1` | Frees ~0.3 GiB of load-time overhead after startup; set `0` to keep it |

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
export MODEL_SIZE=1.7B

# Export IR once (stop qwen3-tts first if it is running — 13G export + 10G serve = OOM).
docker compose run --rm export

# Start the service using the released image rather than building locally.
export QWEN3_TTS_IMAGE=ghcr.io/nmorgowicz-org/qwen3-tts-openvino:v0.15.1
docker compose up -d qwen3-tts
docker stats --no-stream qwen3-tts
```

To update to a newer release, change `QWEN3_TTS_IMAGE` to the new version tag (or `:latest`) and
restart:

```bash
export QWEN3_TTS_IMAGE=ghcr.io/nmorgowicz-org/qwen3-tts-openvino:v0.15.1
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

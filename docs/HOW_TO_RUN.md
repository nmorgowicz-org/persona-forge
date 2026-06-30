# How to run Qwen3-TTS OpenVINO on `dockermisc1`

This is the operator runbook for starting the service, running isolated candidates, and collecting
reproducible benchmark data. Run these commands **on `dockermisc1`** unless a step explicitly says it
runs from the development Mac.

When an agent invokes `ssh` or `scp` from the development environment, those commands must be run
outside its sandbox. Do not retry a sandboxed network command as if DNS or SSH were broken.

## Safety rules

- `dockermisc1` is shared. Never use blanket `docker stop`, `docker kill`, `docker rm`, or `docker
  system prune` commands.
- Touch only a specifically named `qwen3-tts`, `qwen3-tts-candidate`, or `qwen-stream-test` container.
- Never run two full-model containers simultaneously. Check first:

  ```bash
  docker ps --format '{{.Names}} {{.Image}} {{.Status}}' | sort
  free -m
  swapon --show
  ```

- Keep model weights, IR, reference audio, generated audio, profiles, and credentials outside the Git
  checkout.
- Bind-mount the reference WAV read-only. `REF_TEXT` must be the exact transcript of that WAV.
- Use an immutable image digest or commit-SHA tag for production/candidate runs. `latest` is only a
  convenience pointer.
- A full 0.6B paragraph run needs an 8 GiB cgroup. Do not use the 7 GiB short-request setting for long
  prompts. Do not assume 1.7B fits until the selected loader/runtime configuration is measured.

## What each image/container does

### Runtime image

The runtime image starts `python serve.py`, which supervises two Gunicorn masters:

- Public API on port 8318: `/health`, `/generate`, and experimental `/generate/stream`.
- Model worker on port 8319: `/health`, `/infer`, `/infer_stream`, and the development-only
  `/stream_internal` parity endpoint.

Only publish port 8318. Port 8319 should remain inside the container except for an explicitly isolated
debug container bound to `127.0.0.1`.

The runtime image does not contain model weights or generated IR. Those are supplied through bind
mounts at startup.

### Exporter image

The exporter image contains everything in the runtime image plus conversion, parity, listening,
memory, and latency tools such as:

- `export_openvino.py`
- `test_transformer_parity.py`
- `test_ov_generation.py`
- `test_vocoder_parity.py`
- `test_stateful_main_parity.py`
- `dump_audio.py`
- `bench_speed.py`
- `scripts/transform_stateful_ir.py`

Use it for one-shot jobs. Do not run it as the serving container. Export/parity jobs usually need a
writable OpenVINO mount; serving needs that mount read-only.

### Downloader profile

The `qwen3-tts-download` Compose profile only populates the persistent Hugging Face cache. It does not
export OpenVINO IR. If the model is already present on `dockermisc1`, do not download it again.

## Persistent host data

Validated host roots:

```text
Model cache:   /var/data/autopirate/qwen3-tts/model
OpenVINO IR:   /var/data/autopirate/qwen3-tts/openvino
Reference WAV: /var/data/autopirate/qwen3-tts/voice/voice_A.wav
```

Current artifact directory names:

```text
0.6B explicit:
qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1

0.6B stateful:
qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1_stateful

0.6B FP32 vocoder:
qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1_vocoder

1.7B INT8 explicit:
qwen-tts-0.1.1_1.7b_fd4b25438912_ov-2026.2.1

1.7B INT4:
qwen-tts-0.1.1_1.7b_fd4b25438912_ov-2026.2.1_int4g32

1.7B FP32 vocoder:
qwen-tts-0.1.1_1.7b_fd4b25438912_ov-2026.2.1_vocoder
```

List before selecting a graph; do not guess a filename:

```bash
find /var/data/autopirate/qwen3-tts/openvino -maxdepth 2 \
  -type f -name '*.xml' -printf '%h/%f\n' | sort
```

## Bind mounts explained

| Host path | Container path | Mode | Purpose |
|---|---|---|---|
| `/var/data/autopirate/qwen3-tts/model` | `/root/.cache/huggingface/hub` | `rw` | Persistent Hugging Face cache and lock files |
| `/var/data/autopirate/qwen3-tts/openvino` | `/ov` or `/ov_output` | runtime `ro`, tools `rw` | Explicit/stateful transformer IR, vocoder IR, metadata, reports |
| `/var/data/autopirate/qwen3-tts/voice/voice_A.wav` | `/voice/voice_A.wav` | `ro` | Voice-clone reference audio |
| temporary reviewed source files | `/app/<file>.py` | `ro` | Candidate-only source override; never needed by a baked image |

Mount the whole OpenVINO root when explicit, stateful, and vocoder files live in sibling directories.
Then all environment paths can use one stable `/ov/...` namespace.

`rw` on the model cache does not mean weights belong in Git or the image. Hugging Face may need to
create cache locks even when the files already exist.

## Environment variables explained

### Model and voice

| Variable | Example | Meaning |
|---|---|---|
| `MODEL_SIZE` | `0.6B` or `1.7B` | Selects the official Base checkpoint unless `MODEL_REPO` overrides it |
| `MODEL_REPO` | unset | Explicit Hugging Face repo override |
| `MODEL_REVISION` | immutable commit SHA | Optional fail-closed checkpoint pin; should match IR metadata |
| `DEVICE` | `cpu` | PyTorch glue device; this project targets CPU |
| `REF_AUDIO` | `/voice/voice_A.wav` | In-container reference path |
| `REF_TEXT` | exact transcript | Required voice-clone conditioning text |

### Backend and graphs

| Variable | Example | Meaning |
|---|---|---|
| `TTS_BACKEND` | `openvino` | `pytorch` is the fresh-process rollback; `openvino` requires matching metadata/IR |
| `OV_MODEL_DIR` | `/ov/<explicit-dir>` | Directory containing `metadata.json` and explicit graph set |
| `OPENVINO_MAIN_STATEFUL_MODEL` | `/ov/<stateful-dir>/main_stateful_int8_cap768.xml` | Optional static-capacity main graph; unset uses explicit cache |
| `OPENVINO_PREDICTOR_STATEFUL_MODEL` | `/ov/<stateful-dir>/predictor_stateful_int8_cap32.xml` | Optional stateful predictor; reset once per audio frame |
| `OPENVINO_RELEASE_TORCH` | `1` | Frees replaced PyTorch transformer layers before/around compile; one-way in that process |
| `OPENVINO_BUFFER_KV` | `1` | Enables reusable explicit-cache buffers when explicit graphs are selected |
| `OPENVINO_VOCODER_ENABLED` | `1` | Enables the accepted FP32 OpenVINO vocoder |
| `OPENVINO_VOCODER_DIR` | `/ov/<vocoder-dir>` | Directory containing `vocoder_decoder.xml` |

The vocoder is FP32. Do not select the rejected INT8 vocoder files merely because they are present in
an artifact directory.

`OPENVINO_TORCH_DTYPE` is honored by the benchmark loader in `bench_common.py`. At the time of this
handoff, `app_worker.py` still loads the serving wrapper at FP32 directly, so do not assume that setting
this variable changes the serving process until the worker wiring is verified in code and health/logs.

### Threads and memory

| Variable/flag | Valid starting point | Meaning |
|---|---|---|
| `OV_INFERENCE_THREADS` | `6` | OpenVINO thread budget |
| `OMP_NUM_THREADS` | `6` | OpenMP/PyTorch budget inherited before imports |
| `MKL_NUM_THREADS` | `6` | MKL budget |
| `OMP_WAIT_POLICY` | `PASSIVE` | Reduces post-inference spin |
| `--memory` | `8g` for validated 0.6B long request | Hard container memory limit |
| `--memory-swap` | `9g` with `--memory 8g` | Combined memory+swap ceiling; not a performance target |

Keep one request in flight. The service's single executor serializes inference.

## Start the validated 0.6B service directly

The following uses the released v0.12.0 image as a known batch-runtime example. The streaming branch
requires a later baked image containing commit `8f6b862`; do not expect v0.12.0 itself to expose the new
public streaming endpoint unless source files are mounted for a candidate test.

```bash
IMAGE='ghcr.io/nmorgowicz-org/qwen3-tts-openvino@sha256:214eb114859e71d36ff19175d40c332124dfc0249dd6df27034101f7694e687b'
OV_ROOT='/var/data/autopirate/qwen3-tts/openvino'
MODEL_ROOT='/var/data/autopirate/qwen3-tts/model'
VOICE='/var/data/autopirate/qwen3-tts/voice/voice_A.wav'
EXPLICIT='qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1'
STATEFUL="${EXPLICIT}_stateful"
VOCODER="${EXPLICIT}_vocoder"

docker run -d --name qwen3-tts-candidate \
  --memory 8g --memory-swap 9g \
  -p 8318:8318 \
  -e MODEL_SIZE=0.6B \
  -e TTS_BACKEND=openvino \
  -e OV_MODEL_DIR="/ov/$EXPLICIT" \
  -e OPENVINO_MAIN_STATEFUL_MODEL="/ov/$STATEFUL/main_stateful_int8_cap768.xml" \
  -e OPENVINO_PREDICTOR_STATEFUL_MODEL="/ov/$STATEFUL/predictor_stateful_int8_cap32.xml" \
  -e OPENVINO_RELEASE_TORCH=1 \
  -e OPENVINO_VOCODER_ENABLED=1 \
  -e OPENVINO_VOCODER_DIR="/ov/$VOCODER" \
  -e OV_INFERENCE_THREADS=6 \
  -e OMP_NUM_THREADS=6 \
  -e MKL_NUM_THREADS=6 \
  -e OMP_WAIT_POLICY=PASSIVE \
  -e REF_AUDIO=/voice/voice_A.wav \
  -e 'REF_TEXT=Welcome to Rosies. What can I get for you today? You know, Im a good girl. You want me, dont you? I am on the menu too.' \
  -v "$MODEL_ROOT:/root/.cache/huggingface/hub:rw" \
  -v "$OV_ROOT:/ov:ro" \
  -v "$VOICE:/voice/voice_A.wav:ro" \
  "$IMAGE"
```

Follow startup without blocking other work indefinitely:

```bash
docker logs --tail 100 -f qwen3-tts-candidate
```

Expected evidence before calling it ready:

```text
[ov_vocoder] IR OK
[ov_talker] backends: main=stateful-... predictor=stateful-... vocoder=OV
[app_worker] Model loaded and ready.
```

Then:

```bash
curl -fsS http://127.0.0.1:8318/health | python3 -m json.tool

curl --fail-with-body \
  -H 'Content-Type: application/json' \
  --data '{"text":"The service is ready.","language":"English","response_format":"wav"}' \
  -o /tmp/qwen-ready.wav \
  http://127.0.0.1:8318/generate
```

Stop/remove only this candidate:

```bash
docker stop qwen3-tts-candidate
docker rm qwen3-tts-candidate
```

Because `--rm` is not used above, logs remain inspectable until the explicit remove. For ephemeral
benchmark containers, use `--rm`.

## Test unbaked branch files safely

Use this only before CI produces a baked image. From the development Mac, copy exactly the reviewed
runtime files to a temporary host directory (run `ssh`/`scp` outside the agent sandbox):

```bash
ssh nick@dockermisc1 'mkdir -p /tmp/ov-streaming-review'
scp app_api.py app_worker.py streaming_vocoder.py ov_runtime_config.py \
  ov_talker_runtime.py ov_vocoder_runtime.py serve.py \
  nick@dockermisc1:/tmp/ov-streaming-review/
```

Start with the same mounts/environment as the direct command, plus these read-only overrides:

```text
-v /tmp/ov-streaming-review/app_api.py:/app/app_api.py:ro
-v /tmp/ov-streaming-review/app_worker.py:/app/app_worker.py:ro
-v /tmp/ov-streaming-review/streaming_vocoder.py:/app/streaming_vocoder.py:ro
-v /tmp/ov-streaming-review/ov_runtime_config.py:/app/ov_runtime_config.py:ro
-v /tmp/ov-streaming-review/ov_talker_runtime.py:/app/ov_talker_runtime.py:ro
-v /tmp/ov-streaming-review/ov_vocoder_runtime.py:/app/ov_vocoder_runtime.py:ro
-v /tmp/ov-streaming-review/serve.py:/app/serve.py:ro
```

For worker-only diagnostics, bind `127.0.0.1:18319:8319` and override the command with
`python app_worker.py`. For the real public proxy test, use the default `serve.py`, bind
`127.0.0.1:18318:8318`, and call `/generate/stream` on port 18318.

Never treat a mounted-file run as a baked-image validation. Record both the base image digest and the
source commit.

## Streaming API checks

Public raw-PCM request:

```bash
curl --fail-with-body \
  -D /tmp/public-stream.headers \
  -w 'first_byte=%{time_starttransfer} total=%{time_total} bytes=%{size_download}\n' \
  -H 'Content-Type: application/json' \
  --data '{"text":"Streaming transport check.","language":"English"}' \
  -o /tmp/public-stream.f32le \
  http://127.0.0.1:8318/generate/stream
```

Validate/convert:

```bash
stat -c '%s bytes' /tmp/public-stream.f32le
ffmpeg -f f32le -ar 24000 -ac 1 \
  -i /tmp/public-stream.f32le /tmp/public-stream.wav
```

Expected headers:

```text
Content-Type: application/octet-stream
X-Audio-Format: f32le
X-Audio-Sample-Rate: 24000
X-Audio-Channels: 1
X-Stream-Error-Semantics: connection-close
```

The internal parity endpoint is diagnostic only. It returns WAV and parity/timing headers from one
generation:

```bash
curl --fail-with-body \
  -D /tmp/stream-parity.headers \
  -H 'Content-Type: application/json' \
  --data '{
    "text":"Streaming parity test.",
    "language":"English",
    "reuse_streamed_decode":true
  }' \
  -o /tmp/stream-parity.wav \
  http://127.0.0.1:8319/stream_internal
```

Only expose port 8319 on loopback in a temporary worker-only container. Do not publish it on the LAN.

## Run benchmark tools in the exporter image

Use one backend per process. The coupled parity harness can hold PyTorch and OpenVINO weights together
and needs substantially more memory.

Example 0.6B OpenVINO-only audio/RSS run:

```bash
EXPORTER='ghcr.io/nmorgowicz-org/qwen3-tts-openvino:exporter-v0.10.0'
OV_ROOT='/var/data/autopirate/qwen3-tts/openvino'
MODEL_ROOT='/var/data/autopirate/qwen3-tts/model'
VOICE='/var/data/autopirate/qwen3-tts/voice/voice_A.wav'
EXPLICIT='qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1'

docker run --rm \
  --memory 8g --memory-swap 9g \
  -e MODEL_SIZE=0.6B \
  -e OMP_NUM_THREADS=6 \
  -e MKL_NUM_THREADS=6 \
  -e OPENVINO_RELEASE_TORCH=1 \
  -e OPENVINO_MAIN_STATEFUL_MODEL="/ov_output/${EXPLICIT}_stateful/main_stateful_int8_cap768.xml" \
  -e OPENVINO_PREDICTOR_STATEFUL_MODEL="/ov_output/${EXPLICIT}_stateful/predictor_stateful_int8_cap32.xml" \
  -e OPENVINO_VOCODER_ENABLED=1 \
  -e OPENVINO_VOCODER_DIR="/ov_output/${EXPLICIT}_vocoder" \
  -e REF_AUDIO=/voice/voice_A.wav \
  -v "$MODEL_ROOT:/root/.cache/huggingface/hub:rw" \
  -v "$OV_ROOT:/ov_output:rw" \
  -v "$VOICE:/voice/voice_A.wav:ro" \
  "$EXPORTER" \
  python dump_audio.py \
    --ov-only \
    --model-dir "/ov_output/$EXPLICIT" \
    --compression int8 \
    --out-dir "/ov_output/${EXPLICIT}_stateful/audio-streaming-check" \
    --rss-profile "/ov_output/${EXPLICIT}_stateful/rss-streaming-check.json" \
    --rss-sample-ms 50
```

Use `bench_speed.py` for one-backend warm latency. Use `test_ov_generation.py` only when the required
memory for its coupled PyTorch/OpenVINO comparison is available. `scripts/run-m4-on-dockermisc1.sh`
wraps that harness and restores the named Compose service, but inspect its image/path settings before
running it; do not assume the host Compose file currently contains the service.

For 1.7B, select the INT4 directory, set `MODEL_SIZE=1.7B`, point the stateful variables at the validated
1.7B stateful artifacts, and use the separate FP32 vocoder directory. Run no second model container.
Record the exact selected filenames because INT4 graph files may still contain `_int8` in their names.

## Collect benchmark provenance and host data

Capture this before each measured run:

```bash
date -Ins
git rev-parse HEAD
docker image inspect "$IMAGE" --format '{{json .RepoDigests}}'
sha256sum "$OV_ROOT/$EXPLICIT/metadata.json"
python3 - "$OV_ROOT/$EXPLICIT/metadata.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
for key in ('model_repo', 'model_revision', 'source_hash', 'openvino_version', 'compression'):
    print(f'{key}={d.get(key)}')
PY
lscpu | sed -n '1,30p'
free -m
swapon --show
docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}'
```

For a live CPU timeline, write outside Git:

```bash
: > /tmp/qwen-cpu.txt
while docker ps --format '{{.Names}}' | grep -qx qwen3-tts-candidate; do
  printf '%s ' "$(date +%s.%N)" >> /tmp/qwen-cpu.txt
  docker stats --no-stream --format '{{.CPUPerc}} {{.MemUsage}}' \
    qwen3-tts-candidate >> /tmp/qwen-cpu.txt
  sleep 1
done
```

For overlap decisions, aggregate container CPU is only an initial signal. Capture per-core CPU with
`mpstat -P ALL 1` (if installed) and label talker versus vocoder phases in the runtime. Record:

- prompt text/name and language;
- seed and sampling parameters;
- generated frame count and audio duration;
- first-byte, total, transformer, and vocoder seconds;
- median/p95 over warm runs;
- process RSS timeline and kernel `ru_maxrss`;
- cgroup memory, host available RAM, and swap delta;
- image digest, source commit, model revision, metadata hash, graph filenames, precision/cache mode,
  stateful capacities, and thread settings;
- listening verdict and exact non-Git audio/profile paths.

## GHCR authentication

If the image is private, authenticate using a token with `read:packages` and stdin. Never print or
store the token in this repository:

```bash
gh auth refresh -h github.com -s read:packages
gh auth token | docker login ghcr.io -u nmorgowicz --password-stdin
docker pull ghcr.io/nmorgowicz-org/qwen3-tts-openvino:runtime-<immutable-sha>
docker logout ghcr.io
```

Prefer a temporary Docker config or credential helper for repeated automation. A workflow
`GITHUB_TOKEN` does not authenticate `dockermisc1`.

## Failure and rollback

Inspect the named container only:

```bash
docker inspect -f '{{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}}' \
  qwen3-tts-candidate
docker logs --tail 200 qwen3-tts-candidate
```

Common interpretations:

- Exit 137 / `oom=true`: selected model/runtime exceeded the cgroup; do not hide it by silently raising
  production limits. Record the peak and use the documented model/config limit.
- `missing stateful ... IR`: wrong bind mount or filename.
- metadata mismatch: wrong model revision/repo or explicit IR directory.
- vocoder falls back to PyTorch: wrong vocoder directory/filename or `OPENVINO_VOCODER_ENABLED` unset.
- public health 503: worker is loading, failed, or unreachable; do not weaken readiness.

Rollback is a fresh process. Stop/remove only the candidate, then start the previous immutable image or
start with `TTS_BACKEND=pytorch` and no OpenVINO graph variables. Verify `/health`, WAV, and MP3. The
experimental streaming endpoint should return 503 on the PyTorch rollback because it requires the FP32
OpenVINO vocoder.

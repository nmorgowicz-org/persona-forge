# qwen3-tts-openvino

Containerized Qwen3-TTS voice cloning for efficient local CPU inference, with a staged
migration from the working PyTorch baseline to an Intel OpenVINO INT8 backend.

The service is designed for local agents that need private text-to-speech without sending
text or reference audio to an external API. It preserves a small HTTP interface while moving
the expensive transformer work into OpenVINO.

## Project status

| Area | Status |
|---|---|
| PyTorch voice-cloning service | Working baseline |
| Docker runtime/exporter targets | Working and CI-tested |
| HTTP `/generate` API | Working |
| OpenVINO core export | Planned |
| FP32 OpenVINO parity | Planned |
| INT8 compression | Planned |
| Stateful OpenVINO K/V cache | Planned |
| Thin runtime memory loader | Planned |

The current `app_worker.py` still performs model inference with PyTorch float32. Installing
OpenVINO in the image does not by itself activate an OpenVINO backend. Progress and release
gates are defined in the [implementation plan](docs/OPENVINO_IMPLEMENTATION.md).

## Goals

- Preserve voice cloning from a local reference recording and transcript.
- Support both official Base voice-cloning sizes through one `MODEL_SIZE` setting.
- Keep the external HTTP contract stable while the inference backend changes.
- Accelerate both Qwen3-TTS autoregressive transformer paths on Intel CPUs.
- Reduce CPU-seconds and warm memory after unused PyTorch transformer weights are removed.
- Build model-free, reproducible Linux AMD64 images in CI.
- Download model weights and generate machine-tested OpenVINO IR after the image build.
- Keep an explicit `TTS_BACKEND=pytorch` rollback path during migration.

This project does not train or redistribute Qwen model weights, embed private voice samples in
images, or target GPU inference.

## How it works

The container runs two Gunicorn applications under a small signal-aware supervisor:

```text
client / Hermes agent
        |
        | POST /generate :8318
        v
app_api.py
  validation, timeout handling, proxying
        |
        | POST /infer :8319 over container loopback
        v
app_worker.py
  model + persistent voice-clone prompt
  one serialized inference request at a time
        |
        +-- PyTorch prompt construction and generation (current)
        +-- OpenVINO main talker + code predictor (target)
        +-- ONNX Runtime speech tokenizer/decoder
        v
MP3 or WAV response
```

Port `8318` is the public service API. Port `8319` is an internal worker endpoint and normally
does not need to be published outside the container.

`serve.py` starts both Gunicorn masters, forwards container stop signals to their process
groups, allows graceful shutdown, and stops the other service if either one exits. The API
starts immediately; readiness remains unavailable while the worker downloads and loads the
model.

At startup, the worker:

1. Loads the configured Qwen3-TTS model from the Hugging Face cache.
2. Reads `REF_AUDIO` and its exact transcript from `REF_TEXT`.
3. Creates and retains a voice-cloning prompt.
4. Reports healthy only after the model and prompt are ready.

Inference is serialized through a one-worker executor. Gunicorn can accept concurrent HTTP
connections, but only one model generation runs at a time to control CPU and memory pressure.

### OpenVINO target architecture

Qwen3-TTS contains two nested autoregressive workloads:

- A 28-layer main talker that predicts the first audio codebook.
- A 5-layer code predictor that generates the remaining 15 codebooks for every audio frame.

The production backend will export and accelerate both cores. PyTorch initially remains
responsible for prompt construction, embeddings, sampling, and lightweight control flow;
ONNX Runtime continues to decode audio tokens into a waveform.

## Model selection

This project supports the two official Qwen3-TTS Base voice-cloning checkpoints:

| `MODEL_SIZE` | Resolved checkpoint | Deployment guidance |
|---|---|---|
| `0.6B` | `Qwen/Qwen3-TTS-12Hz-0.6B-Base` | Default; lower memory and compute demand |
| `1.7B` | `Qwen/Qwen3-TTS-12Hz-1.7B-Base` | Larger talker; benchmark memory, latency, and quality separately |

`MODEL_REPO` remains an expert override, but normal deployments should only set
`MODEL_SIZE`. The `CustomVoice` and `VoiceDesign` checkpoints have different behavior and are
not substitutes for the Base models used by this voice-cloning service.

The two sizes cannot share generated OpenVINO IR. Export metadata records the exact model
repository, revision, architecture, and tensor shapes, and the runtime refuses to load IR
that does not match its selected checkpoint.

## Repository layout

```text
app_api.py                         public HTTP proxy
app_worker.py                      model worker and current PyTorch backend
model_config.py                    model preset and Hugging Face secret resolver
serve.py                           Gunicorn lifecycle and signal supervisor
Dockerfile                         runtime and exporter image targets
compose.example.yml                validated runtime and download-tool Compose example
SECURITY.md                        private vulnerability-reporting policy
requirements.txt                   base service dependencies
requirements-ov-runtime.txt        OpenVINO runtime dependency
requirements-ov-export.txt         Optimum Intel and NNCF export dependencies
requirements-dev.txt               lightweight repository validation dependencies
scripts/validate_repo.py           model-free repository checks
scripts/download_model.py          explicit persistent-cache pre-download command
tests/                              model-free unit tests
docs/OPENVINO_IMPLEMENTATION.md     architecture and implementation contract
AGENTS.md                           agent rules, tests, and troubleshooting
.github/workflows/                 CI, images, labels, and release automation
```

Model weights, generated IR, reference audio, and generated speech do not belong in this
repository.

## Container images

The Dockerfile has two Linux AMD64 targets:

- `runtime`: service dependencies, CPU-only Torch, Qwen3-TTS, OpenVINO Runtime, and ONNX
  Runtime.
- `exporter`: the runtime image plus Optimum Intel and NNCF conversion dependencies.

Trusted `main` and tag builds publish private GHCR images:

```text
ghcr.io/nmorgowicz-org/qwen3-tts-openvino:runtime-<git-sha>
ghcr.io/nmorgowicz-org/qwen3-tts-openvino:exporter-<git-sha>
```

Production should use an immutable SHA tag or digest. `runtime-latest` and `exporter-latest`
are convenience tags, not deployment locks.

Build locally on an AMD64 Docker host:

```bash
docker build --target runtime -t qwen3-tts-openvino:runtime .
docker build --target exporter -t qwen3-tts-openvino:exporter .
```

The images intentionally contain no Hugging Face weights, OpenVINO IR, reference audio, or
credentials.

## Docker Compose wiring

[`compose.example.yml`](compose.example.yml) is the checked deployment example. Use immutable
SHA tags in production:

```bash
export QWEN3_TTS_IMAGE=ghcr.io/nmorgowicz-org/qwen3-tts-openvino:runtime-<git-sha>
export QWEN3_TTS_EXPORTER_IMAGE=ghcr.io/nmorgowicz-org/qwen3-tts-openvino:exporter-<git-sha>
export MODEL_SIZE=0.6B
export MODEL_CACHE_PATH=/var/data/qwen3-tts/model
export REF_AUDIO_PATH=/private/path/reference.wav
export REF_TEXT='Exact transcript of the reference recording'

docker compose -f compose.example.yml config
docker compose -f compose.example.yml up -d qwen3-tts
```

The example deliberately requires `REF_AUDIO_PATH` and `REF_TEXT`; silently using the wrong
voice transcript would produce a running service with poor output.

The current PyTorch baseline can run from the runtime image with persistent model and voice
mounts:

```yaml
services:
  qwen3-tts:
    image: ghcr.io/nmorgowicz-org/qwen3-tts-openvino:runtime-<git-sha>
    container_name: qwen3-tts
    restart: unless-stopped
    ports:
      - "8318:8318" # omit this when only other Compose services need access
    expose:
      - "8318"
    environment:
      TZ: America/Detroit
      MODEL_SIZE: 0.6B
      DEVICE: cpu
      REF_AUDIO: /voice/reference.wav
      REF_TEXT: "Exact transcript of the reference recording"
      HF_HUB_ENABLE_TF_WARNING: "0"
      HF_HUB_ENABLE_HF_TRANSFER: "0"
    volumes:
      - /var/data/qwen3-tts/model:/root/.cache/huggingface/hub:rw
      - /private/path/reference.wav:/voice/reference.wav:ro
    mem_limit: 7G
    memswap_limit: 8G
```

If the caller is another service in the same Compose project, use
`http://qwen3-tts:8318/generate` and retain only `expose`. Publishing `8318` with `ports` is
needed for host or LAN clients.

The first model download requires the cache mount to be writable. After the cache is fully
populated by the post-build export process, deployments may mount it read-only if the runtime
does not need to fetch additional files.

Both supported checkpoints are public, so a Hugging Face token is not required. For
authenticated downloads, mount a token as a Compose secret instead of putting it directly in
the Compose file:

```yaml
services:
  qwen3-tts:
    environment:
      HF_TOKEN_FILE: /run/secrets/hf_token
    secrets:
      - hf_token

secrets:
  hf_token:
    file: /private/path/hf_token
```

The container reads the secret into `HF_TOKEN` before importing the Hugging Face stack and
never returns or logs it. A direct `HF_TOKEN` environment variable is also supported, but is
more visible through container inspection.

To populate the persistent cache before starting the service, choose either size and run:

```bash
docker run --rm \
  -e MODEL_SIZE=0.6B \
  -e HF_TOKEN_FILE=/run/secrets/hf_token \
  -v /private/path/hf_token:/run/secrets/hf_token:ro \
  -v /var/data/qwen3-tts/model:/root/.cache/huggingface/hub:rw \
  ghcr.io/nmorgowicz-org/qwen3-tts-openvino:runtime-<git-sha> \
  python -m scripts.download_model
```

Omit the token settings and token mount for an anonymous download. Change only
`MODEL_SIZE=1.7B` to download the larger Base model. The future export command will use the
same selection and authentication variables.

The same download is available through the example's tools profile:

```bash
docker compose -f compose.example.yml --profile tools run --rm qwen3-tts-download
```

### One-shot OpenVINO export and quantization

Your understanding is correct for the target workflow: the exporter container is a one-shot
tool. It reuses the mounted Hugging Face cache, writes checkpoint-specific OpenVINO IR into a
persistent output mount, runs parity validation, and applies INT8 compression. It does not
embed weights or generated IR into the image.

The intended command contract is:

```bash
docker run --rm --init \
  -e MODEL_SIZE=0.6B \
  -e MODEL_REVISION=<immutable-hugging-face-revision> \
  -e HF_TOKEN_FILE=/run/secrets/hf_token \
  -v /private/path/hf_token:/run/secrets/hf_token:ro \
  -v /var/data/qwen3-tts/model:/root/.cache/huggingface/hub:rw \
  -v /var/data/qwen3-tts/openvino:/ov_output:rw \
  ghcr.io/nmorgowicz-org/qwen3-tts-openvino:exporter-<git-sha> \
  python export_openvino.py \
    --output-dir /ov_output \
    --compression both \
    --validate
```

This quantization command is an implementation contract, not current functionality. The
first PR provides the exporter dependencies and working pre-download command; Milestones 2
and 3 add `export_openvino.py`, FP32 parity, and INT8 generation. Until then, use only the
download command above. The completed exporter must exit nonzero without publishing an
artifact when export, parity, or compression validation fails.

### Target OpenVINO additions

After the OpenVINO milestones are implemented and the generated IR passes parity checks,
Compose will add:

```yaml
environment:
  TTS_BACKEND: openvino
  OV_MODEL_DIR: /ov_model/qwen-tts-0.1.1_0.6b_ov-2026.2.1
  OV_INFERENCE_THREADS: "6"
  OV_DYNAMIC_QUANT_GROUP_SIZE: "32"
  OMP_WAIT_POLICY: PASSIVE
volumes:
  - /var/data/qwen3-tts/openvino:/ov_model:ro
```

These backend settings are part of the target design and are not active in the current
PyTorch worker.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_SIZE` | `0.6B` | Supported Base model preset: `0.6B` or `1.7B` |
| `MODEL_REPO` | unset | Expert override for the complete Hugging Face model ID |
| `MODEL_REVISION` | repository default | Optional immutable Hugging Face revision for pre-download/export |
| `HF_TOKEN` | unset | Optional Hugging Face token; direct environment form |
| `HF_TOKEN_FILE` | unset | Preferred path to a mounted token secret |
| `DEVICE` | `cpu` | PyTorch device for the baseline |
| `REF_AUDIO` | `/voice/voice_A.wav` | Reference voice recording inside the container |
| `REF_TEXT` | built-in fallback | Exact transcript of `REF_AUDIO`; set explicitly in deployment |
| `PYTHONUNBUFFERED` | `1` in the image | Immediate service logging |
| `ORT_INTRA_OP_NUM_THREADS` | `6` | ONNX Runtime intra-op threads, set before imports |
| `ORT_INTER_OP_NUM_THREADS` | `2` | ONNX Runtime inter-op threads |
| `OMP_NUM_THREADS` | `6` | OpenMP thread limit |
| `MKL_NUM_THREADS` | `6` | MKL thread limit |
| `OPENBLAS_NUM_THREADS` | `6` | OpenBLAS thread limit |
| `SHUTDOWN_TIMEOUT_SECONDS` | `30` | Grace period before the supervisor force-kills child processes |

`REF_TEXT` must match the spoken recording. A mismatched transcript can reduce voice quality
or destabilize generation.

## HTTP API

### Health

```bash
curl -fsS http://127.0.0.1:8318/health | jq
```

Healthy response shape:

```json
{
  "status": "ok",
  "worker": {
    "status": "ok",
    "model": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "device": "cpu",
    "ref_audio": "/voice/reference.wav"
  }
}
```

The API returns `status: degraded` when port 8318 is running but the model worker is not yet
reachable. A degraded response uses HTTP 503, so Docker and orchestrators do not treat the
container as ready. The image health check allows up to ten minutes for first-start download
and model initialization, then checks `/health` every 30 seconds.

### Generate MP3

```bash
curl --fail-with-body \
  -X POST http://127.0.0.1:8318/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "Your local agent can now speak this response.",
    "language": "English",
    "response_format": "mp3"
  }' \
  --output speech.mp3
```

### Generate WAV

```bash
curl --fail-with-body \
  -X POST http://127.0.0.1:8318/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "This response is returned as a wave file.",
    "language": "English",
    "response_format": "wav"
  }' \
  --output speech.wav
```

Request fields:

| Field | Required | Default | Notes |
|---|---|---|---|
| `text` | yes | — | Non-empty text to synthesize |
| `language` | no | `English` | Qwen3-TTS language name |
| `response_format` | no | `mp3` | `mp3` selects MP3; other values currently produce WAV |

The API proxies worker errors and has a 300-second upstream timeout.

## Post-build model export lifecycle

Full model conversion does not run in ARC CI because the current runners do not have enough
guaranteed memory. The intended lifecycle is:

1. CI builds and publishes model-free runtime/exporter images.
2. `dockermisc1` pulls an immutable exporter image.
3. The existing TTS service is stopped during the export maintenance window to release model
   memory.
4. The exporter downloads/reuses the persistent Hugging Face cache.
5. It resolves `MODEL_SIZE`, exports checkpoint-specific FP32 IR, validates
   PyTorch/OpenVINO parity, and then creates INT8 IR.
6. Metadata records the source commit, image digest, model revision, package versions, and IR
   hash.
7. Compose starts the matching runtime image with the validated IR mounted read-only.
8. Health, short-prompt, paragraph, quality, memory, and rollback checks run on the target CPU.

Export and release gates are run independently for 0.6B and 1.7B. Passing the 0.6B gates
does not certify a 1.7B artifact.

The exporter code and commands will land during the corresponding implementation milestones.

## CI and repository automation

- Lightweight repository validation runs on every internal pull request using `arc-general`.
- Apply `ready-to-test` when a PR is ready for expensive runtime/exporter builds on
  `arc-general-docker`.
- Later commits rerun image checks while `ready-to-test` remains applied.
- Pushes to `main`, version tags, and manual image dispatches build unconditionally.
- Label synchronization and path-based PR labels run automatically.
- Release Please manages versions and GitHub releases.
- Renovate monitors requirements, Docker base images, GitHub Actions, OpenVINO dependencies,
  and the independent Torch/Torchaudio Docker ARGs.

OpenVINO, Qwen-TTS, and PyTorch CPU-stack updates require review and are not eligible for
automatic merge.

## Development and validation

Install only the lightweight validation dependency:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
PYTHONDONTWRITEBYTECODE=1 python scripts/validate_repo.py
git diff --check
npx --yes --package renovate@43.245.0 renovate-config-validator renovate.json
```

Do not download the model merely to validate repository metadata or workflow changes.

For implementation constraints, test tiers, VM safety, and diagnostic guidance, read
[AGENTS.md](AGENTS.md).

## Operational notes

- Model startup may take several minutes on first download; check worker logs before treating
  a degraded health response as a crash.
- The supervisor shuts the whole container down if either Gunicorn master exits and forwards
  `SIGTERM` for graceful worker cleanup.
- A `502 Worker unreachable` response means the API process cannot reach port 8319.
- A `504` means the API's 300-second proxy timeout elapsed.
- The baseline currently uses approximately 4.7 GiB warm on the target VM; retain the 7 GiB
  limit until the final OpenVINO loader is measured.
- High active CPU utilization is expected. Success is lower latency and CPU-seconds, not low
  instantaneous CPU usage.
- Generated audio and benchmark artifacts must remain outside Git.
- Never start a second full model in the already-running production container.

Detailed cache, parity, INT8, memory, ARC, and GHCR troubleshooting is maintained in
[AGENTS.md](AGENTS.md).

The HTTP service has no built-in authentication or TLS. Keep it on a trusted Compose network
or place an authenticated TLS reverse proxy in front of it. Report vulnerabilities according
to [SECURITY.md](SECURITY.md).

## License

Repository code is available under the [MIT License](LICENSE). Qwen3-TTS models and upstream
packages retain their own licenses and usage terms.

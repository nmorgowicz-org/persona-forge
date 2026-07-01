# Qwen3-TTS OpenVINO — Agent Guide

## Quick orientation

```
src/qwen3_tts/     Flask app, model runtime, model config, OpenVINO runtime adapters
src/export/        OpenVINO export/quantization, parity tests, benchmark tooling
scripts/           entrypoint.sh (container entrypoint), export.py, download_model.py, run-*.sh
tests/             Unit and integration tests; no model weights needed
requirements/      runtime.txt  openvino.txt  export.txt
Dockerfile         Single image: ENTRYPOINT=entrypoint.sh, default CMD = gunicorn serving
compose.yml        Two services (qwen3-tts, export) sharing one image
```

`PYTHONPATH=/app/src:/app/src/export` — both `qwen3_tts.*` and export modules are importable inside the container.

**One image, two behaviors.** `scripts/entrypoint.sh` is the container ENTRYPOINT; it applies
`LOW_RAM_MODE` tuning (jemalloc, idle unload defaults) before exec-ing the CMD. The serving
container runs the image's default CMD (gunicorn). The export service overrides CMD with
`python scripts/export.py`. There are no multi-stage build targets.

**Gunicorn constraints.** Always `-w 1 -k gthread --threads 4`. Never `--preload`. Never more than
one worker. The single worker holds the model and serializes all inference through a
`concurrent.futures.ThreadPoolExecutor(max_workers=1)` to prevent concurrent model access.

**Model size.** `MODEL_SIZE` (0.6B or 1.7B) is the only required preset. `resolve_model_repo`
in `model_config.py` maps it to the checkpoint and IR paths. 1.7B is the recommended default.

## Project objective

Reproducible Linux AMD64 container that accelerates 0.6B or 1.7B Qwen3-TTS Base voice-cloning
checkpoints on Intel CPUs with OpenVINO while preserving a tested PyTorch rollback path.

Read `docs/dev/OPENVINO_IMPLEMENTATION.md` before changing model export, cache handling,
generation, quantization, memory loading, Docker packaging, or deployment behavior.

## Current state (v0.15.x)

- Single image ships serving and export tooling. CI publishes it as `ghcr.io/nmorgowicz-org/qwen3-tts-openvino:<sha>`.
- `TTS_BACKEND=pytorch` is the tested rollback baseline.
- OpenVINO accelerates both transformer cores and the FP32 vocoder.
- 0.6B ships INT8 with stateful main (cap 768) + stateful predictor (cap 32).
- 1.7B ships INT4 asymmetric (group 32) with stateful main (cap 768) + INT8 explicit predictor.
- Both profiles land at ~5.4–6.9 GiB steady serving RSS on the validated host (cap1024 stateful adds ~0.4 GiB over cap768). Export needs up to 13 GiB.
- `LOW_RAM_MODE=1` enables glibc malloc tuning (`MALLOC_MMAP_THRESHOLD_=65536`, `MALLOC_ARENA_MAX=1`) + idle unload (default 1800s). Python calls `malloc_trim(0)` after idle unload. LD_PRELOAD allocator replacement (jemalloc, tcmalloc) is incompatible with OpenVINO `compile_model()` under transformers 5.x — both caused SIGABRT/SIGSEGV. `libjemalloc2` remains in the image for reference.
- OV compiled kernel cache at `/ov/cache` (default) eliminates ~60–120s recompilation on every restart.
- Full model export, parity, and performance benchmarks run on `dockermisc1`, not on ARC runners.

## Architecture invariants

- Two nested autoregressive transformer paths: 28-layer main talker (codebook 1), 5-layer code predictor (codebooks 2–16). Both must be accelerated.
- Keep prompt construction, embeddings, sampling, and lightweight glue in PyTorch.
- Export main and predictor transformer cores separately; validate K/V cache before introducing stateful models.
- Reuse persistent `InferRequest` objects; never create one per token or per request.
- Preserve the talker object's embeddings, projections, codebook heads, config, dtype, and device behavior.
- Keep `/generate`, `/v1/audio/speech`, `/health`, MP3/WAV output, and serialized inference compatible with the baseline.
- Keep `TTS_BACKEND=pytorch` as an explicit rollback path.
- Return HTTP 503 during initial startup (before `_service_started` is set). After first successful load,
  idle-unloaded requests block in the executor and reload transparently — do not 503 them.

## Model and secret safety

Never commit to Git or bake into the image:
- HF model weights or cache directories
- Generated OpenVINO IR (`.xml`/`.bin`) or ONNX models
- Reference voice audio or generated speech
- HF tokens, GitHub tokens, PEM keys, `.env` files, or deployment credentials

Persistent host paths on `dockermisc1`:
```text
/var/data/autopirate/qwen3-tts/model      ← HF cache (MODEL_CACHE_PATH)
/var/data/autopirate/qwen3-tts/openvino   ← OpenVINO IR  (OV_DATA_PATH)
```

## Dependency rules

- The OpenVINO stack (OpenVINO, NNCF, Transformers, Python) moves together; pin all of them.
- `qwen-tts==0.1.1` hard-pins `transformers==4.57.3` but is installed `--no-deps` in the Dockerfile so that `requirements/runtime.txt` can supply `transformers==5.12.1` (CVE-2026-1839 fix). All other qwen-tts runtime deps (accelerate, einops, librosa, onnxruntime) are listed explicitly in runtime.txt. Re-verify export wrappers and parity gate after any transformers bump.
- Install CPU-only Torch before `qwen-tts` to prevent CUDA library pulls.
- Validated Python 3.13 CPU pair: `torch==2.12.1+cpu` + `torchaudio==2.11.0+cpu`.
- Do not update one OpenVINO-stack dependency in isolation without rebuilding the image and rerunning export parity.
- Optimum Intel is intentionally absent: the custom talker has no registered exporter in `TasksManager`. Use `openvino.convert_model` + `nncf.compress_weights` directly.
- Do not pass datasets, AWQ, GPTQ, LoRA correction, or sensitivity selection to NNCF 3.2.0 `compress_weights`; the API rejects them. Do not substitute W8A8 `nncf.quantize` (caused ~23 dB SNR regression at M6).
- Renovate tracks pip requirements, Docker base images, and GitHub Actions. OpenVINO, Qwen-TTS, and PyTorch CPU-stack updates must not auto-merge.

## Build and CI

- `arc-general`: validation, labels, and release automation.
- `arc-general-docker`: native Linux AMD64 image builds.
- CI builds one image per run — no matrix. Smoke test imports all export and serving modules.
- Image build runs on PRs with `ready-to-test` label. Tag pushes publish to GHCR.
- `main` pushes alone do not build or publish.
- `buildcache` and `latest` are protected from cleanup. Keep at least 5 older versions for rollback.
- Production Compose must pin the SHA tag or digest; never `latest`.

GHCR pulls on `dockermisc1` need a `read:packages` token. Pass via `docker login --password-stdin` only; never echo or embed in Compose.

## Required validation

Repository-only changes:
```bash
python scripts/validate_repo.py
docker compose config --quiet   # requires REF_AUDIO_PATH, REF_TEXT env vars
git diff --check
```

Container or dependency changes: apply `ready-to-test` to trigger the image build and import smoke test on `arc-general-docker`. Do this only after local validation passes.

Model execution changes also require the staged gates from `docs/dev/OPENVINO_IMPLEMENTATION.md`:
1. PyTorch baseline/profile
2. FP32 OpenVINO tensor, token, position, and cache parity
3. INT8 accuracy and greedy-code agreement
4. Voice quality listening checks
5. Warm median/p95 latency, RTF, and peak RSS on `dockermisc1`
6. PyTorch rollback verification

## Test tiers

### Tier 1 — Repository/unit (arc-general, no model)
- K/V cache flattening, naming, ordering, reconstruction
- Prefill vs. one-token decode shapes
- Position IDs, cache positions, masks, cache-length accounting
- Export metadata validation and source/config hash checks
- Backend selection and startup mismatch failures
- HTTP request validation and response formats

### Tier 2 — Container (arc-general-docker, no model weights)
- Build the single image for Linux AMD64
- Import Torch, Torchaudio, Qwen3-TTS, OpenVINO, NNCF, and all export modules
- Assert Torch is a CPU build (no CUDA shared libraries)
- Validate `compose.yml`, the health check endpoint, both MODEL_SIZE presets, the downloader module

### Tier 3 — Model parity (dockermisc1, do_sample=False)
1. PyTorch vs. FP32 OpenVINO main prefill
2. Several main decode steps with growing cache
3. Predictor prefill and all 15 codebook steps
4. Complete generated code sequences

Record max/mean absolute error, top-1 agreement, top-k overlap, cache shapes, first divergent step. Parity gates fail closed — never catch missing outputs or lower thresholds to make a run pass.

### Tier 4 — Quality and performance (dockermisc1)
Record: audio duration, end-to-end latency, RTF, warm median/p95, container peak RSS, host RAM/swap, and listening notes. Keep benchmark prompts in source control; store audio outside Git.

## Troubleshooting

### CPU Torch/Torchaudio unresolvable
Inspect the CPU wheel index directly. Keep TORCH_VERSION and TORCHAUDIO_VERSION as independent Dockerfile ARGs. After changing a pin, rebuild and smoke-test.

### Why Optimum Intel is absent
`qwen3_tts_talker` has no registered exporter in `TasksManager`. Use `openvino.convert_model()` + `nncf.compress_weights()` instead.

### Export expects input_ids
The generation path supplies `inputs_embeds`. Wrappers must expose embeddings as the primary input. An `input_ids`-only IR is incompatible with the current generator.

### Output matches prefill but diverges during decode
Check in order: K/V layer/key/value ordering; cache sequence length; `cache_position`, attention mask, position IDs; main vs. predictor reset scope; predictor codebook embedding and output head. Log the first divergent step before inspecting audio.

### Stateful generation repeats or contaminates requests
- Main state resets once per utterance; predictor state resets once per audio frame.
- Never share an `InferRequest` across concurrent requests.
- Never create a new request per token.
- Use `query_state()` in tests to confirm reset length.

### OpenVINO loaded but RAM stays high
The first hybrid implementation keeps both PyTorch and OpenVINO weights resident. RSS drops only after unused PyTorch layers are released. Measure after GC; allocator retention can hide freed tensors. Do not delete the talker object — embeddings, projections, and codebook heads are still needed.

### INT8 runs but not faster
Confirm both cores use OpenVINO; confirm IR weights are compressed; check MatMul activation quantization; benchmark group sizes 0/32/64; profile main vs. predictor; check for per-token array copies; verify host isn't swapping.

### Export killed / VM swaps heavily
Stop `qwen3-tts` before exporting (13G export + 10G serve = OOM on 15 GiB host). Never load a second model inside the existing container. Keep IR on the persistent OV volume.

### ARC job queued
Confirm `arc-general` or `arc-general-docker` label; confirm ARC GitHub App is installed; check scale set, ephemeral pod, and listener logs.

### GHCR build cache fails
Use the `:buildcache` reference with `mode=min,ignore-error=true`. Cache failure must not invalidate an otherwise successful build.

## Agent handoff requirements

Every handoff must state:
- Source commit and image tag/digest
- Model revision and IR metadata hash
- Completed milestones and remaining release gates
- Exact validation commands and results
- Benchmark prompts and runtime settings (FP32/INT8, explicit/stateful cache)
- Known divergences, first failing step, and non-Git artifact locations
- Rollback procedure and whether it was tested

## Production VM safety (dockermisc1)

- Shared live host — prefer read-only inspection unless the user explicitly authorizes changes.
- Stop only `qwen3-tts` during export; never touch unrelated containers (`litellm*`, `headroom-proxy`, `crowdsec`, `hermes-*`, `*arr`, `searxng`).
- Never run two large model jobs at once (export + serve will OOM a 15 GiB box).
- Record host load, available RAM, and swap alongside performance results.
- On failure, restore the previous immutable image or switch to `TTS_BACKEND=pytorch`.
- Port 8318 has no auth or TLS; keep it on a trusted network or behind an authenticated reverse proxy.

## Commit and PR conventions

Use Conventional Commits (`feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `build`, `ci`, `chore`, `revert`). Use squash merge. The PR title drives Release Please, so user-facing changes need a `feat:` or `fix:` title.

Every implementation PR body must include a Release Please override block:

```text
BEGIN_COMMIT_OVERRIDE
fix(ci): publish one complete container image
fix(runtime): correct gunicorn worker threading
END_COMMIT_OVERRIDE
```

One Conventional Commit line per entry; one supported type per entry; no composite headers. Release Please version PRs are exempt. Keep model artifacts and benchmark audio out of PRs.

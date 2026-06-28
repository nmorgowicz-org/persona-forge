# Qwen3-TTS OpenVINO Project Rules

## Project Objective

Provide a reproducible Linux AMD64 container that accelerates the official 0.6B or 1.7B
Qwen3-TTS Base voice-cloning checkpoint on Intel CPUs with OpenVINO while preserving the
existing API and a tested PyTorch rollback path.

Read `docs/OPENVINO_IMPLEMENTATION.md` before changing model export, cache handling,
generation, quantization, memory loading, Docker packaging, or deployment behavior. It is the
implementation contract for this repository.

## Current State

- `app_api.py` and `app_worker.py` are the working PyTorch service baseline imported from
  `dockermisc1`.
- The OpenVINO generation runtime and `export_openvino.py` are not implemented yet. The
  exporter image currently provides dependencies and a working one-shot model downloader,
  not quantization.
- CI builds model-free `runtime` and `exporter` Docker targets.
- Full model export, INT8 compression, parity testing, and performance benchmarking run on
  `dockermisc1`, not on ARC runners.

Do not describe an OpenVINO milestone as complete until its parity and benchmark gates in the
implementation plan pass on the target VM.

## Architecture Invariants

Qwen3-TTS has two nested autoregressive transformer paths:

1. The 28-layer main talker generates the first audio codebook.
2. The 5-layer code predictor generates the remaining 15 codebooks for every audio frame.

Both cores must be profiled and accelerated. Replacing only one `talker.forward()` call is not
a complete backend.

Preserve these boundaries:

- Keep prompt construction, embeddings, sampling, and lightweight glue in PyTorch initially.
- Export the main and predictor transformer cores separately.
- Validate explicit K/V cache behavior before introducing stateful OpenVINO cache models.
- Reuse persistent `InferRequest` objects; never create one per token.
- Preserve the original talker object's embeddings, projections, configuration, dtype, and
  device behavior.
- Keep `/generate`, `/infer`, `/health`, MP3 output, WAV output, and serialized inference
  compatible with the baseline.
- Keep `TTS_BACKEND=pytorch` as an explicit rollback path.
- Derive tensor shapes from the selected checkpoint and keep IR, metadata, parity results,
  and benchmarks isolated by model repository and revision.
- Keep `serve.py` as the signal-aware supervisor for both Gunicorn masters. If either master
  exits, the container must exit; container stop signals must reach both process groups.
- Return HTTP 503 from public readiness while the worker is loading or unreachable. Do not
  weaken `/health` to return HTTP 200 for a degraded worker.

## Model and Secret Safety

Never commit or copy these into a Git tree or container image:

- Hugging Face model weights or cache directories
- generated OpenVINO IR (`.xml`/`.bin`) or ONNX models
- reference voice audio or generated speech
- Hugging Face tokens, GitHub tokens, PEM keys, `.env` files, or deployment credentials

Persistent host locations belong outside the repository:

```text
/var/data/autopirate/qwen3-tts/model
/var/data/autopirate/qwen3-tts/openvino
```

Repository secrets are configured through GitHub settings. Never print secret values while
validating their presence.

## Dependency Rules

- Pin the OpenVINO stack because OpenVINO, NNCF, Transformers, and Python compatibility move
  together. Optimum Intel is intentionally not a dependency: the custom talker has no
  registered exporter, so export uses `openvino.convert_model` + `nncf.compress_weights`
  directly, and avoiding Optimum keeps the Transformers pin owned solely by `qwen-tts`.
- Do not upgrade `transformers` independently. `qwen-tts==0.1.1` hard-pins
  `transformers==4.57.3`, and the OpenVINO export wrappers depend on that exact
  `DynamicCache` (`to_legacy_cache`/`from_legacy_cache`) and `generate` API. Bump it only
  when `qwen-tts` itself does, and re-verify the export wrappers and parity gate.
- Install CPU-only Torch before `qwen-tts` so pip does not pull CUDA libraries.
- Pin Torch and Torchaudio independently. The validated Python 3.13 CPU pair is currently
  `torch==2.12.1+cpu` with `torchaudio==2.11.0+cpu`.
- Do not update one OpenVINO-stack dependency in isolation without rebuilding both images and
  rerunning export parity.
- Update the implementation plan when a non-obvious compatibility pin changes.
- Renovate tracks pip requirements, Docker base images, GitHub Actions, and the Dockerfile's
  independent Torch/Torchaudio ARGs. OpenVINO, Qwen-TTS, and PyTorch CPU-stack updates require
  review and must not auto-merge.
- Validate Renovate changes with the pinned `renovate-config-validator` command in CI.

## Build and CI Boundaries

Use the correct ARC pool:

- `arc-general`: repository validation, labels, release automation, and non-Docker jobs.
- `arc-general-docker`: native Linux AMD64 runtime/exporter image builds.
- Never download or convert the full model in current ARC jobs; their memory is insufficient.

Cheap repository validation runs on every internal PR. Expensive runtime/exporter image builds
run only when an authorized maintainer applies the `ready-to-test` label. After that label is
present, later commits rerun the image checks. Release Please version tags publish images;
manual workflow dispatches remain an explicit build-and-publish override. Merges to `main` do
not build or publish images by themselves.

Release cleanup must protect `runtime-latest`, `exporter-latest`, `buildcache-runtime`, and
`buildcache-exporter`. Keep five additional package versions for rollback; do not use an
unqualified package-wide retention rule that can delete the active tags or caches.

Images are immutable build artifacts:

```text
ghcr.io/nmorgowicz-org/qwen3-tts-openvino:runtime-<git-sha>
ghcr.io/nmorgowicz-org/qwen3-tts-openvino:exporter-<git-sha>
```

Production Compose must use an immutable SHA tag or digest, not `latest`.

Private GHCR pulls on `dockermisc1` require a GitHub token with `read:packages`. A workflow's
`GITHUB_TOKEN` does not authenticate the target VM. Pass credentials only through
`docker login --password-stdin`; never echo a token, put it in Compose, or commit a Docker
config. Prefer a temporary Docker config for one-shot pulls, or configure a host credential
helper and least-privilege read-only package token for persistent deployment access.

If the repository becomes public, do not run untrusted fork PR code on self-hosted runners.
Keep or strengthen the same-repository PR guards before changing visibility.

## Required Validation

For repository-only changes:

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/validate_repo.py
REF_AUDIO_PATH=./voice/reference.wav \
REF_TEXT='Configuration validation transcript' \
docker compose -f compose.example.yml config --quiet
git diff --check
```

For container or dependency changes, both Docker targets and their import smoke tests must
pass on `arc-general-docker`. Apply `ready-to-test` only after local validation passes and the
branch is ready to spend runner capacity.

For model execution changes, also run the relevant staged gates from the implementation plan:

1. PyTorch baseline/profile.
2. FP32 OpenVINO tensor, token, position, and cache parity.
3. INT8 accuracy and greedy-code agreement analysis.
4. Voice quality listening checks.
5. Warm median/p95 latency, real-time factor, and peak RSS on `dockermisc1`.
6. PyTorch rollback verification.

Do not lower the 7 GiB production container limit until the final thin runtime is measured
under short and long utterances with at least 20% memory headroom.

## Test Design Guidance

Keep tests separated by cost and required environment:

### Tier 1: Repository and unit tests

Run on every PR without model downloads. Use generated tensors and tiny synthetic modules to
test:

- K/V cache flattening, naming, ordering, and reconstruction
- prefill versus one-token decode shapes
- position IDs, cache positions, masks, and cache-length accounting
- export metadata validation and source/config hash checks
- backend selection and startup mismatch failures
- sampling helpers, suppression lists, EOS handling, and repetition penalties
- HTTP request validation and response formats

Synthetic fixtures must be deterministic and small enough for `arc-general`.

### Tier 2: Container tests

Run on `arc-general-docker` without model weights:

- build both `runtime` and `exporter` targets for Linux AMD64
- import Torch, Torchaudio, Qwen3-TTS, OpenVINO, and NNCF as appropriate
- assert Torch reports a CPU build and does not require CUDA shared libraries
- validate executable entrypoints and dependency metadata
- validate `compose.example.yml`, the image health check, both model presets, the downloader
  module, and the signal-aware supervisor entrypoint

### Tier 3: Model parity tests

Run on `dockermisc1` with the persistent model cache. Use `do_sample=False` and fixed inputs.
Compare one boundary at a time:

1. PyTorch versus FP32 OpenVINO main prefill.
2. Several main decode steps with growing cache.
3. Predictor prefill.
4. All 15 predictor codebook steps.
5. Complete generated code sequences.

Record max/mean absolute error, relative error, top-1 agreement, top-k overlap, cache shapes,
and the first divergent step. Exact waveform equality is not a useful parity criterion.

Parity gates must fail closed:

- Do not catch a missing projection, output head, cache output, or required metric and continue
  with a reduced test. Treat it as a harness failure.
- In multi-step decode tests, carry each backend's own K/V output into its next step. Seeding
  every step from PyTorch cache is allowed only as a separately labeled single-step diagnostic.
- Exercise `talker.codec_head` and all 15 predictor `lm_head` selections before claiming token
  parity. Hidden-state SNR alone cannot complete a transformer milestone.
- Synthetic inputs characterize graph conversion only. Milestone acceptance additionally
  requires inputs and mRoPE positions captured from the real generation path, bounded generated-
  code comparison, production-sampling listening checks, and warm performance measurements.
- Do not lower an existing accuracy threshold solely to make a failed run pass. A gate change
  requires documented generation-level evidence and listening results.
- Verify compression modes and parameter semantics against the pinned NNCF API. Unsupported
  convenience names such as a hypothetical `MIX8` mode must not be added to the exporter CLI.

### Tier 4: INT8 quality and performance

Use both deterministic greedy generation and production sampling. Record:

- generated audio duration and end-to-end latency
- model, vocoder, and serialization timings
- main and predictor step counts
- real-time factor, warm median, and p95
- container peak RSS, host available RAM, swap delta, and CPU utilization
- intelligibility, speaker similarity, repetition, truncation, and audible artifacts

Keep benchmark prompts in source control as text. Store generated audio outside Git and label
results with image digest, model revision, IR metadata hash, and runtime configuration.

## Troubleshooting Playbook

### CPU Torch or Torchaudio cannot be resolved

- Inspect the actual CPU wheel index; do not assume Torch and Torchaudio publish matching
  versions.
- Keep their Docker build arguments independent.
- Compare with the versions already importing successfully on `dockermisc1`.
- After changing a pin, rebuild and smoke-test both Docker targets.

### Why Optimum Intel is not used

`qwen3_tts_talker` is a custom architecture with no exporter registered in Optimum Intel's
`TasksManager`, so `optimum-cli export openvino` and `OVModelFor*.from_pretrained(export=True)`
fail with a "custom or unsupported architecture" error. Do not add Optimum Intel to make this
work. Use tensor-only wrapper modules with `openvino.convert_model()`, then
`nncf.compress_weights()`, as described in the implementation plan.

### Export expects `input_ids`

The main generation path supplies `inputs_embeds`. The wrappers must expose embeddings as the
primary input and keep embedding lookup in PyTorch. An `input_ids`-only IR is not compatible
with the current Qwen3-TTS generator.

### Output matches prefill but diverges during decode

Check, in order:

1. flattened K/V layer ordering and key/value ordering
2. cache sequence length before and after the step
3. `cache_position`, attention mask, and position IDs
4. main-request versus predictor-request reset scope
5. the selected predictor codebook embedding and output head
6. trailing-text versus padding embedding selection

Log the first divergent step and compare its PyTorch/OpenVINO inputs before inspecting later
audio output.

### Stateful generation repeats or contaminates requests

- Main state resets once per utterance.
- Predictor state resets once per audio frame, before its 15-codebook sequence.
- Do not share an `InferRequest` across concurrent requests.
- Do not create a new request per token.
- Use `query_state()` in tests to confirm state exists and resets to the expected length.

Separate prefill and decode compiled models do not implicitly share state. The stateful
milestone uses one dynamic stateful model per transformer core.

### Hugging Face generation code rejects the cache/output object

Do not return `None` or a cosmetic `SimpleNamespace` where Transformers expects a real cache
contract. The integration seam is `self.talker.generate(...)` on
`Qwen3TTSForConditionalGeneration` (reached as `wrapped.model.talker.generate(...)`). Note
that this is the *stock* `GenerationMixin.generate`, not a custom method: the per-frame
code-predictor loop lives inside the talker's custom `forward`, and the outer model consumes
`talker_result.hidden_states` (codes from `hid[-1]`, hidden state from `hid[0][-1]`) with
`output_hidden_states=True` and `return_dict_in_generate=True`. The OpenVINO replacement must
reproduce that sampling loop, the in-`forward` predictor invocation, and that exact return
structure, keeping OpenVINO cache state inside the dedicated runtime.

### OpenVINO is loaded but RAM increases

The first hybrid implementation duplicates PyTorch and OpenVINO transformer weights. RAM only
drops after the unused PyTorch main/predictor layers are released or a thin selective loader
is implemented. Measure RSS after collection; allocator retention can hide released tensors.

Do not delete the complete talker object: embeddings, projections, codebook heads, config,
device, and dtype behavior are still required.

### INT8 runs but is not faster

- Confirm both transformer cores are using OpenVINO.
- Confirm the IR weights are actually compressed.
- Check whether activation dynamic quantization is enabled for supported MatMuls.
- Benchmark dynamic group sizes `0`, `32`, and `64`.
- Profile main versus predictor time; the predictor performs up to 15 steps per audio frame.
- Check for numpy/Torch cache copies or request creation inside token loops.
- Check host contention, throttling, and swap before comparing runs.

### CPU usage stays high

High active utilization is expected. Optimize CPU-seconds and wall time, not peak CPU alone.
Set thread variables before importing numerical runtimes, use one inference request at a time,
benchmark 6 versus 8 threads, and keep `OMP_WAIT_POLICY=PASSIVE` to reduce post-inference spin.

### `KV_CACHE_PRECISION=u8` has no effect

The property applies to cache patterns recognized by OpenVINO. It may not quantize arbitrary
explicit K/V graph inputs and outputs. Validate explicit-cache correctness first, then measure
the property after conversion to recognized stateful cache graphs.

### Export is killed or the VM swaps heavily

- Stop only the existing `qwen3-tts` container before export to release its model memory.
- Do not load a second model inside that container.
- Confirm available memory and swap before starting.
- Keep output on the persistent OpenVINO volume so a container exit does not lose validated
  artifacts.

### Exporter image does not quantize

The bootstrap exporter image contains export dependencies but does not make quantization
functional by itself. `python -m scripts.download_model` is currently supported.
`python export_openvino.py --output-dir /ov_output --compression both --validate` becomes the
supported one-shot conversion only when Milestones 2 and 3 implement the script and its
parity gates. Do not add a placeholder that emits unvalidated IR.

### Container remains up after one Gunicorn service exits

- Confirm the image command is `python serve.py`, not a shell with a background process.
- Confirm both Gunicorn masters were started in their own process groups.
- Confirm the supervisor exits after either child exits and forwards stop signals to the
  remaining group.
- A public `/health` response must return HTTP 503 while the worker is unavailable.

### ARC job remains queued

- Confirm the workflow uses the exact `arc-general` or `arc-general-docker` label.
- Confirm the ARC GitHub App installation includes this repository.
- Check the scale set, ephemeral runner pod, listener logs, and node allocatable resources.
- Do not increase Helm limits merely to hide a workload that belongs on `dockermisc1`.

### GHCR build cache fails

Use a separate cache reference per Docker target. Keep `mode=min,ignore-error=true`; large
`mode=max` intermediate caches have previously been rejected by GHCR. A cache-export failure
must not invalidate an otherwise successful image build.

## Agent Handoff Requirements

Every implementation handoff must state:

- source commit and image tag/digest
- model revision and IR metadata hash
- completed milestone and remaining release gates
- exact validation commands and their results
- benchmark prompts and runtime settings
- whether testing used FP32, INT8, explicit cache, or stateful cache
- known divergences, first failing step, and saved non-Git artifacts
- rollback procedure and whether it was tested

Distinguish clearly between code-path validation, synthetic tests, full-model parity, listening
tests, and target-hardware performance. Passing one category does not imply the others.

## Production VM Safety

- Treat `dockermisc1` as a live shared host.
- Prefer read-only inspection unless the user explicitly authorizes deployment or service
  changes.
- Stop only the `qwen3-tts` service during export maintenance; do not disturb unrelated
  containers.
- Record host load, available RAM, and swap beside performance results.
- Do not run a second full model inside the existing 7 GiB production container.
- On export or deployment failure, restore the previous image or use the PyTorch backend.
- The service has no built-in authentication or TLS. Keep port 8318 on a trusted network or
  use an authenticated TLS reverse proxy, and follow `SECURITY.md` for private reports.

## Commit and Pull Request Conventions

Use Conventional Commits:

```text
feat(runtime): add stateful OpenVINO talker
fix(export): preserve predictor cache positions
perf(runtime): reduce K/V cache transfers
docs(plan): record validated dependency pair
ci(images): publish exporter target
```

Supported types: `feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `build`, `ci`, `chore`,
and `revert`.

Use squash merge. Release Please evaluates the pull request title, so a user-facing feature or
fix must have a corresponding `feat:` or `fix:` PR title.

Every implementation PR body must include an explicit Release Please override block. Put one
Conventional Commit entry on each line so every user-visible change that belongs in the release
notes is represented:

```text
BEGIN_COMMIT_OVERRIDE
fix(ci): publish images only from Release Please tags
fix(export): include the OpenVINO export CLI in the exporter image
END_COMMIT_OVERRIDE
```

The block is authoritative release-note input; keep it aligned with the full PR scope instead
of relying on the PR title alone. Generated Release Please version PRs are exempt. Keep generated
model artifacts and benchmark audio out of PRs.

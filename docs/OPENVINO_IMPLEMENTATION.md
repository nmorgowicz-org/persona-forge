# Qwen3-TTS OpenVINO INT8 Implementation Plan

## Objective

Accelerate either official Qwen3-TTS Base voice-cloning checkpoint on the CPU-only
`dockermisc1` VM while preserving the current `/generate`, `/infer`, and voice-cloning
behavior:

- `Qwen/Qwen3-TTS-12Hz-0.6B-Base` is the default and first optimization target.
- `Qwen/Qwen3-TTS-12Hz-1.7B-Base` uses the same runtime design but has its own export,
  validation, memory, and performance gates.

The production backend will use:

- PyTorch for prompt construction, embedding lookups, sampling, and lightweight glue.
- OpenVINO for both autoregressive transformer cores.
- ONNX Runtime for the existing speech tokenizer and waveform decoder.

The optimization target is at least a 2x reduction in warm end-to-end latency without an
audible quality regression. Treat 7-14 seconds for a short utterance as an investigation
target, not a release guarantee. The measured real-time factor, latency distribution, and
peak memory determine whether the backend ships.

[IRIS NOTE] The 2x claim is reasonable as a target on 0.6B but optimistic for 1.7B and long
prompts on this CPU (no AVX-512, 8 vCPUs, noisy host). Confirm with frontier model:
adjust to model-size-specific targets or add conditional language in "Release Gates."

## Validated Deployment Snapshot

Validated on `dockermisc1` on 2026-06-27:

- Host kernel: Linux `7.0.0-27-generic` under KVM.
- CPU exposed to the VM: 8 single-threaded vCPUs from an Intel Core i7-1360P.
- CPU flags include AVX2 and AVX-VNNI; AVX-512 is not exposed.
- RAM: 15 GiB total, approximately 10 GiB in use during inspection.
- Swap: 8 GiB total, approximately 5.6 GiB in use during inspection.
- Container limit: 7 GiB RAM and 8 GiB RAM+swap.
- Warm container usage during inspection: approximately 4.7 GiB.
- Current stack: Python 3.13.13, `qwen-tts==0.1.1`, PyTorch 2.12.1,
  Torchaudio 2.11.0, Transformers 4.57.3, and ONNX Runtime 1.27.0.
- Service source: `/home/nick/docker/qwen3-tts`.
- Compose file: `/home/nick/docker/docker-compose.yml`.
- Model cache: `/var/data/autopirate/qwen3-tts/model`.

The host runs many other containers. Record host load, CPU throttling, available RAM, and
swap activity beside every benchmark so contention is not mistaken for a model regression.

## Runtime Architecture

The installed `qwen-tts==0.1.1` implementation has two nested autoregressive generators.
The relevant model configuration is:

| Component | Layers | Hidden | Intermediate | KV heads | Work per audio frame |
|---|---:|---:|---:|---:|---|
| 0.6B main talker transformer | 28 | 1024 | 3072 | 8 | One decode step |
| 1.7B main talker transformer | 28 | 2048 | 6144 | 8 | One decode step |
| Code predictor transformer (both sizes) | 5 | 1024 | 3072 | 8 | Up to 15 decode steps |

The configured model has 16 audio code groups. The main talker predicts the first codebook.
For every generated audio frame, the code predictor generates the remaining 15 codebooks.
Both transformers are therefore optimization targets.

The actual call path is:

```text
Qwen3TTSModel.generate_voice_clone()
  -> Qwen3TTSForConditionalGeneration.generate()
       -> construct text, speaker, reference, and codec embeddings in PyTorch
       -> Qwen3TTSTalkerForConditionalGeneration.generate()
            -> main talker prefill
            -> for each audio frame:
                 -> code_predictor.generate(max_new_tokens=15)
                 -> assemble the 16-codebook frame embedding
                 -> main talker decode
       -> speech_tokenizer.decode() in ONNX Runtime
  -> waveform
```

The stable integration seam is `wrapped.model.talker.generate(...)`. The outer Qwen3-TTS
method already prepares `inputs_embeds`, `attention_mask`, `trailing_text_hidden`, and
`tts_pad_embed`, then consumes the generated codebooks and hidden states. Implement an
OpenVINO-backed replacement for this generation method while retaining the original talker
object, its embeddings, projections, configuration, and codebook heads.

Source reference: [Qwen3-TTS model implementation](https://github.com/QwenLM/Qwen3-TTS/blob/main/qwen_tts/core/models/modeling_qwen3_tts.py).

## Design Constraints

1. Export the main transformer core and code predictor core as separate OpenVINO models.
   Python sampling and the nested generation schedule remain explicit.
2. Preserve the original `talker` object. Prompt construction uses its
   `text_projection`, text embeddings, codec embeddings, configuration, device, and dtype.
3. Create prefill/decode requests once and reuse them in the explicit-cache milestone.
4. In the final stateful runtime, keep one main request for the utterance and one predictor
   request that resets once per audio frame and serves all 15 codebook steps.
5. Never create an `InferRequest` per token.
6. Validate FP32 OpenVINO parity before applying INT8 weight compression.
7. Keep the 7 GiB container limit until peak RSS is measured under the final backend.
8. Pin `qwen-tts==0.1.1` and verify the expected model classes and configuration at startup.
   The adapter depends on this generation contract.
9. Derive export shapes from the selected checkpoint configuration. Never hard-code the
   0.6B hidden or intermediate sizes into wrappers shared with 1.7B.

## Model Selection and Authentication

Normal deployments select a Base checkpoint with one setting:

```text
MODEL_SIZE=0.6B|1.7B
```

`MODEL_REPO` is an explicit expert override. The shared resolver maps the two supported sizes
to their official Base repositories and rejects unknown sizes. Both checkpoints are public,
so anonymous download works. `HF_TOKEN` is accepted for authenticated Hugging Face access;
`HF_TOKEN_FILE` is the preferred container setting because it reads a mounted secret without
placing the token in Compose source.

Model download, export, runtime loading, metadata validation, health reporting, and
benchmarking must all use the same resolved repository and revision. Every generated output
directory is checkpoint-specific, for example:

```text
/var/data/autopirate/qwen3-tts/openvino/
  qwen-tts-0.1.1_0.6b_<revision>_ov-2026.2.1/
  qwen-tts-0.1.1_1.7b_<revision>_ov-2026.2.1/
```

Never load 0.6B IR for a 1.7B selection or vice versa. Passing release gates for one model
size does not certify the other.

## Dependency Strategy

Split runtime and export dependencies. The production image does not need NNCF or Optimum
Intel after the IR has been generated:

```text
# requirements-ov-runtime.txt
openvino==2026.2.1

# requirements-ov-export.txt
-r requirements-ov-runtime.txt
optimum-intel[openvino]==2.0.0
nncf==3.2.0
```

These versions were current on 2026-06-27 and support Python 3.13 on x86-64 Linux. Re-run
the compatibility smoke test before changing any pin. Do not use loose lower bounds for
this integration; OpenVINO, Optimum Intel, NNCF, and Transformers evolve together.

Optimum Intel does not provide a registered `qwen3_tts_talker` exporter. Use native
`openvino.convert_model()` with purpose-built wrapper modules. `export_from_model()` remains
useful only if a complete custom export configuration is supplied.

The current PyTorch installation includes CUDA libraries on a CPU-only VM. In the image
cleanup milestone, install the matching CPU-only PyTorch wheel before `qwen-tts` to reduce
image size and avoid unnecessary CUDA packages. This is independent of OpenVINO latency and
must be benchmarked separately.

Pin Torch and Torchaudio independently. The Python 3.13 CPU wheel index currently provides
`torch==2.12.1+cpu` but Torchaudio only through `torchaudio==2.11.0+cpu`; this same mixed
version pair is already running successfully in the existing service. Do not assume both
packages publish identical version numbers.

[IRIS NOTE] The Dockerfile's sed-based patch to override ONNX Runtime's intra_op_num_threads
is fragile across qwen-tts releases. Prefer:
- relying on ORT_INTRA_OP_NUM_THREADS (already set in app_worker.py), or
- a small runtime patch in Python rather than in-place sed on a site-packages file.
Confirm with frontier model.

## Build and Artifact Boundaries

CI builds model-free Linux AMD64 images from the private Git repository. Model weights,
reference audio, and generated OpenVINO IR are never copied into an image or committed to
Git.

Use two Docker targets from the same source revision:

- `runtime`: service code, CPU-only PyTorch, Qwen3-TTS, OpenVINO Runtime, ONNX Runtime, and
  audio dependencies.
- `exporter`: the runtime dependencies plus Optimum Intel, NNCF, export code, and parity
  tooling.

Publish immutable SHA tags to private GHCR, for example:

```text
ghcr.io/nmorgowicz-org/qwen3-tts-openvino:runtime-<git-sha>
ghcr.io/nmorgowicz-org/qwen3-tts-openvino:exporter-<git-sha>
```

Workflow placement:

- `arc-general`: linting, unit tests, metadata/schema tests, and cleanup.
- `arc-general-docker`: Buildx builds both AMD64 image targets after an internal PR receives
  `ready-to-test`, and publishes them from trusted `main`/tag events.
- `dockermisc1`: downloads the Hugging Face model, runs export/quantization, validates the
  generated IR, and runs hardware-specific benchmarks.

CI smoke tests may import packages and exercise synthetic wrapper models, but must not
download or convert the full Qwen3-TTS checkpoint. The ARC Docker runner does not have enough
guaranteed memory for the full export.

Every PR receives lightweight validation. Apply `ready-to-test` only after that validation
passes and the branch is ready for the expensive container matrix. Commits pushed while the
label remains present rerun the matrix.

### One-shot exporter CLI contract

The exporter is a disposable tool container, not a long-running service. Milestones 2 and 3
must implement this stable command:

```bash
python export_openvino.py \
  --output-dir /ov_output \
  --compression both \
  --validate
```

`--compression` accepts `fp32`, `int8`, or `both`. Model selection and authentication come
from `MODEL_SIZE`/`MODEL_REPO`, `MODEL_REVISION`, and optional `HF_TOKEN`/`HF_TOKEN_FILE`.
The command reuses the standard Hugging Face cache and writes only to `--output-dir`.

Write into a temporary checkpoint-specific directory and atomically publish the final
directory only after requested export, parity, compression, and metadata checks pass. Exit
nonzero and leave no apparently valid final artifact on any failure. The exporter dependencies
exist in the first repository bootstrap, but this quantization command is not functional until
Milestones 2 and 3 implement `export_openvino.py`.

Relevant current documentation:

- [OpenVINO inference with Optimum Intel](https://docs.openvino.ai/2026/openvino-workflow-generative/inference-with-optimum-intel.html)
- [OpenVINO deployment through `torch.compile`](https://docs.openvino.ai/2026/openvino-workflow/torch-compile.html)
- [OpenVINO weight compression](https://docs.openvino.ai/2026/openvino-workflow/model-optimization-guide/weight-compression.html)
- [Optimum Intel OpenVINO export API](https://github.com/huggingface/optimum-intel/blob/main/optimum/exporters/openvino/convert.py)

## Milestone 0: Reproducible Baseline and Profile

Create `benchmark_tts.py` before changing the backend.

Benchmark corpus:

1. A fixed 10-word sentence.
2. A fixed 50-60-word paragraph.
3. One representative Hermes response containing punctuation and numbers.

For each prompt, record:

- Input word and character count.
- Generated audio duration.
- Total request latency.
- Model generation latency.
- Vocoder latency.
- MP3 encoding latency.
- Real-time factor: generation seconds / audio seconds.
- Peak container memory and host swap delta.
- Host load and CPU utilization.

Run one warm-up and at least five measured iterations. Report median and p95. Use
`do_sample=False` for deterministic parity tests and the production sampling settings for
quality and latency tests.

Add temporary timers around:

- `talker.model.forward`.
- `talker.code_predictor.model.forward`.
- `speech_tokenizer.decode`.
- Audio serialization.

Also count main-talker steps and code-predictor steps. This establishes where time is spent
and prevents optimizing only one side of the nested generator.

Before benchmarking, set thread controls before importing Torch, ONNX Runtime, or OpenVINO:

```python
os.environ["OMP_WAIT_POLICY"] = "PASSIVE"
os.environ["OMP_NUM_THREADS"] = "6"
os.environ["MKL_NUM_THREADS"] = "6"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
torch.set_num_threads(6)
torch.set_num_interop_threads(1)
```

Benchmark 6 and 8 inference threads. Keep one request in flight; the service already
serializes inference with a single-worker executor.

[IRIS NOTE] As OpenVINO is added, these thread settings become insufficient:
PyTorch, OpenVINO, and ONNX Runtime will compete on 8 vCPUs. Introduce an explicit
thread budget (e.g., OpenVINO 4, PyTorch 4, ORT 2-4), then benchmark splits.
Frontier model should double-check that these numbers remain safe under concurrent
workloads and swap pressure.

## Milestone 1: FP32 OpenVINO Feasibility Spike

Use an isolated image tag and leave the production container unchanged.

First try compiling only the two transformer-core forwards with the OpenVINO
`torch.compile` backend. Do not compile either `generate()` method; their Python control
flow and sampling should remain eager.

Candidate configuration:

```python
ov_compile_options = {
    "aot_autograd": True,
    "model_caching": True,
    "cache_dir": "/ov_cache",
    "config": {
        "PERFORMANCE_HINT": "LATENCY",
        "NUM_STREAMS": "1",
        "INFERENCE_NUM_THREADS": "6",
    },
}
```

Compile:

- `wrapped.model.talker.model.forward`.
- `wrapped.model.talker.code_predictor.model.forward`.

This spike is successful only if:

- OpenVINO captures the transformer graphs rather than falling back to eager PyTorch.
- Dynamic-cache mutation does not cause a new compilation on every decode step.
- The second warm request uses cached compiled models.
- Greedy output matches the baseline.
- Warm end-to-end latency improves by at least 10%.

Time-box this spike. If cache objects or dynamic shapes cause repeated graph breaks, proceed
to explicit OpenVINO IR export.

## Milestone 2: Export the Two Transformer Cores

Create `export_openvino.py`. CI places this script in the exporter image. After that image is
published, run it on `dockermisc1` against the persistent model cache and write the result to
a persistent, versioned output directory such as:

```text
/var/data/autopirate/qwen3-tts/openvino/
  qwen-tts-0.1.1_<size>_<revision>_ov-2026.2.1/
    main_prefill.xml
    main_decode.xml
    predictor_prefill.xml
    predictor_decode.xml
    metadata.json
```

### Export wrappers

Create small `torch.nn.Module` wrappers around:

- `talker.model` for the 28-layer main transformer.
- `talker.code_predictor.model` for the 5-layer predictor transformer.

Each wrapper must accept tensors only and return tensors only. Flatten the per-layer K/V
cache into named inputs and outputs. Do not pass a Transformers `Cache` object through the
OpenVINO boundary.

Export two graphs per core:

- Prefill: dynamic sequence-length `inputs_embeds`, masks/positions, no prior cache.
- Decode: one-token `inputs_embeds`, masks/positions, explicit prior K/V tensors.

Keep embedding lookups and output heads in PyTorch for the first implementation. They are
small relative to the transformer cores and retaining them avoids dynamic embedding-table
and codebook-head selection inside the exported graph.

The exporter must:

1. Resolve `MODEL_SIZE`/`MODEL_REPO`, then load `qwen-tts==0.1.1` and the exact configured
   model revision.
2. Put modules in `eval()` mode and use `torch.inference_mode()`.
3. Build example inputs from the real model configuration rather than hard-coded dimensions.
4. Convert with `openvino.convert_model(wrapper, example_input=...)`.
5. Save uncompressed FP32 IR first.
6. Write model revision, package versions, tensor names, shapes, dtypes, and source config
   hash to `metadata.json`.
7. Record the exporter image digest and Git commit in `metadata.json` so every IR can be
   reproduced from source.

Do not run the exporter while the production PyTorch worker remains loaded. The current
worker holds approximately 4.7 GiB, while the host already uses swap. Stop only the
`qwen3-tts` service for the export maintenance window, run the exporter with the model and
OpenVINO directories mounted read-write, then restart the previous service if export or
validation fails.

### FP32 parity gate

Compare PyTorch and OpenVINO at tensor level for:

- Main prefill hidden states and logits.
- Main decode hidden states and logits after several cached steps.
- Predictor prefill and all 15 predictor decode steps.
- K/V cache lengths and layer count.

Use absolute and relative error summaries, top-1 token agreement, and greedy multi-step code
agreement. Do not proceed to INT8 until FP32 OpenVINO follows the same cache and position
semantics as PyTorch.

## INT8 and CPU microarchitecture note

[IRIS NOTE] AVX-512 is not exposed (only AVX2 + AVX-VNNI). INT8 gains may be modest compared
with plans that assume AVX-512 acceleration. Frontier model should verify that OpenVINO 2026.x
plus NNCF 3.2.x behavior on AVX2/AVX-VNNI still justifies INT8 for this architecture, and
whether the dynamic quantization group-size choices (0/32/64) remain appropriate.

## Milestone 3: INT8 Weight Compression and Runtime Tuning

Apply NNCF weight compression to each validated FP32 IR:

```python
import nncf

compressed = nncf.compress_weights(
    ov_model,
    mode=nncf.CompressWeightsMode.INT8_ASYM,
)
ov.save_model(compressed, output_xml)
```

Compile the compressed models for CPU latency:

```python
ov_config = {
    "PERFORMANCE_HINT": "LATENCY",
    "NUM_STREAMS": "1",
    "INFERENCE_NUM_THREADS": "6",
    "DYNAMIC_QUANTIZATION_GROUP_SIZE": "32",
}
compiled = core.compile_model(model_path, "CPU", ov_config)
```

INT8 weight compression and dynamic activation quantization are separate operations.
`DYNAMIC_QUANTIZATION_GROUP_SIZE` controls runtime activation quantization for supported
MatMuls with compressed weights. OpenVINO enables a group size of 32 by default on CPUs
without XMX; explicitly benchmark `0`, `32`, and `64` for this model.

Keep FP32 or FP16 K/V cache for the explicit-cache implementation. The
`KV_CACHE_PRECISION=u8` runtime property applies to recognized OpenVINO LLM cache patterns;
it must not be assumed to quantize arbitrary explicit graph inputs and outputs.

INT8 acceptance checks:

- Tensor error and top-k agreement against the FP32 IR.
- Greedy generated-code agreement or a documented divergence analysis near close logits.
- A/B listening on all benchmark prompts using production sampling.
- Speaker similarity, intelligibility, truncation, repetition, and noise checks.
- Warm median and p95 latency.
- IR size, compiled-model memory, and peak container RSS.

## Milestone 4: OpenVINO Generation Runtime

Create `ov_talker_runtime.py` with an `OpenVINOTalkerGenerator` that implements the exact
nested generation schedule expected by `talker.generate(...)`.

The runtime owns four compiled models and their requests:

```text
main_prefill_request
main_decode_request
predictor_prefill_request
predictor_decode_request
```

At utterance start:

1. Reset main generation state.
2. Run main prefill with the outer method's prepared embeddings and attention mask.
3. Sample the first codebook using the configured top-k, top-p, temperature, repetition
   penalty, suppression list, and EOS handling.

For each audio frame:

1. Reset predictor state.
2. Build predictor prefill input from the main hidden state and first-codebook embedding.
3. Generate codebooks 2-16 with the correct per-codebook embedding and output head.
4. Sum the 16 codebook embeddings.
5. Add the appropriate trailing-text or padding embedding.
6. Run one main decode step.
7. Append the hidden-state/codebook structure expected by the outer Qwen3-TTS method.
8. Stop on the first-codebook EOS token or `max_new_tokens`.

Reuse the installed Transformers logits processors or port their behavior exactly. Sampling
is part of output quality and must not be approximated during the backend change.

Install the runtime by binding only the talker's `generate` method or by calling it from a
small version-pinned adapter. Do not replace `wrapped.model.talker`; the outer model needs
the original object's embeddings, projections, configuration, dtype, and device.

Return the same generation-result fields consumed by
`Qwen3TTSForConditionalGeneration.generate()`, especially `hidden_states` with generated
codebook IDs and main hidden states.

## Milestone 5: Stateful KV Cache

After the explicit-cache runtime passes parity and benchmarks, produce one dynamic stateful
OpenVINO model for each transformer core. Each stateful model must accept both multi-token
prefill and one-token decode inputs; separate compiled prefill and decode models cannot share
an internal state implicitly. Keep this as a separate milestone so cache bugs remain
observable during initial integration.

State ownership:

- Main talker: one compiled stateful model and one persistent request. Its state persists for
  the full utterance and resets once per request.
- Predictor: one compiled stateful model and one persistent request. Its state persists for
  15 codebooks and resets for every audio frame.

Use a persistent `InferRequest` for each stateful model. Call `query_state()` during tests to
verify state count and reset behavior. With recognized stateful KV-cache graphs, benchmark:

```python
{
    "KV_CACHE_PRECISION": "u8",
    "DYNAMIC_QUANTIZATION_GROUP_SIZE": "32",
    "PERFORMANCE_HINT": "LATENCY",
}
```

Compare stateful FP32-cache and U8-cache output quality before selecting the deployment
setting. The expected benefit is lower per-token cache transfer and allocation overhead;
measure it rather than assuming it.

[IRIS NOTE] Because stateful OpenVINO for custom graphs is less robust than for known
architectures, treat stateful as optional (controlled by an env var) rather than mandatory.
Frontier model should review whether stateful KV-cache is worth the complexity once
explicit-cache runtime is stable and meeting latency goals.

## 1.7B feasibility note

[IRIS NOTE] The 1.7B checkpoint must be treated as its own experiment. On 8 vCPUs with
7 GiB container, it will push both memory and latency; consider:
- (a) looser latency gates (e.g., 1.5x as acceptable),
- (b) mandatory memory budgeting before enabling INT8.
Ask a frontier model to propose concrete memory/latency thresholds for 1.7B on this
profile and whether any of the current release gates are unrealistic at this scale.

## Milestone 6: Memory Reduction

The first working backend may temporarily hold both PyTorch transformer weights and OpenVINO
weights. Do not lower the Compose memory limit in that state.

After parity:

1. Keep PyTorch text/codec embeddings, text projection, codebook output heads, prompt logic,
   and ONNX speech components.
2. Release only the PyTorch main-transformer and predictor-transformer layers after OpenVINO
   models compile successfully.
3. Verify that voice-prompt creation and every embedding lookup still work.
4. Measure RSS after garbage collection and, on glibc, an optional `malloc_trim(0)`.
5. If allocator retention remains high, add a thin runtime loader that selectively loads only
   the PyTorch tensors still used at inference rather than loading and deleting the full model.

Reduce `mem_limit` only after measuring cold start, warm inference, a long utterance, and
failure behavior under the proposed limit. Maintain at least 20% headroom above observed
peak RSS.

## Service Integration

Keep `app_api.py` and the external HTTP contract unchanged. Update `app_worker.py` to select
the backend with an environment variable:

```text
TTS_BACKEND=pytorch|openvino
OV_MODEL_DIR=/ov_model/qwen-tts-0.1.1_0.6b_ov-2026.2.1
OV_INFERENCE_THREADS=6
OV_DYNAMIC_QUANT_GROUP_SIZE=32
OV_KV_CACHE_PRECISION=u8
```

The worker should fail startup if metadata does not match the installed Qwen package, model
repository, model revision, architecture, tensor dimensions, or configured code-group count.
Do not silently fall back after a partial OpenVINO initialization; use
`TTS_BACKEND=pytorch` for explicit rollback.

Extend `/health` with:

- Selected backend.
- OpenVINO version and device.
- IR metadata hash.
- Thread and quantization settings.
- Whether stateful KV cache is active.

The public API readiness endpoint returns HTTP 200 only after the worker reports ready and
returns HTTP 503 while the worker is loading or unreachable. The image health check uses this
endpoint. Keep its long first-start grace period because an empty cache may require a complete
checkpoint download.

`serve.py` remains PID 1 and supervises both Gunicorn masters. It must forward `SIGTERM` and
`SIGINT` to both process groups, allow graceful shutdown, and terminate the container if
either service exits. Do not restore a shell command that backgrounds one Gunicorn process
without signal forwarding.

Compose additions after the IR exists:

```yaml
environment:
  - TTS_BACKEND=openvino
  - OV_MODEL_DIR=/ov_model/qwen-tts-0.1.1_0.6b_ov-2026.2.1
  - OV_INFERENCE_THREADS=6
  - OMP_WAIT_POLICY=PASSIVE
volumes:
  - /var/data/autopirate/qwen3-tts/openvino:/ov_model:ro
```

Keep `mem_limit: 7G` and `memswap_limit: 8G` until Milestone 6 is complete.

### Build, export, and deployment sequence

1. Merge a source revision after lightweight CI passes.
2. `arc-general-docker` builds and pushes `runtime-<git-sha>` and `exporter-<git-sha>`.
3. Pull both immutable tags on `dockermisc1`.
4. Set `MODEL_SIZE` to `0.6B` or `1.7B`, with optional `HF_TOKEN_FILE`, and pre-download the
   selected checkpoint into the persistent cache.
5. Stop the existing `qwen3-tts` container to release its model memory.
6. Run `exporter-<git-sha>` with the same model selection and these mounts:
   - `/var/data/autopirate/qwen3-tts/model:/root/.cache/huggingface/hub:rw`
   - `/var/data/autopirate/qwen3-tts/openvino:/ov_output:rw`
7. Run parity and IR metadata validation in the exporter container.
8. Point Compose at `runtime-<git-sha>` and the matching validated IR directory.
9. Start the service, verify `/health`, and run the short and paragraph benchmarks.
10. Roll back by restoring the previous image/Compose settings or by setting
   `TTS_BACKEND=pytorch`.

Deployment must use immutable SHA tags or image digests. Moving `latest` tags may exist for
convenience but must not be the Compose production reference.

## Files to Create or Modify

| File | Action |
|---|---|
| `requirements-ov-runtime.txt` | Add the pinned OpenVINO runtime dependency |
| `requirements-ov-export.txt` | Add pinned Optimum Intel and NNCF export dependencies |
| `benchmark_tts.py` | Reproducible latency, RTF, memory, and quality benchmark harness |
| `profile_tts.py` | Per-component timing and generation-step counters |
| `export_openvino.py` | Implement the documented one-shot export, validation, and compression CLI |
| `ov_export_wrappers.py` | Tensor-only prefill/decode wrappers and cache flattening |
| `ov_talker_runtime.py` | Nested main-talker/code-predictor generation runtime |
| `test_ov_parity.py` | FP32 and INT8 tensor/cache/token parity tests |
| `app_worker.py` | Backend selection, loading, health metadata, and rollback path |
| `app_api.py` | Preserve API behavior and return HTTP 503 until the worker is ready |
| `serve.py` | Supervise both Gunicorn masters and forward shutdown signals |
| `Dockerfile` | Experimental OpenVINO stage and CPU-only PyTorch cleanup |
| `compose.example.yml` | Keep runnable runtime/downloader wiring and add the validated IR mount |
| `.github/workflows/ci.yml` | Lightweight tests on `arc-general` without model download |
| `.github/workflows/image.yml` | Build and publish runtime/exporter targets on `arc-general-docker` |
| `scripts/export-on-dockermisc1.sh` | Versioned host-side export and validation command |

## Release Gates

Ship the OpenVINO backend only when all gates pass:

1. FP32 IR parity passes for both prefill/decode cores and both KV caches.
2. INT8 quality passes deterministic code checks and listening tests.
3. No per-token graph compilation or `InferRequest` creation occurs.
4. Main state resets per utterance and predictor state resets per audio frame.
5. For each model size released, five-run warm median improves by at least 2x, or the measured
   result is explicitly accepted based on quality and resource savings.
6. p95 latency, real-time factor, and peak RSS are recorded for short and paragraph prompts.
7. The container remains below its memory limit without increasing host swap pressure.
8. `/generate`, `/infer`, `/health`, MP3 output, WAV output, and serialized concurrency pass.
9. `TTS_BACKEND=pytorch` provides a tested one-setting rollback.

[IRIS NOTE] Gate 5 (2x improvement) should probably be model-size-specific: 2x for 0.6B is
reasonable; for 1.7B on this hardware, 1.5x might be more honest. Ask frontier model to
clarify thresholds and whether we should call this out explicitly here.

## First Commands for the Implementation Session

Run read-only verification before modifying the service:

```bash
ssh nick@dockermisc1
cd /home/nick/docker/qwen3-tts

docker exec qwen3-tts python3 - <<'PY'
import inspect
import os
from qwen_tts.core.models.configuration_qwen3_tts import Qwen3TTSConfig
from qwen_tts.core.models.modeling_qwen3_tts import (
    Qwen3TTSTalkerCodePredictorModel,
    Qwen3TTSTalkerForConditionalGeneration,
    Qwen3TTSTalkerModel,
)

model_size = os.getenv("MODEL_SIZE", "0.6B").upper()
model_id = {
    "0.6B": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
}[model_size]
config = Qwen3TTSConfig.from_pretrained(model_id, local_files_only=True)

print("talker class:", Qwen3TTSTalkerForConditionalGeneration)
print("talker model class:", Qwen3TTSTalkerModel)
print("predictor model class:", Qwen3TTSTalkerCodePredictorModel)
print("talker forward:", inspect.signature(Qwen3TTSTalkerForConditionalGeneration.forward))
print("main core forward:", inspect.signature(Qwen3TTSTalkerModel.forward))
print("predictor core forward:", inspect.signature(Qwen3TTSTalkerCodePredictorModel.forward))
print("talker config:", config.talker_config)
PY
```

This inspection loads configuration and source only. Do not load a second full model inside
the running 7 GiB container; the production worker already holds the model weights.

The implementation session should then complete Milestone 0 and attach the baseline/profile
results before selecting the `torch.compile` spike or custom IR path.
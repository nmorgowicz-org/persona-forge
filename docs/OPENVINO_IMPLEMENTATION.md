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
- A decision (Milestone 0 finding) for the waveform decoder: it is **PyTorch, not ONNX
  Runtime** on the live install — `speech_tokenizer.decode` runs `Qwen3TTSTokenizerV2Decoder
  .chunked_decode`, a 114M-parameter conv/GAN vocoder, in a single non-iterative forward. At
  ~29% of end-to-end it is a strong OpenVINO/INT8 conversion candidate (no KV cache, no loop),
  and leaving it in PyTorch caps the achievable speedup. See "Milestone 0".

The optimization target is at least a 2x reduction in warm end-to-end latency without an
audible quality regression. Treat 7-14 seconds for a short utterance as an investigation
target, not a release guarantee. The measured real-time factor, latency distribution, and
peak memory determine whether the backend ships.

Targets are model-size-specific. 2x warm-latency reduction is a reasonable goal for 0.6B.
For 1.7B on this CPU (no AVX-512, 8 vCPUs, noisy host) it is optimistic; treat 1.5x as
the acceptance floor and validate per "Release Gates." The code predictor (15 sequential
forward passes per audio frame) is the dominant cost *within the transformer loop*: the
measured Milestone 0 baseline (0.6B, FP32, sampling — see "Milestone 0") puts it at ~69%
of main+predictor time, confirming the ~70% external figure when scoped that way. It is
therefore the highest-value transformer target, not a co-equal of the main talker.

Two findings from that baseline reshape the end-to-end picture and must be carried forward:

- The `speech_tokenizer.decode` (code -> waveform) is **~29% of end-to-end wall time** in a
  single call (8.1 s of a 27.8 s run). Accelerating only the two transformer cores leaves
  this untouched and caps the achievable speedup; the tokenizer/vocoder decode is now a
  first-class profiling and optimization target, not glue. Profiled: it is **PyTorch**
  (`Qwen3TTSTokenizerV2Decoder.chunked_decode`, 114M params, single non-iterative forward),
  not ONNX Runtime — so it is a clean OpenVINO/INT8 conversion candidate, not a fixed cost.
- Greedy decoding (`do_sample=False`) does **not** terminate on this model — it runs to
  `max_new_tokens` instead of emitting EOS (a short sentence ran past 575 frames / 46 s of
  audio before being stopped). Realistic latency/RTF must be measured under production
  sampling. Parity tests, which need determinism, must therefore compare a *bounded* number
  of decode steps (prefill + N steps), never a full greedy utterance to EOS.

## Implementation Status

**Milestone 1.5 — Vocoder decoder export: COMPLETE (2026-06-28)**

- FP32 IR exported and validated: SNR **46.4 dB** vs PyTorch (mean_abs 1.76e-4, p99.9 6.8e-3).
  The 1e-4 max_abs gate is not the right criterion for a GAN conv decoder where floating-point
  accumulation reordering produces single-sample outliers; SNR ≥ 40 dB is the accepted gate.
- INT8 weight compression **rejected**: SNR 16.3 dB (audibly degraded); speedup negligible
  (1.23×) vs FP32 IR (1.27×). Conv/GAN operations do not benefit from weight-only INT8.
- Warm vocoder-only latency (dockermisc1, 6 threads, seq=325): PyTorch 15.6s → FP32 IR 12.3s
  (1.27×). The 1.5× target was set for INT8; FP32-only is accepted given INT8 is rejected on
  quality grounds. End-to-end impact: vocoder is 29% of wall time, so 1.27× vocoder → ~1.07×
  end-to-end — modest on its own. Transformer cores are the dominant remaining target.
- IR artifacts: `qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1_vocoder/` on dockermisc1.
  Parity report: `vocoder_parity_metrics.json`. Benchmark: `vocoder_benchmark.json`.

In place today:

- PyTorch-only worker (`app_worker.py`) serving `/infer` and `/health`, with the
  single-worker serialized executor and signal-forwarding supervisor (`serve.py`).
- Model selection and HF authentication helpers (`model_config.py`).
- Split dependency sets (`requirements.txt`, `requirements-ov-runtime.txt`,
  `requirements-ov-export.txt`) and `runtime`/`exporter` Docker targets.
- Model-free CI validation (`scripts/validate_repo.py`) and one-shot download tool.
- Milestone 0 harness (`bench_common.py`, `benchmark_tts.py`, `profile_tts.py`) with a
  first measured baseline captured under "Milestone 0" (0.6B FP32, sampling, RTF ~6.6).
- Milestone 1.5 vocoder export: `VocoderDecoderWrapper`, `vocoder_dims()`, `--vocoder-only`
  flag, `test_vocoder_parity.py` (with SNR/p99 metrics and SNR gate), `benchmark_vocoder.py`.
  FP32 IR passes SNR gate; INT8 rejected (see above). Runtime integration pending.
- Milestone 2 transformer core export: COMPLETE (2026-06-28)

**Milestone 2 — Transformer core export and FP32 parity gate: COMPLETE (2026-06-28)**

Four IR graphs exported and parity-gated against PyTorch eager on dockermisc1:

- `main_prefill.xml`, `main_decode.xml` (28-layer, 0.6B main talker)
- `predictor_prefill.xml`, `predictor_decode.xml` (5-layer code predictor)

FP32 parity (OV 2026.2.1, 6 threads, seed 20260628): SNR **72–91 dB** across all 8
scopes (prefill + 3 decode steps for each core). Gate: SNR ≥ 60 dB. All pass.
IR artifacts: `qwen-tts-0.1.1_0.6b_main_ov-2026.2.1/` on dockermisc1.
Parity report: `transformer_parity.json`.

Two non-obvious export bugs encountered and fixed during this milestone:

1. **`create_causal_mask` bakes static `kv_length` into the decode IR**: The model's
   `create_causal_mask` calls `past_key_values.get_mask_sizes()`, which returns Python ints
   at trace time. These become static constants in the OV IR, locking the decode mask to the
   example prior length. Fix: `CoreCacheWrapper._build_causal_mask` constructs a 4D additive
   mask from tensor ops and passes it as `attention_mask`. This triggers the
   `_preprocess_mask_arguments` early-exit (transformers 4.57.3: `if isinstance(m, Tensor)
   and len(m.shape) == 4: return True, m, ...`), bypassing `get_mask_sizes()` entirely.

2. **`DynamicLayer.lazy_initialization` creates a rank-1 empty tensor that OV rejects**:
   The default `lazy_initialization` seeds `self.keys = torch.tensor([])` (shape `[0]`,
   rank 1). PyTorch allows `torch.cat([rank-1-empty, rank-4-keys], dim=-2)` as a special
   case; OV's converter validates axis bounds per input rank and rejects axis -2 for rank 1.
   A subclass approach (`layer_class_to_replicate`) failed because `DynamicCache.__init__()`
   calls `Cache.__init__(layer_class_to_replicate=DynamicLayer)`, setting an *instance*
   attribute that overrides any class attribute on the subclass. Fix: monkey-patch
   `DynamicLayer.lazy_initialization` at module import time to seed with
   `key_states[..., :0, :]` — a rank-4 `[batch, kv_heads, 0, head_dim]` tensor.

**Caveat**: the parity gate uses `position_ids = arange(seq)` and `cache_position = arange(seq)`
as a scaffold. The main core uses 3-axis mRoPE expansion (`position_ids.expand(3, ...)`);
exact values from the live `talker.generate` path have not been traced and compared.
The parity gate proves IR correctness and dynamic-shape safety; end-to-end code-sequence
agreement requires M4 integration and a generation-level comparison.

Not yet implemented: INT8 compression validation, the OpenVINO generation runtime
(`ov_talker_runtime.py`), and the `TTS_BACKEND=openvino` worker path with its `/health`
metadata.

## Validated Deployment Snapshot

Validated on `dockermisc1` on 2026-06-28 (M2 complete):

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
- OV IR artifacts: `/var/data/autopirate/qwen3-tts/openvino/qwen-tts-0.1.1_0.6b_main_ov-2026.2.1/`
  (main transformer cores, FP32, M2 validated). Vocoder IR:
  `qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1_vocoder/` (M1.5 validated).
- Exporter image: `ghcr.io/nmorgowicz-org/qwen3-tts-openvino:exporter-v0.4.4`

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
  -> Qwen3TTSForConditionalGeneration.generate()   # custom; builds all embeddings
       -> construct text, speaker, reference, and codec embeddings in PyTorch
       -> self.talker.generate(inputs_embeds=..., attention_mask=..., **subtalker_kwargs)
            # NOTE: this is STOCK transformers GenerationMixin.generate, not a custom method
            -> main talker prefill, then per-frame decode driven by the HF sampling loop
            -> talker.forward (custom) runs the code predictor for codebooks 2..16 inline
       -> consume talker_result.hidden_states: codes = hid[-1], hidden = hid[0][-1]
       -> speech_tokenizer.decode() -> Qwen3TTSTokenizerV2Decoder.chunked_decode (PyTorch, ~29%)
  -> waveform
```

The integration seam is `self.talker.generate(...)` on `Qwen3TTSForConditionalGeneration`
(reached as `wrapped.model.talker.generate(...)`). Two facts verified against
`qwen-tts==0.1.1` that the Milestone 4 implementer must rely on:

- `talker.generate` is **not** a custom method — it is the stock transformers
  `GenerationMixin.generate`. The custom nested schedule (predict first codebook, then run
  the 5-layer code predictor for codebooks 2..16, assemble the 16-codebook frame, decode the
  next main step) lives inside the talker's custom `forward`, threaded via the `subtalker_*`
  sampling kwargs. So the OpenVINO replacement must reproduce both the HF sampling loop *and*
  the in-`forward` code-predictor invocation; there is no single custom generate to mirror.
- The outer model calls the talker with `output_hidden_states=True` and
  `return_dict_in_generate=True`, then reads `talker_result.hidden_states`, taking the
  generated codes from `hid[-1]` and the main hidden state from `hid[0][-1]`. The replacement
  must return this exact structure.

The outer method already prepares `inputs_embeds`, `attention_mask`, `trailing_text_hidden`,
and `tts_pad_embed`. Implement an OpenVINO-backed replacement for the talker generation while
retaining the original talker object, its embeddings, projections, configuration, and
codebook heads.

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

Split runtime and export dependencies. The production image does not need NNCF after the
IR has been generated:

```text
# requirements-ov-runtime.txt
openvino==2026.2.1

# requirements-ov-export.txt
-r requirements-ov-runtime.txt
nncf==3.2.0
```

These versions were current on 2026-06-27 and support Python 3.13 on x86-64 Linux. Re-run
the compatibility smoke test before changing any pin. Do not use loose lower bounds for
this integration; OpenVINO, NNCF, and Transformers evolve together.

### Export library: `openvino` + `nncf` only, no Optimum Intel

The export path uses OpenVINO and NNCF directly. Optimum Intel is intentionally **not** a
dependency. The reasoning, which a future implementation must not silently reverse:

- The talker is a custom architecture. Optimum Intel exports models through architecture
  configs registered in its `TasksManager`; there is no registered `qwen3_tts_talker`
  exporter, so `optimum-cli export openvino` and `OVModelFor*.from_pretrained(export=True)`
  fail for this model with a "custom or unsupported architecture" error.
- Both APIs the plan actually needs are standalone and require neither Optimum nor a
  registered config:
  - `openvino.convert_model(wrapper, example_input=...)` traces a plain `torch.nn.Module`
    (the per-core wrappers from Milestone 2) straight to an `openvino.Model`.
  - `nncf.compress_weights(ov_model, mode=nncf.CompressWeightsMode.INT8_ASYM)` quantizes
    that `openvino.Model`. Optimum Intel is only a convenience wrapper over this same NNCF
    call, so it adds nothing for custom modules.
- Avoiding Optimum Intel also removes a transitive constraint: each Optimum Intel release
  pins a compatible Transformers range, which can collide with the exact Transformers
  version `qwen-tts==0.1.1` requires. Depending only on `openvino` + `nncf` keeps the
  Transformers pin owned solely by `qwen-tts`.

The only scenario that would justify Optimum Intel is reusing its `export_from_model()`
plumbing, and that still requires writing a complete `custom_export_configs` entry for the
talker — strictly more work than the custom-wrapper + `convert_model()` path above. Do not
add it for that reason without a concrete justification recorded here.

The current PyTorch installation includes CUDA libraries on a CPU-only VM. In the image
cleanup milestone, install the matching CPU-only PyTorch wheel before `qwen-tts` to reduce
image size and avoid unnecessary CUDA packages. This is independent of OpenVINO latency and
must be benchmarked separately.

Pin Torch and Torchaudio independently. The Python 3.13 CPU wheel index currently provides
`torch==2.12.1+cpu` but Torchaudio only through `torchaudio==2.11.0+cpu`; this same mixed
version pair is already running successfully in the existing service. Do not assume both
packages publish identical version numbers.

The Dockerfile's sed-based patch of ONNX Runtime's `intra_op_num_threads` in
`speech_vq.py` is fragile across `qwen-tts` releases (it depends on an exact source line)
and should be replaced. Because `qwen-tts` sets `intra_op_num_threads` explicitly on the
`SessionOptions`, that hard-coded value overrides the `ORT_INTRA_OP_NUM_THREADS` environment
variable, so the env var alone does not fix it. Apply a small runtime monkeypatch in Python
before the ONNX session is created (or upstream a configurable thread count) instead of
editing a site-packages file at build time.

## Build and Artifact Boundaries

CI builds model-free Linux AMD64 images from the private Git repository. Model weights,
reference audio, and generated OpenVINO IR are never copied into an image or committed to
Git.

Use two Docker targets from the same source revision:

- `runtime`: service code, CPU-only PyTorch, Qwen3-TTS, OpenVINO Runtime, ONNX Runtime, and
  audio dependencies.
- `exporter`: the runtime dependencies plus NNCF, export code, and parity tooling.

Publish immutable SHA tags to private GHCR, for example:

```text
ghcr.io/nmorgowicz-org/qwen3-tts-openvino:runtime-<git-sha>
ghcr.io/nmorgowicz-org/qwen3-tts-openvino:exporter-<git-sha>
```

Workflow placement:

- `arc-general`: linting, unit tests, metadata/schema tests, and cleanup.
- `arc-general-docker`: Buildx builds both AMD64 image targets after an internal PR receives
  `ready-to-test`, and publishes them from Release Please version tags or an explicit manual
  workflow dispatch. Merges to `main` do not publish images.
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
Set `SOURCE_COMMIT` to the full commit SHA for the mounted exporter source and
`EXPORTER_IMAGE_DIGEST` to the immutable `sha256:...` registry digest; publication fails if
either provenance value is absent or malformed.
The command reuses the standard Hugging Face cache and writes only to `--output-dir`.

Write into a temporary checkpoint-specific directory and atomically publish the final
directory only after requested export, parity, compression, and metadata checks pass. Exit
nonzero and leave no apparently valid final artifact on any failure. The exporter dependencies
exist in the first repository bootstrap, but this quantization command is not functional until
Milestones 2 and 3 implement `export_openvino.py`.

Relevant current documentation:

- [Convert a PyTorch model with `openvino.convert_model()`](https://docs.openvino.ai/2026/openvino-workflow/model-preparation/convert-model-pytorch.html)
- [OpenVINO deployment through `torch.compile`](https://docs.openvino.ai/2026/openvino-workflow/torch-compile.html)
- [OpenVINO weight compression (NNCF `compress_weights`)](https://docs.openvino.ai/2026/openvino-workflow/model-optimization-guide/weight-compression.html)

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

### Measured baseline (first pass)

0.6B Base, FP32, CPU (dockermisc1, no AVX-512), **production sampling**, 10-word prompt,
single profiled generation via `profile_tts.py --prompt short`:

| Component             | Time    | Share | Calls | Per call |
| --------------------- | ------- | ----- | ----- | -------- |
| `code_predictor`      | 12.66 s | 45.6% | 795   | 15.9 ms  |
| `speech_tokenizer.decode` | 8.09 s | 29.1% | 1   | 8.09 s   |
| `main_talker`         | 5.78 s  | 20.8% | 54    | 107 ms   |
| other / glue          | 1.25 s  | 4.5%  | —     | —        |
| **end-to-end**        | 27.78 s | —     | —     | RTF 6.55 |

Predictor/main step ratio 14.7 (≈ the 15 codebooks/frame). Predictor is ~69% of the
transformer loop (main+predictor) — confirms the ~70% assumption. But note the tokenizer
decode is ~29% of *end-to-end*: a two-core-only backend caps speedup around 3.4x and must
be paired with tokenizer profiling. Greedy (`do_sample=False`) did not terminate; these
numbers are sampling-mode and parity must use bounded decode steps (see "Set the right
warm-latency target").

Warm latency from `benchmark_tts.py --prompts short --iterations 5` (same config, 5 measured
runs after 1 warm-up): median **28.7 s**, p95 **30.8 s** for ~4.6 s of audio (RTF 6.18);
**peak RSS 6394 MiB**, swap delta negligible (466 pages in, 0 out). The 6.4 GiB peak against
the 7 GiB production limit leaves <20% headroom *at FP32 baseline*, before any hybrid backend
that transiently holds both PyTorch and OpenVINO weights — the thin selective loader / memory
milestone is load-bearing for the limit, not optional polish.

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

Once OpenVINO is added, a single shared thread count is insufficient: PyTorch and OpenVINO
compete for the same 8 vCPUs (ONNX Runtime too if any encode path uses it). Because the
stages run sequentially per request — transformer generation, then the one-shot vocoder
decode — the active stage should get the bulk of the cores. The vocoder decoder is PyTorch
today (or OpenVINO once converted), not ONNX Runtime; budget threads for whichever engine
actually runs `chunked_decode`. Start from an explicit per-engine budget (OpenVINO transformer
cores 6, vocoder decode 6 while it is the only active stage, residual PyTorch glue small) and
benchmark alternative splits. Set every engine's thread count explicitly rather than
leaving any at its library default.

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

## Milestone 1.5: Vocoder Decoder Export

Export `speech_tokenizer.model.decoder` (`Qwen3TTSTokenizerV2Decoder`) before tackling the
transformer cores. It is the simplest of the three models — no KV cache, no autoregressive
loop, single feed-forward call — and it contributes ~29% of end-to-end latency (Milestone 0).
Doing it first exercises `export_openvino.py` end-to-end (convert → INT8 → dynamic-axis →
metadata) on clean footing before the cache/mRoPE complexity of Milestone 2.

### Export contract (verified qwen-tts==0.1.1)

Access path: `wrapped.model.speech_tokenizer.model.decoder` — the inference-level
`Qwen3TTSTokenizer` stores the loaded `Qwen3TTSTokenizerV2Model` under `.model`, whose
`.decoder` is the `Qwen3TTSTokenizerV2Decoder` instance.
`VocoderDecoderWrapper` in `ov_export_wrappers.py` wraps it for `openvino.convert_model`.

```
forward(codes) -> wav

codes:  [batch=1, num_quantizers=16, seq_len]  int64  (VQ indices, 0..codebook_size-1=2047)
wav:    [batch=1, 1, audio_samples]            float32 (clamped [-1, 1])
```

Decoder config defaults (Qwen3-TTS-12Hz-0.6B-Base, also 1.7B — both use same vocoder):

```
num_quantizers=16, codebook_size=2048
upsample_rates=(8, 5, 4, 3), upsampling_ratios=(2, 2)
total_upsample = prod([8, 5, 4, 3, 2, 2]) = 1920  (samples per input frame at 24 kHz)
```

**What to export**: `Decoder.forward` (the per-chunk call). The `chunked_decode` loop
(`chunk_size=300, left_context_size=25`) stays in Python. Only one graph needed: no
prefill/decode split, no cache tensors.

Use `python export_openvino.py --output-dir /ov_output --compression both --vocoder-only`
for this milestone. The exporter writes an isolated `_vocoder` artifact directory so a
validated vocoder-only result cannot be mistaken for, or block, the later five-graph export.

**Fixed input contract**: export `codes` as `[1, 16, 325]`. The stock chunk loop uses a
300-frame chunk plus up to 25 frames of left context. TorchScript bakes the decoder's Python
shape arithmetic, and `torch.export` cannot satisfy the convolution/transposed-convolution
guards for an arbitrary symbolic length, so post-conversion `reshape()` is not a valid dynamic
graph. Right-pad shorter decoder calls to 325 frames with valid code `0`, run the causal graph,
then crop to `actual_frames * 1920` output samples before applying the stock left-context crop.
Parity at 8, 32, 300, and 325 frames must prove padded future codes do not affect retained audio.

The tokenizer transformer normally builds its causal/sliding-window mask through Transformers'
generic `torch.vmap` mask factory, which TorchScript/OpenVINO cannot trace. The tensor-only
vocoder wrapper must construct the equivalent 4-D additive masks directly (`kv <= q` and
`kv > q - sliding_window`) and pass the `full_attention`/`sliding_attention` mapping into
`pre_transformer`. Compare the wrapper against the stock decoder in PyTorch before conversion;
this bypass is accepted only if the FP32 waveform gate below passes.

### FP32 parity gate

Run `Decoder.forward` in PyTorch and through the compiled FP32 IR on the same random codes
tensor. Accept if SNR ≥ 40 dB on the full-length (325-frame) output waveform.

Max-abs is NOT the right gate for a GAN vocoder: the transposed-conv upsampler causes
OpenVINO to reorder floating-point accumulation, producing rare single-sample outliers that
inflate max_abs to ~0.05 while the mean error (1.76e-4) and SNR (46.4 dB) remain excellent.
Use `--fp32-min-snr 40` when invoking `test_vocoder_parity.py` for this model.

Run `test_vocoder_parity.py --model-dir <versioned-vocoder-dir> --fp32-min-snr 40 \
    --sequence-lengths 325` in the exporter container. The gate writes `vocoder_parity.json`
beside the IR with source/image provenance, metadata hash, error summaries, SNR, and timings.

**Validated result (2026-06-28, 0.6B-Base, OV 2026.2.1):** SNR 46.4 dB, mean_abs 1.76e-4,
p99.9 6.8e-3. Wrapper seam: 0.0 error at seq=325. Gate: PASSED.

### INT8 acceptance gate (REJECTED for vocoder)

Weight-only INT8 compression (`nncf.compress_weights`) does not benefit GAN/conv operations:

- INT8 IR SNR: 16.3 dB (audibly degraded; gate is ≥ 30 dB).
- INT8 speedup: 1.23× vs FP32 IR 1.27× — negligible gain.

INT8 vocoder is rejected. FP32 IR is the accepted vocoder backend.

### Performance target

Baseline: `speech_tokenizer.decode` = ~8.1 s per utterance (29% of 27.8 s end-to-end).
Achieved: **1.27× FP32 speedup** (PyTorch 15.6s → FP32 IR 12.3s, warm 6-thread, seq=325).
The 1.5× INT8 target is withdrawn — INT8 is quality-rejected. FP32 result accepted.

## Milestone 2: Export the Two Transformer Cores ✓ COMPLETE

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

- `talker.model` for the main transformer.
- `talker.code_predictor.model` for the predictor transformer.

Each wrapper must accept tensors only and return tensors only. Flatten the per-layer K/V
cache into named inputs and outputs. Do not pass a Transformers `Cache` object through the
OpenVINO boundary.

Derive every shape from the loaded config; do not hard-code. Verified attribute paths and
values for the 0.6B Base checkpoint (`qwen-tts==0.1.1`, transformers 4.57.3):

- Main core: `config.talker_config` → `num_hidden_layers=28`, `hidden_size=1024`,
  `intermediate_size=3072`, `num_attention_heads=16`, `num_key_value_heads=8` (GQA).
- Predictor core: `config.talker_config.code_predictor_config` → `num_hidden_layers=5`,
  `hidden_size=1024`, `intermediate_size=3072`, `num_key_value_heads=8`.
- `config.talker_config.num_code_groups=16` (1 main codebook + 15 predictor codebooks).

The 1.7B checkpoint shares this layout but with larger `hidden_size`/`intermediate_size`;
read it from its own config rather than scaling these numbers by hand.

Verified core forward and cache contract (qwen-tts==0.1.1 / transformers 4.57.3),
implemented in `ov_export_wrappers.py`:

- `head_dim=128` for both cores — decoupled from `hidden_size/num_attention_heads`
  (1024/16=64). Do not assume `head_dim = hidden/heads`. Each per-layer K/V tensor is
  `[batch, num_key_value_heads=8, seq, head_dim=128]`.
- Both core forwards accept `inputs_embeds, attention_mask, position_ids, past_key_values,
  cache_position, use_cache` and return `BaseModelOutputWithPast`. The predictor core
  additionally accepts `generation_steps`.
- The cores use a `DynamicCache`, which in transformers 4.57.3 stores `self.layers[i]`
  (`.keys`/`.values`) — not the older `key_cache`/`value_cache` lists. The wrappers convert
  flat tensors via `DynamicCache.from_legacy_cache()` / `.to_legacy_cache()` rather than
  touching internals, so the boundary stays a flat tensor list (`k0, v0, k1, v1, ...`).
- Pass `cache_position` (and `position_ids`) as **explicit** wrapper inputs. If omitted, the
  core derives `cache_position` from the cache length, which trace-bakes the decode graph to
  the example prior length and breaks dynamic decode.
- The main core expands `position_ids` into a 3-axis mRoPE layout internally. The exact
  `position_ids`/`cache_position` values the eager generation path supplies at prefill and at
  each decode step are NOT yet confirmed and are the primary subject of the FP32 parity gate
  (greedy top-1 token agreement). The predictor's `generation_steps` semantics across the 15
  codebook steps are likewise parity-gated.

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
3. Load the export copy with `attn_implementation="eager"`, then explicitly set
   `_attn_implementation="eager"` on the distinct nested configs under the vocoder decoder,
   main core, and predictor core. The top-level load option does not propagate into the separately
   loaded speech tokenizer. Its default mask path uses nested `torch.vmap` operations that
   TorchScript/OpenVINO cannot trace (`unordered_map::at`). The vocoder wrapper supplies the
   equivalent explicit mask described in Milestone 1.5; the transformer-core mask seam remains
   separately parity-gated. Record the selected implementation in metadata and compare against
   the normal PyTorch baseline at the parity gate.
4. Build example inputs from the real model configuration rather than hard-coded dimensions.
5. Convert with `openvino.convert_model(wrapper, example_input=...)`.
6. Save uncompressed FP32 IR first.
7. Write model revision, package versions, tensor names, shapes, dtypes, and source config
   hash to `metadata.json`.
8. Record the exporter image digest and Git commit in `metadata.json` so every IR can be
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

This VM exposes AVX2 + AVX-VNNI but not AVX-512, so do not expect AVX-512-class INT8
throughput. INT8 weight compression is still justified here: autoregressive decode is
memory-bandwidth bound, and weight-only INT8 roughly halves weight footprint and per-token
cache transfer, which is the primary win on this profile. AVX-VNNI accelerates the INT8
dot products, giving a smaller compute gain on top. Validate empirically rather than
assuming AVX-512 numbers. Keep `DYNAMIC_QUANTIZATION_GROUP_SIZE=32` as the default and
benchmark 0 and 64 to confirm the accuracy/latency trade-off on AVX2/AVX-VNNI.

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

Stateful OpenVINO for hand-built custom graphs is less robust than for recognized LLM
architectures, so this milestone is optional and gated by an environment variable, not a
prerequisite for shipping. Pursue it only after the explicit-cache runtime is stable and
meeting latency goals, and only if the measured per-token cache-transfer and allocation
overhead justifies the added complexity. The explicit-cache runtime remains the supported
default.

## 1.7B feasibility note

The 1.7B checkpoint is a separate experiment with its own gates; passing 0.6B does not
certify it. On 8 vCPUs with a 7 GiB container it pushes both memory and latency, so:

- Latency: accept 1.5x warm-latency improvement rather than 2x.
- Memory: INT8 weight compression is mandatory (FP32 1.7B weights plus the transient
  PyTorch + OpenVINO double-hold during bring-up will not fit). Budget memory before
  enabling the backend and keep at least 20% headroom below the 7 GiB limit (target peak
  RSS under ~5.6 GiB).
- Validate cold start, warm inference, and a long utterance under the memory limit before
  declaring 1.7B shippable.

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

### Private GHCR authentication on `dockermisc1`

The GitHub Actions token that publishes the images is scoped to the workflow runner and is not
available on `dockermisc1`. Before pulling a private image, authenticate with a token that has
`read:packages`. When GitHub CLI is already authenticated on the host, use:

```bash
gh auth refresh -h github.com -s read:packages
gh auth token | docker login ghcr.io -u nmorgowicz --password-stdin
docker pull ghcr.io/nmorgowicz-org/qwen3-tts-openvino:exporter-<git-sha>
docker logout ghcr.io
```

Never print the token or place it in shell history, Compose, or repository files. For automated
deployments, use a least-privilege read-only package token with a Docker credential helper. For
a one-shot pull, a temporary Docker config that is deleted immediately after the pull avoids
leaving registry credentials on disk.

### Build, export, and deployment sequence

1. Merge a source revision after lightweight CI passes, then merge the corresponding Release
   Please pull request.
2. The Release Please tag triggers `arc-general-docker` to build and push
   `runtime-<release-commit-sha>` and `exporter-<release-commit-sha>`.
3. Authenticate `dockermisc1` to private GHCR with `read:packages`, pull both immutable tags,
   then remove temporary registry credentials.
4. Set `MODEL_SIZE` to `0.6B` or `1.7B`, with optional `HF_TOKEN_FILE`, and pre-download the
   selected checkpoint into the persistent cache.
5. Stop the existing `qwen3-tts` container to release its model memory.
6. Run `exporter-<git-sha>` with the same model selection and these mounts:
   - `/var/data/autopirate/qwen3-tts/model:/root/.cache/huggingface/hub:rw`
   - `/var/data/autopirate/qwen3-tts/openvino:/ov_output:rw`
   If the root-owned output directory does not exist, create it with `sudo install -d` and
   assign it to the deployment user before starting the exporter.
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
| `requirements-ov-export.txt` | Add the pinned NNCF export dependency (no Optimum Intel) |
| `benchmark_tts.py` | Reproducible latency, RTF, memory, and quality benchmark harness |
| `profile_tts.py` | Per-component timing and generation-step counters |
| `export_openvino.py` | Implement the documented one-shot export, validation, and compression CLI |
| `ov_export_wrappers.py` | Tensor-only prefill/decode wrappers and cache flattening |
| `test_vocoder_parity.py` | Deterministic vocoder wrapper, dynamic-shape, FP32, and INT8 parity gate |
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
5. For each model size released, the five-run warm median improves by at least the
   model-specific floor (2x for 0.6B, 1.5x for 1.7B), or the measured result is explicitly
   accepted based on quality and resource savings.
6. p95 latency, real-time factor, and peak RSS are recorded for short and paragraph prompts.
7. The container remains below its memory limit without increasing host swap pressure.
8. `/generate`, `/infer`, `/health`, MP3 output, WAV output, and serialized concurrency pass.
9. `TTS_BACKEND=pytorch` provides a tested one-setting rollback.

Gate 5 is model-size-specific: the warm median must improve by at least 2x for 0.6B and at
least 1.5x for 1.7B, or the measured result must be explicitly accepted on quality and
resource-savings grounds.

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

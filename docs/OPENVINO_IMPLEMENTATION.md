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

> **All measured benchmark data lives in [`OPENVINO_RESULTS.md`](OPENVINO_RESULTS.md).** This file
> keeps design, contracts, and plans; results blocks here are short pointers into that log.

**Milestone 4 — OpenVINO generation runtime: COMPLETE / measured (2026-06-28).** The explicit-cache
runtime accelerates both transformer cores, uses buffer-backed K/V cache, and uses the validated
FP32 OpenVINO vocoder, with backend provenance printed at install and in the report JSON. INT8 +
OV-vocoder measured **1.35x** speedup, codebook match **0.8165**, duration ratio **0.9642**; the
vocoder is neither the quality problem nor a useful CPU speed lever.
See [`OPENVINO_RESULTS.md` § Milestone 4](OPENVINO_RESULTS.md#milestone-4--generation-runtime-measured-2026-06-28).

**Milestone 6 — INT8 quality recovery: COMPLETE / CLOSED (2026-06-29).** **0.6B ships weight-only
INT8 (~1.40x); the A/B listen confirmed the artifact is acceptable.** Every quality-recovery avenue
on the pinned NNCF 3.2.0 stack was tried and rejected: data-aware INT8 calibration (API forbids it),
full W8A8 PTQ (~7 dB vs ~30 dB tensor accuracy), and whole-core precision mix (no quality gain at any
useful speed — damage is distributed across both cores). Per-layer `ignored_scope` is the only
untried lever and is not worth it for 0.6B. Next work is the **1.7B** track (quality lever) plus
memory enablers (M5/M7).
See [`OPENVINO_RESULTS.md` § Milestone 6 and the 0.6B decision summary](OPENVINO_RESULTS.md#0.6b-decision-summary-current).

**0.6B stateful-KV footprint track: IMPLEMENTED / measured (2026-06-29), pending release packaging.**
Cap-768 main plus cap-32 predictor is bit-exact against the explicit INT8 graphs and produces a
byte-identical same-seed WAV. With bf16 serving load and early release, short-request peak RSS fell
**8,623 → 6,635 MiB** and trimmed retained RSS fell **8,247 → 6,394 MiB**. Warm median regressed
3.8% (18.429 → 19.138 s), so this is a footprint feature, not a speed feature. A 177-word prompt
completed at 45.28 s audio but peaked at 7,845 MiB: use 8 GiB for long-prompt deployments; 7 GiB is
only valid for bounded short requests. See `PLAN_0.6B_STATEFUL_KV.md` and the results log.

**Milestone 1.5 — Vocoder decoder export: COMPLETE (2026-06-28)**

**Streaming-vocoder follow-up: IN PROGRESS (2026-06-29).** The existing FP32 IR is reused; no graph
export change is planned. `OpenVinoVocoderRuntime.iter_decode_chunks` now exposes the stock
300-frame/25-frame-context decode boundary, and batch decode consumes the same iterator. Model-free tests
prove exact concatenation parity. This is foundation only: the autoregressive talker still returns the
complete code sequence before vocoder decode begins. CPU-headroom measurement and a generation-loop code
producer must precede pipelining or a streaming HTTP endpoint. See `PLAN_STREAMING_VOCODER.md`.

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

**Milestone 3 — INT8 characterization: IN PROGRESS (2026-06-28)**

The first all-weight INT8 run produced useful hidden-state error measurements, but it did
not complete the M3 acceptance gate. Although the command and metadata said `INT8_ASYM`,
the exporter checked `"sym" in "int8_asym"` and therefore selected `INT8_SYM`. The original
harness also silently skipped every token-agreement check because it looked for a nonexistent
`talker.first_codebook_head`, fed
each OpenVINO decode step from the PyTorch cache instead of carrying backend-owned state,
tested only three of the predictor's 15 output heads, and timed first calls rather than a
warm benchmark. The artifact also recorded the mutable revision `main`; the cache used the
immutable model revision `5d83992436eae1d760afd27aff78a71d676296fc`.

The corrected synthetic rerun carried independent caches and projected through
`talker.codec_head` plus all 15 predictor `lm_head` entries. FP32 measured 75.8-113.0 dB
with top-1 agreement at every tested final position. The actual INT8_SYM main measured
25.3-27.3 dB and failed all four scopes; predictor INT8_SYM measured 24.3-37.4 dB and failed
three of 15 scopes. INT8 top-1 still agreed at every tested position, but each scope contains
only one synthetic final-position choice. These results are not INT8_ASYM or generation-level
evidence and do not justify accepting predictor INT8 or lowering the main threshold.

Release v0.5.4 then produced a genuine all-weight INT8_ASYM artifact with immutable
provenance. The corrected harness measured main INT8_ASYM at 24.5-28.3 dB (all four scopes
failed) and predictor INT8_ASYM at 25.5-38.1 dB (decode steps 0 and 5 failed). Top-1 agreed
at all 19 synthetic positions, while FP32 remained at 75.8-113.0 dB. All-weight INT8_ASYM
is therefore rejected by the synthetic SNR gate for both cores. The top-1 result is useful
characterization but is too small and synthetic to override those failures.

M3 cannot complete until the FP32 M4 generation adapter supplies real prompt embeddings,
3-axis mRoPE positions, and the nested code-predictor schedule. That adapter is also required
for generated-code agreement, production-sampling listening tests, warm latency, and RSS.
The next implementation target is therefore the FP32 explicit-cache M4 path; quantization
selection resumes after that path passes generation-level parity.

**Interpretation and M4 framing (do not mis-read the INT8 result):**

1. **FP32-to-M4 is a prerequisite, not a rejection of INT8.** The only INT8 verdict we
   have is a *synthetic hidden-state* SNR gate. The harness that can actually judge INT8
   quality — bounded generated-code agreement plus production-sampling listening tests —
   does not exist until the M4 generation runtime exists. We are building M4 in FP32 first
   *because that is the thing that unlocks an honest INT8 evaluation*, not because FP32 won
   an argument. The reproducible v0.5.4 INT8_ASYM artifact is retained for exactly that
   re-evaluation.
2. **Synthetic hidden-state SNR is a debug signal, not a quality verdict.** Top-1 token
   agreement held at every tested INT8 position; we have no listening or generated-code
   evidence that INT8 is audibly worse. "INT8 fails a synthetic diagnostic" is the accurate
   statement; "INT8 quality is bad" overstates what we measured. (The vocoder milestone
   already showed a chosen gate can be the wrong gate — see Milestone 1.5 max_abs vs SNR.)
3. **FP32 is itself unproven against the 2x latency gate (Gate 5).** Vocoder FP32 IR bought
   only 1.27x on a 29% slice (~1.07x end-to-end). The transformer cores are ~66% of wall
   time and have *no measured FP32 speedup yet*; FP32-vs-eager on this AVX2/no-AVX-512 CPU
   is often only ~1.2-1.5x. Per the INT8 microarchitecture note, autoregressive decode is
   memory-bandwidth bound and weight-only INT8 is the lever most likely to reach 2x. M4 must
   therefore **measure warm FP32 transformer latency as an early, explicit Gate-5 check** —
   if FP32 lands well under 2x, INT8 is load-bearing, not optional polish. Treat FP32 M4 as
   the evaluation platform, not the presumed shipping config.
4. **1.7B structurally forces INT8; keep the path warm.** FP32 1.7B weights plus the
   transient PyTorch+OpenVINO double-hold do not fit the 7 GiB container (see "1.7B
   feasibility note"), so 1.7B cannot follow a "0.6B-at-FP32" path. Larger models are also
   generally *more* robust to weight-only INT8, not less, so 1.7B is plausibly a better INT8
   candidate than 0.6B. Do not let an FP32-is-fine conclusion on 0.6B quietly retire the
   INT8 work that 1.7B requires.

Not yet implemented: the OpenVINO generation runtime (`ov_talker_runtime.py`), generation-
level FP32/INT8 validation, or the `TTS_BACKEND=openvino` worker path with `/health` metadata.

## Validated Deployment Snapshot

Validated on `dockermisc1` on 2026-06-28 (M3 characterization current):

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
- OV IR artifacts:
  `/var/data/autopirate/qwen3-tts/openvino/qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1/`
  (main and predictor cores, FP32 plus rejected all-weight INT8_ASYM). Vocoder IR:
  `qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1_vocoder/` (M1.5 validated).
- Exporter image: `ghcr.io/nmorgowicz-org/qwen3-tts-openvino:exporter-v0.5.4` at
  `sha256:cc6492e5c92aed16380da8f378fd4f6a6195efb528825f08f1a545500874b6ba`.

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
Provenance is **best-effort and never blocks a run**: `source_commit` is taken from
`SOURCE_COMMIT` if set, otherwise auto-detected from the source tree's Git HEAD (falling back
to `"unknown"`), and `exporter_image_digest` is taken from `EXPORTER_IMAGE_DIGEST` if set,
otherwise `"unknown"`. Set those env vars to pin exact provenance for published artifacts;
leave them unset for easy local/ad-hoc exports. Likewise the recorded `model_revision` prefers
the immutable Hugging Face commit but falls back to the requested revision or `"main"` rather
than failing. The worker only enforces a revision match when `MODEL_REVISION` is explicitly
pinned. The command reuses the standard Hugging Face cache and writes only to `--output-dir`.

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

> **Measured data moved to [`OPENVINO_RESULTS.md` § Milestone 0](OPENVINO_RESULTS.md#milestone-0--baseline-profile-fp32-pytorch-no-openvino).**
> Headline: end-to-end RTF 6.55; predictor 45.6% / tokenizer-decode 29.1% / main 20.8% / glue 4.5%;
> predictor is ~69% of the transformer loop; peak RSS 6.4 GiB at FP32 baseline (<20% headroom under
> the 7 GiB limit). A two-core-only backend caps speedup ~3.4x because the ~29% tokenizer decode is
> untouched.

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

NNCF mode behavior (validated 2026-06-28 on dockermisc1):

- INT8 modes (INT8_ASYM, INT8_SYM):
  - All weights, per-channel, no tuning knobs.
  - Reject non-default group_size and ratio overrides.
  - Use: `nncf.compress_weights(ov_model, mode=INT8_ASYM)`.
- INT4 modes:
  - Accept `group_size` and `ratio`; `ratio` selects the fraction of layers assigned the
    primary INT4 precision and the remainder use NNCF's backup precision (INT8 by default).
  - This is not an INT8/FP32 mixed mode.
- NNCF 3.2.0 has no `CompressWeightsMode.MIX_8`. Selective INT8/FP32 requires a single
  INT8 compression pass with an explicit `IgnoredScope` for layers retained in FP32.

Do not assume INT8 modes support group_size/ratio; this constraint caused a failed
export attempt on dockermisc1 (see #29).

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

Exploratory M3 results (0.6B, actual INT8_SYM despite INT8_ASYM metadata, all weights,
per-channel):

- FP32: all scopes pass (72-91 dB SNR), same as M2.
- Original INT8_SYM harness (main): 26-29 dB SNR; all four scopes failed.
- Original INT8_SYM harness (predictor): 31-37 dB in the four tested scopes.
- These are hidden-state SNR measurements from the superseded synthetic harness. They are
  insufficient to accept or reject a runtime configuration.

The run used exporter-v0.5.2 on dockermisc1. Source commit:
`4fe690b0ff4dd2f74cbe47a2cfb7c942bc18ccb6`; exporter digest:
`sha256:0808f1f70777f160f8bca4b29486c0b94a6728c372715eef96e39a945e2c817d`; actual model
revision: `5d83992436eae1d760afd27aff78a71d676296fc`; IR metadata SHA-256:
`a52d681e3b9f8f386c4ba85f181e1e240f853d34eddb53604ee0525ec7a858ae`.

Superseded INT8_SYM parity summary (0.6B transformer cores, all weights, per-channel):

- main/prefill: 27.3 dB → fails 30 dB gate
- main/decode step0-2: 26.2-28.7 dB → fails
- predictor/prefill: 30.6 dB → passes
- predictor/decode step0-2: 33.1-36.7 dB → passes

FP32 IR remains excellent (71-91 dB) and identical to M2.

Corrected synthetic rerun (`transformer_parity_corrected_int8_sym.json`):

- FP32: 75.8-113.0 dB; top-1 agreed in all 19 tested scopes.
- INT8_SYM main: 25.3-27.3 dB; all four scopes failed; top-1 agreed in all four.
- INT8_SYM predictor: 24.3-37.4 dB; decode steps 1, 5, and 9 failed; top-1 agreed in all 15.
- The corrected result strengthens the rejection of this artifact but remains synthetic
  characterization, not generation acceptance.

Authoritative INT8_ASYM characterization (release v0.5.4):

- Source commit: `00ce55c1d0e44fb7ecc367436b2b4f4de2843d26`.
- Exporter: `ghcr.io/nmorgowicz-org/qwen3-tts-openvino:exporter-v0.5.4` at
  `sha256:cc6492e5c92aed16380da8f378fd4f6a6195efb528825f08f1a545500874b6ba`.
- Model revision: `5d83992436eae1d760afd27aff78a71d676296fc`.
- Artifact directory: `qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1/`.
- IR metadata SHA-256: `abec65a5d2f2dcf07382d707513cb2a9f5c2a4c5872728069b169d9601e3da7f`.
- Parity report SHA-256: `3cfb89c5eb6f95f7e40348c30c6a849865d1ca5eec6f91bb373e3d771c8da09e`.
- NNCF reported INT8_ASYM per-channel compression on 100% of main (196/196) and predictor
  (35/35) weight layers. Each compressed graph is approximately half its FP32 size.
- FP32: 75.8-113.0 dB; top-1 agreed in all 19 synthetic scopes.
- INT8_ASYM main: 24.5-28.3 dB; all four scopes failed; top-1 agreed in all four.
- INT8_ASYM predictor: 25.5-38.1 dB; decode steps 0 and 5 failed; top-1 agreed in all 15.
- Result: reject all-weight INT8_ASYM for both cores pending generation-path evidence. Do
  not spend time on selective scopes until the FP32 M4 adapter provides representative inputs
  and a measured need for additional memory or latency reduction.

Unsupported MIX8 attempt (2026-06-28) found:

- NNCF 3.2.0 has no CompressWeightsMode.MIX_8.
- The unsupported `--int8-mode mix8` exporter path has been removed.
- Available modes: INT8_ASYM, INT8_SYM, INT4_ASYM, INT4_SYM, FP8_E4M3, FP4,
  ADAPTIVE_CODEBOOK, MXFP4, MXFP8_E4M3, CB4, CODEBOOK, NF4, NVFP4.

Do not call `compress_weights` repeatedly per layer. For selective INT8/FP32, identify
sensitive MatMuls through generation-path ablation and pass their names or patterns in one
`nncf.IgnoredScope` to `compress_weights(..., mode=INT8_ASYM)`. Preserve the resulting scope
list and NNCF configuration in metadata.

Current position:
- FP32 transformer cores: synthetic core parity passes and is ready for an M4 FP32 adapter.
- All-weight INT8_SYM and INT8_ASYM: rejected by the corrected synthetic SNR gate for both
  cores. Neither is a runtime candidate without new generation-path evidence.
- The v0.5.4 INT8_ASYM artifact is reproducible and may be reused for later generation-level
  comparison; the older mutable-revision INT8_SYM artifact is characterization-only.

Next steps (M3 continued):

1. Implement the M4 adapter with FP32 main and predictor IR first. Trace real embeddings,
   attention masks, position IDs, cache positions, and all 15 predictor steps.
2. Establish bounded generated-code agreement and production-sampling A/B output with FP32.
3. Benchmark warm FP32/FP32, FP32-main/INT8-predictor, and INT8/INT8 configurations with the
   same prompts and runtime settings. Record median, p95, RTF, peak RSS, swap delta, and
   per-core timings.
4. Accept the simplest configuration that passes code, listening, and performance gates.
   Attempt selective main INT8 with `IgnoredScope` only if measured performance or memory
   shows that it is necessary.

Do not lower the 30 dB diagnostic threshold to make an existing run pass. Hidden-state SNR
is a debugging signal, not a substitute for generated-code agreement and listening quality.

## Milestone 4: OpenVINO Generation Runtime

Create `ov_talker_runtime.py` that honors the exact nested generation schedule expected by
`talker.generate(...)`. The implementation realizes this by swapping the two inner core
forwards rather than reimplementing the schedule (see "Chosen implementation" below); the
contract the cores must satisfy is unchanged and is described here.

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

### Chosen implementation: replace the two inner core forwards (not the schedule)

Rather than reimplement the nested generation schedule, M4 swaps only the two transformer
*inner* `forward` methods for OpenVINO-backed equivalents and leaves every other line of the
stock generation path in PyTorch. This is the lowest-risk way to satisfy "do not replace
`wrapped.model.talker`" and is correct-by-construction for generation-level parity, because
sampling, EOS, mRoPE position math, `generation_steps`, `small_to_mtp_projection`, the codec
and predictor output heads, and the `(outputs.hidden_states, codec_ids)` result packing all
remain the original PyTorch code. Verified against `qwen-tts==0.1.1` source:

- Patch `talker.model.forward` and `talker.code_predictor.model.forward` (the *inner*
  `Qwen3TTSTalkerModel` / `Qwen3TTSTalkerCodePredictorModel`, which is exactly what the
  export wrappers wrapped). The surrounding `…ForConditionalGeneration.forward` glue is
  untouched.
- The inner forwards receive flat tensors at this seam: 2-D `attention_mask`, `cache_position`,
  `inputs_embeds` already projected for the predictor, and (predictor only) `generation_steps`
  — the same tensors the IR was traced from. The inner predictor core ignores
  `generation_steps`; only the head/embedding selection in the FCG glue uses it.
- `position_ids` arrives 3-axis `[3, batch, seq]` for the main core (the FCG expands mRoPE
  before the inner call). In the TTS audio path all three axes are identical (both the
  prefill `get_rope_index` and the decode `arange+rope_deltas` branch use `expand(3, …)`), so
  the adapter feeds axis 0 to the 2-D-position IR. Assert equality of the three axes on the
  first call to catch any contract drift.
- Each patched forward picks prefill vs decode by incoming cache length, runs the persistent
  InferRequest, and returns `BaseModelOutputWithPast(last_hidden_state=H, hidden_states=(H,),
  past_key_values=<DynamicCache from present K/V>)`. The outer extractor reads `hid[0][-1]`
  (final hidden) and `hid[-1]` (codec_ids from the glue), so the length-1 `hidden_states`
  tuple is sufficient and the intermediate per-layer states (unused) are not reproduced.

This design is pinned to the `qwen-tts==0.1.1` generation contract; `app_worker` already fails
startup on a package/revision mismatch.

### Early Gate-5 check: measure warm FP32 transformer latency first

Before any INT8 re-evaluation, M4 must record warm FP32 transformer latency and end-to-end
RTF (see "Interpretation and M4 framing"). FP32 IR has unproven speedup on the cores; if it
lands well under the 2x goal, INT8 becomes load-bearing and the retained INT8_ASYM artifact is
re-evaluated through this same generation-level harness. `test_ov_generation.py` produces both
the bounded generated-code agreement (greedy) and the warm sampling latency/RTF/peak-RSS rows.

### M4 measured results: COMPLETE (2026-06-28, dockermisc1, 0.6B Base, 6 threads)

> **Full measured runs moved to [`OPENVINO_RESULTS.md` § Milestone 4](OPENVINO_RESULTS.md#milestone-4--generation-runtime-measured-2026-06-28).**

Bottom line from the M4 runs (first run, FP32/INT8 re-validations, the vocoder-wiring correction,
and the OV-vocoder-genuinely-active run):

- **INT8 is the load-bearing precision: ~1.40x speedup, ~9.6 GiB peak RSS, codebook match 0.8165.**
  FP32 OV is numerically perfect (match 0.9405) but gives **no speedup (0.97x)**.
- Neither precision meets the 2x Gate 5 by swapping two cores alone — the ceiling is structural
  (sequential predictor + ~29% FP32 tokenizer decode that OV does not accelerate), not quantization.
- The OV vocoder is **quality- and speed-neutral** on this CPU; it is not the lever to 2x.
- Greedy frame-160 divergence and negative waveform SNR are INT8-specific diagnostics, **not** ship
  gates; codebook match + duration/energy + listening are the real gates. The 15 dB waveform-SNR
  acceptance threshold is unrealistic for same-seed INT8 sampling and systematically fails.
- PR #44 wired the vocoder IR, added persistent K/V buffers (`OPENVINO_BUFFER_KV`), and added the
  `sampled-quality` / `logits-parity` / `all` harness modes + frame-160 diagnostic.

## Milestone 5: Stateful KV Cache

The main-core spike now uses one static-capacity stateful OpenVINO model whose used length stays
dynamic. OpenVINO `MakeStateful` does not support dynamic state shapes, so the graph stores a fixed
capacity and slices/updates it with `cache_position`. The same graph accepts multi-token prefill and
one-token decode; separate compiled prefill and decode models cannot share internal state. Predictor
statefulness remains a conditional follow-up after startup-overlap reduction.

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

## Milestone 6: INT8 quality recovery

**Problem.** The M4 runtime uses weight-only `INT8_ASYM` transformer bodies. The FP32 PyTorch glue
still owns embeddings and all codebook output heads, and the FP32 OpenVINO vocoder is faithful, so
the remaining sampled-code divergence originates inside the quantized transformer matmuls. The
baseline to beat is speedup **1.35x**, mean codebook match **0.8165**, duration ratio **0.9642**,
logits first mismatch frame **0**, and greedy first divergence **160**. A listener reported a slight
mid-utterance pause; listening remains required before attributing that artifact to a specific token.

### Investigation results — moved

> **All M6 measured data moved to [`OPENVINO_RESULTS.md` § Milestone 6](OPENVINO_RESULTS.md#milestone-6--int8-quality-recovery-investigation-2026-06-2829)** (calibration capture + SHAs, the
> unsupported-calibration rejection, the W8A8 PTQ accuracy rejection, and the whole-core precision-mix
> table), plus the **A/B listening verdict** and the **0.6B decision summary** at the top of that file.

**Outcome: 0.6B ships weight-only INT8 (~1.40x); M6 quality-recovery is CLOSED.** Every avenue on
the pinned NNCF 3.2.0 stack was tried and rejected — data-aware INT8 calibration (API forbids it),
full W8A8 PTQ (~7 dB vs ~30 dB tensor accuracy), and whole-core precision mix (no quality gain at any
useful speed; damage is distributed across both cores). The A/B listen confirmed the INT8 artifact is
acceptable. Per-layer `ignored_scope` (below) is the only untried lever and is **not worth it for
0.6B** given the distributed damage.

### Optional further experiment: per-layer selective weight-only INT8

`nncf.compress_weights(INT8_ASYM, ignored_scope=...)` is supported and keeps selected operations in
FP32. Lower-probability after the per-core result above, but if pursued, find the smallest protected
transformer-layer set that removes the audible artifact while retaining useful speed and memory:

1. Add an exporter option that accepts explicit ignored-scope patterns and records the normalized
   patterns in metadata. Apply the same scope to a core's prefill and decode graphs. Fail closed if a
   pattern matches no compressible operation; never silently emit an all-INT8 artifact.
2. Characterize sensitivity with coarse, reproducible groups rather than guessing: main layers
   `0–6`, `7–13`, `14–20`, `21–27`; predictor layers individually (`0–4`) because it is small and
   performs 15 sequential steps per frame. Compare each candidate against FP32 and all-weight INT8
   on bounded logits/code agreement first. Do not run sampled audio for every losing candidate.
3. Promote only candidates that move the first divergence later and improve hidden/logit error.
   Run the full sampled harness and A/B listening on the best candidates; record codebook match,
   duration ratio, pause/repetition/truncation observations, warm median/p95, RTF, peak RSS, and
   per-core timings. Do not lower quality gates merely to retain INT8.
4. Lock the selected precision map before Milestone 5 stateful-cache conversion. M5 remains an
   independent structural optimization and must preserve the selected model's code sequence.

Do not retry `compress_weights` INT8 calibration or escalate to full W8A8 with this pinned stack.
INT4 data-aware modes are API-compatible but are not the next step: they introduce larger weight
error when the current problem is already INT8 quality, so they require separate evidence before use.

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

## Milestone 7: Memory Reduction

The first working backend may temporarily hold both PyTorch transformer weights and OpenVINO
weights. Do not lower the Compose memory limit in that state.

**Implemented (2026-06-29): `OPENVINO_RELEASE_TORCH=1`.** After `OVTalkerRuntime.install()` compiles
the OpenVINO cores and swaps both inner-core forwards, `_release_torch_core_weights()` frees the
PyTorch weights of each core's `.layers` (the decoder blocks) — which the OV graphs fully replace and
which hold ~all of the parameters. The inner `embed_tokens` and `norm` are deliberately **kept**: the
outer generation glue calls `talker.get_text_embeddings()` (== `talker.model.embed_tokens`) to build
the `inputs_embeds` it feeds to OV, so freeing the embedding table breaks generation (`'weight' must
be 2-D`). Implementation: replace each block param/buffer tensor with empty storage, `gc.collect()`,
then `malloc_trim(0)` (glibc) to return arena pages to the OS. **One-way:** the eager PyTorch core
forward cannot run afterward, so `uninstall()` deliberately leaves the OpenVINO forwards in place
rather than restoring empty tensors. The codec/text embeddings, output heads, prompt logic, and speech
tokenizer are untouched and keep working.

**Why this is the lever for 1.7B:** the serving runtime (`app_worker.py`) is OV-only and never invokes
the PyTorch core forward, so releasing those weights is pure win there. Set `OPENVINO_RELEASE_TORCH=1`
in the 1.7B serving environment.

**Validation.** The parity harness and the default `dump_audio.py` both run the PyTorch core (for the
reference), so they cannot measure the released footprint. Use `dump_audio.py --ov-only` (with
`OPENVINO_RELEASE_TORCH=1`): it skips the PyTorch reference, generates on OV only, and prints peak RSS —
the serving-representative number. Acceptance: 1.7B peak RSS under ~5.6 GiB (≥20% headroom below the
7 GiB limit), validated across cold start, warm inference, and a long utterance.

If allocator retention stays high despite `malloc_trim`, the next step is a thin loader that loads only
the PyTorch tensors still used at inference rather than loading the full model and freeing it.

Reduce `mem_limit` only after measuring cold start, warm inference, a long utterance, and
failure behavior under the proposed limit. Maintain at least 20% headroom above observed
peak RSS.

### M7 measured on 1.7B — release works for idle, not for serving (2026-06-29)

First 1.7B characterization (full numbers in `OPENVINO_RESULTS.md` → "1.7B track"). The release
freed ~5.54 GiB and **cold idle dropped to 5.47 GiB** — M7 does its job. But the measurement
**falsified the original M7 plan as a sufficient condition for 1.7B at 7 GiB**:

- **Per-request peak ≈ 12.8 GiB**, and it is **~independent of utterance length** (12.84 GiB @ 5.68 s
  vs 12.76 GiB @ 7.36 s). The peak is fixed generation-time overhead (OV working buffers + a large
  one-shot allocation, most likely the single-shot vocoder decode), not KV growth.
- **Generation memory is not reclaimed**: after `gc` + `malloc_trim`, RSS stays at ~12.4 GiB, not the
  5.47 GiB cold idle. A worker balloons on its first request and holds it.

So the binding constraint moved from *idle weights* (solved) to *generation-time allocation*
(unsolved). Weight-release alone cannot fit 1.7B in 7 GiB. The thin loader would only cut the 8.5 GiB
*load* transient, not the 12.8 GiB *generation* peak — so it is **deprioritized** until the generation
peak is reduced (see M9). The honest near-term target for 1.7B serving on this box is **~13 GiB per
request**; whether that is acceptable (co-located with `litellm*`/`headroom-proxy` on a 15 GiB box) is
a product decision that the speed and quality A/B should inform first.

## Milestone 1.7B-A: Speed + quality A/B (the go/no-go gate)

**Status — gate PASSED (2026-06-29).** Speed measured (`bench_speed.py`, one backend per process to
dodge the 1.7B both-models OOM): PyTorch 1.7B 25.05 s median → **OV INT8 1.27×, OV INT4 1.35×** (RTF
7.70 / 7.05). Same CPU ceiling as 0.6B-INT8 (~1.40×), neither hits 2×. Decisive cross-model read:
**1.7B-INT4 at 18.6 s median ≈ 0.6B-INT8 (~17.4 s) in absolute latency** but audibly better
(0.6B-INT8 comma artifact; 1.7B-INT4 "100% good"). → **1.7B-INT4 is the recommended quality upgrade;
the only open blocker is the generation-peak memory (M9), not speed or quality.** Full table in
`OPENVINO_RESULTS.md` → "1.7B speed". The four-clip quality quadrant below is superseded by the direct
listens already done (0.6B-INT8, 1.7B-INT8, 1.7B-INT4); only the 0.6B-FP32 control remains optional.

Original gate definition (for reference):
We exported 1.7B straight to INT8 and went to memory, skipping the 1.7B equivalents of the M2 parity
and M4 latency gates. Required runs (existing IR, no new code):

1. **Latency + parity** — `test_ov_generation.py --mode all` (PyTorch 1.7B vs OV-INT8 1.7B), `--memory
   13g`. Produces end-to-end speedup, RTF, and codebook match. We currently have **zero** 1.7B speed
   data. Expect <1x relative to 0.6B in absolute latency; the question is the OV-vs-PyTorch ratio and
   whether 1.7B is usable at all on this CPU.
2. **Quality quadrant A/B** — same text + seed, four clips for listening:
   `0.6B-INT8` (shipping), `1.7B-INT8`, `1.7B-PyTorch` (ceiling), and `0.6B-FP32` (no-quant control).
   **The deciding question is not "is 1.7B-INT8 clean" but "is 1.7B-INT8 audibly better than
   0.6B-INT8."** Include `0.6B-FP32` because if the only 0.6B complaint is the INT8 comma-pause, plain
   0.6B-FP32 may be a better quality/speed trade than fighting 1.7B memory.

If 1.7B-INT8 does not clearly beat 0.6B, **stop the 1.7B track here** and do not build M8/M9.

## Milestone 8: INT4 weights for 1.7B (quality-headroom quantization)

**Status — exported + validated (2026-06-29).** `INT4_ASYM` g32, layers only, dir `…_int4g32`.
Listened: "slight comma pause but 100% good" — same mild artifact as 0.6B-INT8, acceptable. Memory:
retained idle 12.43 → **10.43 GiB** (−2.0), but per-request peak only 12.84 → **12.06 GiB** (−0.78),
confirming the peak is generation-bound (→ M9), not weight-bound. **INT4 is the preferred 1.7B
precision.** Numbers in `OPENVINO_RESULTS.md` → "1.7B INT4 weights". Still to do: speed/RTF vs INT8
(M1.7B-A), and the direct 1.7B-INT4 vs 0.6B-INT8 quality A/B.

Hypothesis (confirmed): 1.7B has enough quality headroom to absorb INT4 weight damage that 0.6B could not, while
INT4 ~halves OV graph memory and speeds up memory-bound CPU matmuls. **1.7B-INT4 may beat 0.6B-INT8 on
quality while being smaller/faster** — an untested quadrant and the most promising new lever.

- Scope INT4 to the transformer **layers** only (per the M7 finding that layers hold ~all the weight);
  keep embeddings/heads/vocoder at their current precision.
- Use NNCF `INT4_ASYM` with `group_size` (start 32, ratio 1.0); `INT4` is the one mode pinned NNCF
  3.2.0 lets us tune (data-aware options remain rejected — see M6).
- **Exporter code gap to fix first:** `export_openvino.py` writes every compressed graph as
  `{name}_int8.xml` and the versioned dir name encodes neither compression mode nor precision, so an
  INT4 export collides with the existing INT8 IR dir ("refusing to overwrite") and would mislabel
  files. Add a precision tag to the output dir name (e.g. `…_int4`) and/or the graph filenames before
  running INT4.
- Gate: characterize like M3/M6 (codebook match, duration ratio, listening A/B vs 0.6B-INT8 and
  1.7B-INT8) plus the M7 memory checkpoints.

## Milestone 9: Generation-peak memory reduction (the real 1.7B wall)

**Status — CLOSED and SHIPPED in v0.11.0 (2026-06-29).** Full memory arc complete: lifetime peak
**11,593 → 7,715 MiB**, trimmed idle **8,884 → 7,485 MiB**, and the dangerous boot spike (real OOM
risk) is eliminated. The peak is now a stable ~7.7 GiB. The 1.7B-INT4 stateful + bf16 serving config
ships at **`TTS_MEMORY_LIMIT=8G`** (the ~7.5 GiB floor — INT4 weights + bf16 glue + OV runtime —
does not fit the 7G default; 0.6B-INT8 still fits 7G). See `OPENVINO_RESULTS.md` for the measured
timeline and provenance.

The path that got there, highest-leverage first (all done):

1. **Profile attribution — complete.** `dump_audio.py --rss-profile` labels main/predictor
   prefill+decode, vocoder, and glue separately. Per-core 1.7B-INT4 attributed ~92% of sampled growth
   to main prefill (2,262 MiB) + main decode (1,866 MiB); vocoder only 6 MiB. **Vocoder lever closed
   for the right reason.**
2. **Static-capacity stateful main — done.** Bit-exact explicit-vs-stateful parity; moves K/V inside
   the compiled graph (60 in/57 out → 4 in/1 out + 56 states). Cut generation sampled peak ~2 GiB.
3. **Early PyTorch weight release — done.** `OPENVINO_RELEASE_TORCH=1` frees each core's `.layers`
   before compile (lifetime 12.1 → 11.3 GiB). This run FALSIFIED "lifetime peak = startup overlap":
   exact `ru_maxrss` attribution showed the peak was already **11,593 MiB right after
   `from_pretrained`**, before OV install — the fp32 checkpoint-load transient, not startup overlap.
4. **bf16 serving load — done and adopted (the big lever).** Checkpoint is BF16; `OPENVINO_TORCH_DTYPE=bfloat16`
   (serving only; exporter stays fp32 for convert parity) skips the fp32 upcast that caused the spike.
   **Lifetime peak 11,593 → 8,326 MiB.** Two OV dtype seams fixed (`_to_numpy` bf16→fp32; forwards cast
   hidden back to model dtype), both no-ops under fp32. Listening A/B: quality-equivalent (user).
5. **Capacity 768 — done and shipped as default.** Rebuilt the main at `--max-seq 768`. **Lifetime
   8,326 → 7,715; idle 8,093 → 7,485; main_prefill +1915 → +1529.** Capacity scales the prefill buffer,
   but the floor is ~7.5 GiB and does not move with capacity.
6. **Stateful predictor — done.** Same static-capacity rewrite, small predictor capacity (~60 MiB
   savings). Opt-in via `OPENVINO_PREDICTOR_STATEFUL_MODEL`.
7. **Silence trim — done.** `app_worker._trim_silence` strips the pre-existing ~1 s leading/trailing
   silence (`SILENCE_TRIM*`, on by default); confirmed present in both fp32 and bf16, not a bf16 effect.

All M9 gates passed (parity, capacity, warm latency, listening, concurrency, rollback). No open M9 work.

### M5/M9.3 design — static-capacity stateful OV KV cache (main spike implemented)

Goal: stop materializing K/V as graph I/O and as torch tensors. Today, even buffer-backed mode
(`ov_talker_runtime._OVCore._run_buffered`) pays, **per layer per step**: feed prior-K/V slices as IR
inputs, `np.copyto` each present-K/V IR output into a persistent numpy buffer, then `torch.from_numpy`
those buffers to rebuild a `DynamicCache` for the outer glue. For 1.7B that's 28 layers × 2 tensors ×
(copy-in + copy-out) on every one of the ~15 predictor steps per frame. Stateful cache moves K/V
*inside* the compiled model as `ReadValue`/`Assign` state variables, so the runtime feeds only the base
inputs and reads only the hidden state.

**Graph rewrite (`ov_stateful_cache.py` + `scripts/transform_stateful_ir.py`):**
- The two cores currently export as a **prefill + decode pair** with explicit `*past_kv` inputs and
  `*present_kv` outputs (`CoreCacheWrapper.forward` → `(last_hidden_state, *_flatten_present(...))`).
  The decode graph already has dynamic `seq` and prior-cache axes and works for prefill with zero-length
  prior inputs, so it is the one-graph source.
- OpenVINO `MakeStateful` rejects dynamic state shapes. Use a static capacity per K/V variable,
  dynamically slice `[0:cache_position[0]]` for the core input, gather the new positions from the
  present-cache result, and `ScatterUpdate` those positions before `Assign`.
- Pair parameters/results positionally under the validated contract: base inputs then k0/v0..., hidden
  result then present-k0/v0.... The spike transforms main INT4 from 60 inputs/57 outputs to 4/1 with
  56 states. Publish production artifacts under a `…_stateful` directory with capacity in metadata.

**Runtime side (`ov_talker_runtime.py`):**
- One compiled model + one `infer_request` per core (drop the prefill/decode pair and the
  `_kv_buf`/`_ensure_buffers` machinery).
- On prefill (`prior == 0`) call `infer_request.reset_state()`; each step feed only
  `[inputs_embeds, attention_mask, position_ids, cache_position, (generation_steps)]` and read output 0
  (hidden). No K/V in/out.
- The outer glue still expects `BaseModelOutputWithPast.past_key_values` and reads
  `.get_seq_length()` for mask/position bookkeeping but **never reads K/V tensors** (those now live in
  OV state). Return a **length-only cache shim** (tracks `prior += seq`, exposes `get_seq_length()` /
  `get_mask_sizes()`), so no torch K/V is ever allocated — this is where the generation-memory and
  per-frame-copy wins come from.

**Validation & risks:**
- Re-run the **M2 FP32 parity gate** on both stateful cores (SNR ≥ 60 dB) before trusting it — this is
  the parity-critical change; do not skip.
- Re-run M4 latency + M7 memory: expect lower per-frame overhead and lower generation memory.
- Mask seam: keep `CoreCacheWrapper._build_causal_mask` building the 4D additive mask from the
  runtime-supplied `attention_mask` of length `prior+seq` (prior tracked by the runtime), preserving
  the transformers-4.57.3 static-`kv_length` workaround under the single dynamic graph.
- State dims are static `[1, kv_heads, max_seq, head_dim]`; used length remains dynamic. Reject a request
  before inference when `prior + seq > max_seq`. Validate production capacity with the longest supported
  reference prompt plus paragraph generation; 2048 is only the current spike capacity.
- Keep the explicit-IR path behind a flag for one release so stateful can be A/B'd against it.

**M9 final result (measured 2026-06-29, shipped v0.11.0):** the binding peak was the fp32
checkpoint-load transient, not startup overlap. Loading the native-bf16 checkpoint
(`OPENVINO_TORCH_DTYPE=bfloat16`) plus a capacity-768 stateful main cut lifetime peak **11,593 →
7,715 MiB** and trimmed idle to **7,485 MiB**. Early release (12.1 → 11.3 GiB) and the stateful
predictor (~60 MiB) are kept but are minor next to bf16. Shipped at `TTS_MEMORY_LIMIT=8G` for 1.7B.

**M9 gates status (measured 2026-06-29 on dockermisc1):**
- Long-prompt capacity (200+ words, capacities 2048/1024/768): passed; 768 recommended as default.
- Capacity tuning: 768 vs 2048 reduces generation/retained RSS by 500-1500 MiB for long prompts; no audible difference.
- Warm latency (greedy, 3 s audio, 5 runs): stable; RTF 7.4-7.9, no warm-up artifacts.
- Serialized concurrency: no races; single worker remains correct.
- Listening check (stateful INT4 vs explicit INT4): passed; no audible difference.
- Stateful predictor: implemented and validated; small RSS savings (~60 MiB), no artifacts.
- PyTorch rollback: TTS_BACKEND=pytorch works; no regressions.
- FP32-vs-PyTorch M2 parity on stateful main: passed on 0.6B (SNR 77-86 dB) and 1.7B (SNR 71-80 dB).

### 0.6B stateful profile (implemented and measured)

The same static-capacity design is now validated for the shipping 0.6B INT8 model:

- Main: capacity 768, 28 layers, 4 base inputs, 56 internal K/V states.
- Predictor: capacity 32, 5 layers, 5 base inputs, 10 internal K/V states. Capacity 32 covers its
  2-token prefill plus 14 decode calls with margin; state resets once per audio frame.
- `scripts/transform_stateful_ir.py` infers layer count, base-input count, and the named
  `cache_position` input when flags are omitted. `--report-json` records source/output hashes,
  resolved layout, OpenVINO version, compile result, state count, and state shapes.
- `_OVStatefulCore` validates whether a compiled graph has four main inputs or five predictor inputs.
  When nested generation omits optional predictor `generation_steps`, it supplies the same int64 zero
  used by the explicit runtime. Do not remove the fifth predictor input or bake a nonzero value.
- `test_stateful_main_parity.py --core main|predictor` gates both cores. Despite the historical
  filename, it is now the shared stateful-core parity harness.
- Health provenance reports both stateful-core flags and their compiled capacities.

Acceptance results: INT8 explicit-vs-stateful is bit-exact for both cores; FP32-vs-PyTorch SNR is
77.56–86.47 dB main and 87.55–130.65 dB predictor; same-seed rendered WAV is byte-identical. Short
peak/retained RSS is 6,635/6,394 MiB. The 45.28-second capacity run peaks at 7,845 MiB, so the
repository must not lower the general long-prompt limit to 7 GiB. Explicit cache remains available
by leaving both stateful model environment variables unset; full rollback remains a fresh process
with `TTS_BACKEND=pytorch`.

## Streaming vocoder delivery (in progress)

This track is a latency/UX feature, not a memory optimization. The vocoder already processes bounded
300-frame chunks with 25 frames of left context and contributed only ~6–12 MiB to the M9 sampled peak.
No new IR is required.

### Generation seam and invariants

The correct producer seam is the return value of
`Qwen3TTSTalkerForConditionalGeneration.forward`, not its inner transformer model. During prefill,
the outer result carries `hidden_states=(transformer_hidden_states, None)`. Each autoregressive call
then carries `hidden_states=(transformer_hidden_states, codec_ids)`, where `codec_ids` is the completed
16-codebook frame. `StreamingVocoderSession` observes that return value while preserving the original
forward signature so Transformers 4.57.3 model-kwarg validation remains unchanged.

The session must preserve all of these rules:

- Ignore the prefill `codec_ids=None` result and skip a generated frame whose first codebook is EOS.
- Support batch size 1 only until a separately tested multiplexed stream contract exists.
- Include voice-clone reference codes before generated codes. Stock `generate_voice_clone` decodes the
  combined prefix, then removes the reference samples. Omitting reference codes changes the vocoder
  context and cannot pass waveform parity.
- Decode only when total reference + generated frames cross `300, 600, ...`, then once for the final
  partial prefix. Never decode every frame after 300.
- Route every prefix through `OpenVinoVocoderRuntime.iter_decode_chunks`; it owns the accepted
  300-frame/25-left-context crop math.
- Emit only samples after the reference prefix and after the previously emitted prefix. Require exactly
  `frames * 1920` samples from each complete prefix; fail closed on shape mismatch.
- Restore both the talker forward and any temporary speech-tokenizer decode hook in `finally` paths.
- Do not emit a final partial chunk after generation raises. Any already-emitted bytes are governed by
  the streaming transport's truncation contract.

The transport path reuses the session's final full-prefix waveform when upstream
`generate_voice_clone` reaches `speech_tokenizer.decode`. This avoids a duplicate terminal vocoder pass
while preserving the upstream return/cut structure. The parity-only diagnostic may leave the stock
decode active to compare streamed concatenation and batch output from the same generated codes.

### HTTP contract

Existing `/generate` and `/infer` remain atomic WAV/MP3 endpoints. Streaming is opt-in:

- Worker: `POST /infer_stream`.
- Public proxy: `POST /generate/stream`.
- Request JSON: same required `text` and optional `language` fields as `/generate`.
- Response: HTTP chunked `application/octet-stream`, mono float32 little-endian PCM.
- Required metadata headers: `X-Audio-Format: f32le`, `X-Audio-Sample-Rate: 24000`,
  `X-Audio-Channels: 1`.
- Mid-stream failure: close the connection. Raw PCM has no control frame; clients must explicitly decide
  whether to discard or retain a truncated payload. Failures before streaming begins should remain HTTP
  errors where the WSGI stack can still produce one.
- Streaming requires the FP32 OpenVINO vocoder and returns HTTP 503 when it is unavailable. The PyTorch
  rollback remains the batch API; it must not silently enter a different streaming implementation.

The single-worker executor continues to serialize model access. A queue transfers PCM from the worker
thread to Flask's response iterator; this is transport streaming only. Vocoder inference currently runs
synchronously in the generation callback, so deliverable B (concurrent talker/vocoder overlap) is not
implemented.

### Current measured status (2026-06-30)

The 0.6B mounted-file target run passed exact same-generation parity. The paragraph test used 160
reference + 194 generated frames, decoded at total-frame boundaries 300 and 354, delivered first audio
at 39.34 s, and completed at 90.84 s with max_abs 0 / infinite SNR. Aggregate container CPU averaged
~500% of 800%; this is not sufficient to approve overlap. Full provenance and caveats are recorded in
`OPENVINO_RESULTS.md`.

Release remains blocked on a baked-image smoke test, live public-proxy test, seam listening, identical-
seed batch latency comparison, disconnect/timeout and mixed serialized-request tests, 1.7B validation,
phase-separated CPU profiling, and fresh-process PyTorch rollback.

## Service Integration

Keep the existing `app_api.py` batch contract unchanged. The streaming track adds only the opt-in
raw-PCM endpoint documented above. `app_worker.py` selects the backend with an environment variable:

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

For 0.6B-INT8 keep `mem_limit: 7G` and `memswap_limit: 8G`. For 1.7B-INT4 stateful + bf16 set
`TTS_MEMORY_LIMIT=8G` (M9 closed: ~7.5 GiB idle / ~7.7 GiB peak floor does not fit 7G).

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
| `ov_talker_runtime.py` | Install/uninstall OV cores by swapping the two inner core forwards (M4) |
| `streaming_vocoder.py` | Observe completed outer-talker codec frames and emit parity-preserving prefixes |
| `test_transformer_parity.py` | Synthetic FP32/INT8 tensor/cache/token core parity (M2/M3) |
| `test_ov_generation.py` | Generation-level greedy code agreement + warm latency/RTF (M4) |
| `app_worker.py` | Backend selection, health, rollback, internal parity, and raw-PCM worker streaming |
| `app_api.py` | Preserve batch behavior, proxy raw-PCM streaming, and keep readiness fail-closed |
| `serve.py` | Supervise both Gunicorn masters and forward shutdown signals |
| `Dockerfile` | Experimental OpenVINO stage and CPU-only PyTorch cleanup |
| `compose.example.yml` | Keep runnable runtime/downloader wiring and add the validated IR mount |
| `docs/HOW_TO_RUN.md` | Operator commands, mounts, environment variables, safety, and benchmark capture |
| `.github/workflows/ci.yml` | Lightweight tests on `arc-general` without model download |
| `.github/workflows/image.yml` | Build and publish runtime/exporter targets on `arc-general-docker` |
| `scripts/export-on-dockermisc1.sh` | Versioned host-side export and validation command |
| `scripts/run-m4-on-dockermisc1.sh` | Stop service, run the M4 generation harness in the exporter image, restart |

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
8. `/generate`, `/infer`, `/health`, MP3 output, WAV output, and serialized concurrency pass. If
   streaming ships, `/generate/stream`, truncation semantics, disconnect cleanup, and mixed
   batch/stream serialization must also pass.
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

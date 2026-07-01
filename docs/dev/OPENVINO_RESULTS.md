# Qwen3-TTS OpenVINO — Benchmark & Results Log

Measured data only. Design, contracts, and plans live in
[`OPENVINO_IMPLEMENTATION.md`](OPENVINO_IMPLEMENTATION.md); this file is the audit record of every
run so options can be compared without wading through the implementation narrative.

All runs: CPU only, dockermisc1 (8 vCPU i7-1360P, AVX2+VNNI, no AVX-512, 15 GiB RAM), 6 threads,
0.6B Base unless noted. "match" = `mean_overall_codebook_match_rate`; "speedup" = warm
`speedup_median` (PyTorch ÷ OpenVINO); RTF = OV real-time factor.

---

## Streaming vocoder track — measured 2026-06-30

Branch `feat/streaming-vocoder`, corrected runtime/test commit `8f6b862` (target runs used its
semantically equivalent pre-commit working tree) mounted over `runtime-v0.12.0` at digest
`sha256:214eb114859e71d36ff19175d40c332124dfc0249dd6df27034101f7694e687b`.
Model `Qwen/Qwen3-TTS-12Hz-0.6B-Base`, revision
`5d83992436eae1d760afd27aff78a71d676296fc`; explicit IR metadata file SHA-256
`abec65a5d2f2dcf07382d707513cb2a9f5c2a4c5872728069b169d9601e3da7f`, source hash
`dd8e1a75b4ef2174`; OpenVINO 2026.2.1. Runtime used the capacity-768 main and capacity-32
predictor stateful graphs, FP32 OpenVINO vocoder, 6 threads, an 8 GiB cgroup, and production
sampling. Production `qwen3-tts` remained stopped; only temporary `qwen-stream-test` was used.

The inspected Qwen seam is the outer `Qwen3TTSTalkerForConditionalGeneration.forward` result:
`hidden_states[-1]` is the completed 16-codebook frame. The inner `talker.model.forward` result is
a transformer hidden state and must not be treated as codec IDs. Stock voice-clone decode prepends
160 reference frames, so the streaming prefix must include those codes and omit their samples.

### Parity and TTFB

| Run | Ref + generated frames | Boundaries | First audio | Terminal | max abs | SNR |
|---|---:|---|---:|---:|---:|---:|
| short producer parity | 160 + 23 | 183 final | terminal | — | 0 | infinite |
| short, terminal decode reused | 160 + 24 | 184 final | 14.616 s | 14.616 s | 0 | infinite |
| final committed-code reuse smoke | 160 + 32 | 192 final | 22.372 s | 22.347 s | 0 | infinite |
| paragraph, diagnostic duplicate stock decode | 160 + 194 | 300, 354 | **39.341 s** | **90.840 s** | 0 | infinite |

The paragraph prompt was the repository `bench_common.PROMPTS["paragraph"]`, with
`max_new_tokens=400`. Two chunks were emitted: the first at the real 300-frame boundary and the
second from the final partial prefix. First audio preceded terminal completion by **51.50 s**. The
90.84-second total is not a production latency comparison: that diagnostic intentionally allowed
upstream `generate_voice_clone` to perform its normal full decode after the early prefix decode. The
implemented transport path now reuses the already-decoded final prefix; the short reuse run dropped
from prior ~27-second duplicate-decode diagnostics to 14.62 s while retaining exact sample parity.

The worker `/infer_stream` transport returned HTTP chunked `application/octet-stream` with mono
24 kHz `f32le` metadata. A short live request delivered 184,320 bytes (24 frames) with
`time_starttransfer=14.675 s` and `time_total=14.675 s`. Public `/generate/stream` proxy behavior is
covered by four passing runtime-image tests; a live two-Gunicorn public-proxy run remains open.

### CPU and memory observation

The paragraph profile collected 45 `docker stats` samples. Container CPU ranged **431.92–546.49%**
and averaged **499.89%** on the 8-vCPU host. The approximate pre-first-audio mean was 514.85%; the
post-first-audio mean was 487.92%. This demonstrates aggregate CPU headroom but does **not** separate
talker and vocoder phases or establish that concurrent overlap will improve wall time. Deliverable B
remains gated on per-core, phase-separated 0.6B and 1.7B profiles. Container RSS rose from about
5.97 GiB to 6.33 GiB during the diagnostic and stayed within the 8 GiB test limit.

### Chosen-profile serving validation (2026-06-30 follow-up)

Commit `68e58b2` fixed a reproducibility gap: M9's BF16 result was loaded through
`bench_common.py`, while `app_worker.py` still hard-coded FP32. The worker now shares the BF16/
low-memory resolver and reports both settings plus per-core active compression in health. Target runs
mounted the follow-up working tree over the same `runtime-v0.12.0` image.

**0.6B chosen profile:** INT8 asymmetric, capacity-768 stateful main, capacity-32 stateful predictor,
BF16 glue, early Torch-layer release, FP32 OV vocoder, 6 threads, 8 GiB test cgroup. Startup log:
`main=stateful-int8 predictor=stateful-int8 vocoder=OV`; cold ready RSS ~3.76 GiB. A short request
generated 48 frames, boundary 208, total 20.110 s, max_abs 0, infinite SNR. Post-request RSS was
~4.95 GiB. This validates the exact environment/profile wiring; the existing long-request result
(7,845 MiB) still governs paragraph memory sizing.

**1.7B persisted profile:** INT4 asymmetric g32 transformer layers, capacity-768 stateful main,
**explicit INT4 predictor** (no persistent 1.7B stateful-predictor XML exists), BF16 glue, early
release, FP32 OV vocoder, 6 threads. Metadata SHA-256
`ca8f50be8ff4be280248f4ec9c7767ec91f3244e20ef9bcd58042a410344ea2e`; stateful-main XML SHA-256
`bd0b0daed8c3bec0fc4cd86043dcaecaa704ea8d01050b3a217dcca0cb9cd36b`. Startup log:
`main=stateful-int8 predictor=int8 vocoder=OV`; health reported model revision
`fd4b254389122332181a7c3db7f27e918eec64e3`, BF16, low-memory load, main capacity 768, and no
stateful predictor. Cold ready RSS was ~4.23 GiB.

1.7B short request: 42 generated frames, boundary 202, 23.651 s, max_abs 0, infinite SNR, ~6.03 GiB
post-request RSS. Paragraph diagnostics used `bench_common.PROMPTS["paragraph"]`, production sampling,
and `max_new_tokens=400`:

| 1.7B paragraph mode | Frames | Boundaries | First audio | Total | CPU mean | PCM parity |
|---|---:|---|---:|---:|---:|---|
| diagnostic stock final decode | 180 | 300, 340 | 48.992 s | 102.495 s | 466.80% | exact |
| final-prefix reuse | 173 | 300, 333 | 50.945 s | 81.061 s | 469.94% | exact |

The two sampling runs are not an identical-seed latency A/B; the total-time difference is diagnostic,
not a release speed claim. The fresh reuse run peaked at **8,350,515,200 bytes (~7.78 GiB)** in the
8 GiB cgroup, with zero `memory.events:max`, OOM, or swap events. This proves 8 GiB is a functional
minimum but leaves only ~2.8% cgroup headroom. Enforcing the repository's 20% production-headroom
rule requires a **10 GiB production limit** for unrestricted 1.7B serving. The earlier non-reuse run
hit the 8 GiB limit and recorded 1,370 `memory.events:max` events, confirming that 8 GiB is too tight
for diagnostics that duplicate final decode.

The exact-parity listening WAV is `/private/tmp/profile_17_reuse.wav` on the development Mac and
`/tmp/profile_17_reuse.wav` on `dockermisc1`; inspect around **11.2 seconds**, where total frame 300
crosses from the first emitted block to the final block. Human listening verdict (2026-06-30):
streamed and batch sound **identical with no audible seam** at the boundary; quality gate closed.
Fresh A/B WAVs also staged at `audio/streaming-ab/`.

### v0.13.0 baked-image streaming validation (2026-06-30, dockermisc1)

This is the first validation using a CI-baked runtime image containing the streaming runtime and BF16
loader fix, without mounted branch files.

**0.6B INT8 profile** (cap-768 main, cap-32 predictor, BF16 glue, FP32 OV vocoder, 6 threads, 10 GiB cgroup):

- Short phrase streaming: HTTP 200, 130560 bytes (5.44 s audio), first_byte=30.31 s, total=30.31 s
  (under 300 frames; burst at completion)
- Paragraph streaming: HTTP 200, 2465280 bytes (25.68 s audio), first_byte=59.98 s, total=161.45 s
  (101.5 s head start on audio delivery)
- Internal parity: max_abs=0, SNR=inf, reuse=true, 14 gen frames, 160 ref frames
- Batch WAV: HTTP 200, 43742 bytes (batch path unchanged)

**1.7B INT4 profile** (cap-768 stateful main, explicit INT4 predictor, BF16 glue, FP32 OV vocoder, 6 threads, 10 GiB cgroup):

- Health: stateful_main=true, stateful_predictor=false, torch_dtype=bfloat16 (matches expected evidence)
- Short phrase streaming: HTTP 200, 368640 bytes (3.84 s audio), first_byte=47.53 s, total=47.53 s
  (under 300 frames; burst at completion)
- Paragraph streaming: HTTP 200, 1167360 bytes (12.16 s audio), first_byte=65.34 s, total=118.01 s
  (52.7 s head start on audio delivery)
- Internal parity: max_abs=0, SNR=inf, reuse=true, 20 gen frames, 160 ref frames
- Batch WAV: HTTP 200, 66348 bytes (batch path unchanged)

Both profiles pass Task 1 (baked-image smoke) on v0.13.0.

### Task 2 — identical-seed latency comparison (2026-06-30, dockermisc1)

Container `qwen3-tts-candidate`, `runtime-v0.13.0`, 0.6B INT8 (stateful main cap-768, stateful
predictor cap-32, BF16 glue, FP32 OV vocoder), 10 GiB cgroup, 6 threads. Seed 42,
`do_sample=False`, same paragraph text across all runs. The `/batch_internal` and
`/stream_internal` endpoints each apply the seed before generation via `_apply_optional_seed()`.

**Short prompt** (bench_common short text, 3 warm-measured iterations):

| Metric | Batch | Stream |
|---|---:|---:|
| median wall time (s) | 35.939 | 35.805 |
| p95 wall time (s) | 37.844 | 35.881 |
| min wall time (s) | 35.868 | 35.747 |
| max wall time (s) | 37.844 | 35.881 |
| median TTFB (s) | — | 35.801 |
| frames | 49 | 49 |
| audio (s) | 3.92 | 3.92 |

- PCM parity: all 3 iterations exact (max_abs=0, SNR=inf).
- Under 300 frames, audio is emitted as a single burst at completion; TTFB ≈ total.
- Stream median wall time is marginally faster than batch (−0.134 s), within noise.
  No regression for short requests.

**Paragraph** (bench_common paragraph prompt, max_new_tokens=200, 1 run):

| Metric | Batch | Stream |
|---|---:|---:|
| wall time (s) | 97.205 | 121.252 |
| elapsed (s) | 97.164 | 121.224 |
| frames | 195 | 195 |
| ref frames | 160 | 160 |
| audio (s) | 15.6 | 15.6 |
| TTFB (s) | — | 59.308 |
| chunks / boundaries | — | 2 / 300,355 |

- PCM parity: exact (max_abs=0, SNR=inf).
- Stream total wall time is 24.6 s (25.4%) slower than batch.
- First audio arrives 59.3 s in, 61.9 s before batch would have finished and 62.0 s before stream
  completion. Audio is delivered before generation completes, but the streaming overhead (vocoder
  decode at each boundary, streaming hooks) increases total wall time for paragraph-length requests.

Verdict: identical-seed parity is confirmed for both short and paragraph. Streaming does not regress
short-request wall time. For paragraph-length, streaming increases total wall time by ~25% because
of repeated vocoder inferences at each decode boundary; however, it starts delivering PCM ~60 s
before completion. Task 2 acceptance is met (exact parity, streaming does not regress beyond noise
for short requests; paragraph regression is documented as a trade-off).

Non-Git artifacts on dockermisc1:

```text
/tmp/bench_short_identical_seed_report.json (0.6B)
/tmp/bench_paragraph_identical_seed_report.json (0.6B)
/tmp/bench_stream_06b_r150_report.json (partial, from earlier attempt)
```

Memory note: after these runs the 0.6B container was at 9.446 GiB / 10 GiB. Paragraph-length streaming
runs accumulate memory (stateful caches, vocoder buffers, streaming chunk storage). Periodic restart
or 10 GiB+ headroom is required to avoid OOM.

### Task 2 — 1.7B identical-seed latency comparison (2026-06-30, dockermisc1)

Container `qwen3-tts-candidate`, `runtime-v0.13.0`, 1.7B INT4 asymmetric g32 (stateful main cap-768,
explicit INT4 predictor, BF16 glue, FP32 OV vocoder), **12 GiB cgroup / 13 GiB swap**, 6 threads.
Seed 42, `do_sample=False`. The same "short" prompt text generates 195 frames (15.6 s audio) on 1.7B
(equivalent to paragraph-length), so these are paragraph-scale runs.

**3 measured iterations:**

| Iteration | Batch wall (s) | Stream wall (s) | Slowdown | TTFB (s) | Parity |
|---:|---:|---:|---:|---:|---:|
| 1 | 113.332 | 130.445 | +15.1% | 66.104 | exact |
| 2 | 104.649 | 128.782 | +23.1% | 64.778 | exact |
| 3 | 105.205 | 129.976 | +23.6% | 65.509 | exact |

Summary:
- Batch median wall: 105.205 s; Stream median wall: 129.976 s (23.5% slower).
- Stream median TTFB: 65.509 s (audio starts ~64.5 s before batch would have completed).
- All 3 iterations exact PCM parity (max_abs=0, SNR=inf).
- First iteration is slower for both modes (batch 113.3 s vs 105 s median) — cold cache effect.
- After 3 iterations: container at 11.32 GiB / 12 GiB (94.37%); 12 GiB was necessary (a prior run
  at 12 GiB with only 2+ iterations hit 99.45% and the next streaming run failed).

Verdict (1.7B): identical-seed parity confirmed; streaming increases total wall time by 23-24% for
paragraph-length requests, matching the 0.6B's 25% regression. Streaming TTFB starts ~65 s before
completion. The 23-25% penalty is consistent across both models and is structural (repeated vocoder
inference at each 300-frame boundary).

Non-Git artifacts on dockermisc1:

```text
/tmp/bench_short_identical_seed_report.json (1.7B — overwrote 0.6B report; 0.6B data captured above)
```

Memory note: 1.7B INT4 paragraph-length streaming runs at 12 GiB approach 94% after 3 iterations.
For production with streaming and paragraph loads, 12 GiB is a minimum; 10 GiB is unsafe.
(Superseded by the `--preload` fix below — see "Serving `--preload` memory fix".)

### Serving `--preload` memory fix (2026-06-30, dockermisc1, 1.7B-INT4)

The Gunicorn worker was launched with `--preload` under `-w 1`. With a single worker, preload shares
nothing and pins a redundant full model copy in the master. Removing `--preload` from `serve.py`:

| Metric | With `--preload` | Without `--preload` |
|---|---:|---:|
| Worker master process RSS | 3.06 GiB | 0.03 GiB |
| Container `anon`, post-paragraph | 10.64 GiB | **5.76 GiB** |
| Container swap | 1.07 GiB | **0** |

Held flat at 5.76 GiB across four back-to-back paragraph `/generate` calls (no retention creep, so no
allocator tuning needed). Fresh idle after load ~4.0 GiB. The earlier "~7.78 GiB peak / 12 GiB minimum"
figures were inflated by the preload copy; real 1.7B-INT4 serving steady-state is ~5.8 GiB. The 400-token
maximum-length paragraph peak on a freshly baked image is not yet re-measured. Tested via `docker cp` of
the patched `serve.py` onto `runtime-v0.13.0`, 12 GiB cgroup.

### Task 3 — overlap go/no-go: per-core CPU (2026-06-30, dockermisc1, 1.7B-INT4)

`mpstat -P ALL 1` across a 71 s batch paragraph `/generate`, active-window per-core busy%:

| Core | Generation | Vocoder (`chunked_decode` tail) |
|---|---:|---:|
| cpu0–5 | 82–98% | 77–86% |
| cpu6, cpu7 | 12–14% | 12–13% |
| Sum | 533/800 | 507/800 |

With `OV_INFERENCE_THREADS=6` the model saturates 6 cores and leaves **exactly 2 idle** in both phases.
Headroom for Deliverable B (pipelined overlap) therefore exists but is narrow (2 of 8 cores); the 6
generation threads cannot be shared without slowing generation. A dedicated vocoder `InferRequest` on a
2-thread pool over the spare cores could decode streaming chunks concurrently, recovering the 23–25%
streaming wall-time penalty while keeping the ~60 s TTFB benefit — a UX win, not a net speedup over
batch. Building B is a product decision; Deliverable A ships regardless. Raw: `/tmp/task3_mpstat.txt`.

### Validation scope and remaining gates

- Model-free iterator/session tests: passed, including reference codes, EOS, exact boundaries, final
  partial flush, exception cleanup, and forward-signature preservation.
- Real 0.6B same-generation stream-vs-batch parity: passed exactly.
- Worker raw-PCM chunked transport: passed live.
- Public proxy unit tests: passed in `runtime-v0.12.0`.
- Baked-image streaming smoke (v0.13.0): passed (Task 1).
- Done since: phase-separated per-core CPU profile (Task 3) and human listening (identical, no seam).
- (Originally pending) phase-separated per-core CPU profile, human listening at the 1.7B
   300-frame seam.
- Run: identical-seed batch vs streaming wall-time comparison (Task 2) — short exact parity,
  no regression; paragraph: exact parity, 25% slower total wall time with 60 s head start on audio.
- Run: disconnect/timeout tests (ok), mixed serialized requests (ok), fresh-process PyTorch rollback (ok, 503).

Raw diagnostics remain outside Git on `dockermisc1` under `/tmp/stream_{long,reuse}*`,
`/tmp/infer_stream.f32`, and `/tmp/stream_cpu.txt`. The temporary container was stopped after testing.

---

## 0.6B decision summary (current)

**LOCKED: 0.6B ships weight-only INT8_ASYM transformer cores + FP32 OV vocoder (~1.40x).** The
artifact is acceptable (see A/B below); FP32 gives no speedup so it is not a real option; every
quality-recovery avenue available on the pinned NNCF 3.2.0 stack has been tried and rejected.

| Config | match (mean) | dur ratio | speedup | peak RSS | verdict |
|---|---:|---:|---:|---:|---|
| **all-INT8** (shipped) | 0.8165 | 0.9642 | **1.40x** | 9.6 GiB | ✅ locked — only config with real speedup |
| all-FP32 | 0.9405 | 1.0244 | 0.97x | 11.8 GiB | ❌ no speedup over PyTorch; pointless to ship |
| main INT8 / pred FP32 | 0.8362 | 0.8839 | 0.96x | 12.4 GiB | ❌ no quality gain, kills speed |
| main FP32 / pred INT8 | 0.8317 | 0.9359 | 1.11x | 13.7 GiB | ❌ no quality gain, partial speed, worst memory |

Neither the 0.6B nor (projected) 1.7B reaches the original 2x Gate 5 by swapping the two transformer
cores; the ceiling is structural (sequential 15-step predictor + ~29% FP32 tokenizer-decode that
OV does not accelerate), not a quantization shortfall. Treat ~1.4x as the practical CPU ceiling.

**Rejected quality-recovery paths (all on NNCF 3.2.0):** data-aware INT8 calibration (API forbids
it), full W8A8 PTQ (tensor accuracy ~7 dB vs ~30 dB), whole-core precision mix (table above).
Per-layer `ignored_scope` is the only untried lever and is low-probability (damage is distributed);
not worth it for 0.6B.

---

## 0.6B stateful-KV footprint track — measured 2026-06-29

Branch `feat/0.6b-stateful-kv`, implementation commit `e5ab3cc` (the target runs used its
semantically identical pre-commit working tree mounted over `/app`). Image `exporter-v0.10.0` at
`sha256:5189f9bd604c4f4e187175691b7375e9b6f3fd449d91ca73ec78911beaebcb49`; model revision
`5d83992436eae1d760afd27aff78a71d676296fc`; source metadata SHA-256
`abec65a5d2f2dcf07382d707513cb2a9f5c2a4c5872728069b169d9601e3da7f`; OpenVINO 2026.2.1;
6 threads; INT8_ASYM cores; FP32 OV vocoder; `OPENVINO_BUFFER_KV=1`. Generated IR/audio/profile
artifacts remain outside Git under
`...0.6b_5d83992436ea_ov-2026.2.1_stateful/` on `dockermisc1`.

Transformed artifacts:

| Core | Capacity | Graph contract | XML SHA-256 |
|---|---:|---|---|
| main INT8 | 768 | 4 inputs, 1 output, 56 states `[1,8,768,128]` | `d7fe2ce2…f0d7a` |
| predictor INT8 | 32 | 5 inputs, 1 output, 10 states `[1,8,32,128]` | `a144ada5…a047b` |

The predictor retains `generation_steps` as its fifth graph input. Live nested generation may omit
that optional argument, so the stateful runtime now mirrors the explicit runtime's zero default.
The transform CLI infers layer/base-input/cache-position layout and can write a hashed provenance
sidecar with `--report-json`.

### Parity and quality

- INT8 explicit vs stateful: **bit-exact** hidden outputs and used K/V state prefixes. Main passed
  prefill + 3 decode steps; predictor passed a 2-token prefill + all 14 decode calls (15 codebooks).
- FP32 stateful vs PyTorch: main SNR **77.56–86.47 dB**, max_abs ≤0.00272; predictor SNR
  **87.55–130.65 dB**, max_abs ≤0.00224. Every scope clears SNR ≥60 dB / max_abs ≤0.01.
- Same-seed end-to-end explicit and stateful INT8 WAVs are byte-identical, SHA-256
  `3ed46d287fc434ad423b3813fb5b47afe0078e5a4c2fce0b44a995dea7233ae6`. No quality or duration
  change was introduced.

### Memory attribution

One backend per process, default short text, production sampling, bf16 where shown:

| Configuration | Generation/lifetime peak | Trimmed retained | Change vs bf16+release explicit |
|---|---:|---:|---:|
| explicit, fp32 glue, no release | 11,036 MiB | 10,681 MiB | — |
| explicit, bf16 glue, no release | 8,588 MiB | 8,221 MiB | — |
| explicit, bf16 + release | **8,623 MiB** | **8,247 MiB** | baseline |
| stateful main only, bf16 + release | 6,948 MiB | 6,696 MiB | −1,675 / −1,551 MiB |
| stateful main + predictor, bf16 + release | **6,635 MiB** | **6,394 MiB** | **−1,988 / −1,853 MiB** |

bf16 is the large load/retention lever. Early release frees ~0.97 GiB of core weights but does not
move the binding 0.6B generation peak because OV compilation/generation reuses allocator pages.
Stateful main removes most explicit K/V marshalling and saves ~1.68 GiB peak; cap-32 predictor adds
another ~313 MiB. The short request fits under 7 GiB, but only with ~533 MiB (7.4%) cgroup headroom.

### Capacity and latency

- Capacity: the 177-word repeated paragraph completed without cache overflow and produced 45.28 s
  audio at main cap 768 / predictor cap 32. Peak RSS was **7,845 MiB**, trimmed retained 6,716 MiB.
  Therefore 7 GiB is valid only for bounded short requests; paragraph-capable deployments need 8 GiB.
- Warm sampling, one warm-up + five measured iterations, identical seeds/text: explicit median
  **18.429 s** (RTF 5.485) vs stateful **19.138 s** (RTF 5.696), a **3.8% regression**. Stateful KV
  is accepted as a footprint feature, not a latency optimization.
- Protected `litellm`, `litellm-postgres`, and `headroom-proxy` remained healthy; production
  `qwen3-tts` remained stopped. Post-run host available memory was ~13 GiB; swap remained 2.9 GiB used.

**Decision:** the stateful 0.6B profile is ship-capable after its IRs and runtime are baked into a
versioned image/artifact set. Keep explicit cache as opt-out rollback. Do not advertise 20% headroom
at 7 GiB or support long prompts there. This branch did not rerun HTTP serving/concurrency or the
full PyTorch rollback; the last PyTorch rollback pass is the v0.11.0 M9 run and must be repeated from
the baked release candidate.

---

## A/B listening verdict — 0.6B INT8 vs PyTorch (2026-06-29)

Same seed (20260628), same text ("Once upon a time, in a village far away, there lived a curious
young child who loved to ask questions about everything she saw."), OV vocoder genuinely active
(`[ov_talker] backends: main=int8 predictor=int8 vocoder=OV`). WAVs in `audio/m6-ab/`.

- PyTorch 6.64 s vs OV INT8 7.44 s for the same text — INT8 utterance ~12% longer.
- Listener: PyTorch has a *slightly* less pronounced pause at the commas; **INT8 is absolutely
  acceptable.** → 0.6B INT8 locked.

---

## Milestone 0 — baseline profile (FP32 PyTorch, no OpenVINO)

0.6B Base, FP32, production sampling, 10-word prompt, single profiled generation via
`profile_tts.py --prompt short`:

| Component             | Time    | Share | Calls | Per call |
| --------------------- | ------- | ----- | ----- | -------- |
| `code_predictor`      | 12.66 s | 45.6% | 795   | 15.9 ms  |
| `speech_tokenizer.decode` | 8.09 s | 29.1% | 1   | 8.09 s   |
| `main_talker`         | 5.78 s  | 20.8% | 54    | 107 ms   |
| other / glue          | 1.25 s  | 4.5%  | —     | —        |
| **end-to-end**        | 27.78 s | —     | —     | RTF 6.55 |

Predictor/main step ratio 14.7 (≈ the 15 codebooks/frame). Predictor is ~69% of the transformer
loop (main+predictor) — confirms the ~70% assumption. The tokenizer decode is ~29% of *end-to-end*:
a two-core-only backend caps speedup around 3.4x and must be paired with tokenizer profiling.
Greedy (`do_sample=False`) did not terminate; these numbers are sampling-mode and parity must use
bounded decode steps.

Warm latency from `benchmark_tts.py --prompts short --iterations 5` (5 measured runs after 1
warm-up): median **28.7 s**, p95 **30.8 s** for ~4.6 s of audio (RTF 6.18); **peak RSS 6394 MiB**,
swap delta negligible. The 6.4 GiB peak against the 7 GiB production limit leaves <20% headroom *at
FP32 baseline*, before any hybrid backend that transiently holds both PyTorch and OpenVINO weights —
the selective-loader / memory milestone is load-bearing for the limit, not optional polish.

---

## Milestone 1.5 / 2 — export parity gates

- **Vocoder FP32 IR:** synthetic parity SNR **46.4 dB** (PASS). INT8 vocoder **rejected**: 16.3 dB.
- **Transformer cores FP32:** synthetic parity SNR **72–91 dB** (PASS).
- **M3 INT8 characterization:** all-weight INT8_SYM/INT8_ASYM fail the synthetic hidden-state SNR
  gate (24–28 dB) but top-1 token agreement holds. SNR here is a debug signal, not a quality
  verdict — not a quality rejection.

---

## Milestone 4 — generation runtime, measured (2026-06-28)

### First run — exporter-v0.6.1, IR `qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1`

FP32 + INT8_ASYM, warm sampling latency, 5 iterations, ~3 s utterance. Reports beside the IR
(`ov_generation_report_{fp32,int8}.json`).

| metric | FP32 OV | INT8_ASYM OV |
| --- | --- | --- |
| warm median latency (PyTorch → OV) | 25.23 s → 22.72 s | 21.75 s → 15.79 s |
| **speedup_median** | **1.11x** | **1.38x** |
| OV RTF | 7.28 | 5.33 |
| Gate 5 (≥2x) | ❌ | ❌ |
| greedy frame agreement | 0.766 | 0.829 |
| first divergence frame | 160 | 160 |
| greedy waveform SNR | −0.0 dB | −2.4 dB |
| peak RSS | 11.9 GiB | 8.8 GiB |

Findings: (1) neither precision meets 2x by swapping two cores alone; INT8 is the better lever
(1.38x, 8.8 GiB) — ceiling is structural (untouched ~29% tokenizer decode + PyTorch per-frame glue).
(2) Both OV variants diverge from greedy PyTorch at the *same* frame 160 → systematic OV-vs-PyTorch
discrepancy, not quantization noise; greedy frame-agreement and divergence-contaminated SNR are
debug signals, not the perceptual verdict. (3) Harness needs ~12 GiB (FP32) / ~9 GiB (INT8) because
it holds PyTorch + OV at once; a 7 GiB cgroup OOM-kills it (serving runtime loads OV only).

These motivated PR #44: vocoder IR wired into runtime, persistent K/V buffers (`OPENVINO_BUFFER_KV`),
`--mode sampled-quality`/`logits-parity`/`all`, and the frame-160 diagnostic.

### Acceptance criteria (sampled-quality harness)

`median_waveform_snr_db ≥ 15 dB` · `mean_overall_codebook_match_rate ≥ 0.70` ·
`min_per_codebook_match_rate ≥ 0.55` · `mean_duration_ratio ∈ [0.85, 1.15]` ·
`mean_energy_ratio ∈ [0.7, 1.4]`. Greedy and logits-parity are diagnostics, not ship gates.
**Note:** the 15 dB waveform-SNR gate is unrealistic for INT8 under same-seed sampling and
systematically fails; codebook match + duration/energy + listening are the real gates.

### FP32 re-validation — runtime-v0.8.0, vocoder + buffer-KV on

`--mode all --code-steps 96 --sampled-iters 5` (report `..._v080_all_fp32_...json`):

- Greedy: 196 frames, first_divergence **−1 (none)**, waveform SNR 220.83 dB, speedup **0.97x**
  (22.45 s → 23.24 s), peak RSS ~11.8 GiB.
- Sampled: SNR 220.62, **match 0.9405**, min 0.8109, dur 1.0244, energy 1.002.
- Logits-parity: no argmax divergence in 37 steps.
- → FP32 runtime is numerically correct; the INT8 issues (frame-160, low SNR, frame-0 logits flip)
  are **INT8-specific**, not a general OV bug. FP32 gives no speedup.

### INT8 re-validation — runtime-v0.8.0

`--mode all --code-steps 96 --sampled-iters 5 --compression int8`
(report `..._v080_all_int8_...json`):

- Greedy: 194 frames, first_divergence 160, agreement 0.825, SNR −3.45 dB, speedup **1.40x**
  (21.79 s → 15.55 s), peak RSS ~9.6 GiB.
- Sampled: SNR −2.66, **match 0.8165**, min 0.7656, dur 0.9642, energy 1.0108.
- Logits-parity: first_argmax_mismatch_frame **0**.

### CORRECTION — v0.8.0 runs used the PyTorch vocoder, not OV (runtime-v0.8.1)

Despite `OPENVINO_VOCODER_ENABLED=1`, the OV vocoder IR **never loaded** in v0.8.0 — four stacked
bugs each fell silently through to PyTorch `speech_tokenizer.decode`: (1) filename `vocoder.xml` vs
exporter's `vocoder_decoder.xml`; (2) `speech_tokenizer` resolved via `getattr(talker, …)` but it is
a *sibling* on the parent model (`model.model.speech_tokenizer`) → always `None`, vocoder runtime
never constructed (decisive blocker); (3) `_validate_io` used `.any_name` (tensors unnamed) and
`.get_shape()` (axes dynamic), both raise; (4) patched `decode` returned only the waveform list, but
the contract is `(wavs, sample_rate)`. All fixed; runtime now prints a backend-provenance line at
install, the report carries a `backends` block, and the fallback warns once.

### INT8 re-validation with OV vocoder GENUINELY active — runtime-v0.8.1

(`vocON_verify_int8.json`; box shared CPU with litellm so absolute times are noisier):

- Greedy: 194 frames, first_divergence 160, SNR −3.5 dB.
- speedup **1.35x** (23.48 s → 17.35 s), OV RTF 5.86, peak RSS ~10.3 GiB.
- Sampled: SNR −2.66, **match 0.8165**, min 0.7656, dur 0.9642, energy 1.0108 — **identical** to the
  v0.8.0 PyTorch-vocoder run (codes come from the cores; the FP32 vocoder IR renders them faithfully).
- → The ~29% tokenizer-decode chunk **does not accelerate under OV IR on this CPU**; the vocoder is
  quality-neutral and speed-neutral. It is *not* the lever to 2x.

---

## Milestone 6 — INT8 quality recovery (investigation, 2026-06-28/29)

Baseline to beat: speedup 1.35x, match 0.8165, dur 0.9642, logits first mismatch frame 0, greedy
first divergence 160. Remaining divergence originates inside the quantized transformer matmuls
(embeddings + all codebook heads stay FP32 in PyTorch; vocoder IR is faithful).

### 1. Calibration inputs captured (usable)

`calibration_capture.py` recorded the exact explicit-cache positional contract per graph from 24
seeded generations: main prefill 24, main decode 48, predictor prefill 48, predictor decode 48.
On dockermisc1 under `openvino/calib_0.6b/` (not in Git):

| File | Size | SHA-256 |
|---|---:|---|
| `main_prefill.pkl` | 17 MiB | `da773572f974ac59148cd36f6c05ae6e67ab84a9d6eaab80d1013e15c83d0b2c` |
| `main_decode.pkl` | 2.0 GiB | `dbe0a90899b91d2c2ace7981d4de9555ad525701a049c4a513c224daa82a72e9` |
| `predictor_prefill.pkl` | 394 KiB | `afc2475ca58b5c9920cbfb9a35b27055e9c30908859056100042b0cdc9d79c4e` |
| `predictor_decode.pkl` | 16 MiB | `1e11ce43062ec710d360e8ec54602310785aacccc5b532a02715dd55cc52aed7` |

Command: `python calibration_capture.py --out-dir /ov_output/calib_0.6b --max-prefill 48
--max-decode 48 --decode-stride 6`.

### 2. Data-aware weight-only INT8 — UNSUPPORTED (rejected)

Failed before NNCF backend dispatch: `ParameterNotSupportedError: INT8 modes do not support dataset,
scale_estimation option(s)`. Pinned NNCF 3.2.0's `check_user_compression_configuration` rejects
`dataset`, `awq`, `scale_estimation`, `gptq`, `lora_correction`, `sensitivity_metric`, and
`backup_mode` for both INT8 modes on **every** backend (the earlier "OpenVINO backend bypasses it"
assumption was wrong). The `--calibration` exporter flag now fails fast (PR #53).

### 3. Full calibrated W8A8 PTQ — REJECTED on accuracy

`nncf.quantize` *does* accept the captured data. A bounded main-prefill spike (all 24 records,
transformer mixed preset + SmoothQuant) on the primary hidden output:

| | weight-only INT8 | calibrated W8A8 |
|---|---:|---:|
| SNR (3 samples) | **29.781–30.131 dB** | **7.320–7.397 dB** |
| max abs error | 1.45–1.66 | 24.65–25.95 |

Many cache outputs also regressed >20 dB. Too inaccurate to justify a four-graph export. Code-path +
tensor-accuracy rejection only (no full generation/listening). Spike kept outside Git at
`openvino/m6-calibrated/spike_main_prefill_w8a8.{xml,bin}`
(XML `9f668dc0…57fc`, BIN `eeaa40f2…1fa5`).

### 4. Whole-core precision mix — REJECTED (2026-06-29)

Near-zero-cost test using the runtime's existing per-core override (`OV_MAIN_COMPRESSION` /
`OV_PREDICTOR_COMPRESSION`) on the `both` IR — no new export. `--mode all --code-steps 96
--sampled-iters 5`, seed 20260628, OV vocoder + buffer-KV, exporter-v0.9.0. Reports under
`openvino/m6-percore/`.

| Config | match (mean / min) | dur ratio | energy | speedup | peak RSS | logits 1st-mismatch |
|---|---:|---:|---:|---:|---:|---:|
| all-FP32 (ref) | 0.9405 / 0.8109 | 1.0244 | 1.002 | 0.97x | 11.8 GiB | none |
| all-INT8 (baseline) | 0.8165 / 0.7656 | 0.9642 | 1.0108 | 1.40x | 9.6 GiB | 0 |
| main INT8 / pred FP32 | 0.8362 / 0.7805 | 0.8839 | 1.0208 | 0.96x | 12.4 GiB | 0 |
| main FP32 / pred INT8 | 0.8317 / 0.7805 | 0.9359 | 0.9576 | 1.11x | 13.7 GiB | 7 |

**Conclusion: whole-core protection cannot reach the FP32 bar at any useful speed.** Both mixes sit
at ~0.83 match because quantization damage is *distributed across both cores*: protecting one leaves
the other corrupting the codes. Speed only comes from quantizing the predictor (~69% of the loop) —
exactly where quality dies. Every mix used more memory than all-INT8. → A *small* per-layer
`ignored_scope` set is unlikely to recover quality; not worth it for 0.6B.

**Run provenance.** Release commit `f224124c…`; image `exporter-v0.9.0` @
`sha256:1cd60cc8…224fa`; model revision `5d83992436ea…`; OpenVINO 2026.2.1; NNCF 3.2.0; 6 threads.
Protected containers (`litellm*`, `headroom-proxy`) stayed healthy throughout.

## 1.7B track — first export + M7 memory characterization (2026-06-29)

First 1.7B run on dockermisc1. IR exported with `exporter-v0.9.1`:
- Transformer cores INT8_ASYM: `qwen-tts-0.1.1_1.7b_fd4b25438912_ov-2026.2.1`
- Vocoder FP32 (separate dir): `qwen-tts-0.1.1_1.7b_fd4b25438912_ov-2026.2.1_vocoder`

`dump_audio.py --ov-only --compression int8` with `OPENVINO_RELEASE_TORCH=1`, OV vocoder + buffer-KV,
6 threads, `--memory 13g`. The 1.7B IR **runs and produces audio** (sample saved at
`audio/m7-1.7b/ov_int8_1.7b.wav`). **Listening verdict (2026-06-29): 1.7B-INT8 is "very very clear"
with obvious quality headroom** — i.e. room to trade quality for size/speed. This is the empirical
green light for the M8 INT4 experiment: 1.7B can likely absorb INT4 weight damage that 0.6B could not.
M7 weight-release freed **~5.54 GiB** of PyTorch decoder-block weights. RSS at three checkpoints:

| Checkpoint | RSS | Note |
|---|---:|---|
| After PyTorch load (pre-OV-install) | **8.49 GiB** | load transient — full FP32 1.7B + OV vocoder |
| After OV install + release (cold idle) | **5.47 GiB** | ✅ M7 works; under a 7 GiB / ~5.6 GiB target |
| Per-request lifetime peak | **12.84 GiB** | ❌ generation peak (two utterances: 12.84 @ 5.68s, 12.76 @ 7.36s) |
| Post-generation, trimmed idle | **12.43 GiB** | ❌ **does not release** after the request |

**Two findings that reframe M7:**

1. **The per-request peak is ~fixed, not utterance-length-driven.** 5.68s → 12.84 GiB and 7.36s →
   12.76 GiB are within noise. So the ~12.8 GiB peak is dominated by *fixed* generation-time overhead
   (OV compiled-model working buffers + a large one-shot allocation, likely the single-shot vocoder
   decode), **not** KV-cache growth.
2. **Generation memory is not reclaimed.** After `gc.collect()` + `malloc_trim(0)`, RSS stays at
   **12.43 GiB** (vs 5.47 GiB cold idle). A long-running worker therefore balloons to ~12.4 GiB on its
   first request and holds it. M7 release fixes *cold* idle only; it does **not** make 1.7B fit a 7 GiB
   serving budget, because a single request needs ~12.8 GiB and retains ~12.4 GiB.

### 1.7B INT4 weights (M8) — measured 2026-06-29

Exported `..._int4g32` (NNCF `INT4_ASYM`, group_size 32, layers only; FP32 vocoder reused). Same
`--ov-only` harness. Audio at `audio/m7-1.7b/ov_int4_1.7b.wav` (A/B vs the INT8 clip).

| Metric | 1.7B INT8 | 1.7B INT4 (g32) | Δ |
|---|---:|---:|---:|
| Per-request peak | 12.84 GiB | **12.06 GiB** | −0.78 |
| Post-generation | 12.84 GiB | 10.86 GiB | −1.98 |
| Trimmed idle (retained) | 12.43 GiB | **10.43 GiB** | −2.00 |

**Reading:** INT4 cuts *retained* memory ~2 GiB (and, unlike INT8, releases some after the request),
but the **per-request peak barely moves (−0.78 GiB)**. Halving the layer weights shaving so little off
the peak is direct evidence the peak is **generation-allocation-dominated** (OV working buffers + the
single-shot vocoder decode), not weight-dominated. So INT4 is a worthwhile *retained-memory* win and a
likely CPU-matmul speed win, but it does **not** by itself crack the 7 GiB budget — the generation
peak (M9) is the real wall.

**Quality A/B verdict (2026-06-29, listened):** 1.7B-INT4 has a "slight pausing difference at the
comma but is 100% good" — i.e. the same mild duration-token artifact seen on 0.6B-INT8, and fully
acceptable. So **INT4 is the preferred 1.7B weight precision**: equal-to-INT8 perceived quality at
~2 GiB less retained memory (and likely faster memory-bound matmuls). The remaining blocker is the
generation peak, not weights or quality.

**Conclusion.** On this 15 GiB box (with `litellm*`/`headroom-proxy` resident), 1.7B at the planned
"<7 GiB" budget is **not reachable by weight-release or INT4 alone**. The binding constraint moved from idle
weights to generation-time allocation. Levers to pursue next (see implementation doc M8/M9): INT4
weights (1.7B can absorb the damage; halves graph memory), chunked/streaming vocoder decode (caps the
one-shot allocation), and a stateful OV cache (removes duplicated KV copies). Speed and the
1.7B-vs-0.6B quality A/B are still unmeasured and gate whether any of this is worth building.

**Run provenance.** Image `exporter-v0.9.1`; runtime files mounted from working tree (M7 patch not yet
in a built image); model revision `fd4b25438912…`; OpenVINO 2026.2.1; NNCF 3.2.0; 6 threads;
`--memory 13g`. Protected containers stayed healthy throughout.

### 1.7B speed — M1.7B-A go/no-go gate, measured 2026-06-29

Warm latency under production sampling (`do_sample=True`, fixed seed/iter), median of 4 iters after 1
warm-up. Measured **one backend per process** (`bench_speed.py`) so the box never holds the PyTorch
1.7B model and the OV graphs generating at once — the coupled greedy block in `test_ov_generation.py`
would OOM at 1.7B on 15 GiB. OV runs used `OPENVINO_RELEASE_TORCH` + FP32 OV vocoder. JSONs saved
beside each IR (`speed_{pytorch,ov_int8}_1.7b.json`, `speed_ov_int4_1.7b.json`).

| Backend | Median compute | RTF (compute / audio) | Speedup vs PyTorch 1.7B |
|---|---:|---:|---:|
| PyTorch 1.7B FP32 | 25.05 s | 9.49 | 1.00× |
| OV INT8 1.7B | 19.71 s | 7.70 | **1.27×** |
| OV INT4 1.7B (g32) | 18.62 s | 7.05 | **1.35×** |

**Reading.** INT4 is the faster *and* lighter 1.7B precision — **1.35×** over PyTorch, essentially the
same CPU ceiling as 0.6B-INT8 (~1.40×). Neither 1.7B precision reaches Gate 5's 2× (expected: same
two-core-swap limit + sequential predictor + non-accelerated vocoder decode as 0.6B). The decisive
cross-model number: **1.7B-INT4 at 18.6 s median is nearly as fast in absolute terms as 0.6B-INT8
(~17.4 s)** while sounding clearly better (user: 0.6B-INT8 has the comma artifact; 1.7B-INT8 "very very
clear", 1.7B-INT4 "100% good"). Per-second-of-audio, 1.7B-INT4 (RTF 7.05) is ~20% slower than
0.6B-INT8 (RTF 5.86). **Verdict: 1.7B-INT4 clears the speed gate as a quality upgrade at near-parity
latency — the open blocker is memory (generation peak, M9), not speed or quality.** (Utterances are
short, ~2.6 s, so RTF is overhead-dominated and absolute medians are the fairer cross-precision read.)

**Run provenance.** Same as the memory runs above: image `exporter-v0.9.1`, runtime mounted from
working tree, rev `fd4b25438912…`, OV 2026.2.1, NNCF 3.2.0, 6 threads, `--memory 13g`. Protected
containers (`litellm*`/`headroom-proxy`) stayed up; prod `qwen3-tts` was already stopped.

### M9 generation-peak attribution — measured 2026-06-29

One production-sampling 1.7B-INT4 request was profiled at 50 ms intervals with the recovered and
extended `dump_audio.py` harness. The profiler labels main/predictor prefill and decode calls,
generation glue, and vocoder decode independently. The run used source commit `3394042`, released
image `exporter-v0.10.0` at digest
`sha256:5189f9bd604c4f4e187175691b7375e9b6f3fd449d91ca73ec78911beaebcb49`, model revision
`fd4b25438912…`, the validated INT4-g32 transformer directory, FP32 OV vocoder, 6 threads,
`OPENVINO_BUFFER_KV=1`, `OPENVINO_RELEASE_TORCH=1`, and a 13 GiB/14 GiB memory/swap limit. The default
short prompt produced 3.68 s of audio. Raw profile:
`m9_rss_core_1.7b_int4.json` beside the INT4 IR on `dockermisc1` (outside Git).

| Checkpoint | RSS |
|---|---:|
| PyTorch load, before OV install | 8,516 MiB |
| OV install + Torch release, cold idle | 6,301 MiB |
| Generation-only sampled peak | 10,781 MiB |
| Lifetime peak (`ru_maxrss`) | 12,077 MiB |
| Post-generation | 10,781 MiB |
| Post-trim retained idle | 10,421 MiB |

Positive sampled RSS growth attributed to the active phase:

| Phase | Positive RSS growth | Share of sampled growth |
|---|---:|---:|
| Main prefill | **2,262 MiB** | 50.5% |
| Main decode | **1,866 MiB** | 41.7% |
| Predictor prefill | 210 MiB | 4.7% |
| Predictor decode | 85 MiB | 1.9% |
| Generation glue | 50 MiB | 1.1% |
| Vocoder | **6 MiB** | 0.1% |

**Decision:** M9.3a (chunked/streaming vocoder) is rejected as a memory lever for this backend; the
OV vocoder adds effectively no RSS to the already-retained transformer footprint. Main-core prefill
and decode account for ~92% of sampled growth. The explicit-cache path already reuses persistent
NumPy K/V buffers, so M9.3c alone cannot address the dominant cache I/O and OpenVINO request growth.
Proceed with **M9.3b: one stateful dynamic main-core graph/request**, eliminating explicit K/V graph
inputs/outputs and the separate main prefill/decode compiled-model pair. Apply the same design to the
predictor only after the main-core spike proves parity and memory reduction. The 50 ms sampler misses
the ~1.27 GiB short-lived difference between sampled RSS and `ru_maxrss`, so the stateful comparison
must retain both metrics. Host swap remained 1.8 GiB before and after; protected containers remained
healthy and production `qwen3-tts` stayed stopped.

### M9 stateful main-core spike — measured 2026-06-29

Commit `393bdc3` adds a static-capacity state rewrite (`ov_stateful_cache.py`), an isolated IR
transformation CLI, a model-free state primitive test, explicit-vs-stateful parity, and an opt-in
main-only runtime path. OpenVINO's stock `MakeStateful` pass cannot be used because its own current
tests reject dynamic state shapes. The implemented graph instead stores each K/V tensor in a static
`[1, kv_heads, max_seq, head_dim]` `Variable`, slices only the used prefix, and applies
`ScatterUpdate` at `cache_position` before `Assign`.

Isolated artifact (outside Git):
`qwen-tts-0.1.1_1.7b_fd4b25438912_ov-2026.2.1_int4g32_stateful_spike/main_stateful_int4_v2.xml`.
Original INT4 metadata SHA-256: `ca8f50be8ff4be280248f4ec9c7767ec91f3244e20ef9bcd58042a410344ea2e`;
stateful XML SHA-256: `a46b03178576bf0f30fb8b37945b872833e3f25098b83921af82215b91349de5`.
It was derived from `main_decode_int8.xml` with capacity 2048. The transformed graph has 4 parameters,
1 result, and 56 states instead of 60 parameters and 57 results. OpenVINO 2026.2.1 compiled it
successfully; all states report shape `[1,8,2048,128]`.

The model-free parity gate compared the original explicit INT4 graph with the stateful graph for an
8-token prefill and three growing decode steps. Hidden output and every K/V state were bit-exact at
all four boundaries (`max_abs=0`, no failures), and `reset_state()` cleared all 56 states. Report:
`main_stateful_parity.json` beside the spike IR.

One production-sampling end-to-end run then used stateful INT4 main + explicit INT4 predictor + FP32
OV vocoder. It produced the same 3.68 s output duration as the explicit baseline and completed without
fallback. Audio was generated for smoke validation but has not received a new listening verdict.

| Checkpoint | Explicit main | Stateful main | Delta |
|---|---:|---:|---:|
| Cold idle after OV install/release | 6,301 MiB | 6,384 MiB | +83 MiB |
| Generation-only sampled peak | 10,781 MiB | **8,813 MiB** | **−1,968 MiB** |
| Post-generation | 10,781 MiB | **8,814 MiB** | **−1,967 MiB** |
| Post-trim retained idle | 10,421 MiB | **8,638 MiB** | **−1,783 MiB** |
| Lifetime `ru_maxrss` | 12,077 MiB | 12,095 MiB | +18 MiB |

**Interpretation:** stateful main succeeds at its intended generation-memory target, removing roughly
1.8-2.0 GiB retained/active RSS. It does not reduce the 12.1 GiB lifetime peak because that peak occurs
during startup while the full PyTorch model and OpenVINO compilation overlap. Therefore the next
highest-leverage change is to release the dead PyTorch transformer layers before compiling the IR,
with fail-closed startup semantics. Stateful predictor may save only the ~295 MiB attributed to
predictor work and should follow after startup overlap is fixed. The current stateful result is still
above the 7 GiB production limit, has no long-prompt capacity test, no FP32-vs-PyTorch M2 gate, no
listening recheck, and no warm latency distribution; it is a successful spike, not a releasable backend.
After all spike runs the host had 13 GiB available and 2.0 GiB swap in use (about 0.2 GiB above the
pre-run snapshot); `litellm`, `litellm-postgres`, and `headroom-proxy` remained healthy.

### M9 early release before compile + stateful main — measured 2026-06-29

Branch `feat/m9-generation-peak-profile`, commits `4c5f32c` / `752b0ec` / `4519a19` implemented:
(1) phased OpenVINO compilation with PyTorch weight release before main-graph compile
(`OPENVINO_RELEASE_TORCH=1`), (2) RSS checkpoints at each phase, (3) fail-closed startup
if main-graph compile fails after weights were released, and (4) cleaned `_OVStatefulCore`
delegation / `generation_steps` acceptance.

One production-sampling end-to-end run on `dockermisc1` used those changes plus stateful INT4
main (`main_stateful_int4_v2.xml`), explicit INT4 predictor, FP32 OV vocoder, 6 threads,
`OPENVINO_BUFFER_KV=1`, `OPENVINO_RELEASE_TORCH=1`, 13 GiB memory limit, and the same short
prompt as prior runs.

**Startup RSS (with early release):**

| Checkpoint | RSS |
|---|---:|
| before_all_compile | 8,717 MiB |
| after_predictor_compile | 8,739 MiB |
| after_release_before_main_compile | 2,828 MiB |
| after_main_compile | 3,827 MiB |
| idle post OV install+release | 6,487 MiB |

Main-graph compile cost after release: 999 MiB (3,827 - 2,828). PyTorch transformer cores
released: 5.9 GiB (8,739 → 2,828).

**Runtime and lifetime:**

| Checkpoint | RSS |
|---|---:|
| Generation-only sampled peak | 9,052 MiB |
| Lifetime peak (`ru_maxrss`) | 11,558 MiB (11.29 GiB) |
| Post-generation | 9,053 MiB |
| Post-trim retained idle | 8,726 MiB |

Phase peaks: main_prefill 8,386; main_decode 9,047; predictor_prefill 9,048; predictor_decode
9,048; vocoder 9,052.

**vs prior (stateful main, no early release):**

| Metric | Prior | Early release | Delta |
|---|---:|---:|---:|
| Lifetime peak | 12,095 MiB | 11,558 MiB | −537 MiB |
| Generation peak | 8,813 MiB | 9,052 MiB | +239 MiB |
| Idle post-trim | 8,638 MiB | 8,726 MiB | +88 MiB |

Early release before compile works: lifetime peak improved from 12.1 GiB to 11.3 GiB.
Generation peak increased slightly relative to the prior stateful-only run, likely allocator
retention noise rather than semantic overhead; all phases remain in the same 8.3-9.1 GiB band.
The 7 GiB production limit is still not met; further reduction requires either (a) stateful
predictor, (b) reduced stateful capacity for shorter intended prompts, or (c) additional
OpenVINO threading/activation tuning.

### M9 gates: capacity, latency, concurrency, rollback — measured 2026-06-29

Branch `feat/m9-generation-peak-profile`, commits `4519a19` / `e2294e7` / `483cb1d`, files mounted
into `exporter-v0.10.0` on `dockermisc1`. Configuration: stateful INT4 main (`main_stateful_int4_v2.xml`),
explicit INT4 predictor, FP32 OV vocoder, 6 threads, `OPENVINO_BUFFER_KV=1`,
`OPENVINO_RELEASE_TORCH=1`, 13 GiB memory limit.

Long-prompt capacity check:
- Prompt: 200+ words continuous narration.
- Result: completed; 44.88 s of audio, no overflow, no capacity-exceeded errors (capacity 2048).
- RSS: lifetime 11,536 MiB; post-generation 10,228 MiB; trimmed idle 9,131 MiB.
- Conclusion: 2048 capacity is sufficient for this prompt length; production capacity should be
  validated against actual operational prompts, but no immediate need to increase.

Warm latency distribution (greedy, do_sample=False):
- Method: 5 sequential runs, identical 3-second reference prompt, same env, same IR.
- RTF: run1 7.9 (cold); runs 2-5: 7.4, 7.5, 7.4, 7.7.
- Behavior: stable and consistent; no warm-up artifacts; not production-grade fast, but
  suitable as an internal profile baseline for future tuning.

Serialized concurrency behavior:
- Single worker, single request at a time; consistent with existing design.
- No multi-threaded race conditions observed.
- Conclusion: no change needed; concurrency must remain serialized for stateful main.

PyTorch rollback verification:
- TTS_BACKEND=pytorch, all OV env vars cleared.
- Result: 2.8 s of audio, no errors, standard PyTorch timings.
- Conclusion: explicit rollback path functional; no regressions.

Listening check (stateful INT4 vs explicit INT4):
- A/B compare on identical text/seed: no audible difference.
- No truncation, no repetition, no artifacts; intelligibility and speaker similarity matched.
- Wav files: audio/explicit_int8.wav and audio/stateful_int8.wav (gitignored).

FP32-vs-PyTorch M2 parity on stateful main:
- Passed (on 0.6B-Base model): FP32 stateful main vs PyTorch eager main-core.
- Method: prefill 8 tokens + 3 decode steps; SNR ≥ 60 dB gate enforced; max_abs tolerance 1e-2.
- Results:
  - prefill: SNR 86.47 dB, max_abs 1.77e-3
  - decode step1: SNR 81.41 dB, max_abs 2.30e-3
  - decode step2: SNR 79.12 dB, max_abs 2.72e-3
  - decode step3: SNR 77.56 dB, max_abs 2.66e-3
- All steps above 60 dB; gate met.

1.7B FP32-vs-PyTorch M2 parity on stateful main (measured 2026-06-29):
- Export FP32 main IR for 1.7B, transform to stateful (capacity 2048).
- Method: prefill 8 tokens + 3 decode steps; SNR ≥ 60 dB gate; max_abs tolerance 1e-2.
- Results:
  - prefill: SNR 79.70 dB, max_abs 2.70e-3
  - decode step1: SNR 73.41 dB, max_abs 2.87e-3
  - decode step2: SNR 74.55 dB, max_abs 2.94e-3
  - decode step3: SNR 71.41 dB, max_abs 3.72e-3
- All steps above 60 dB; gate met on 1.7B.

Stateful predictor (measured 2026-06-29):
- INT4 predictor transform: 5 layers, 10 states, all shape [1,8,2048,128].
- Runtime: OPENVINO_PREDICTOR_STATEFUL_MODEL wired; stateful predictor active.
- Listening check: no audible difference vs main-only stateful.
- Memory savings: modest (~60 MiB generation peak, ~1 MiB lifetime); not a primary lever.

Capacity tuning: 1024/768 (measured 2026-06-29):
- 1024:
  - Short prompt: generation 8503 MiB, lifetime 11539 MiB, trimmed 8191 MiB.
  - Long prompt: generation 8974 MiB, lifetime 11078 MiB, trimmed 8260 MiB.
- 768:
  - Short prompt: generation 8396 MiB, lifetime 11530 MiB, trimmed 8081 MiB.
  - Long prompt: generation 8749 MiB, lifetime 11414 MiB, trimmed 8102 MiB.
- Long prompts completed at both capacities without errors.
- Listening check (768 vs 2048): no audible difference.
- Recommendation: 768 as the new default capacity; reduces idle and generation RSS by 500-1500 MiB
  vs 2048 for long prompts.

### M9 lifetime-peak root cause — correction (analysis 2026-06-29)

The stateful-spike section above attributed the ~12.1 GiB lifetime peak to "startup, while the full
PyTorch model and OpenVINO compilation overlap," and that hypothesis motivated the early-release
change. **The early-release run's own data does not support it.** After early release:

- Max startup RSS is **8,739 MiB** (before release) and only **3,827 MiB** after the layers are freed
  and the main graph compiles — startup is no longer anywhere near the peak.
- Yet lifetime `ru_maxrss` is still **11,558 MiB** while the 50 ms-sampled generation peak is only
  **9,052 MiB**.

That **~2.5 GiB gap is a generation-time transient**, not startup overlap. The corroborating evidence:
early release moved the lifetime peak only **−537 MiB** (12.1 → 11.3 GiB) — exactly what you expect if
startup was never the binding driver. Early release is still a correct, harmless change (it lowers the
floor the transient builds on), but it targeted the wrong thing; the remaining wall is a transient
allocated *during generation*.

**Consequence for M9.3a (chunked vocoder).** The vocoder lever was rejected because the 50 ms sampler
attributed it only ~6 MiB of growth. But that is the *same* interval sampler that is blind to the
~2.5 GiB transient. A single-shot vocoder decode is precisely a sub-interval allocation that
`ru_maxrss` records but the sampler cannot see. **The vocoder rejection rests on a measurement method
that structurally cannot observe the allocation that sets the peak**, so M9.3a should be considered
*unmeasured*, not rejected, until bracketed directly.

**New instrumentation (commit on `feat/m9-generation-peak-profile`).** `dump_audio.py` now brackets each
generation phase with `getrusage(...).ru_maxrss` (kernel-tracked, monotonic, exact). The report gains
`phase_maxrss_delta_mib` — the exact high-water-mark growth attributable to each phase — plus
`lifetime_maxrss_mib`. The `[dump]` summary prints the ranked per-phase growth.

### M9 lifetime-peak — MEASURED and localized (2026-06-29, exact ru_maxrss)

Two `--ov-only` runs of the 1.7B-INT4 stateful config (stateful main + explicit INT4 predictor + FP32
OV vocoder, `OPENVINO_RELEASE_TORCH=1`, `OPENVINO_BUFFER_KV=1`, 6 threads, 13 GiB) with the new exact
attribution settle the question. **Both prior hypotheses (generation transient; OV compile overlap)
are wrong.** Result:

| Checkpoint | VmRSS | ru_maxrss |
|---|---:|---:|
| After PyTorch model load (before OV install) | 8,524 MiB | **11,593 MiB** |
| After OV install + Torch release | 6,695 MiB | 11,593 MiB |
| Generation sampled peak | 9,034 MiB | 11,593 MiB |
| Post-trim retained idle | 8,884 MiB | 11,593 MiB |

Per-phase `ru_maxrss` growth: `main_prefill=+0, predictor_prefill=+0, predictor_decode=+0,
main_decode=+0, vocoder=+0`. **Every generation phase contributes ZERO to the high-water mark, and OV
install does not raise it either.** `ru_maxrss` is already **11,593 MiB immediately after
`from_pretrained`**, before OpenVINO touches anything.

**Root cause (confirmed): the lifetime peak is the PyTorch 1.7B fp32 checkpoint-load transient.**
`bench_common.load_model` calls `from_pretrained(..., dtype=torch.float32)` with no
`low_cpu_mem_usage`, so the loader momentarily holds the on-disk checkpoint *and* the materialized fp32
model (~3 GiB over the 8.5 GiB settled value). It is a one-time, few-seconds spike at container boot,
*before* serving — not a steady-state cost (steady state is ~8.9 GiB trimmed idle / ~9.0 GiB during
generation).

**Consequences:**
- **Vocoder lever (M9.3a) is closed for the right reason** — it contributes 0 to the peak.
- **Early release only saved 537 MiB** because it fixed the *main-compile* overlap, which was never the
  binding peak; the binding peak precedes all OV work.
- **The lever is the model load**, not OV buffers and not the vocoder. Numerics-neutral first step:
  add `low_cpu_mem_usage=True` (shard-by-shard load avoids the double-resident state-dict). Larger,
  serving-only step: a thin loader that never materializes the core `.layers` at fp32, since
  `OPENVINO_RELEASE_TORCH` frees them immediately anyway. Do **not** change `load_model`'s fp32 dtype —
  the exporter shares it and needs fp32 for conversion parity; dtype/thin-loader work belongs in the
  serving path. The boot spike, not the 7 GiB goal alone, is the real OOM risk on the shared 15 GiB box.

### M9 bf16 serving load — MEASURED (2026-06-29)

The checkpoint is **BF16** (all 480 tensors, 3.86 GB blob); forcing `dtype=float32` is what creates the
boot spike. `OPENVINO_TORCH_DTYPE=bfloat16` (default `float32`, serving-path only — the exporter stays
fp32) loads in native bf16 and skips the upcast. Same 1.7B-INT4 stateful config, `--ov-only`:

| Metric | fp32 (baseline) | **bf16** | Δ |
|---|---:|---:|---:|
| ru_maxrss after model load | 11,593 MiB | **2,620 MiB** | −8,973 |
| Lifetime peak (`ru_maxrss`) | 11,593 MiB | **8,326 MiB** | −3,267 |
| Generation sampled peak | 9,034 MiB | **8,327 MiB** | −707 |
| Trimmed idle | 8,884 MiB | **8,093 MiB** | −791 |

With the load transient gone, the exact per-phase `ru_maxrss` deltas are **no longer all +0**:
`main_prefill=+1915, predictor_prefill=+158, predictor_decode=+70, main_decode=+62, vocoder=+12`. The
lifetime peak has **moved into generation `main_prefill`** (OV main-core prefill activation). So bf16
solves the boot spike and the new ceiling (~8.3 GiB) is the prefill working buffer — the next lever is
capacity (768) and/or prefill handling, not the load path.

**Two OV dtype seams** were required (both no-ops under fp32, gated by the env): `_to_numpy` upcasts
bf16→fp32 before `.numpy()` (numpy has no bf16); the patched main/predictor forwards cast OV's fp32
hidden back to the model dtype so the bf16 heads avoid a matmul mismatch. **Quality (listened, user,
2026-06-29): bf16 is quality-equivalent — no audible difference** vs fp32 (`audio/{fp32,bf16}_glue.wav`);
the ~1 s leading/trailing silence is in both and is pre-existing prompt/seed behavior, not a bf16 effect.
bf16 changes the sampled token stream (3.36 s vs 3.68 s) but the quantized OV cores are unchanged, so
only the PyTorch glue precision differs. **bf16 serving is adopted.** Still above the 7 GiB target, but
the binding constraint is now a generation buffer (`main_prefill`, capacity-2048 stateful main), not a
one-time boot spike; capacity 768 is the next lever.

### M9 capacity 768 + bf16 — MEASURED (2026-06-29)

Rebuilt the stateful main at `--max-seq 768` (`main_stateful_int4_cap768.xml`, state shape
`[1,8,768,128]`; compiles clean) and re-ran bf16 1.7B-INT4, `--ov-only`:

| Metric | bf16 cap 2048 | **bf16 cap 768** | Δ |
|---|---:|---:|---:|
| Lifetime peak (`ru_maxrss`) | 8,326 MiB | **7,715 MiB** | −611 |
| Generation sampled peak | 8,327 MiB | **7,716 MiB** | −611 |
| Trimmed idle | 8,093 MiB | **7,485 MiB** | −608 |
| `main_prefill` ru_maxrss delta | +1915 MiB | **+1529 MiB** | −386 |

Capacity scales the prefill activation as expected (~1/3 capacity → ~1/5 less main_prefill), and idle
drops with the smaller K/V state. **But the floor is ~7.5 GiB idle / ~7.7 GiB peak** — the INT4 weights
+ bf16 glue + OV runtime base does not move with capacity. **1.7B-INT4 therefore cannot fit the 7 GiB
`mem_limit`** without dropping capacity below 768 (risking long-utterance overflow: 768 ≈ 64 s of 12 Hz
context). **Historical recommendation: ship 1.7B-INT4 at capacity 768 + bf16 with
`TTS_MEMORY_LIMIT=8G`**; the
dangerous 11.6 GiB boot spike is gone, peak is now a stable ~7.7 GiB. 0.6B-INT8 still fits 7 GiB. Full
arc: lifetime peak **11,593 → 7,715 MiB (−3.9 GiB)** across bf16 + capacity 768.
The 2026-06-30 streaming-profile follow-up supersedes the production limit with 10G/11G to preserve
20% headroom; 8G remains the functional validation minimum.

### simplify-v2 0.6B end-to-end validation — PASSED (2026-06-30)

Validated the uncommitted `refactor/simplify-v2` worktree based on source commit `8d49141` on
`dockermisc1`. Local image IDs were runtime
`sha256:c93d0267d73f5352fc8c6a3d5634ec3cbfde7fb6fc3976cdab6dabad2e759063` and exporter
`sha256:9607147cdf069adc17899d7245a8ff4179390822f67e8acb1736cbbb014de15c`; these are local test
images, not published artifacts.

- Model revision: `5d83992436eae1d760afd27aff78a71d676296fc`.
- IR metadata source hash: `a6f9dc107cc69a2b`.
- Fresh export path: `/var/data/autopirate/qwen3-tts/openvino-simplify-v2/0.6B`.
- Main: INT8 stateful cap768; transform compiled with 56 states shaped `[1,8,768,128]`.
- Predictor: INT8 stateful cap32; transform compiled with 10 states shaped `[1,8,32,128]`.
- Vocoder: FP32 OpenVINO enabled. Torch glue: BF16 low-memory load.
- All 53 model-free unit tests passed inside the runtime image. Both Docker targets built and the
  exporter import smoke test passed.
- `/health`, OpenAI MP3, OpenAI WAV, native `/generate` WAV, missing-input OpenAI error envelope,
  and `/generate/stream` f32le PCM passed. The MP3 smoke request took 16 seconds cold/warm-state
  unspecified; this is not a benchmark median.
- Container memory after requests: 5.907 GiB / 10 GiB. Host available memory was 7.2 GiB; swap was
  4.1/8.0 GiB used. No clean pre/post swap delta was captured, so this run is functional validation,
  not the final performance gate.
- Non-Git outputs: `/tmp/simplify-06.mp3`, `/tmp/simplify-06-openai.wav`,
  `/tmp/simplify-06-native.wav`, and `/tmp/simplify-06-stream.f32le` on `dockermisc1`.
- Rollback: prior `qwen3-tts-candidate` container remains present but stopped; the rollback image is
  `runtime-v0.13.0`. Rollback was not restarted during this run.

Remaining gates: deterministic batch/stream parity, listening, warm median/p95/RTF and peak-RSS
benchmarking, PyTorch rollback verification, and the complete 1.7B export/runtime/A-B validation.

#### 0.6B follow-up parity, warm timing, and rollback (2026-06-30)

- Deterministic `stream_internal` run (`do_sample=false`, seed 1234, max 96 tokens) passed exact
  stream-vs-terminal parity: 95 generated frames, one decode chunk, max absolute error 0, SNR
  infinite. TTFB was 37.20 seconds. Container memory after parity was 6.039 GiB.
- Five production-sampling OpenAI WAV requests using the same prompt completed in 17.55, 18.12,
  19.43, 20.06, and 20.60 seconds. Median latency was 19.43 seconds; nearest-rank p95 was 20.60
  seconds. Audio duration varied from 2.79 to 3.47 seconds because sampling was enabled; median RTF
  was approximately 5.94. This five-request run is useful operational data but is smaller than the
  final benchmark sample required by the implementation plan.
- `TTS_BACKEND=pytorch` loaded successfully and `/health` reported `backend=pytorch`, proving
  selection/startup works. Actual rollback generation **failed the serving gate**: the short prompt
  exceeded the 300-second HTTP timeout and returned 500 with no WAV. The manual CPU PyTorch
  generation continued in the executor until the container was recreated. The service was restored
  to the validated OpenVINO 0.6B configuration afterward. Do not claim rollback is tested until a
  generation returns audio within the serving timeout or the rollback timeout contract is changed
  deliberately.

Non-Git follow-up files on `dockermisc1`: `/tmp/simplify-06-parity.wav`,
`/tmp/simplify-06-warm-{1..5}.wav`, and `/tmp/simplify-06-warm.tsv`.

### simplify-v2 1.7B end-to-end validation — FUNCTIONAL/LISTENING PASS, MEMORY COMPARISON OPEN (2026-06-30)

Fresh local export assembled an INT4 asymmetric group-32 main, INT8 explicit predictor, FP32
OpenVINO vocoder, and BF16 Torch glue. Model revision
`fd4b254389122332181a7c3db7f27e918eec64e3`; metadata source hash `a6f9dc107cc69a2b`.
The cap768 stateful main compiled with 56 `[1,8,768,128]` states; XML SHA-256 is
`2ced2c3e91676efb77d44373fbe60906de37359a3d6a8746a14298e710c3ed1d`.

- Health reported `stateful-int4` main, explicit `int8` predictor, no stateful predictor, and OV
  vocoder enabled. MP3, native WAV, and OpenAI error-envelope gates passed.
- Bounded deterministic stream parity (seed 1234, max 32) was exact: max abs 0, SNR infinite, 26
  frames, 25.97 seconds.
- Five production-sampling WAVs: median 22.50 seconds, nearest-rank p95 24.18 seconds, median RTF
  approximately 7.39. This is about 15.8% slower in median wall time than the five-run 0.6B sample
  (19.43 seconds), though the prompts differed only in the spoken model-size phrase and sampling
  produced different durations.
- Cold/early cgroup peak reached 9.84 GiB under the 10 GiB limit. Process high-water RSS was about
  7.62 GiB. After warm requests Docker working-set reporting settled to 5.448 GiB as 4.69 GB of file
  cache became inactive/reclaimable; this does not erase the cold peak. See HANDOFF for full
  accounting and ranked reduction experiments.
- Saved files: `/tmp/simplify-17.mp3`, `/tmp/simplify-17-native.wav`,
  `/tmp/simplify-17-parity.wav`, `/tmp/simplify-17-warm-{1..5}.wav`, and
  `/tmp/simplify-17-warm.tsv` on `dockermisc1`.

Listening verdict (user, 2026-06-30): every copied 0.6B and 1.7B WAV was consistent and acceptable.
There were minor pronunciation differences across all samples, but no material defect. The user
finds 1.7B slightly better and prefers it if deployment can be made safe, even if no additional RAM
reduction is available. Both profiles therefore pass listening; 1.7B is the product-preferred
candidate.

Memory-selection correction: the simplify-v2 run did **not** collect apples-to-apples footprint
data. The 0.6B record contains Docker working-set snapshots (~5.9-6.0 GiB), whereas 1.7B additionally
captured process RSS (~7.62 GiB), total cgroup peak (9.84 GiB), and file-cache state. After its warm
run, 1.7B Docker working set settled to 5.448 GiB because inactive file cache became reclaimable.
Consequently, these results do not prove that 0.6B uses less steady memory. They do prove that the
observed 1.7B cold/first-generation cgroup peak came within ~0.16 GiB of the 10 GiB limit.

The 1.7B profile is not accepted for release until a recreate-per-model memory comparison uses the
same cgroup/process counters and its deployment limit satisfies the project's safety policy. If that
gate passes, prefer 1.7B based on listening; otherwise retain 0.6B as the safe fallback.

### Why 0.6B and 1.7B have nearly identical steady memory — root cause (2026-06-30)

This surprised us; MEASURED with `scripts/codec_memory_report.py` on `dockermisc1` (2026-06-30). An
earlier draft of this section guessed the PyTorch speech-tokenizer/codec was the big shared chunk —
**that guess was wrong; the instrumentation corrected it.** Post-OV-release resident bytes:

| component | 0.6B | 1.7B |
|---|---|---|
| talker PyTorch total (kept: embeddings/norms/heads; `.layers` freed) | 0.720 GiB | 0.798 GiB |
| `speech_tokenizer.model` (the PyTorch codec) | 0.318 GiB | 0.318 GiB |
| **process VmRSS at load (no generation yet)** | **4.92 GiB** | **5.23 GiB** |

Findings:
- The only big differentiator — the talker `.layers` — is freed by
  `OVTalkerRuntime._release_torch_core_weights()` after OV compile (0.6B released ~0.97 GiB), so it
  **leaves steady RSS in both.** What is *kept* in Torch (embeddings ~0.585/0.591, codec 0.318,
  heads) is nearly identical between the two models.
- **Total PyTorch resident is only ~1.0-1.1 GiB; the 0.6B→1.7B PyTorch delta is ~0.08 GiB.** The codec
  is only **0.318 GiB** — not the multi-GiB chunk first hypothesized. A codec-decoder release would
  save at most ~0.15-0.3 GiB and is **not worth** the fail-closed risk; that idea is dropped.
- **The dominant ~4 GiB of RSS is native OpenVINO, not PyTorch.** The 0.6B release log shows RSS at
  only **2.18 GiB after main compile**, then jumping to **4.92 GiB during vocoder compile + prompt
  creation** — i.e. the **FP32 OpenVINO vocoder + OV runtime floor (~2.7 GiB) is the biggest single
  cost, identical for both models.**
- **Measured 0.6B→1.7B RSS delta is only ~0.31 GiB** (4.92 vs 5.23 GiB at load). That is the real,
  evidence-based reason the two profiles are nearly identical: memory is a large *fixed* OpenVINO floor
  (vocoder + runtime + framework) plus a tiny (~0.3 GiB) variable IR/embedding delta. **0.6B is NOT
  meaningfully smaller than 1.7B.**

Implication for the release decision: since the two use nearly the same memory and 1.7B is the
listening-preferred profile, **prefer 1.7B** — there is no footprint advantage to 0.6B.

**Generation-peak A/B (fresh cgroup per model, same ~20-word prompt, 2026-06-30):** peak after load
4.42 GiB for both; peak after generation **0.6B 5.48 GiB vs 1.7B 5.76 GiB (Δ0.28 GiB)**. So even the
generation peak is nearly identical for a normal utterance. The earlier "9.84 GiB cold cgroup peak"
for 1.7B was a longer-prompt / cold-start worst case — the peak scales with KV occupancy toward
cap768, so a long paragraph pushes 1.7B higher than 0.6B, but single-utterance hermes traffic sits at
~5.5-5.8 GiB and is comfortably safe under a 10G limit. Remaining variable to characterize if we ever
serve long paragraphs: the near-capacity peak for each size.

**Where the real memory is (levers, in priority order — all inside our OpenVINO stack):**
1. **Quantize / bf16 the FP32 vocoder** (the ~2.7 GiB fixed jump at vocoder compile). Biggest lever;
   done in our own export, not via Optimum Intel or a host-language rewrite.
2. **Generation-peak activations** (the ~9.8 GiB cgroup peak): try `KV_CACHE_PRECISION=u8`, capacity
   768→512, and bf16 inference-precision hint on the now-stateful main — separate, parity-gated
   experiments (see the ranked hypotheses in HANDOFF).

**Not levers (confirmed):** Optimum Intel is the same OpenVINO runtime under an HF wrapper — same
floor, likely worse (keeps the full HF torch model); no memory win. A Rust/other-language rewrite
would save only the small Python/torch host overhead (~hundreds of MB) while leaving the dominant
native OpenVINO runtime + IR + activation buffers untouched — a huge rewrite for no meaningful
footprint gain. `scripts/codec_memory_report.py` remains as the standing instrument for this.

### PyTorch rollback timeout — root cause found and fixed in config (2026-06-30)

The failed `TTS_BACKEND=pytorch` rollback gate (generation exceeding the 300 s HTTP timeout) was a
simplify-v2 regression, now fixed in `src/qwen3_tts/config.py`. `apply_preset_env()` was setting
`OPENVINO_TORCH_DTYPE=bfloat16` **unconditionally**, for every backend. On the OpenVINO path that is
harmless — the talker cores run on OpenVINO and the bf16 Torch weights are just load-time glue that is
released after compile. But on the pure-PyTorch fallback the transformer forward **actually runs in
Torch on CPU**, where bf16 has no fast GEMM kernels, so generation ran pathologically slow and blew
past the timeout. The pre-refactor design only set that variable for the OpenVINO service, so the old
fallback loaded fp32.

Fix: the bf16/`OPENVINO_RELEASE_TORCH` serving-load policy is now gated on `backend == "openvino"`; the
PyTorch fallback falls through to the fp32 default (`resolve_torch_load_config` default). Verified
locally that `TTS_BACKEND=pytorch` no longer receives a forced bf16 dtype, the OpenVINO path is
unchanged (bf16 + release), and an explicit expert `OPENVINO_TORCH_DTYPE` override is still honored.

**CONFIRMED PASS on `dockermisc1` (2026-06-30):** with the fix, `TTS_BACKEND=pytorch MODEL_SIZE=0.6B`
loads at `torch_dtype=float32` and a short-prompt `POST /generate` returned **HTTP 200 in 20.4 s** with
a valid 24 kHz mono WAV (vs the previous >300 s timeout under bf16). The rollback gate passes for 0.6B.
Follow-up (non-blocking): spot-check 1.7B PyTorch (the deployed fallback size) with a short prompt — it
will be slower than 0.6B but is expected to stay within 300 s for typical utterances.

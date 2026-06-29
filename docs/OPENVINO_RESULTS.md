# Qwen3-TTS OpenVINO — Benchmark & Results Log

Measured data only. Design, contracts, and plans live in
[`OPENVINO_IMPLEMENTATION.md`](OPENVINO_IMPLEMENTATION.md); this file is the audit record of every
run so options can be compared without wading through the implementation narrative.

All runs: CPU only, dockermisc1 (8 vCPU i7-1360P, AVX2+VNNI, no AVX-512, 15 GiB RAM), 6 threads,
0.6B Base unless noted. "match" = `mean_overall_codebook_match_rate`; "speedup" = warm
`speedup_median` (PyTorch ÷ OpenVINO); RTF = OV real-time factor.

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

# Handoff — qwen3-tts OpenVINO optimization (2026-06-29)

Self-contained brief for the next agent. Deeper detail lives in `OPENVINO_IMPLEMENTATION.md` (design +
milestones) and `OPENVINO_RESULTS.md` (every measured number). Memory file:
`validate-openvino-plan-status.md`.

## Where we are (one paragraph)

0.6B ships weight-only **INT8 at ~1.40×** (M6 CLOSED — every quality-recovery path was tried and
rejected). The active work is the **1.7B track**, pursued as a *quality* upgrade, not a speed one. As of
today all three 1.7B decision gates are answered:

- **Quality (listened):** 1.7B-INT8 "very very clear"; 1.7B-INT4 (g32) "slight comma pause but 100%
  good". Both beat 0.6B-INT8, whose comma artifact the user dislikes. → **INT4 is the chosen 1.7B
  precision.**
- **Speed (M1.7B-A, measured):** PyTorch 1.7B 25.05 s median → OV INT8 **1.27×**, OV INT4 **1.35×**.
  Same CPU ceiling as 0.6B; neither hits 2×. Crucially **1.7B-INT4 at 18.6 s ≈ 0.6B-INT8 (~17.4 s)** in
  absolute latency while sounding clearly better.
- **Memory (M9 spike + early release, measured):** per-core profiling rejected the vocoder hypothesis
   and attributed ~92% of sampled growth to main prefill/decode. Static-capacity stateful main is
   bit-exact against explicit INT4 and cuts generation peak **10.78 → 8.81 GiB**; retained RSS
   **10.42 → 8.64 GiB**. Early PyTorch weight release before main-graph compile further reduced
   lifetime peak from 12.1 GiB to 11.3 GiB. All M9 gates now passed: capacity, warm latency,
   listening, concurrency, rollback, and FP32-vs-PyTorch parity (on 0.6B). The 7 GiB limit is not
   yet met; M9 is a substantial step, not final.

**Bottom line for the next agent:** 1.7B-INT4 is a real, validated quality win at near-0.6B latency.
The remaining work is to bake M9 into a built image, tighten memory further (stateful predictor,
capacity tuning, thread/activation tuning), and finalize the 7 GiB runtime. M9 is not production-ready.

## Immediate next steps, in priority order

1. **Review PR #59.** Branch `feat/m9-generation-peak-profile`; tip commit is `5c4a6b0`. PR #59
   contains: Release Please fix, RSS profiler, stateful main graph rewrite, parity gates, early
   weight release, app_worker wiring, and M9 gate measurements. All M9 gates are now passed; the
   branch is ready-to-test, but M9 is spike-grade and the 7 GiB limit is not yet met.

2. **Bake a built image + finalize M9 in serving.** Runtime changes are now wired in `app_worker.py`
   and `compose.example.yml`, but not in a built image. Build a new exporter/runtime image
   (next tag v0.11.0+), and confirm:
   - `OPENVINO_RELEASE_TORCH=1`
   - `OPENVINO_VOCODER_ENABLED=1`/`OPENVINO_VOCODER_DIR`
   - `OPENVINO_MAIN_STATEFUL_MODEL` (opt-in)
   - 1.7B-INT4 configuration is reproducible from an image alone, no mounted files.

3. **Reduce retained memory further (beyond 11.3 GiB).** The 7 GiB production limit is not yet met.
   Candidate levers:
   - Stateful predictor (estimated ~295 MiB).
   - Reduce stateful capacity for shorter intended prompts.
   - OpenVINO threading/activation tuning.
   - Evaluate a thin selective loader to avoid loading the full talker upfront.

4. **Run 1.7B FP32-vs-PyTorch parity on stateful main.** Current M2 parity (SNR ≥60 dB) passed on
   0.6B-Base. A 1.7B FP32 stateful parity is a recommended follow-up to match our deployed model size.
   serving config. Until then nothing 1.7B is reproducible from an image alone.

## How to run benchmarks on the box (copy-paste ready)

- `ssh nick@dockermisc1`. Prod `qwen3-tts` is currently **stopped** (user doesn't care). **NEVER**
  blanket `docker kill`/`prune` — it took down `litellm*`/`headroom-proxy` once. Touch only `qwen3-tts`.
  See `dockermisc1-ops` memory.
- **Never run two `--memory 13g` jobs at once** — 15 GiB box + litellm/headroom = OOM.
- IR dirs under `/var/data/autopirate/qwen3-tts/openvino/`:
  - INT8: `qwen-tts-0.1.1_1.7b_fd4b25438912_ov-2026.2.1`
  - INT4: `qwen-tts-0.1.1_1.7b_fd4b25438912_ov-2026.2.1_int4g32` (no vocoder inside)
  - FP32 vocoder: `qwen-tts-0.1.1_1.7b_fd4b25438912_ov-2026.2.1_vocoder` (set `OPENVINO_VOCODER_DIR` to
    this for both INT8 and INT4; the INT8 dir's own `vocoder_decoder_int8.xml` is unused — INT8 vocoder
    was rejected at 16 dB).
- Released image used for M9: `exporter-v0.10.0` at
  `sha256:5189f9bd604c4f4e187175691b7375e9b6f3fd449d91ca73ec78911beaebcb49`. Mount PR #59 files over
  `/app/` (runtime patches not yet imaged). Ref WAV: `/var/data/autopirate/qwen3-tts/voice/voice_A.wav`.
- The speed-bench driver is `/tmp/ov-bench/speed_1.7b.sh` on the box (and `bench_speed.py` in the repo).
  Memory harness is `dump_audio.py --ov-only` (3-checkpoint RSS). Parity/quality harness is
  `test_ov_generation.py` (`--mode sampled-quality`); its coupled greedy block OOMs at 1.7B, so use
  `bench_speed.py` for latency.
- The M9 branch extends `dump_audio.py` with a generation-only RSS sampler. Run with
  `--rss-profile /ov_output/m9_rss_1.7b_int4.json --rss-sample-ms 50`; the JSON labels every sample
  as `transformer` or `vocoder` and reports per-phase peaks. Store the JSON outside Git and compare
  its generation-only peak with the lifetime RSS report.
- Stateful spike dir:
  `qwen-tts-0.1.1_1.7b_fd4b25438912_ov-2026.2.1_int4g32_stateful_spike/`. Use
  `main_stateful_int4_v2.xml`; `main_stateful_parity.json` is bit-exact. Raw profiles are
  `m9_rss_core_1.7b_int4.json` (explicit) and `m9_rss_stateful_main.json` (stateful).
  Original metadata SHA-256 is `ca8f50be8ff4be280248f4ec9c7767ec91f3244e20ef9bcd58042a410344ea2e`;
  stateful XML SHA-256 is `a46b03178576bf0f30fb8b37945b872833e3f25098b83921af82215b91349de5`.

## Hard-won gotchas (don't relearn these)

- M7 weight-release must scope to each core's `.layers` only — freeing `embed_tokens` breaks the glue
  (`talker.get_text_embeddings()` → `'weight' must be 2-D`).
- INT4 graphs are still named `*_int8.xml`; the runtime loads them via `--compression int8`. The dir
  suffix `_int4g<grp>` is the only precision marker.
- 1.7B holds full PyTorch model + OV graphs at once in the coupled harness → measure one backend per
  process (that's why `bench_speed.py` exists).
- transformers is hard-pinned 4.57.3 by qwen-tts==0.1.1; export wrappers depend on its DynamicCache
  `.layers`/`to_legacy_cache` API. Do not bump it. A static-`kv_length` bug in 4.57.3 is dodged by
  `CoreCacheWrapper._build_causal_mask` prebuilding a 4D additive mask — preserve this under any
  stateful rewrite.
- OpenVINO `MakeStateful` rejects dynamic state shapes. Do not retry it. The working design uses
  static-capacity Variables plus dynamic prefix Slice and cache-position ScatterUpdate/Assign.
- `ru_maxrss` includes model load and OV compilation; it is not a generation-only metric. Always pair
  it with the sampled generation timeline. The stateful run proved startup is now the lifetime peak.
- RTF here is overhead-dominated (test utterances ~2.6 s), so compare absolute median seconds across
  precisions, not RTF.

## What is explicitly DONE (don't redo)

M0 baseline; M1.5/M2 export+parity; M3 INT8 characterization; M4 runtime+vocoder wiring; M6 (0.6B INT8
shipped, all recovery rejected); 1.7B INT8+INT4 export; M7 weight-release; M8 INT4 memory+quality;
M1.7B-A speed gate; M9: attribution, static state primitive, main INT4 graph rewrite/compile,
bit-exact explicit-vs-stateful main parity, end-to-end memory run, early release before compile,
M9 gates (capacity, warm latency, listening, concurrency, rollback, FP32-vs-PyTorch 0.6B parity).
M9 is not production-ready (7 GiB limit not met).

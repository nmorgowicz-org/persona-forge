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
    lifetime peak from 12.1 GiB to 11.3 GiB. All M9 gates now passed: capacity tuning, warm latency,
    listening, concurrency, rollback, stateful predictor, and FP32-vs-PyTorch parity (on 0.6B and
    1.7B). Capacity 768 is validated and recommended. The 7 GiB limit is not yet met; M9 is a
    substantial step, not final.

**Bottom line for the next agent:** 1.7B-INT4 is a real, validated quality win at near-0.6B latency.
The 7 GiB limit is **not** met (idle ~8.1 GiB at cap 768, lifetime ~11.3 GiB) and — per the analysis
below — the binding ~2.5 GiB is an **unattributed generation transient**, not the startup overlap the
early-release change targeted. The next move is to measure that transient, not to start cutting blind.

> **Correction recorded 2026-06-29 (see RESULTS.md "M9 lifetime-peak root cause — correction").** The
> early-release run falsified the "lifetime peak = startup overlap" hypothesis: post-release startup
> tops out at 8.7 GiB yet lifetime `ru_maxrss` is 11.56 GiB while the 50 ms-sampled gen peak is only
> 9.05 GiB. That ~2.5 GiB gap is a generation transient the interval sampler is blind to. Because the
> vocoder was rejected (M9.3a) on that same blind sampler (~6 MiB), **the vocoder lever is unmeasured,
> not rejected.**

## Immediate next steps, in priority order

1. **Lifetime peak is MEASURED — it is the PyTorch model-load transient (done; act on it).**
   Exact `ru_maxrss` attribution (RESULTS.md "M9 lifetime-peak — MEASURED and localized") shows
   `ru_maxrss` is already **11,593 MiB right after `from_pretrained`**, before OV install, and every
   generation phase (incl. vocoder) adds **+0**. The peak is the 1.7B fp32 checkpoint-load transient in
   `bench_common.load_model` (`from_pretrained(..., dtype=torch.float32)`, no `low_cpu_mem_usage`),
   ~3 GiB over the 8.5 GiB settled value — a one-time boot spike, not steady state (~8.9 GiB idle).
   The vocoder lever (M9.3a) is closed for the right reason. **Status:**
   - **(a) `low_cpu_mem_usage=True`: tried, no effect** (device_map already implied it). Kept as
     best-practice.
   - **(b) bf16 serving load: DONE and measured** — `OPENVINO_TORCH_DTYPE=bfloat16` (default float32,
     serving-only; exporter stays fp32). Checkpoint is BF16, so loading native bf16 skips the upcast.
     **Lifetime peak 11,593 → 8,326 MiB; after-load ru_maxrss 11,593 → 2,620; trimmed idle 8,884 →
     8,093.** Two OV dtype seams fixed (`_to_numpy` bf16→fp32; forwards cast hidden back to model dtype),
     both no-ops under fp32. See RESULTS "M9 bf16 serving load".
   **Two things remain on bf16:** (i) a **listening A/B** (`audio/{fp32,bf16}_glue.wav`) — bf16 changes
   the sampled stream (3.36 s vs 3.68 s); the OV cores are unchanged so only glue precision differs;
   (ii) it is **~8.3 GiB, still above 7 GiB** — the new ceiling is generation `main_prefill` (+1915 MiB
   exact), so the next lever is **stateful capacity 768 and/or prefill handling**, not the load path.

2. **Review PR #59.** Branch `feat/m9-generation-peak-profile`; tip is the commit following this
   handoff. Contains: Release Please fix, RSS profiler (+ exact `ru_maxrss` attribution), stateful
   main graph rewrite, parity gates, early weight release, app_worker wiring, stateful predictor
   wiring, capacity tuning, M9 gate measurements, and the repo-hygiene cleanup (removed the committed
   501 KB `m9_rss_*.json`; gitignore + `scripts/validate_repo.py` now reject raw profile JSONs). All
   M9 gates pass but the 7 GiB limit is not met — keep it draft until step 1 settles the path.

3. **Pick the memory lever from step 1's result.**
   - **3a (if vocoder-bound):** chunked/streaming vocoder decode to cap the single-shot decode buffer.
   - **3b (if transformer-bound):** OV activation/buffer reuse + threading/activation tuning; evaluate
     a thin selective loader to avoid materializing the full talker upfront.
   - Either way, re-confirm 768 capacity holds under the longest operational prompt.

4. **Bake a built image + finalize M9 in serving** (after a lever lands, or now if the team accepts
   ~8.1 GiB idle as good enough on the 15 GiB box). Runtime changes are wired in `app_worker.py` and
   `compose.example.yml` but not yet imaged. Build a new exporter/runtime image (next tag v0.11.0+) and
   confirm: `OPENVINO_RELEASE_TORCH=1`, `OPENVINO_VOCODER_ENABLED=1`/`OPENVINO_VOCODER_DIR`,
   `OPENVINO_MAIN_STATEFUL_MODEL` (opt-in), `OPENVINO_PREDICTOR_STATEFUL_MODEL` (opt-in, small),
   capacity 768 default, and that the 1.7B-INT4 config is reproducible from the image alone.

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
stateful predictor wiring and listening check, capacity tuning (768/1024 validated),
M9 gates (capacity, warm latency, listening, concurrency, rollback, FP32-vs-PyTorch 0.6B and 1.7B
parity). M9 is not production-ready (7 GiB limit not met).

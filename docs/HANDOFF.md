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
- **Memory (M7/M8, measured):** the wall. 1.7B-INT4 retained idle 10.43 GiB, but the **per-request peak
  is ~12.06 GiB and barely moved from INT8 (−0.78 GiB)** — i.e. the peak is generation-allocation-bound
  (OV working buffers + single-shot vocoder decode), NOT weight-bound. Weight-release (M7) + INT4 do
  **not** fit the "<7 GiB" budget on the 15 GiB box.

**Bottom line for the next agent:** 1.7B-INT4 is a real, validated quality win at near-0.6B latency.
The *only* thing standing between it and shipping is the ~12 GiB generation peak. That makes **M9
(generation-peak reduction)** the single highest-leverage next workstream.

## Immediate next steps, in priority order

1. **Release baseline landed.** PR #57 merged as `679799d8`; Release Please produced v0.10.0 and the
   container workflow completed. New work must branch from v0.10.0-era `main`. The PR override block
   placed entries on adjacent lines, so Release Please parsed only the first entry; it also used
   hidden `docs` types and invalid composite headers such as `docs+export:` and `feat(bench)+docs:`.
   The M9 follow-up requires blank-line-separated, single-type entries and makes every supported
   project commit type visible so future override blocks retain all intended entries.

2. **M9 — profile the generation peak (do this before building anything).** Run one generation under a
   memory profiler (e.g. `tracemalloc` around `generate_voice_clone`, or sample `/proc/self/status`
   VmRSS in a thread) on 1.7B-INT4 to attribute the ~12 GiB peak. Hypotheses to confirm/refute, in
   order of suspected size: (a) single-shot vocoder decode allocates the whole waveform + conv
   activations at once; (b) OV compiled-model working buffers; (c) DynamicCache KV duplicated as
   numpy↔torch in the buffered path. The profile decides which of 3a/3b/3c below is worth building.

3. **M9 levers (build the one the profile points at):**
   - **3a. Chunked/streaming vocoder decode.** The decoder already takes a fixed `--vocoder-chunk`
     (325 frames = 300 + 25 ctx). If the profile blames the vocoder, decode in chunks and concatenate,
     capping the one-shot allocation. Lowest-risk, likely biggest win.
   - **3b. Stateful OV KV cache (folds in former M5).** Full design spec is already written in
     `OPENVINO_IMPLEMENTATION.md` → "M5/M9.3 design — stateful OV KV cache". Removes the per-layer
     per-step KV copies and the torch KV allocation. Export side: collapse each core's prefill+decode
     into one dynamic graph, name K/V tensors, apply `apply_make_stateful_transformation`. Runtime
     side: one infer_request/core, `reset_state()` on prefill, return a length-only cache shim. **Must
     re-run the M2 FP32 parity gate (SNR ≥ 60 dB) — this is the parity-critical change.** Higher effort,
     deeper risk; do it only if 3a doesn't get under budget.
   - **3c.** Reuse/preallocate OV buffers across steps if 3b is too big a lift.
   - Success = per-request peak AND retained RSS under the chosen 1.7B budget with ≥20% headroom; re-run
     the M7 three-checkpoint harness after each lever.

4. **Bake a built image + wire serving (once M9 lands).** Runtime fixes (vocoder wiring, M7
   release-torch, any M9 work) are currently **mounted from the working tree**, not in a built image.
   Build a new exporter/runtime image (next tag ~v0.9.2+), and wire `OPENVINO_RELEASE_TORCH=1` +
   `OPENVINO_VOCODER_ENABLED=1`/`OPENVINO_VOCODER_DIR` into `app_worker.py`/compose for the 1.7B-INT4
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
- Image `ghcr.io/nmorgowicz-org/qwen3-tts-openvino:exporter-v0.9.1`. Mount working-tree `.py` over
  `/app/` (runtime patches not yet imaged). Ref WAV: `/var/data/autopirate/qwen3-tts/voice/voice_A.wav`.
- The speed-bench driver is `/tmp/ov-bench/speed_1.7b.sh` on the box (and `bench_speed.py` in the repo).
  Memory harness is `dump_audio.py --ov-only` (3-checkpoint RSS). Parity/quality harness is
  `test_ov_generation.py` (`--mode sampled-quality`); its coupled greedy block OOMs at 1.7B, so use
  `bench_speed.py` for latency.
- The M9 branch extends `dump_audio.py` with a generation-only RSS sampler. Run with
  `--rss-profile /ov_output/m9_rss_1.7b_int4.json --rss-sample-ms 50`; the JSON labels every sample
  as `transformer` or `vocoder` and reports per-phase peaks. Store the JSON outside Git and compare
  its generation-only peak with the three-checkpoint/lifetime RSS report before choosing M9.3a,
  M9.3b, or M9.3c.

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
- RTF here is overhead-dominated (test utterances ~2.6 s), so compare absolute median seconds across
  precisions, not RTF.

## What is explicitly DONE (don't redo)

M0 baseline; M1.5/M2 export+parity; M3 INT8 characterization; M4 runtime+vocoder wiring; M6 (0.6B INT8
shipped, all recovery rejected); 1.7B INT8+INT4 export; M7 weight-release; M8 INT4 memory+quality;
M1.7B-A speed gate. The M5 stateful-cache **design** is written (not implemented).

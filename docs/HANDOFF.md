# Handoff — qwen3-tts OpenVINO optimization (2026-06-29, after v0.11.0)

Self-contained brief for the next agent. Deeper detail lives in `OPENVINO_IMPLEMENTATION.md` (design +
milestones) and `OPENVINO_RESULTS.md` (every measured number). Memory file:
`validate-openvino-plan-status.md`.

## Where we are (one paragraph)

**Everything is merged to `main` and released as v0.11.0** (tag `qwen3-tts-openvino-v0.11.0`,
commit `f8b7e5e`; PR #59 squashed in `08415a5`). 0.6B ships weight-only **INT8 at ~1.40×** (M6
CLOSED). The **1.7B-INT4 track is functionally complete** — a validated *quality* win at near-0.6B
latency, with the memory wall (M9) now CLOSED. All three 1.7B decision gates are answered and shipped:

- **Quality (listened):** 1.7B-INT4 (g32) "slight comma pause but 100% good", beats 0.6B-INT8 whose
  comma artifact the user dislikes. → **INT4 is the chosen 1.7B precision.**
- **Speed (M1.7B-A, measured):** OV INT4 **1.35×** (18.6 s ≈ 0.6B-INT8's ~17.4 s) while sounding
  clearly better. CPU-bound; neither size hits 2×.
- **Memory (M9, CLOSED):** full arc **lifetime peak 11,593 → 7,715 MiB, trimmed idle 8,884 →
  7,485 MiB**, dangerous boot spike eliminated. Driven by (1) **bf16 serving load** — the binding peak
  was the fp32 checkpoint-load transient, and loading the native-bf16 checkpoint skips the upcast
  (11,593 → 8,326); (2) **capacity-768 stateful main** (8,326 → 7,715); plus stateful predictor, early
  weight release, and a serving silence-trim. The ~7.5 GiB floor (INT4 weights + bf16 glue + runtime)
  does not move with capacity, so **1.7B ships at `TTS_MEMORY_LIMIT=8G`** (0.6B-INT8 still fits 7G).

**Bottom line for the next agent:** the 1.7B-INT4 quality track is DONE and shipped. There is no open
blocker. Remaining work is *enablement and polish*, not core engineering — see next steps. The one
honest caveat: all M9 numbers were measured with PR-#59 runtime files mounted over the released
`exporter-v0.10.0` image; **a v0.11.0 image that bakes those runtime files has not yet been built and
smoke-tested end-to-end** (the code is on `main`, the image is not yet published).

## Immediate next steps, in priority order

1. **Build + publish the v0.11.0 runtime/exporter image and smoke-test it (the only real loose end).**
   The M9 runtime changes (`app_worker.py`, `ov_talker_runtime.py`, `bench_common.py`, stateful
   transforms) are on `main` but were validated by *mounting* them over `exporter-v0.10.0`. Build the
   image at the v0.11.0 tag and confirm the 1.7B-INT4 config is reproducible **from the image alone**:
   `OPENVINO_TORCH_DTYPE=bfloat16`, `OPENVINO_RELEASE_TORCH=1`, `OPENVINO_MAIN_STATEFUL_MODEL`
   (capacity-768 main), `OPENVINO_PREDICTOR_STATEFUL_MODEL` (opt-in, small), `OPENVINO_VOCODER_ENABLED=1`
   /`OPENVINO_VOCODER_DIR`, `SILENCE_TRIM=1`, `TTS_MEMORY_LIMIT=8G`. Re-confirm the headline numbers
   (lifetime ~7,715 / idle ~7,485 MiB) hold from the baked image, then this track is fully closed.
   *This is an outward-facing GHCR publish — confirm with the user before pushing.*

2. **Ship a capacity-768 main IR as a first-class production artifact.** Today the cap-768 main lives in
   the spike dir as `main_stateful_int4_cap768.xml`. Promote it into the released INT4 IR directory with
   capacity recorded in metadata, and document the `transform_stateful_ir.py` rebuild recipe (already in
   `compose.example.yml`'s "Capacity tuning" block) in the user-facing README/quickstart so operators
   can retune. Validate bit-exact parity with `scripts/test_stateful_main_parity.py` after the rebuild.

3. **Optional further memory headroom (only if a 7G 1.7B target is ever required).** The floor is
   ~7.5 GiB; the largest remaining single contributor is the `main_prefill` activation (+1,529 MiB at
   cap 768). Levers, in order: drop capacity to 512 (~42 s max utterance — risky for paragraphs), OV
   activation/buffer reuse, thread/activation tuning. Not needed for the shipped 8G target; pursue only
   on explicit request. Re-confirm 768 holds under the longest operational prompt either way.

4. **Decide 1.7B's release role vs 0.6B.** 1.7B-INT4 is the quality leader but needs 8G and is ~1.07×
   slower in absolute latency than nothing-special; 0.6B-INT8 is the lean 7G default. This is a
   product/positioning call for the user, not an engineering one — surface it, don't decide it.

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
- Image used for all M9 measurements: `exporter-v0.10.0` at
  `sha256:5189f9bd604c4f4e187175691b7375e9b6f3fd449d91ca73ec78911beaebcb49`, with the (now-merged) M9
  runtime files **mounted over `/app/`** — they are on `main` but **not yet baked into a v0.11.0 image**
  (step 1). The cap-768 bf16 run script + log on the box: `/tmp/ov-m9/run_bf16_cap768.sh`,
  `bf16_cap768.log`. Ref WAV: `/var/data/autopirate/qwen3-tts/voice/voice_A.wav`.
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
parity); M9 bf16 serving load + capacity-768 + silence-trim + capacity-tuning docs. **M9 CLOSED and
shipped in v0.11.0** (lifetime peak 7,715 / idle 7,485 MiB at 8G). Only remaining task: bake +
smoke-test the v0.11.0 image (step 1 above).

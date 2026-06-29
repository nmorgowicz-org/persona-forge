# Handoff — 0.6B stateful-KV footprint work (2026-06-29)

Self-contained brief for the next agent. Deeper detail lives in `OPENVINO_IMPLEMENTATION.md` (design +
milestones) and `OPENVINO_RESULTS.md` (every measured number). Memory file:
`validate-openvino-plan-status.md`.

## Where we are (one paragraph)

`main` is released as v0.11.0 (tag `qwen3-tts-openvino-v0.11.0`, commit `f8b7e5e`; PR #59 squashed
in `08415a5`). Current work is on **`feat/0.6b-stateful-kv` and is not merged/released**. The 0.6B
implementation source commit is **`e5ab3cc`**. The
INT8 stateful profile is implemented and passes its footprint/quality gates: cap-768 main + cap-32
predictor, bf16 serving glue, and early release cut the short peak **8,623 → 6,635 MiB** and retained
RSS **8,247 → 6,394 MiB**. Explicit/stateful INT8 output is bit-exact at both cores and the rendered
WAV is byte-identical. Warm median is 3.8% slower, and a 45.28-second request peaks at 7,845 MiB, so
long-prompt deployments still need 8 GiB. The 1.7B-INT4 track remains closed and released:

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

**Bottom line for the next agent:** core 0.6B stateful engineering and target-host validation are
done. Remaining work is packaging/publish validation: commit/push/PR this branch, bake the runtime,
promote the generated IRs with their provenance sidecars, and smoke-test without bind-mounted code.
Do not claim 7 GiB support for unrestricted paragraph generation.

## Immediate next steps, in priority order

1. **Publish this branch through a PR, then bake and smoke-test the next image.** The measured run used
   `exporter-v0.10.0` with branch files mounted over `/app`. Rebuild both container targets and test
   from the image alone with `MODEL_SIZE=0.6B`, `OPENVINO_TORCH_DTYPE=bfloat16`,
   `OPENVINO_RELEASE_TORCH=1`, cap-768 `OPENVINO_MAIN_STATEFUL_MODEL`, cap-32
   `OPENVINO_PREDICTOR_STATEFUL_MODEL`, and the FP32 OV vocoder. Apply `ready-to-test` only after the
   repository tests pass. Repeat `/health`, serialized serving, explicit-cache opt-out, and a fresh
   `TTS_BACKEND=pytorch` rollback process; those were not rerun on this branch. Publishing GHCR
   artifacts is outward-facing; confirm before manual publish.

2. **Promote the 0.6B stateful IRs as versioned production artifacts.** Source directory:
   `qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1`; generated directory adds `_stateful`. Promote
   `main_stateful_int8_cap768.{xml,bin}` and `predictor_stateful_int8_cap32.{xml,bin}` plus their
   `*.transform.json` provenance. Do not put them in Git or bake weights into an image. Re-run both
   explicit-vs-stateful parity commands after promotion.

3. **Choose and document the 0.6B memory policy.** Short requests peak at 6,635 MiB and fit 7 GiB with
   only 7.4% headroom; the 45.28-second run peaks at 7,845 MiB. Prefer 8 GiB unless the API enforces a
   bounded short text/request policy. Do not lower capacity below 768 without a replacement long-prompt
   gate; the current 177-word prompt completed at that capacity.

4. **Keep rollback explicit.** Unset both stateful-model variables for explicit-cache A/B. Restart a
   fresh process with `TTS_BACKEND=pytorch` for full rollback; early release makes in-process fallback
   impossible by design.

## How to run benchmarks on the box (copy-paste ready)

- `ssh nick@dockermisc1`. Prod `qwen3-tts` is currently **stopped** (user doesn't care). **NEVER**
  blanket `docker kill`/`prune` — it took down `litellm*`/`headroom-proxy` once. Touch only `qwen3-tts`.
  See `dockermisc1-ops` memory.
- **Never run two `--memory 13g` jobs at once** — 15 GiB box + litellm/headroom = OOM.
- IR dirs under `/var/data/autopirate/qwen3-tts/openvino/`:
  - 0.6B explicit INT8: `qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1`
  - 0.6B stateful artifacts/reports: the same name plus `_stateful`; raw RSS, parity, speed JSON,
    and generated WAVs remain there outside Git. Source metadata SHA-256 is
    `abec65a5d2f2dcf07382d707513cb2a9f5c2a4c5872728069b169d9601e3da7f`.
  - 0.6B FP32 vocoder: the explicit directory name plus `_vocoder`.
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
- Predictor stateful IR has five base inputs; `generation_steps` is retained at index 4. Live nested
  generation may omit it, so `_OVStatefulCore` must preserve the explicit runtime's int64-zero default.
- 0.6B cap-32 predictor is deliberate: its per-frame cache is reset and the validated path is a
  2-token prefill plus 14 decode calls. Main capacity remains 768.
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
shipped in v0.11.0** (lifetime peak 7,715 / idle 7,485 MiB at 8G). On this branch, 0.6B stateful
main+predictor transform, runtime input handling, INT8 bit-exact parity, FP32 PyTorch parity,
byte-identical end-to-end quality, short/long RSS, and five-run warm latency are complete. Remaining:
merge/publish, promote IR artifacts, and baked-image smoke test.

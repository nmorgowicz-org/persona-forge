# Plan — apply the M9 levers to 0.6B (footprint reduction, speed bonus)

> **Primary goal: reduce the 0.6B memory footprint.** The M9 levers that shrank 1.7B do the same for
> 0.6B; a possible warm-latency win from removing per-frame K/V marshalling is a bonus, not the point.

Branch: `feat/0.6b-stateful-kv`. Status: **framework only, nothing measured yet.** This doc is the
self-contained brief; deeper design lives in `OPENVINO_IMPLEMENTATION.md` § "M5/M9.3 design" and every
1.7B number lives in `OPENVINO_RESULTS.md`.

## Why this, and why only this, carries over from 1.7B

The 1.7B work bundled several levers. For a **footprint** goal, three of them help 0.6B and two don't:

| 1.7B lever | Footprint effect on 0.6B | Verdict |
| --- | --- | --- |
| **bf16 serving load** (`OPENVINO_TORCH_DTYPE=bfloat16`) | **Lowers the load-time peak** — skips the fp32 upcast of the bf16 checkpoint (the lever that cut 1.7B's lifetime peak 11.6→8.3 GiB). Already-built, shared code. | **Pursue.** |
| **Early weight release** (`OPENVINO_RELEASE_TORCH=1`) | **Lowers steady idle** — frees each core's `.layers` after OV install. Already-built. | **Pursue.** |
| **Stateful MAIN + PREDICTOR KV cache** | **Lowers generation peak** — moves K/V inside the compiled graph, so no torch K/V is allocated and the per-step `np.copyto`/`torch.from_numpy` buffers disappear (cut 1.7B generation peak ~2 GiB). *Also* a possible latency win (predictor runs ~15×/frame, where the copy overhead concentrates). | **Pursue.** |
| **INT4 weights (g32)** | Would shrink weights further, but 0.6B can't absorb INT4 damage — INT8 is already at the quality edge (the comma artifact the user dislikes). | **Skip** (quality, not footprint). |
| **Silence trim** (`SILENCE_TRIM*`) | Not a footprint lever; already on for 0.6B. | Done already. |

**Bottom line:** the same three levers that shrank 1.7B (bf16 load, early release, stateful KV) shrink
0.6B too — bf16 cuts the load peak, release cuts idle, stateful KV cuts the generation peak. The
catch: **0.6B is already small, so the absolute savings are smaller in GiB** than on 1.7B, and we have
**no measured 0.6B baseline yet** (step 0 below). The latency question rides along for free.

## Honest expectation (set this before measuring)

- **Footprint:** the savings are *directional certainties* (these levers provably reduced 1.7B) but the
  **absolute GiB is unknown for 0.6B and will be smaller** than 1.7B's because 0.6B's weights, glue, and
  K/V are all smaller to begin with. Step 0 measures the baseline so the win is quantified, not assumed.
- **Latency:** RTF is **overhead-dominated** (~2.6 s utterances) and the **vocoder (~29% of wall time)
  is untouched**, so the ceiling is the transformer-core share only. Magnitude uncertain — a few percent
  or meaningful, most likely from the predictor (15×/frame). Treat as a bonus, measured not assumed.
- **Gate:** ship the new config if footprint drops with **zero audible/parity regression**; a latency
  win is upside, not a requirement.

## What to reuse vs. what is 0.6B-specific

**Reuse unchanged:**
- `scripts/transform_stateful_ir.py` — the graph rewriter (explicit prefill/decode pair → one stateful
  graph with `ReadValue`/`Assign` state variables). Worked for 1.7B main (28 layers) and predictor
  (5 layers).
- `ov_talker_runtime.py` stateful path — `OPENVINO_MAIN_STATEFUL_MODEL` / `OPENVINO_PREDICTOR_STATEFUL_MODEL`
  env knobs, the length-only cache shim, `_match_dtype`, `_to_numpy`. These are size-agnostic.
- The transformers-4.57.3 static-`kv_length` workaround in `CoreCacheWrapper._build_causal_mask`
  (prebuilt 4D additive mask) — **must be preserved**; do not regress it.

**Derive per-0.6B (do NOT hardcode the 1.7B values):**
- `--num-layers` for main and predictor. Read `num_hidden_layers` (main) and the predictor's layer
  count from the **0.6B model config**, or count the `*present_kv` outputs in the 0.6B `*_decode.xml`
  (states = 2 × layers). Docs hint 0.6B main is also 28-layer, but **verify against the IR, don't
  assume.**
- `--base-input-count` and `--cache-position-index` — re-derive from the 0.6B decode graph's input
  order exactly as was done for 1.7B (main used base-input-count 4, cache-position-index 3). If the
  0.6B export wrapper matches, these are identical; confirm by inspecting the 0.6B `main_decode.xml`
  inputs.
- **Capacity** (`--max-seq`). 0.6B's typical utterances are short; pick a capacity that covers the
  longest operational prompt with margin. Start at **768** (≈64 s @ 12 Hz) for parity with 1.7B; tune
  down if you want to shave idle RAM (not the point here — speed is).

## Step-by-step

0.6B INT8 IR on the box:
`/var/data/autopirate/qwen3-tts/openvino/qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1/`
(INT4 graphs are named `*_int8.xml` by convention — for 0.6B these are genuinely INT8).

0. **Measure the 0.6B baseline footprint first (so the win is quantified, not assumed).** Run the
   explicit-cache 0.6B-INT8 serving config through `dump_audio.py --ov-only` and record lifetime peak,
   trimmed idle, and per-phase `ru_maxrss` deltas — exactly the harness used for 1.7B M9. Without this
   number, "reduced footprint" is unfalsifiable. Then measure again after each lever (bf16 → release →
   stateful) so each lever's contribution is attributable, as was done for 1.7B.

1. **Inspect the 0.6B decode graphs** to confirm layer count + input layout:
   - Count `*present` K/V outputs in `main_decode_int8.xml` and `predictor_decode_int8.xml`
     → `--num-layers` = outputs / 2.
   - Confirm input order matches the 1.7B contract (base inputs first, then k0/v0…) →
     `--base-input-count`, `--cache-position-index`.

2. **Transform the main core** (substitute the verified `--num-layers N`, capacity `C`):
   ```bash
   python scripts/transform_stateful_ir.py \
     --input  <0.6b-ir>/main_decode_int8.xml \
     --output <0.6b-ir>/main_stateful_int8_cap<C>.xml \
     --num-layers <N_main> --base-input-count 4 --cache-position-index 3 \
     --max-seq <C> --state-prefix main --compile-smoke
   ```

3. **Transform the predictor core** (small capacity — its cache resets per frame):
   ```bash
   python scripts/transform_stateful_ir.py \
     --input  <0.6b-ir>/predictor_decode_int8.xml \
     --output <0.6b-ir>/predictor_stateful_int8_cap<Cp>.xml \
     --num-layers <N_pred> --base-input-count <verify> --cache-position-index <verify> \
     --max-seq <Cp> --state-prefix predictor --compile-smoke
   ```

4. **Bit-exact parity gate (do NOT skip).** Re-run the same explicit-vs-stateful comparison used for
   1.7B (box-side harness: the stateful run of `dump_audio.py` / `test_ov_generation.py` comparing
   stateful vs explicit hidden states). Require bit-exact (or SNR ≥ 60 dB) on **both** cores for 0.6B
   before trusting either. This is the parity-critical change.

5. **Wire + measure latency.** Run the 0.6B serving config with
   `OPENVINO_MAIN_STATEFUL_MODEL` / `OPENVINO_PREDICTOR_STATEFUL_MODEL` pointed at the new graphs and
   compare warm median/p95 against explicit-cache 0.6B-INT8 using `bench_speed.py` (one backend per
   process — the coupled harness OOMs/double-loads). Same seed, same text, ≥5 runs.

6. **Listening check.** A/B stateful vs explicit 0.6B-INT8 — confirm no new artifact (the comma artifact
   is pre-existing and should be unchanged; the silence trim already handles leading/trailing silence).

## Decision gate

- **Ship** the new 0.6B config (bf16 + release as defaults; stateful cores opt-out via unset env)
  **if footprint drops vs. the step-0 baseline with zero parity/listening regression.** A latency win
  is upside, not required.
- **Per-lever, not all-or-nothing:** bf16 + release are cheap, shared, and almost certainly net
  positive — adopt them even if stateful KV turns out marginal. Keep stateful only if its
  generation-peak saving is worth the added IR artifacts to maintain.
- **Record the numbers in `OPENVINO_RESULTS.md`** either way. A small or null footprint saving is still
  worth documenting — it tells us 0.6B is already near its floor and closes the question.

## Guardrails (carried from M9)

- **Box hygiene:** never blanket `docker kill`/`prune` (it took down `litellm*`/`headroom-proxy`); touch
  only `qwen3-tts`. Never two `--memory 13g` jobs at once. See `dockermisc1-ops` memory.
- INT8/INT4 graphs are both named `*_int8.xml`; the suffix on the dir is the only precision marker.
- Measure one backend per process. RTF is overhead-dominated → compare absolute median seconds.
- Preserve the 4D-mask workaround under any rewrite.

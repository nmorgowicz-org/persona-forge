# Plan — apply the M9 stateful-KV cache to 0.6B (a *speed* lever)

Branch: `feat/0.6b-stateful-kv`. Status: **framework only, nothing measured yet.** This doc is the
self-contained brief; deeper design lives in `OPENVINO_IMPLEMENTATION.md` § "M5/M9.3 design" and every
1.7B number lives in `OPENVINO_RESULTS.md`.

## Why this, and why only this, carries over from 1.7B

The 1.7B work bundled several levers. Most do **not** help 0.6B; one does. Be honest about which:

| 1.7B lever | Helps 0.6B? | Verdict |
| --- | --- | --- |
| **INT4 weights (g32)** | **No.** 0.6B can't absorb INT4 damage — INT8 is already at the quality edge (the comma artifact the user dislikes); INT4 would be worse. | Skip. |
| **bf16 serving load** (`OPENVINO_TORCH_DTYPE`) | Marginal. Frees ~load-time memory, but 0.6B already fits 7G comfortably, so it buys nothing operationally. The code path is shared, so it's free if wanted. | Low value; optional. |
| **Early weight release** (`OPENVINO_RELEASE_TORCH`) | Same — free, low value at 0.6B's memory headroom. | Optional. |
| **Silence trim** (`SILENCE_TRIM*`) | Already size-agnostic; lives in `app_worker` and is on for 0.6B today. | Done already. |
| **Stateful MAIN KV cache** | **Yes — as a latency lever.** Removes the per-step K/V marshalling (feed prior slices as IR inputs, `np.copyto` each present-K/V out into a numpy buffer, `torch.from_numpy` to rebuild a `DynamicCache`). | **Pursue.** |
| **Stateful PREDICTOR KV cache** | **Yes — likely the bigger win.** The predictor runs ~15 forwards per audio frame, so the per-frame copy overhead concentrates here. | **Pursue.** |

**Bottom line:** for 0.6B the stateful KV cache is a *speed* experiment, not a memory one. The
shipped 0.6B-INT8 is ~1.40×; the open question is whether removing per-frame K/V copy/marshalling on
both transformer cores moves warm latency on the *default* model.

## Honest expectation (set this before measuring)

- RTF here is **overhead-dominated** (test utterances ~2.6 s) and the **vocoder is ~29% of wall time
  and is untouched** by this change. So the ceiling is the transformer-core share only.
- The win is real but its **magnitude is uncertain** — could be a few percent or meaningful. The
  predictor (15×/frame) is where to expect most of it. Treat this as a measured go/no-go, not a
  guaranteed ship. **Gate: keep it only if warm median improves with zero audible/parity regression.**

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

- **Ship** the 0.6B stateful cores (make them the 0.6B default, opt-out via unset env) **only if** warm
  median improves and parity + listening pass.
- **If the latency win is within noise**, keep the explicit path as 0.6B's default and record the
  negative result in `OPENVINO_RESULTS.md` (so this isn't re-litigated). Even a null result is worth
  documenting — it tells us 0.6B latency is fully vocoder/compute-bound, not marshalling-bound.

## Guardrails (carried from M9)

- **Box hygiene:** never blanket `docker kill`/`prune` (it took down `litellm*`/`headroom-proxy`); touch
  only `qwen3-tts`. Never two `--memory 13g` jobs at once. See `dockermisc1-ops` memory.
- INT8/INT4 graphs are both named `*_int8.xml`; the suffix on the dir is the only precision marker.
- Measure one backend per process. RTF is overhead-dominated → compare absolute median seconds.
- Preserve the 4D-mask workaround under any rewrite.

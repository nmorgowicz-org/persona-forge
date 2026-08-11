# Diagnostic scripts

Scripts here are for investigating export/runtime bugs — not part of the normal export or
serving path (see `scripts/export.py`, `scripts/transform_stateful_ir.py` for those). Most take
raw `.xml`/`.bin` OpenVINO IR files as arguments and run standalone (`python3 <script> ...`),
no model/container needed unless noted. Kept because the next IR- or memory-shaped bug is likely
to need the same kind of comparison again.

## Reusable tools (general-purpose, reach for these first)

- **`compare_ir_constants.py <reference.xml> <candidate.xml>`** — diffs every `Constant` node
  between two structurally-equivalent OpenVINO IRs (by friendly name): shape/dtype mismatches,
  exact-match count, and the largest numeric deltas. Use when two IRs *should* be identical (e.g.
  same export, different transformers version) and you need to find which weight/buffer diverged.
  This is what found the corrupted RoPE `inv_freq` Constant in the 2026-07-02 NaN bug (see
  `docs/dev/resolved/EXPORT_PIPELINE_INT4_NAN_FIX.md`).

- **`compare_stateless_ir.py <reference.xml> <candidate.xml> [--seed N] [--seq N] [--hidden N]`**
  — feeds identical deterministic synthetic inputs (fixed seed) through two *stateless* IR graphs
  and reports per-output finite/min/max/mean/std. Use to bisect where a graph goes non-finite
  without needing real model inputs or a running server — e.g. comparing a known-good graph
  against a suspect one layer-output-by-layer-output. Exit code is nonzero if the candidate
  produces any non-finite output.

- **`codec_memory_report.py`** — reports resident PyTorch memory by component (talker layers vs.
  speech-tokenizer/codec) to explain steady-state RSS differences between model sizes. Must run
  *inside* the runtime image (needs torch + qwen_tts + model + IR):
  `docker compose run --rm --entrypoint python persona-forge scripts/diagnostics/codec_memory_report.py`.

## One-off spikes (proof-of-concept for a specific bug, kept as reference)

These aren't meant to be run again as-is — they're worked examples of how a specific bug was
proven, useful as a template if a similar bug shows up.

- **`repair_rope_ir_spike.py <known_good_fp32.xml> <broken_fp32.xml> <output_int4.xml>`** —
  swaps one specific Constant (`__module.core.rotary_emb/aten::to/Convert_compressed`, the
  main-talker RoPE `inv_freq` buffer) from a known-good FP32 IR into a broken one, then re-runs
  INT4 compression on the repaired graph. This was the decisive causal-proof step for the
  2026-07-02 INT4 NaN bug — confirming the corrupted Constant was sufficient to explain the
  failure, not just correlated with it. Hardcodes that one Constant's name; not generic.

- **`stateful_cache_spike.py`** — model-free spike (no qwen3-tts model involved) validating the
  static-capacity K/V state buffer + `ScatterUpdate` + State-API-reset design later used for the
  M9.3b stateful-cache work. Useful as a minimal worked example of that OpenVINO pattern if a
  similar static-capacity state design is needed elsewhere.

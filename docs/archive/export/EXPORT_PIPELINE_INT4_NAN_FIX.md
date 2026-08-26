# Handoff: export-pipeline transformers-5.x fix + INT4 main-talker NaN bug

**Date:** 2026-07-02  **Branch:** `feat/voice-design`  **Box:** `docker-agent`

This document records two related, now-fixed bugs found while validating the VoiceDesign export
pipeline under `transformers==5.12.1`, plus one still-open, unrelated bug found along the way.

## Resolution summary

Two bugs blocked a working OpenVINO INT4 export under transformers 5.x. Both are fixed and the
fix has been independently verified end-to-end (real `/generate` requests, not just unit tests).

### 1. Export pipeline API drift (transformers 5.x)

`docker compose --profile export run --rm export` failed during `ov.convert_model` tracing.
Three separate API changes were involved:

- `DynamicLayer.lazy_initialization()` arity changed — patched in `src/export/ov_export_wrappers.py`.
- `DynamicCache.from_legacy_cache()` / `.to_legacy_cache()` removed — replaced with the
  `DynamicCache(...)` positional constructor and `.layers[i].keys` / `.layers[i].values` access
  (see `CoreCacheWrapper._build_cache` / `._flatten_present` in `src/export/ov_export_wrappers.py`).
- `create_causal_mask()` signature changed, exposing two pre-existing bugs in the installed
  `qwen_tts` package itself (not our code — patched via `Dockerfile` string-replace):
  - typo'd dict key `"input_embeds"` → `"inputs_embeds"` in
    `Qwen3TTSTalkerCodePredictorModel.forward`'s `mask_kwargs`.
  - a leftover `"cache_position"` kwarg that transformers 5.x's `create_causal_mask()` no longer
    accepts.

With these fixes, `docker compose --profile export run --rm export` completes and produces valid
FP32/INT8/INT4 IR.

### 2. INT4 main-talker NaN bug (the fixed export pipeline then exposed this)

Every real `/generate` call against the freshly-exported INT4 main graph failed with
`RuntimeError: probability tensor contains either inf, nan or element < 0` — 100% reproducible,
on the very first `torch.multinomial` call, from the main talker's own prefill logits
(vocab_size=3072, not the code_predictor).

**Isolation.** Building the same freshly-exported checkpoint as FP32 (no NNCF quantization) or
INT8 (`compress_weights(mode=INT8_ASYM)`) produced completely clean, finite logits — same source
IR, same stateful-cache transform, same runtime. Only the INT4 (`int4_asym`, group_size=32,
ratio=1.0) variant was non-finite. This ruled out the stateful-cache transform, mRoPE/position-id
handling, and the transformers-5.x compat patches as the cause, and pointed at the INT4
compression step itself.

**Root cause.** A synthetic-input A/B test between an old known-good T4 (transformers-4.x) INT4
export and the new T5 export showed the new export's layer-0 rotary embedding Constant
(`__module.core.rotary_emb/aten::to/Convert_compressed`) had a corrupted range
(`1.25e-6 .. 65504.0`, i.e. clipped to FP16 max) versus the old export's correct decreasing
`inv_freq` values. Under transformers 5.x, `Qwen3TTSTalkerRotaryEmbedding`'s non-persistent
`inv_freq` buffer stays uninitialized on meta-device / `low_cpu_mem_usage=True` load — the
existing `_init_weights` patch only repairs `Parameter`s, not this buffer. FP32/INT8 carried the
bad-but-finite values through unharmed; INT4's much coarser quantization grid turned the garbage
buffer non-finite immediately in layer 0, cascading to all-NaN output.

Proven causally (not just by correlation) by swapping only that one Constant in the FP32 IR for
the known-good value, re-running the identical INT4 compression, and confirming the repaired
graph produced finite logits closely matching the old T4 graph's numeric range, while an
untouched control from the same source IR remained 100% non-finite.

**Fix.** `src/qwen3_tts/transformers_compat.py` adds `repair_rotary_buffers()`, which recomputes
every custom rotary module's `inv_freq` via its own `rope_init_fn(config, device)` immediately
after `Qwen3TTSModel.from_pretrained()`, and fails closed unless the result is 1-D, finite,
positive, strictly decreasing, and starts at 1.0. Called from both `src/export/export_openvino.py`
(export time) and `src/qwen3_tts/model.py` (runtime load), so both the export pipeline and the
PyTorch/OpenVINO serving path get the same repair.

## Independent verification (2026-07-02)

The above was diagnosed and fixed by an assisting agent session that ran out of quota before
fully updating this document or cleaning up its test container. The following was verified
independently in a follow-up session, not taken on the fixing agent's word:

- Restarted the OpenVINO-backend serving container on docker-agent
  (`~/projects/qwen3-tts-openvino-voicedesign-test`, image `qwen3-tts-openvino:local`) against the
  freshly-exported IR at `data/ov/1.7B/`.
- Two real `/generate` requests: both HTTP 200, valid 24kHz mono MP3 output, no NaN, steady
  memory ~5.1 GiB.
- Confirmed the local uncommitted diff on `feat/voice-design`
  (`Dockerfile`, `scripts/export.py`, `src/export/export_openvino.py`,
  `src/export/ov_export_wrappers.py`, `src/qwen3_tts/model.py`, `src/qwen3_tts/transformers_compat.py`,
  `tests/test_export_openvino.py`, `tests/test_export_rope_repair.py`) matches byte-for-byte what
  was validated on docker-agent, except `src/export/test_transformer_parity.py` (a diagnostic-only
  parity test, not on the serving path — the local copy is actually further along, with a
  transformers-4/5 compat fallback that the docker-agent copy lacks).

## Known separate, still-open bug: PyTorch rollback path

The plan calls for a PyTorch-backend (`TTS_BACKEND=pytorch`) rollback gate as part of validating
this fix. That gate is **not** currently satisfied. Reproduced directly:

```
RuntimeError: mat1 and mat2 shapes cannot be multiplied (1x350208 and 2048x2048)
  ... modeling_qwen3_tts.py:805, in self.o_proj(attn_output)
```

This is the main talker's eager self-attention reshape bug on longer prefill sequences —
`o_proj` receives a flattened `(batch, seq*hidden)` tensor instead of `(batch, seq, hidden)`. It
is unrelated to the RoPE/NaN fix above (the OpenVINO serving path never executes this code path)
and was already flagged as a known, independent issue during the original diagnosis. Do not rely
on the PyTorch backend as a fallback until this is fixed separately.

## Where things stand

- OpenVINO export + serving path: fixed, verified, safe to build VoiceDesign UI work against.
- PyTorch fallback/rollback path: broken, pre-existing, separate bug — not fixed here.
- Nothing has been committed. The full diff above is uncommitted on `feat/voice-design`, pending
  explicit go-ahead to commit.

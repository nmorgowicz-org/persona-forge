# Transformers 5 Compatibility Hacks — Agent Reference

> These patches are fragile and non-obvious. Removing or simplifying any of them without
> validation will likely crash generation or produce garbage audio. Treat them as critical.

## Why this exists

qwen-tts==0.1.1 was designed for transformers 4.x. We’re using transformers 5.x for CVE-2026-1839.
The Dockerfile and runtime code monkeypatch several internal behaviors to keep things working.

## qwen-tts installed --no-deps

- `qwen-tts==0.1.1` hard-pins `transformers==4.57.3`.
- Dockerfile installs it `--no-deps`, then separately installs `transformers==5.12.1`.
- All code in qwen_tts is NOT fully validated under T5; these patches compensate.

## Dockerfile sed patches

- speech_vq.py:
  - Overrides `intra_op_num_threads` from 1 to 6 for ONNX Runtime.
  - Fragile: depends on exact string; future qwen-tts releases may break this.
- modeling_qwen3_tts_tokenizer_v2.py:
  - Strips `@check_model_inputs` decorator that breaks under T5.
- modeling_mimi.py:
  - Renames `create_sliding_window_causal_mask` → `create_causal_mask` due to T5 symbol changes.

## Python patches in modeling_qwen3_tts.py

- Replaces direct use of initialization helpers with explicit imports (`from transformers import initialization as init`).
- Replaces `module.weight.data.normal_` / `zero_` / `fill_` calls with `init.normal_`, `init.zeros_`, `init.ones_`.
- Adds guard for `padding_idx` to avoid errors on meta-device init.
- Replaces `input_embeds` / `"input_embeds"` with `inputs_embeds` / `"inputs_embeds"`.
- Removes incompatible `cache_position` passes in new signatures.

## Configuration patch in configuration_qwen3_tts.py

- Removes `layer_type_validation` import from T4; substitutes `self.validate_layer_type()`.

## RoPE / rotary buffers (transformers_compat.py + Dockerfile rope_utils patch)

- qwen-tts registers `inv_freq` as non-persistent; T5 can materialize it uninitialized on meta-device.
- `repair_rotary_buffers`:
  - Recomputes `inv_freq` from the `rope_init_fn` and validates it (finite, positive, decreasing, starts at 1.0 for default type).
  - Required after every model load under T5.
- Dockerfile injects custom `_compute_default_rope_parameters` into `modeling_rope_utils` and sets `"default"` as init function, because T5 changed how RoPE is wired.

## Talker prepare_inputs_for_generation patch (transformers_compat.py)

Applied at model-load time (for both backends) via `patch_talker_prepare_inputs()`.
Two issues in one patch:

- **Stale inputs_embeds bug (TTS_BACKEND=pytorch crash):**
  T5's centralised `prepare_inputs_for_generation` forwards all model_kwargs,
  including the original long-sequence `inputs_embeds` from step 1, into every
  decode step. The talker's `forward` uses `inputs_embeds.shape[1] > 1` to detect
  prefill; with stale (B, 171, 2048) embeds on a 1-token decode step, it re-enters
  the prefill path with a wrong mask vs. accumulated K/V → attention corruption →
  `attn_output` reshape produces (B, seq*hidden) → matmul crash at o_proj.
  Fix: drop `inputs_embeds` from model_inputs on non-first iterations.

- **Full input_ids on decode steps:**
  T5 passes the accumulated (B, N) `input_ids` instead of just the last token.
  The talker uses `input_ids.shape[1]` for RoPE + codec embedding; N>1 produces
  garbage RoPE/logits, EOS ≈ 0, runs to capacity.
  Fix: clip `input_ids` to `[:, -1:]` in decode steps (past_key_values present,
  not first iteration).

CRITICAL: reverting either fix under T5 will crash (pytorch) or produce
non-terminating/garbage generation (both backends).

## Agent rule

- If bumping transformers, qwen-tts, or related deps, assume these patches need review and retesting.
- Do not “clean up” these patches unless you’ve proven they’re no longer needed with a full run.

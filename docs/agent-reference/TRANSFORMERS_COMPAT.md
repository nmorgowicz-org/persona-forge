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

## OVTalkerRuntime patch (talker.py _patch_talker_prepare_inputs)

- T5 now passes full accumulated `input_ids` instead of last token during decode.
- qwen3_tts's talker uses `input_ids.shape[1]` as seq_length for RoPE + codec embedding.
- Without clipping, all past tokens are treated as current → garbage RoPE/logits, EOS ≈ 0, runs to capacity.
- Fix: monkeypatch `prepare_inputs_for_generation` to clip `input_ids` to `[:, -1:]` in decode steps.
- CRITICAL: reverting this under T5 will cause non-terminating generation.

## Agent rule

- If bumping transformers, qwen-tts, or related deps, assume these patches need review and retesting.
- Do not “clean up” these patches unless you’ve proven they’re no longer needed with a full run.

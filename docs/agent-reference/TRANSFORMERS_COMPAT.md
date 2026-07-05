# Transformers 5 Compatibility Hacks — Agent Reference

> These patches are fragile and non-obvious. Removing or simplifying any of them without
> validation will likely crash generation or produce garbage audio. Treat them as critical.

## Why this exists

qwen-tts==0.1.1 was designed for transformers 4.x. We're using transformers 5.12.1 for
CVE-2026-1839. The Dockerfile and runtime code monkeypatch several internal behaviors to
keep both backends (OpenVINO and PyTorch) working.

Both `TTS_BACKEND=openvino` and `TTS_BACKEND=pytorch` are working under transformers 5.12.1
with these patches in place.

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
- modeling_rope_utils.py:
  - Injects custom `_compute_default_rope_parameters` and sets `"default"` as init function
    because T5 changed how RoPE is wired.

## Python patches in modeling_qwen3_tts.py (via Dockerfile)

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
- Dockerfile injects custom `_compute_default_rope_parameters` into `modeling_rope_utils` and sets `"default"` as init function.

## Talker prepare_inputs_for_generation patch (transformers_compat.py)

Applied at model-load time (for both backends) via `patch_talker_prepare_inputs()`.
Three issues fixed in one patch:

- **Stale inputs_embeds bug (primary crash cause for PyTorch backend):**
  T5's centralized `prepare_inputs_for_generation` forwards all model_kwargs,
  including the original long-sequence `inputs_embeds` from step 1, into every
  decode step. The talker's `forward` uses `inputs_embeds.shape[1] > 1` to detect
  prefill; with stale embeds on a 1-token decode step, it re-enters the prefill path
  → wrong masks vs. K/V cache → attention corruption → matmul crash.
  Fix: drop `inputs_embeds` from model_inputs on non-first iterations.

- **Full input_ids on decode steps:**
  T5 passes the accumulated (B, N) `input_ids` instead of just the last token.
  The talker uses `input_ids.shape[1]` for RoPE + codec embedding; N>1 produces
  garbage RoPE/logits, EOS ≈ 0, runs to capacity.
  Fix: clip `input_ids` to `[:, -1:]` in decode steps.

- **Stale attention_mask leak:**
  A prefill attention_mask (e.g. (1, 171)) leaks into decode steps and corrupts
  causal mask creation and Q/K/V lengths.
  Fix: pop `attention_mask` from model_inputs on non-first iterations.

CRITICAL: reverting any of these fixes under T5 will crash (pytorch) or produce
non-terminating/garbage generation (both backends).

## Attention mask broadcast fix (transformers_compat.py, PyTorch backend)

Applied at model-load time via `patch_eager_attention_mask_broadcast()`.

- **sdpa_attention_forward stale-mask slicing:**
  If a 4D attention_mask's Q/K dimensions don't match the current query and key
  lengths, it is sliced to match. Without this, stale masks from prefill cause
  shape mismatches in SDPA attention.

- **create_causal_mask / create_sliding_window_causal_mask decode-mode bypass:**
  In decode mode (single-token input with existing cache), return `None` instead
  of building a mask. This avoids stale prefill-length masks being used to create
  incorrect causal masks. Patches `transformers.masking_utils`, `modeling_qwen3_tts`,
  and the tokenizer module which has its own imports.

## Agent rule

- If bumping transformers, qwen-tts, or related deps, assume these patches need review and retesting.
- Do not "clean up" these patches unless you've proven they're no longer needed with a full run
  on both backends.
"""Compatibility repairs for qwen-tts objects loaded under Transformers 5."""

from __future__ import annotations

import functools


def repair_rotary_buffers(root, torch) -> list[dict[str, object]]:
    """Recompute non-persistent RoPE buffers after meta-device model loading.

    qwen-tts registers ``inv_freq`` with ``persistent=False``, so it is absent from the
    checkpoint. Transformers 5 can construct that buffer on the meta device and later
    materialize it as uninitialized storage. A merely finite check is insufficient: the
    observed corruption used the finite FP16 extrema (-65504, 65504). Recompute from the
    module's own config/initializer and fail closed on the default-RoPE invariants.
    """
    repaired = []
    for name, module in root.named_modules():
        initializer = getattr(module, "rope_init_fn", None)
        config = getattr(module, "config", None)
        if not callable(initializer) or config is None or not hasattr(module, "inv_freq"):
            continue
        inv_freq, attention_scaling = initializer(config, torch.device("cpu"))
        inv_freq = inv_freq.detach().to(device="cpu", dtype=torch.float32).contiguous()
        if inv_freq.ndim != 1 or inv_freq.numel() == 0:
            raise RuntimeError(f"invalid RoPE inv_freq shape for {name}: {tuple(inv_freq.shape)}")
        if not bool(torch.isfinite(inv_freq).all()) or not bool((inv_freq > 0).all()):
            raise RuntimeError(f"non-finite/non-positive RoPE inv_freq after repair for {name}")
        rope_type = getattr(module, "rope_type", "default")
        if rope_type == "default" and inv_freq.numel() > 1:
            if not bool((inv_freq[:-1] > inv_freq[1:]).all()):
                raise RuntimeError(f"default RoPE inv_freq is not strictly decreasing for {name}")
            if not bool(torch.isclose(inv_freq[0], torch.tensor(1.0))):
                raise RuntimeError(f"default RoPE inv_freq does not start at 1.0 for {name}")
        module.inv_freq = inv_freq
        module.original_inv_freq = inv_freq.clone()
        module.attention_scaling = attention_scaling
        repaired.append(
            {
                "module": name,
                "rope_type": rope_type,
                "length": inv_freq.numel(),
                "min": float(inv_freq.min()),
                "max": float(inv_freq.max()),
            }
        )
    if not repaired:
        raise RuntimeError("no rotary embedding buffers found to repair")
    return repaired


def patch_talker_prepare_inputs() -> None:
    """Fix two transformers 5.x issues in the talker's prepare_inputs_for_generation.

    1) Stale inputs_embeds leak:
       Transformers 5.x centralised prepare_inputs_for_generation into GenerationMixin.
       On decode steps, it forwards all model_kwargs, including the original long
       inputs_embeds from step 1. Qwen3TTSTalkerForConditionalGeneration.forward
       uses ``inputs_embeds.shape[1] > 1`` to decide "prefill path". With stale
       (B, 171, 2048) embeds on a 1-token decode step, this causes:
       - Wrong attention mask (q_length=171 vs accumulated kv_length)
       - Corrupted attn_output reshape → (B, seq*hidden) → matmul crash.

       Fix: drop inputs_embeds from model_kwargs on non-first steps.

    2) Full input_ids on decode steps:
       T5 passes the accumulated (B, N) input_ids instead of just the last token.
       The talker uses input_ids.shape[1] for RoPE and codec-embedding, so N>1
       produces garbage RoPE/logits and non-terminating generation.

       Fix: clip input_ids to last token on decode steps (past_key_values not None,
       not first iteration).
    """
    from qwen_tts.core.models import modeling_qwen3_tts as M
    from qwen_tts.core.models.modeling_qwen3_tts import (
        Qwen3TTSTalkerCodePredictorModelForConditionalGeneration,
        Qwen3TTSTalkerForConditionalGeneration,
    )

    _base_talker_pigf = Qwen3TTSTalkerForConditionalGeneration.prepare_inputs_for_generation
    _base_predictor_pigf = Qwen3TTSTalkerCodePredictorModelForConditionalGeneration.prepare_inputs_for_generation

    call_count = 0

    def _fixed_pigf(cls_label, base_fn, self_inner, input_ids,
                    past_key_values=None, inputs_embeds=None,
                    is_first_iteration=None, **kwargs):
        nonlocal call_count
        call_count += 1

        # First iteration (prefill): delegate fully to transformers.
        if is_first_iteration:
            if call_count == 1:
                print(
                    f"[diag] {cls_label} prepare_inputs step={call_count} mode=prefill "
                    f"input_ids={tuple(input_ids.shape) if input_ids is not None else None} "
                    f"inputs_embeds={tuple(inputs_embeds.shape) if inputs_embeds is not None else None}",
                    flush=True,
                )
            return base_fn(self_inner, input_ids=input_ids,
                           past_key_values=past_key_values,
                           inputs_embeds=inputs_embeds,
                           is_first_iteration=is_first_iteration,
                           **kwargs)

        # Decode step: clip input_ids to last token (required under T5).
        if (
            past_key_values is not None
            and input_ids is not None
            and input_ids.shape[1] > 1
        ):
            input_ids = input_ids[:, -1:]

        # Call the base, then remove stale inputs_embeds so forward() does not
        # mistake this decode step for a prefill.
        model_inputs = base_fn(self_inner, input_ids=input_ids,
                               past_key_values=past_key_values,
                               inputs_embeds=inputs_embeds,
                               is_first_iteration=is_first_iteration,
                               **kwargs)

        # Log first few decode steps
        if call_count <= 5:
            has_embeds_before = "inputs_embeds" in model_inputs
            print(
                f"[diag] {cls_label} prepare_inputs step={call_count} mode=decode "
                f"input_ids={tuple(input_ids.shape) if input_ids is not None else None} "
                f"inputs_embeds_before_pop={tuple(model_inputs.get('inputs_embeds').shape) if has_embeds_before else None} "
                f"has_embeds_before={has_embeds_before}",
                flush=True,
            )

        model_inputs.pop("inputs_embeds", None)

        # During decode, the prefill attention_mask (4D, e.g. B,1,170,170) leaks into
        # SDPA which broadcasts it wrongly, producing garbage shapes. For single-token
        # decode steps we rely on SDPA's causal masking instead.
        if "attention_mask" in model_inputs:
            mask = model_inputs["attention_mask"]
            if mask.dim() == 4 and mask.shape[2] > 1:
                model_inputs.pop("attention_mask")

        return model_inputs

    @functools.wraps(_base_talker_pigf)
    def _talker_fixed_pigf(self, input_ids, past_key_values=None,
                           inputs_embeds=None, is_first_iteration=None, **kwargs):
        return _fixed_pigf("talker", _base_talker_pigf, self, input_ids,
                           past_key_values, inputs_embeds,
                           is_first_iteration, **kwargs)

    @functools.wraps(_base_predictor_pigf)
    def _predictor_fixed_pigf(self, input_ids, past_key_values=None,
                              inputs_embeds=None, is_first_iteration=None, **kwargs):
        return _fixed_pigf("predictor", _base_predictor_pigf, self, input_ids,
                           past_key_values, inputs_embeds,
                           is_first_iteration, **kwargs)

    Qwen3TTSTalkerForConditionalGeneration.prepare_inputs_for_generation = _talker_fixed_pigf
    Qwen3TTSTalkerCodePredictorModelForConditionalGeneration.prepare_inputs_for_generation = _predictor_fixed_pigf
    print(
        "[transformers_compat] patched talker and code predictor "
        "prepare_inputs_for_generation (T5 stale-embeds + input_ids clip + attention_mask fix)",
        flush=True,
    )




def patch_eager_attention_mask_broadcast() -> None:
    """Fix attention_mask issues in PyTorch backend.

    Two problems during T5-style decode (auto-regressive generation with cache):

    1) Stale 4D attention_mask from prefill:
       - Prefill creates a mask (B,1,170,170)
       - Decode passes it unchanged instead of updating for (B,1,1,171)
       - SDPA broadcasts it wrong, producing garbage shapes and matmul crash
       - 350208 = 170 * 2048 (pre-fill seq * hidden)
       - Fix: patch sdpa_attention_forward to slice 4D mask to current Q/K lengths.

    2) create_causal_mask with None attention_mask:
       - Our prepare_inputs_for_generation patches pop the 4D mask to avoid (1)
       - create_causal_mask then gets attention_mask=None in decode
       - In some transformers 5.x / qwen_tts configs, this creates a wrong mask
       - Fix: monkeypatch create_causal_mask to force a clean causal mask
         when in decode mode (single-token inputs, cache present).
    """
    from qwen_tts.core.models import modeling_qwen3_tts as M
    import torch

    # 1) Patch sdpa_attention_forward for stale-mask slicing
    from transformers.integrations import sdpa_attention

    orig_sdpa = sdpa_attention.sdpa_attention_forward

    @functools.wraps(orig_sdpa)
    def patched_sdpa_attention_forward(
        module,
        query,
        key,
        value,
        attention_mask,
        scaling,
        dropout=0.0,
        **kwargs,
    ):
        if (
            attention_mask is not None
            and attention_mask.dim() == 4
            and query.dim() == 4
        ):
            q_len, k_len = query.shape[2], key.shape[3]
            if (
                attention_mask.shape[2] != q_len
                or attention_mask.shape[3] != k_len
            ):
                attention_mask = attention_mask[:, :, :q_len, :k_len]

        return orig_sdpa(
            module,
            query,
            key,
            value,
            attention_mask,
            scaling,
            dropout,
            **kwargs,
        )

    sdpa_attention.sdpa_attention_forward = patched_sdpa_attention_forward

    # 2) Patch create_causal_mask to ensure correct decode-time masks
    orig_create_causal_mask = M.create_causal_mask

    @functools.wraps(orig_create_causal_mask)
    def patched_create_causal_mask(
        config,
        inputs_embeds,
        attention_mask,
        past_key_values=None,
        position_ids=None,
        **kwargs,
    ):
        # If we're in decode mode (single-token input with cache present)
        # and attention_mask is None, the upstream implementation may produce
        # an incorrect mask shape for T5-style generation. Force a clean
        # causal mask: (B, 1, q_len, kv_len) where q_len = 1.
        is_decode = (
            inputs_embeds.shape[1] == 1
            and past_key_values is not None
        )
        if is_decode:
            if not hasattr(patched_create_causal_mask, "_diag"):
                patched_create_causal_mask._diag = True
                print(
                    f"[decode_mask_fix] decode-mode detected: "
                    f"inputs={tuple(inputs_embeds.shape)} past_len={past_key_values.get_seq_length()}",
                    flush=True,
                )
            # Full attention on all keys (past + current): upper-triangular is
            # handled by SDPA's is_causal=True when mask is None. Return None
            # to let the attention kernel use its native causal behavior.
            return None

        return orig_create_causal_mask(
            config,
            inputs_embeds,
            attention_mask,
            past_key_values=past_key_values,
            position_ids=position_ids,
            **kwargs,
        )

    M.create_causal_mask = patched_create_causal_mask
    print(
        "[transformers_compat] patched sdpa_attention_forward and "
        "create_causal_mask (PyTorch decode mask fix)",
        flush=True,
    )

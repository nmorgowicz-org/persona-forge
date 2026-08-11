"""Compatibility repairs for qwen-tts objects loaded under Transformers 5."""

from __future__ import annotations

import functools
import logging

logger = logging.getLogger(__name__)

_patch_talker_prepare_inputs_applied = False
_patch_eager_attention_mask_broadcast_applied = False

def repair_rotary_buffers(root, torch) -> list[dict[str, object]]:
    """Recompute non-persistent RoPE buffers after meta-device model loading."""
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
    """Fix transformers 5.x T5-style decode issues.

    Problems during auto-regressive generation with cache:

    1) Stale inputs_embeds leak:
       Transformers 5.x forwards the original long inputs_embeds from step 1 into
       all decode steps. Qwen3TTSTalkerForConditionalGeneration.forward uses
       inputs_embeds.shape[1] > 1 to choose the prefill path. With stale (B, L, D)
       embeds on a 1-token decode step, it reconstructs a full-length inputs_embeds
       instead of a single-token one, causing Q/K/V length mismatches and crashes.

    2) Full input_ids on decode steps:
       T5-style generation passes accumulated (B, N) input_ids instead of just the
       last token. The talker uses input_ids.shape[1] for RoPE and codec-embedding,
       so N>1 produces garbage RoPE/logits and non-terminating generation.

    3) Stale attention_mask:
       A prefill attention_mask (e.g. (1, 171)) leaks into decode steps where the
       model is only processing 1 token. The create_causal_mask and attention layers
       use this stale mask length to create wrong masks, leading to shape mismatches
       in the attention output (e.g. Q=171, K=341, V=171 instead of Q=1, K=171, V=171).
    """
    global _patch_talker_prepare_inputs_applied
    if _patch_talker_prepare_inputs_applied:
        return
    _patch_talker_prepare_inputs_applied = True

    from qwen_tts.core.models.modeling_qwen3_tts import (
        Qwen3TTSTalkerCodePredictorModelForConditionalGeneration,
        Qwen3TTSTalkerForConditionalGeneration,
    )

    _base_talker_pigf = Qwen3TTSTalkerForConditionalGeneration.prepare_inputs_for_generation
    _base_predictor_pigf = Qwen3TTSTalkerCodePredictorModelForConditionalGeneration.prepare_inputs_for_generation

    def _fixed_pigf(cls_label, base_fn, self_inner, input_ids,
                    past_key_values=None, inputs_embeds=None,
                    is_first_iteration=None, **kwargs):
        # First iteration (prefill): delegate fully to transformers.
        if is_first_iteration:
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

        # Call the base, then clean up stale items.
        model_inputs = base_fn(self_inner, input_ids=input_ids,
                               past_key_values=past_key_values,
                               inputs_embeds=inputs_embeds,
                               is_first_iteration=is_first_iteration,
                               **kwargs)

        # Pop stale inputs_embeds so forward() does not take the prefill path.
        model_inputs.pop("inputs_embeds", None)

        # Pop stale attention_mask (1D/2D/4D) from prefill.
        # During decode, relying on past_key_values + causal masking is sufficient.
        # A stale attention_mask with the prefill length corrupts causal mask creation
        # and causes Q/K/V length mismatches in the attention layer.
        if "attention_mask" in model_inputs:
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


def patch_eager_attention_mask_broadcast() -> None:
    """Defensive patches for attention_mask issues in PyTorch backend.

    1) Slice stale 4D masks in sdpa_attention_forward and eager_attention_forward.
    2) Return None from create_causal_mask in decode mode to avoid
       stale-mask-based causal masks (create_sliding_window_causal_mask is
       always computed for real, since a sliding-window layer cannot safely
       skip masking once the cache outgrows the window).
    """
    global _patch_eager_attention_mask_broadcast_applied
    if _patch_eager_attention_mask_broadcast_applied:
        return
    _patch_eager_attention_mask_broadcast_applied = True

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
            q_len, k_len = query.shape[2], key.shape[2]
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

    # 1b) Patch eager_attention_forward for the same stale-mask slicing. qwen_tts
    # defines its own eager_attention_forward (not routed through
    # transformers.integrations), and its own mask slicing only trims the key
    # dimension (`attention_mask[:, :, :, :key_states.shape[-2]]`), leaving a
    # stale query dimension that silently broadcasts to the wrong shape instead
    # of raising, corrupting attention output whenever config._attn_implementation
    # == "eager".
    orig_eager = M.eager_attention_forward

    @functools.wraps(orig_eager)
    def patched_eager_attention_forward(
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
            q_len, k_len = query.shape[2], key.shape[2]
            if (
                attention_mask.shape[2] != q_len
                or attention_mask.shape[3] != k_len
            ):
                attention_mask = attention_mask[:, :, :q_len, :k_len]

        return orig_eager(
            module,
            query,
            key,
            value,
            attention_mask,
            scaling,
            dropout,
            **kwargs,
        )

    M.eager_attention_forward = patched_eager_attention_forward

    # 2) Patch create_causal_mask and create_sliding_window_causal_mask
    from transformers import masking_utils

    def _make_decode_mask_patch(orig_fn, skip_on_decode):
        @functools.wraps(orig_fn)
        def patched_fn(**kwargs):
            # Handle both "inputs_embeds" (correct) and "input_embeds" (qwen_tts tokenizer bug).
            inputs_embeds = kwargs.get("inputs_embeds")
            if inputs_embeds is None:
                inputs_embeds = kwargs.get("input_embeds")
            past_key_values = kwargs.get("past_key_values")

            # In decode mode (single-token input with existing cache), skip mask creation.
            # Only safe for full causal attention: with no mask, SDPA attends over the
            # whole cache, which is correct for causal layers but wrong for
            # sliding-window layers once the cache exceeds the window — those still
            # need a real mask computed below.
            if (
                skip_on_decode
                and inputs_embeds is not None
                and inputs_embeds.shape[1] == 1
                and past_key_values is not None
            ):
                return None

            # Normalize for the original transformers create_causal_mask:
            # - qwen_tts tokenizer uses "input_embeds" instead of "inputs_embeds"
            # - also passes "cache_position" which the original doesn't accept
            call_kwargs = {
                "config": kwargs.get("config"),
                "inputs_embeds": inputs_embeds,
                "attention_mask": kwargs.get("attention_mask"),
                "past_key_values": past_key_values,
                "position_ids": kwargs.get("position_ids"),
            }
            return orig_fn(**call_kwargs)

        return patched_fn

    masking_utils.create_causal_mask = _make_decode_mask_patch(
        masking_utils.create_causal_mask, skip_on_decode=True
    )
    masking_utils.create_sliding_window_causal_mask = _make_decode_mask_patch(
        masking_utils.create_sliding_window_causal_mask, skip_on_decode=False
    )
    M.create_causal_mask = masking_utils.create_causal_mask
    M.create_sliding_window_causal_mask = masking_utils.create_sliding_window_causal_mask

    # Patch tokenizer module which has its own import and uses "input_embeds" (typo).
    try:
        from qwen_tts.core.tokenizer_12hz import modeling_qwen3_tts_tokenizer_v2 as T
        T.create_causal_mask = masking_utils.create_causal_mask
        T.create_sliding_window_causal_mask = masking_utils.create_sliding_window_causal_mask
        T.eager_attention_forward = patched_eager_attention_forward
    except Exception:
        logger.exception(
            "Failed to apply attention-mask compat patches to qwen_tts "
            "tokenizer_12hz module; if its internals changed, the stale-mask "
            "broadcast/shape bug this patch guards against may resurface."
        )

"""Tensor-only wrappers around the two Qwen3-TTS transformer cores for OpenVINO export.

`openvino.convert_model` traces a plain `torch.nn.Module`. These wrappers exist so the
trace never sees a transformers `Cache` object: each wrapper accepts flat tensors and
returns flat tensors, rebuilding/extracting the `DynamicCache` internally.

Per-core forward contract (verified against qwen-tts==0.1.1, transformers 4.57.3):

    inputs:  inputs_embeds      [batch, seq, hidden]
             attention_mask     [batch, total_seq]      (prefill seq, or prior+1 on decode)
             position_ids       [batch, seq]            (the core expands to the 3-axis
                                                          mRoPE layout internally)
             cache_position     [seq]                   (passed explicitly so the decode
                                                          graph stays dynamic in prior length)
             *past_kv           2*num_layers tensors    (empty for the prefill graph)
                                 each K/V is [batch, num_kv_heads, prior_seq, head_dim]
    outputs: last_hidden_state  [batch, seq, hidden]
             *present_kv         2*num_layers tensors, ordered k0, v0, k1, v1, ...

Two graphs are exported per core from this one wrapper, differing only by example input:
  - prefill: no past_kv, dynamic `seq`
  - decode:  one-token `seq`, explicit prior past_kv

Embedding lookups and codebook output heads stay in PyTorch (implementation plan).

NOT YET VERIFIED — must be locked down by the Milestone 2 FP32 parity gate on dockermisc1:
  * That the `position_ids` / `cache_position` values fed here match exactly what the
    eager generation path passes at prefill and at every decode step (the main core uses
    a 3-axis mRoPE expansion; greedy top-1 token agreement is the gate).
  * Predictor specifics: its core forward also accepts `generation_steps`; the predictor
    cache resets every audio frame and runs 15 codebook steps. See PredictorCoreWrapper.
"""

from __future__ import annotations

import torch
import torch.nn as nn
from transformers.cache_utils import DynamicCache


class CoreCacheWrapper(nn.Module):
    """Wrap a Qwen3-TTS transformer core with flat-tensor cache in/out."""

    def __init__(self, core: nn.Module, num_layers: int) -> None:
        super().__init__()
        self.core = core
        self.num_layers = num_layers

    def _build_cache(self, past_kv: tuple[torch.Tensor, ...]) -> DynamicCache:
        if not past_kv:
            return DynamicCache()
        if len(past_kv) != 2 * self.num_layers:
            raise ValueError(
                f"expected {2 * self.num_layers} past K/V tensors, got {len(past_kv)}"
            )
        legacy = tuple(
            (past_kv[2 * i], past_kv[2 * i + 1]) for i in range(self.num_layers)
        )
        return DynamicCache.from_legacy_cache(legacy)

    @staticmethod
    def _flatten_present(cache: DynamicCache) -> list[torch.Tensor]:
        present: list[torch.Tensor] = []
        for key, value in cache.to_legacy_cache():
            present.append(key)
            present.append(value)
        return present

    def _run_core(self, *, inputs_embeds, attention_mask, position_ids, cache_position, cache, **extra):
        return self.core(
            inputs_embeds=inputs_embeds,
            attention_mask=attention_mask,
            position_ids=position_ids,
            cache_position=cache_position,
            past_key_values=cache,
            use_cache=True,
            **extra,
        )

    def forward(self, inputs_embeds, attention_mask, position_ids, cache_position, *past_kv):
        cache = self._build_cache(past_kv)
        out = self._run_core(
            inputs_embeds=inputs_embeds,
            attention_mask=attention_mask,
            position_ids=position_ids,
            cache_position=cache_position,
            cache=cache,
        )
        return (out.last_hidden_state, *self._flatten_present(out.past_key_values))


class MainCoreWrapper(CoreCacheWrapper):
    """Wraps `talker.model` — the 28-layer main transformer (0.6B)."""


class PredictorCoreWrapper(CoreCacheWrapper):
    """Wraps `talker.code_predictor.model` — the 5-layer code-predictor transformer.

    The predictor core forward additionally accepts `generation_steps`. It is exposed as
    an explicit input so the per-codebook step index is not baked into the traced graph.
    Parity must confirm how the eager path supplies it across the 15 codebook steps.
    """

    def forward(self, inputs_embeds, attention_mask, position_ids, cache_position, generation_steps, *past_kv):
        cache = self._build_cache(past_kv)
        out = self._run_core(
            inputs_embeds=inputs_embeds,
            attention_mask=attention_mask,
            position_ids=position_ids,
            cache_position=cache_position,
            cache=cache,
            generation_steps=generation_steps,
        )
        return (out.last_hidden_state, *self._flatten_present(out.past_key_values))


def core_dims(core_config) -> dict[str, int]:
    """Derive export shapes from a core's config. Never hard-code these."""

    hidden = core_config.hidden_size
    n_heads = core_config.num_attention_heads
    head_dim = getattr(core_config, "head_dim", None) or (hidden // n_heads)
    return {
        "num_layers": core_config.num_hidden_layers,
        "hidden_size": hidden,
        "num_kv_heads": core_config.num_key_value_heads,
        "head_dim": head_dim,
    }

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

Causal mask strategy (critical for dynamic-shape correctness):
  Both model forwards call `create_causal_mask(... past_key_values=cache ...)`, which
  internally calls `cache.get_mask_sizes()` → returns a Python int at trace time → that
  integer is baked into the IR as a static constant. The decode graph would always emit
  a mask of size (example prior + 1), breaking inference at any other cache length.

  Fix: `_build_causal_mask` constructs a 4D additive mask from tensor shape operations
  only. Passing it as `attention_mask` triggers `_preprocess_mask_arguments`'s early-exit
  path (transformers 4.57.3, line: `if isinstance(m, Tensor) and len(m.shape) == 4: ...`)
  so `create_causal_mask` returns it unchanged and no Python integer from the cache is
  ever used. This works identically for both model forwards.

NOT YET CONFIRMED on dockermisc1 (Milestone 2 parity gate):
  * That `position_ids` / `cache_position` values match the eager generation path exactly
    (the main core uses 3-axis mRoPE expansion; top-1 token agreement is the gate).
  * Predictor specifics: the base model's forward accepts but ignores `generation_steps`;
    the cache resets every audio frame and runs 15 codebook steps. See PredictorCoreWrapper.
"""

from __future__ import annotations

import torch
import torch.nn as nn
from transformers.cache_utils import DynamicCache
from transformers.cache_utils import DynamicLayer


class _OVDynamicLayer(DynamicLayer):
    """DynamicLayer whose lazy_initialization starts with a rank-4 zero-length tensor.

    The default implementation uses `torch.tensor([])` (shape [0], rank 1).  PyTorch
    allows `torch.cat([rank-1-empty, rank-4-keys], dim=-2)` as a special case, but
    OpenVINO's converter validates axis bounds against each input's rank independently
    and rejects axis -2 for a rank-1 tensor (valid range: [-1, 0]).  Slicing to
    `[..., :0, :]` gives a rank-4 empty tensor so the cat is always rank-safe.
    """

    def lazy_initialization(self, key_states: torch.Tensor) -> None:
        self.dtype = key_states.dtype
        self.device = key_states.device
        empty = key_states[..., :0, :]   # [batch, kv_heads, 0, head_dim] — rank 4
        self.keys = empty
        self.values = empty
        self.is_initialized = True


class _OVDynamicCache(DynamicCache):
    """DynamicCache that uses _OVDynamicLayer so every aten::cat in the trace is rank-safe."""

    layer_class_to_replicate = _OVDynamicLayer


class CoreCacheWrapper(nn.Module):
    """Wrap a Qwen3-TTS transformer core with flat-tensor cache in/out."""

    def __init__(self, core: nn.Module, num_layers: int) -> None:
        super().__init__()
        self.core = core
        self.num_layers = num_layers

    def _build_cache(self, past_kv: tuple[torch.Tensor, ...]) -> DynamicCache:
        if not past_kv:
            return _OVDynamicCache()
        if len(past_kv) != 2 * self.num_layers:
            raise ValueError(
                f"expected {2 * self.num_layers} past K/V tensors, got {len(past_kv)}"
            )
        legacy = tuple(
            (past_kv[2 * i], past_kv[2 * i + 1]) for i in range(self.num_layers)
        )
        return _OVDynamicCache.from_legacy_cache(legacy)

    @staticmethod
    def _flatten_present(cache: DynamicCache) -> list[torch.Tensor]:
        present: list[torch.Tensor] = []
        for key, value in cache.to_legacy_cache():
            present.append(key)
            present.append(value)
        return present

    @staticmethod
    def _build_causal_mask(
        attention_mask: torch.Tensor,
        cache_position: torch.Tensor,
        inputs_embeds: torch.Tensor,
    ) -> torch.Tensor:
        """Build a 4-D additive causal mask from a 2-D padding mask and cache positions.

        Returns [batch, 1, seq_q, total_seq] with 0 for attended and -inf for masked.
        Passing a 4-D tensor as attention_mask to create_causal_mask triggers its early-exit
        path, so the total_seq dimension stays dynamic in the exported IR.
        """
        dtype = inputs_embeds.dtype
        device = inputs_embeds.device
        q_pos = cache_position[:, None]                                    # [seq_q, 1]
        k_pos = torch.arange(attention_mask.shape[-1], device=device)[None, :]  # [1, total_seq]
        causal_ok = k_pos <= q_pos                                         # [seq_q, total_seq]
        pad_ok = attention_mask.bool()                                     # [batch, total_seq]
        combined = causal_ok[None, None] & pad_ok[:, None, None, :]       # [batch, 1, seq_q, total_seq]
        zero = torch.zeros((), device=device, dtype=dtype)
        neg_inf = torch.full((), torch.finfo(dtype).min, device=device, dtype=dtype)
        return torch.where(combined, zero, neg_inf)

    def _run_core(self, *, inputs_embeds, attention_mask, position_ids, cache_position, cache, **extra):
        mask_4d = self._build_causal_mask(attention_mask, cache_position, inputs_embeds)
        return self.core(
            inputs_embeds=inputs_embeds,
            attention_mask=mask_4d,
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


class VocoderDecoderWrapper(nn.Module):
    """Wraps `speech_tokenizer.model.decoder` for OpenVINO export.

    Verified against qwen-tts==0.1.1 (Milestone 1.5):

        forward(codes) -> wav

        codes:  [batch, num_quantizers=16, seq_len]  int64   (VQ codebook indices, 0..2047)
        wav:    [batch, 1, audio_samples]             float32 (clamped to [-1, 1])

    The exported graph uses a fixed 325-frame input: a 300-frame chunk plus the decoder's
    25-frame left context. Runtime code right-pads shorter chunks with code 0 and crops the
    causal decoder output to the original frame count.

    The chunked_decode loop (chunk_size=300, left_context=25) stays in Python; only the
    per-chunk Decoder.forward call is exported. total_upsample = prod((8,5,4,3)+(2,2)) = 1920
    samples per input frame at 24 kHz output.

    No KV cache, no position IDs — the VQ lookup and conv/GAN decoder are fully feed-forward.
    """

    def __init__(self, decoder: nn.Module) -> None:
        super().__init__()
        self.decoder = decoder

    @staticmethod
    def _attention_masks(hidden: torch.Tensor, sliding_window: int) -> dict[str, torch.Tensor]:
        """Build traceable 4-D additive causal and sliding-window masks."""
        seq_len = hidden.shape[1]
        positions = torch.arange(seq_len, device=hidden.device)
        query = positions[:, None]
        key = positions[None, :]
        causal_allowed = key <= query
        sliding_allowed = causal_allowed & (key > query - sliding_window)
        min_value = torch.finfo(hidden.dtype).min
        zero = torch.zeros((), device=hidden.device, dtype=hidden.dtype)
        blocked = torch.full((), min_value, device=hidden.device, dtype=hidden.dtype)

        def additive(allowed: torch.Tensor) -> torch.Tensor:
            mask = torch.where(allowed, zero, blocked)
            return mask[None, None, :, :].expand(hidden.shape[0], 1, seq_len, seq_len)

        return {
            "full_attention": additive(causal_allowed),
            "sliding_attention": additive(sliding_allowed),
        }

    def forward(self, codes: torch.Tensor) -> torch.Tensor:
        if codes.shape[1] != self.decoder.config.num_quantizers:
            raise ValueError(
                f"expected {self.decoder.config.num_quantizers} codebooks, got {codes.shape[1]}"
            )

        hidden = self.decoder.quantizer.decode(codes)
        hidden = self.decoder.pre_conv(hidden).transpose(1, 2)
        masks = self._attention_masks(hidden, self.decoder.config.sliding_window)
        hidden = self.decoder.pre_transformer(
            inputs_embeds=hidden,
            attention_mask=masks,
        ).last_hidden_state
        hidden = hidden.permute(0, 2, 1)
        for blocks in self.decoder.upsample:
            for block in blocks:
                hidden = block(hidden)
        wav = hidden
        for block in self.decoder.decoder:
            wav = block(wav)
        return wav.clamp(min=-1, max=1)


def vocoder_dims(decoder_config) -> dict[str, int]:
    """Derive export-relevant dimensions from Qwen3TTSTokenizerV2DecoderConfig."""
    import numpy as np
    return {
        "num_quantizers": decoder_config.num_quantizers,
        "codebook_size": decoder_config.codebook_size,
        "total_upsample": int(np.prod(list(decoder_config.upsample_rates) + list(decoder_config.upsampling_ratios))),
    }

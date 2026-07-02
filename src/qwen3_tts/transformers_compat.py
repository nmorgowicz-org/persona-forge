"""Compatibility repairs for qwen-tts objects loaded under Transformers 5."""

from __future__ import annotations


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

"""Model-size presets — the single ``MODEL_SIZE`` knob.

One ``MODEL_SIZE`` (``0.6B`` or ``1.7B``) maps to the full low-level runtime configuration that a user
would otherwise have to assemble from a dozen ``OPENVINO_*``/``OV_*`` environment variables. Values
here are the working, validated candidate settings from dockermisc1 (see docs/dev/OPENVINO_RESULTS.md).

The OpenVINO IR locations are **stable, size-keyed paths** that the one-command export
(``scripts/export.py`` / ``docker compose run --rm export``) writes to — no export hashes leak into
the runtime config.
"""

from __future__ import annotations


def _ir_paths(size: str) -> dict[str, str]:
    base = f"/ov/{size}"
    return {
        "ov_model_dir": f"{base}/ir",
        "main_stateful_model": f"{base}/main_stateful_cap768.xml",
        "vocoder_dir": f"{base}/vocoder",
    }


PRESETS: dict[str, dict[str, object]] = {
    "0.6B": {
        "model_repo": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        "backend": "openvino",
        "main_compression": "int8",
        "predictor_compression": "int8",
        "vocoder_enabled": True,
        "stateful_capacity": 768,
        "torch_dtype": "bfloat16",
        "mem_limit": "10G",
        "mem_swap_limit": "11G",
        **_ir_paths("0.6B"),
    },
    "1.7B": {
        "model_repo": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "backend": "openvino",
        "main_compression": "int4",
        "predictor_compression": "int8",
        "vocoder_enabled": True,
        "stateful_capacity": 768,
        "torch_dtype": "bfloat16",
        "mem_limit": "10G",
        "mem_swap_limit": "11G",
        **_ir_paths("1.7B"),
    },
}


def normalize_size(model_size: str | None) -> str:
    """Return the canonical preset key for a user-supplied MODEL_SIZE (case-insensitive)."""
    key = (model_size or "0.6B").strip()
    for preset_key in PRESETS:
        if preset_key.lower() == key.lower():
            return preset_key
    choices = ", ".join(PRESETS)
    raise ValueError(f"Unsupported MODEL_SIZE={model_size!r}; choose one of: {choices}")


def get_preset(model_size: str | None) -> dict[str, object]:
    """Return a copy of the preset settings for the given MODEL_SIZE."""
    return dict(PRESETS[normalize_size(model_size)])

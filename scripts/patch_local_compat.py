#!/usr/bin/env python3
"""Apply the same qwen_tts/transformers compat patches the Dockerfile bakes into the
container image (Dockerfile:45-78), but to a local uv-managed .venv's site-packages.

The Docker image patches installed site-packages after `pip install` because qwen_tts==0.1.1
was written against an older transformers API; the container's own comments explain each
patch. `uv sync` alone does not apply them, so a plain local venv fails to import
persona_forge.app. Run this once after `uv sync` (idempotent — safe to re-run).
"""
import sysconfig
import pathlib
import re
import sys


def site_packages() -> pathlib.Path:
    return pathlib.Path(sysconfig.get_paths()["purelib"])


def sed_replace(path: pathlib.Path, pattern: str, replacement: str) -> None:
    if not path.exists():
        print(f"  skip (missing): {path}")
        return
    text = path.read_text()
    new_text = re.sub(pattern, replacement, text)
    if new_text != text:
        path.write_text(new_text)
        print(f"  patched: {path}")
    else:
        print(f"  already patched (or no match): {path}")


def delete_lines_matching(path: pathlib.Path, pattern: str) -> None:
    if not path.exists():
        print(f"  skip (missing): {path}")
        return
    lines = path.read_text().splitlines(keepends=True)
    kept = [line for line in lines if not re.search(pattern, line)]
    if len(kept) != len(lines):
        path.write_text("".join(kept))
        print(f"  patched: {path}")
    else:
        print(f"  already patched (or no match): {path}")


def replace_all(path: pathlib.Path, replacements: list[tuple[str, str]]) -> None:
    if not path.exists():
        print(f"  skip (missing): {path}")
        return
    text = path.read_text()
    original = text
    for old, new in replacements:
        text = text.replace(old, new)
    if text != original:
        path.write_text(text)
        print(f"  patched: {path}")
    else:
        print(f"  already patched (or no match): {path}")


def main() -> int:
    sp = site_packages()
    print(f"site-packages: {sp}")

    # Dockerfile:45-46
    sed_replace(
        sp / "qwen_tts/core/tokenizer_25hz/vq/speech_vq.py",
        r"option\.intra_op_num_threads = 1",
        "option.intra_op_num_threads = 6",
    )

    # Dockerfile:47-48
    delete_lines_matching(
        sp / "qwen_tts/core/tokenizer_12hz/modeling_qwen3_tts_tokenizer_v2.py",
        r"@check_model_inputs",
    )

    # Dockerfile:49-50
    sed_replace(
        sp / "transformers/models/mimi/modeling_mimi.py",
        r"create_sliding_window_causal_mask",
        "create_causal_mask",
    )

    # Dockerfile:51-64
    replace_all(
        sp / "qwen_tts/core/models/modeling_qwen3_tts.py",
        [
            (
                "from transformers.activations import ACT2FN",
                "from transformers import initialization as init\nfrom transformers.activations import ACT2FN",
            ),
            (
                "module.weight.data.normal_(mean=0.0, std=std)",
                "init.normal_(module.weight, mean=0.0, std=std)",
            ),
            ("module.bias.data.zero_()", "init.zeros_(module.bias)"),
            ("module.weight.data.fill_(1.0)", "init.ones_(module.weight)"),
            (
                "if module.padding_idx is not None:\n                module.weight.data[module.padding_idx].zero_()",
                "if module.padding_idx is not None and not getattr(module.weight, \"_is_hf_initialized\", False):\n                module.weight.data[module.padding_idx].zero_()",
            ),
            (
                "self.padding_idx = config.pad_token_id",
                "self.padding_idx = getattr(config, \"pad_token_id\", None)",
            ),
            ("input_embeds=inputs_embeds", "inputs_embeds=inputs_embeds"),
            ('"input_embeds": inputs_embeds,', '"inputs_embeds": inputs_embeds,'),
            (
                '\n                "cache_position": cache_position,\n',
                "\n",
            ),
            ("\n            cache_position=cache_position,\n", ""),
        ],
    )

    # Dockerfile:65-70
    replace_all(
        sp / "qwen_tts/core/models/configuration_qwen3_tts.py",
        [
            (
                "from transformers.configuration_utils import PretrainedConfig, layer_type_validation",
                "from transformers.configuration_utils import PretrainedConfig",
            ),
            ("layer_type_validation(self.layer_types)", "self.validate_layer_type()"),
        ],
    )

    # Dockerfile:71-78
    rope_path = sp / "transformers/modeling_rope_utils.py"
    if rope_path.exists():
        text = rope_path.read_text()
        original = text
        fn = (
            "\ndef _compute_default_rope_parameters(config=None, device=None, **kwargs):\n"
            "    import torch as _t\n"
            "    base = float(getattr(config, 'rope_theta', 10000.0))\n"
            "    factor = float(getattr(config, 'partial_rotary_factor', 1.0))\n"
            "    head_dim = getattr(config, 'head_dim', None) or (getattr(config, 'hidden_size', 512) // getattr(config, 'num_attention_heads', 8))\n"
            "    dim = int(head_dim * factor)\n"
            "    inv_freq = 1.0 / (base ** (_t.arange(0, dim, 2, dtype=_t.int64).float().to(device) / dim))\n"
            "    return inv_freq, 1.0\n\n"
        )
        text = text.replace("ROPE_INIT_FUNCTIONS:", fn + "ROPE_INIT_FUNCTIONS:")
        text = text.replace(
            '"linear": _compute_linear_scaling_rope_parameters',
            '"default": _compute_default_rope_parameters,\n    "linear": _compute_linear_scaling_rope_parameters',
        )
        if text != original:
            rope_path.write_text(text)
            print(f"  patched: {rope_path}")
        else:
            print(f"  already patched (or no match): {rope_path}")
    else:
        print(f"  skip (missing): {rope_path}")

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

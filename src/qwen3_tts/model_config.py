"""Shared model selection and Hugging Face authentication helpers."""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path


MODEL_PRESETS = {
    "0.6B": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
}

# VoiceDesign is a separate checkpoint (see docs/plans/PLAN_voice_design.md) that
# generate_voice_design() requires; it is never the primary MODEL_SIZE selection, only
# ever loaded via the lazy model-swap path (qwen3_tts.voice_design).
VOICE_DESIGN_MODEL_PRESETS = {
    "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
}


def resolve_voice_design_model_repo(environ: MutableMapping[str, str] = os.environ) -> str:
    """Resolve the VoiceDesign checkpoint, with VOICE_DESIGN_MODEL_REPO as an expert override."""

    override = environ.get("VOICE_DESIGN_MODEL_REPO", "").strip()
    if override:
        return override

    model_size = environ.get("VOICE_DESIGN_MODEL_SIZE", "1.7B").strip().upper()
    try:
        return VOICE_DESIGN_MODEL_PRESETS[model_size]
    except KeyError as exc:
        choices = ", ".join(VOICE_DESIGN_MODEL_PRESETS)
        raise RuntimeError(
            f"Unsupported VOICE_DESIGN_MODEL_SIZE={model_size!r}; choose {choices}"
        ) from exc


def configure_hf_token(environ: MutableMapping[str, str] = os.environ) -> None:
    """Populate HF_TOKEN from a Docker secret without logging the credential."""

    if environ.get("HF_TOKEN"):
        return

    token_file = environ.get("HF_TOKEN_FILE")
    if not token_file:
        return

    try:
        token = Path(token_file).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Unable to read HF_TOKEN_FILE: {token_file}") from exc
    if not token:
        raise RuntimeError(f"HF_TOKEN_FILE is empty: {token_file}")

    environ["HF_TOKEN"] = token


def resolve_model_repo(environ: MutableMapping[str, str] = os.environ) -> str:
    """Resolve a supported Base checkpoint, with MODEL_REPO as an expert override."""

    override = environ.get("MODEL_REPO", "").strip()
    if override:
        return override

    model_size = environ.get("MODEL_SIZE", "0.6B").strip().upper()
    try:
        return MODEL_PRESETS[model_size]
    except KeyError as exc:
        choices = ", ".join(MODEL_PRESETS)
        raise RuntimeError(f"Unsupported MODEL_SIZE={model_size!r}; choose {choices}") from exc


def resolve_torch_load_config(torch_module, environ: MutableMapping[str, str] = os.environ):
    """Resolve runtime/benchmark Torch dtype and low-memory loading."""

    requested = (environ.get("OPENVINO_TORCH_DTYPE") or "float32").strip().lower()
    aliases = {
        "float32": "float32",
        "fp32": "float32",
        "bfloat16": "bfloat16",
        "bf16": "bfloat16",
        "float16": "float16",
        "fp16": "float16",
    }
    try:
        canonical = aliases[requested]
    except KeyError as exc:
        choices = ", ".join(sorted(aliases))
        raise ValueError(
            f"unsupported OPENVINO_TORCH_DTYPE={requested!r}; choose {choices}"
        ) from exc

    low_cpu_mem_usage = (
        (environ.get("OPENVINO_LOW_CPU_MEM_USAGE") or "1").strip() != "0"
    )
    return getattr(torch_module, canonical), canonical, low_cpu_mem_usage

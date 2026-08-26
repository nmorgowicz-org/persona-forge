"""Shared model selection and Hugging Face authentication helpers."""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path


MODEL_PRESETS = {
    "0.6B": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
}

# VoiceDesign is a separate checkpoint (see docs/architecture/VOICE_DESIGN.md) that
# generate_voice_design() requires; it is never the primary MODEL_SIZE selection, only
# ever loaded via the lazy model-swap path (persona_forge.voice_design).
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
    """Populate HF_TOKEN from environment, a Docker secret file, or a persisted runtime token.

    Precedence:
      1) HF_TOKEN env var (set by user, Compose, or runtime config)
      2) HF_TOKEN_FILE (explicit Docker secret)
      3) /app/.hf_token (persisted via runtime config panel, if it exists)
    """

    if environ.get("HF_TOKEN"):
        return

    token_file = environ.get("HF_TOKEN_FILE") or "/app/.hf_token"

    try:
        token = Path(token_file).read_text(encoding="utf-8").strip()
    except OSError:
        return  # no file or unreadable: continue with no token

    if not token:
        return  # empty file: continue with no token

    environ["HF_TOKEN"] = token


def resolve_model_repo(environ: MutableMapping[str, str] = os.environ) -> str:
    """Resolve a supported Base checkpoint, with MODEL_REPO as an expert override."""

    override = environ.get("MODEL_REPO", "").strip()
    if override:
        return override

    model_size = environ.get("MODEL_SIZE", "1.7B").strip().upper()
    try:
        return MODEL_PRESETS[model_size]
    except KeyError as exc:
        choices = ", ".join(MODEL_PRESETS)
        raise RuntimeError(f"Unsupported MODEL_SIZE={model_size!r}; choose {choices}") from exc


def resolve_torch_load_config(
    torch_module,
    environ: MutableMapping[str, str] = os.environ,
    *,
    backend: str | None = None,
):
    """Resolve runtime/benchmark Torch dtype and low-memory loading."""

    # Runtime priority:
    #  - openvino: must be bf16 (enforced).
    #  - pytorch: MODEL_DTYPE (default fp32).
    #  - pocket_tts: treated as pytorch for this resolver.
    #
    # Re-resolve this policy for every model load instead of retaining the dtype
    # selected when the worker first imported this module.
    b = (backend or "").strip().lower()

    if b == "openvino":
        canonical = "bfloat16"
    else:
        # For pytorch and pocket_tts: allow MODEL_DTYPE override; default fp32.
        # Backward-compat shim: if no explicit backend was given and only
        # OPENVINO_TORCH_DTYPE is set, treat it as MODEL_DTYPE.
        # When backend is explicitly "pytorch" / "pocket_tts", ignore it and
        # default to fp32 to respect the caller's intent.
        model_dtype = environ.get("MODEL_DTYPE")
        if model_dtype:
            requested = model_dtype.strip().lower()
        elif b:
            # explicit backend (pytorch, pocket_tts) → ignore OPENVINO_TORCH_DTYPE
            requested = "float32"
        else:
            # no explicit backend → honor legacy OPENVINO_TORCH_DTYPE
            legacy = environ.get("OPENVINO_TORCH_DTYPE")
            requested = (legacy or "float32").strip().lower()
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
                f"unsupported MODEL_DTYPE={requested!r}; choose {choices}"
            ) from exc

    low_cpu_mem_usage = (
        (environ.get("OPENVINO_LOW_CPU_MEM_USAGE") or "1").strip() != "0"
    )
    return getattr(torch_module, canonical), canonical, low_cpu_mem_usage

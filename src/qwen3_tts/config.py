"""Resolve the ``MODEL_SIZE`` preset into the low-level environment the runtime reads.

The existing OpenVINO runtime modules (``model_config``, ``openvino/runtime_config``,
``openvino/talker``) read their settings from ``os.environ``. Rather than rewrite all of them to take
parameters, this module derives those low-level variables from the chosen ``MODEL_SIZE`` preset and
writes them into the environment **with ``setdefault``** — so an explicit variable set by an expert
always wins. Call :func:`apply_preset_env` once, as early as possible, before importing Torch/OpenVINO
or reading any of the low-level variables (``model.py`` does this at import time).
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping

from qwen3_tts.presets import get_preset, normalize_size

# The reference WAV is always mounted at this fixed path (see compose.yml / .env.example).
REF_AUDIO_PATH = "/voice/reference.wav"


def _setdefault(environ: MutableMapping[str, str], key: str, value: object) -> None:
    if value is None:
        return
    environ.setdefault(key, str(value))


def apply_preset_env(environ: MutableMapping[str, str] = os.environ) -> dict[str, object]:
    """Populate low-level runtime env vars from the ``MODEL_SIZE`` preset; return the preset.

    Explicit pre-existing variables are never overwritten (expert override). When
    ``TTS_BACKEND=pytorch`` is requested, the OpenVINO defaults are still set but ignored by the
    PyTorch backend, preserving the zero-IR rollback path.
    """
    model_size = environ.get("MODEL_SIZE", "0.6B")
    environ["MODEL_SIZE"] = normalize_size(model_size)
    preset = get_preset(model_size)

    # Backend (MODEL_REPO is resolved from MODEL_SIZE by model_config.resolve_model_repo).
    # An explicit TTS_BACKEND wins; otherwise the preset default (openvino).
    _setdefault(environ, "TTS_BACKEND", preset["backend"])
    backend = (environ.get("TTS_BACKEND") or preset["backend"]).strip().lower()

    # OpenVINO IR locations — the stable, size-keyed paths the export writes.
    _setdefault(environ, "OV_MODEL_DIR", preset["ov_model_dir"])
    _setdefault(environ, "OPENVINO_MAIN_STATEFUL_MODEL", preset["main_stateful_model"])
    _setdefault(
        environ,
        "OPENVINO_PREDICTOR_STATEFUL_MODEL",
        preset["predictor_stateful_model"],
    )
    _setdefault(environ, "OPENVINO_VOCODER_DIR", preset["vocoder_dir"])
    _setdefault(environ, "OPENVINO_VOCODER_ENABLED", "1" if preset["vocoder_enabled"] else "0")

    # Compression (carried for metadata/validation).
    _setdefault(environ, "OV_MAIN_COMPRESSION", preset["main_compression"])
    _setdefault(environ, "OV_PREDICTOR_COMPRESSION", preset["predictor_compression"])

    # Serving-load policy applies ONLY to the OpenVINO backend. There the talker cores run on
    # OpenVINO, so the bf16 Torch weights are just load-time glue that is released after compile.
    # On the pure-PyTorch fallback the transformer forward actually runs in Torch on CPU, where
    # bf16 has no fast GEMM kernels and generation blows past the request timeout — so leave the
    # dtype at the fp32 default there. (The exporter must stay fp32 and never calls this; HANDOFF §11.)
    if backend == "openvino":
        _setdefault(environ, "OPENVINO_TORCH_DTYPE", preset["torch_dtype"])
        _setdefault(environ, "OPENVINO_RELEASE_TORCH", "1")
    _setdefault(environ, "OPENVINO_LOW_CPU_MEM_USAGE", "1")

    return preset

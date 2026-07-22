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

from qwen3_tts.presets import get_preset, has_valid_export, normalize_size

# The reference WAV is always mounted at this fixed path (see compose.yml / .env.example).
REF_AUDIO_PATH = "/voice/reference.wav"


def normalize_backend(value: str | None) -> str:
    """Canonicalize a TTS_BACKEND value.

    Accepts the repo-style hyphenated spelling (``pocket-tts``) as an alias for the
    internal underscore form (``pocket_tts``) so either works in compose/.env.
    """
    return (value or "").strip().lower().replace("-", "_")


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
    model_size = environ.get("MODEL_SIZE", "1.7B")
    environ["MODEL_SIZE"] = normalize_size(model_size)

    max_speech_seconds = environ.get("TTS_MAX_SPEECH_SECONDS")
    preset = get_preset(model_size, float(max_speech_seconds) if max_speech_seconds else None)
    _setdefault(environ, "TTS_MAX_SPEECH_SECONDS", preset["max_speech_seconds"])

    # Backend (MODEL_REPO is resolved from MODEL_SIZE by model_config.resolve_model_repo).
    # An explicit TTS_BACKEND wins (this is how .env.example's TTS_BACKEND=pocket_tts becomes
    # the actual product default). The preset's own backend fallback must stay pytorch/openvino
    # — this preset's model_repo is a Qwen3-TTS checkpoint, which pocket_tts (a separate engine)
    # cannot run. Phase A4b (D9 addendum, D15): auto-select openvino only if a real IR export
    # already exists on disk for this preset — never trigger the export itself; pytorch remains
    # the safe zero-setup fallback everywhere else.
    explicit_backend_was_set = "TTS_BACKEND" in environ
    engine_fallback = "openvino" if has_valid_export(preset) else "pytorch"
    _setdefault(environ, "TTS_BACKEND", engine_fallback)
    backend = normalize_backend(environ.get("TTS_BACKEND") or engine_fallback)
    # Persist the canonical form so every downstream reader sees pocket_tts, not pocket-tts.
    environ["TTS_BACKEND"] = backend
    # Surfaced by /health so a user isn't surprised by which engine mode auto-selected.
    preset["backend_source"] = "explicit" if explicit_backend_was_set else "auto-fallback"
    preset["backend_fallback_choice"] = engine_fallback

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

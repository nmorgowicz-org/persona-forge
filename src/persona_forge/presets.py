"""Model-size presets — the single ``MODEL_SIZE`` knob.

One ``MODEL_SIZE`` (``0.6B`` or ``1.7B``) maps to the full low-level runtime configuration that a user
would otherwise have to assemble from a dozen ``OPENVINO_*``/``OV_*`` environment variables. Values
here are the working, validated candidate settings from dockermisc1 (see docs/dev/benchmarks/OPENVINO_RESULTS.md).

The OpenVINO IR locations are **stable, size-keyed paths** that the one-command export
(``scripts/export.py`` / ``docker compose run --rm export``) writes to — no export hashes leak into
the runtime config.
"""

from __future__ import annotations

import os

from persona_forge import paths
from persona_forge.paths import Environ

# The main stateful graph's codec runs at 12 Hz — one frame per 1/12 second of audio.
# This is what turns a human "max speech seconds" knob into an OpenVINO static-capacity
# frame count. See docs/dev/benchmarks/OPENVINO_RESULTS.md ("768 ~= 64s of 12 Hz context").
FRAME_RATE_HZ = 12

# qwen3-tts-engine-only (pytorch/openvino) knob — pocket_tts is unbounded and never reads
# this. 300s gives long-form/roleplay generations real headroom; changing it re-sizes the
# OpenVINO IR's stateful K/V capacity, so it requires re-export (docs/HOW_TO_RUN.md).
DEFAULT_MAX_SPEECH_SECONDS = 300.0


def capacity_for_seconds(seconds: float) -> int:
    """Convert a max-speech-length target (seconds) into a stateful K/V frame capacity."""
    if seconds <= 0:
        raise ValueError("seconds must be positive")
    return round(seconds * FRAME_RATE_HZ)


def seconds_for_capacity(capacity: int) -> float:
    """Inverse of :func:`capacity_for_seconds` — used for human-readable error/health text."""
    return capacity / FRAME_RATE_HZ


def _ir_paths(size: str, capacity: int, environ: Environ = os.environ) -> dict[str, str]:
    base = paths.ov_root(environ) / size
    return {
        "ov_model_dir": str(base / "ir"),
        "main_stateful_model": str(base / f"main_stateful_cap{capacity}.xml"),
        "vocoder_dir": str(base / "vocoder"),
    }


# 0.6B's predictor capacity is fixed at 32 frames — unrelated to the main graph's
# max-speech-driven capacity — so it is keyed by size only, not by the resolved capacity.
_PREDICTOR_STATEFUL_FILENAMES = {"0.6B": "predictor_stateful_cap32.xml"}


def _predictor_stateful_model(size: str, environ: Environ = os.environ) -> str | None:
    filename = _PREDICTOR_STATEFUL_FILENAMES.get(size)
    if filename is None:
        return None
    return str(paths.ov_root(environ) / size / filename)


PRESETS: dict[str, dict[str, object]] = {
    "0.6B": {
        "model_repo": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        # pocket_tts is a separate engine/checkpoint and cannot run a Qwen3-TTS model — this
        # preset's backend must be pytorch (cpu/cuda/mps/rocm/xpu) or openvino only.
        "backend": "pytorch",
        "main_compression": "int8",
        "predictor_compression": "int8",
        "vocoder_enabled": True,
        "max_speech_seconds": DEFAULT_MAX_SPEECH_SECONDS,
        "predictor_stateful_model": None,  # resolved dynamically in get_preset() via ov_root()
        "torch_dtype": "bfloat16",
        "mem_limit": "10G",
        "mem_swap_limit": "11G",
    },
    "1.7B": {
        "model_repo": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "backend": "pytorch",
        "main_compression": "int4",
        "predictor_compression": "int8",
        "vocoder_enabled": True,
        "max_speech_seconds": DEFAULT_MAX_SPEECH_SECONDS,
        "predictor_stateful_model": None,
        "torch_dtype": "bfloat16",
        "mem_limit": "10G",
        "mem_swap_limit": "11G",
    },
}


# VoiceDesign (docs/architecture/VOICE_DESIGN.md) only ever generates a short sample
# utterance for reference capture, never long-form speech, so its IR capacity can stay
# much smaller than the Base preset's default.
VOICE_DESIGN_DEFAULT_MAX_SPEECH_SECONDS = 30.0


def _voice_design_ir_paths(size: str, capacity: int, environ: Environ = os.environ) -> dict[str, str]:
    # A distinct, size-keyed directory tree (never "<ov_root>/<size>/...") so a VoiceDesign
    # export can never collide with — or accidentally overwrite — the Base export for
    # the same MODEL_SIZE.
    base = paths.ov_root(environ) / f"{size}-voicedesign"
    return {
        "ov_model_dir": str(base / "ir"),
        "main_stateful_model": str(base / f"main_stateful_cap{capacity}.xml"),
        "vocoder_dir": str(base / "vocoder"),
    }


VOICE_DESIGN_PRESETS: dict[str, dict[str, object]] = {
    "1.7B": {
        "model_repo": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        # Unused by apply_preset_env (only PRESETS' "backend" feeds that) — VoiceDesign always
        # runs the Qwen3TTSModel path (openvino/pytorch), never pocket_tts (app.py guards this).
        "backend": "openvino",
        "main_compression": "int4",
        "predictor_compression": "int8",
        "vocoder_enabled": True,
        "max_speech_seconds": VOICE_DESIGN_DEFAULT_MAX_SPEECH_SECONDS,
        "predictor_stateful_model": None,
        "torch_dtype": "bfloat16",
    },
}


def normalize_voice_design_size(model_size: str | None) -> str:
    """Return the canonical preset key for a user-supplied VOICE_DESIGN_MODEL_SIZE."""
    key = (model_size or "1.7B").strip()
    for preset_key in VOICE_DESIGN_PRESETS:
        if preset_key.lower() == key.lower():
            return preset_key
    choices = ", ".join(VOICE_DESIGN_PRESETS)
    raise ValueError(f"Unsupported VOICE_DESIGN_MODEL_SIZE={model_size!r}; choose one of: {choices}")


def get_voice_design_preset(
    model_size: str | None = None,
    max_speech_seconds: float | None = None,
    main_compression: str | None = None,
    environ: Environ = os.environ,
) -> dict[str, object]:
    """Return a copy of the VoiceDesign preset settings, mirroring :func:`get_preset`.

    ``main_compression`` overrides the preset default main-core compression (e.g. from
    ``VOICE_DESIGN_MAIN_COMPRESSION``) for export-time experiments — e.g. comparing an
    INT8 main core against the default INT4 for accent fidelity. It only affects which IR
    variant scripts/export.py promotes; it does not change the IR output path, so re-running
    export with a different override overwrites the previous VoiceDesign IR in place.

    ``environ`` is forwarded to :func:`persona_forge.paths.ov_root` so callers holding an
    injected mapping (rather than the real process environment) get IR paths resolved
    against it — see docs/plans/20260829-no_more_docker_architecture.md §4.
    """
    key = normalize_voice_design_size(model_size)
    preset = dict(VOICE_DESIGN_PRESETS[key])
    seconds = max_speech_seconds if max_speech_seconds is not None else preset["max_speech_seconds"]
    capacity = capacity_for_seconds(seconds)
    preset["max_speech_seconds"] = seconds
    preset["stateful_capacity"] = capacity
    if main_compression is not None:
        if main_compression not in ("int4", "int8"):
            raise ValueError(
                f"Unsupported VOICE_DESIGN_MAIN_COMPRESSION={main_compression!r}; "
                "choose int4 or int8"
            )
        preset["main_compression"] = main_compression
    preset.update(_voice_design_ir_paths(key, capacity, environ))
    return preset


def has_valid_export(preset: dict[str, object]) -> bool:
    """Return True iff a real OpenVINO IR export already exists on disk for ``preset``.

    Phase A4b (D9 addendum, D15): checks the filesystem, not env — this must reflect the
    actual export state, never trigger ``scripts/export.py`` itself. A preset with no
    ``predictor_stateful_model`` (e.g. 1.7B) only requires the main graph to be present.
    """
    main_path = preset.get("main_stateful_model")
    if not main_path or not os.path.isfile(str(main_path)):
        return False
    predictor_path = preset.get("predictor_stateful_model")
    if predictor_path and not os.path.isfile(str(predictor_path)):
        return False
    return True


def normalize_size(model_size: str | None) -> str:
    """Return the canonical preset key for a user-supplied MODEL_SIZE (case-insensitive)."""
    key = (model_size or "1.7B").strip()
    for preset_key in PRESETS:
        if preset_key.lower() == key.lower():
            return preset_key
    choices = ", ".join(PRESETS)
    raise ValueError(f"Unsupported MODEL_SIZE={model_size!r}; choose one of: {choices}")


def get_preset(
    model_size: str | None,
    max_speech_seconds: float | None = None,
    environ: Environ = os.environ,
) -> dict[str, object]:
    """Return a copy of the preset settings for the given MODEL_SIZE.

    ``max_speech_seconds`` overrides the preset default (e.g. from ``TTS_MAX_SPEECH_SECONDS``)
    and drives both the derived ``stateful_capacity`` (frames) and the ``main_stateful_model``
    IR path, which is capacity-keyed so different capacities never collide on disk.

    ``environ`` is forwarded to :func:`persona_forge.paths.ov_root` so callers holding an
    injected mapping (rather than the real process environment) get IR paths resolved
    against it — see docs/plans/20260829-no_more_docker_architecture.md §4.
    """
    key = normalize_size(model_size)
    preset = dict(PRESETS[key])
    seconds = max_speech_seconds if max_speech_seconds is not None else preset["max_speech_seconds"]
    capacity = capacity_for_seconds(seconds)
    preset["max_speech_seconds"] = seconds
    preset["stateful_capacity"] = capacity
    preset["predictor_stateful_model"] = _predictor_stateful_model(key, environ)
    preset.update(_ir_paths(key, capacity, environ))
    return preset

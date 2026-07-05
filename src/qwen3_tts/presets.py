"""Model-size presets — the single ``MODEL_SIZE`` knob.

One ``MODEL_SIZE`` (``0.6B`` or ``1.7B``) maps to the full low-level runtime configuration that a user
would otherwise have to assemble from a dozen ``OPENVINO_*``/``OV_*`` environment variables. Values
here are the working, validated candidate settings from dockermisc1 (see docs/dev/benchmarks/OPENVINO_RESULTS.md).

The OpenVINO IR locations are **stable, size-keyed paths** that the one-command export
(``scripts/export.py`` / ``docker compose run --rm export``) writes to — no export hashes leak into
the runtime config.
"""

from __future__ import annotations

# The main stateful graph's codec runs at 12 Hz — one frame per 1/12 second of audio.
# This is what turns a human "max speech seconds" knob into an OpenVINO static-capacity
# frame count. See docs/dev/benchmarks/OPENVINO_RESULTS.md ("768 ~= 64s of 12 Hz context").
FRAME_RATE_HZ = 12

# The historical fixed capacity (768 frames) was chosen as exactly 64s at 12 Hz, so this
# stays the default and reproduces the exact IR filename/capacity every existing deployment
# (including dockermisc1) already has on disk.
DEFAULT_MAX_SPEECH_SECONDS = 64.0


def capacity_for_seconds(seconds: float) -> int:
    """Convert a max-speech-length target (seconds) into a stateful K/V frame capacity."""
    if seconds <= 0:
        raise ValueError("seconds must be positive")
    return round(seconds * FRAME_RATE_HZ)


def seconds_for_capacity(capacity: int) -> float:
    """Inverse of :func:`capacity_for_seconds` — used for human-readable error/health text."""
    return capacity / FRAME_RATE_HZ


def _ir_paths(size: str, capacity: int) -> dict[str, str]:
    base = f"/ov/{size}"
    return {
        "ov_model_dir": f"{base}/ir",
        "main_stateful_model": f"{base}/main_stateful_cap{capacity}.xml",
        "vocoder_dir": f"{base}/vocoder",
    }


PRESETS: dict[str, dict[str, object]] = {
    "0.6B": {
        "model_repo": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        "backend": "openvino",
        "main_compression": "int8",
        "predictor_compression": "int8",
        "vocoder_enabled": True,
        "max_speech_seconds": DEFAULT_MAX_SPEECH_SECONDS,
        "predictor_stateful_model": "/ov/0.6B/predictor_stateful_cap32.xml",
        "torch_dtype": "bfloat16",
        "mem_limit": "10G",
        "mem_swap_limit": "11G",
    },
    "1.7B": {
        "model_repo": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "backend": "openvino",
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


# VoiceDesign (docs/dev/architecture/voice_design.md) only ever generates a short sample
# utterance for reference capture, never long-form speech, so its IR capacity can stay
# much smaller than the Base preset's default.
VOICE_DESIGN_DEFAULT_MAX_SPEECH_SECONDS = 30.0


def _voice_design_ir_paths(size: str, capacity: int) -> dict[str, str]:
    # A distinct, size-keyed directory tree (never "/ov/<size>/...") so a VoiceDesign
    # export can never collide with — or accidentally overwrite — the Base export for
    # the same MODEL_SIZE.
    base = f"/ov/{size}-voicedesign"
    return {
        "ov_model_dir": f"{base}/ir",
        "main_stateful_model": f"{base}/main_stateful_cap{capacity}.xml",
        "vocoder_dir": f"{base}/vocoder",
    }


VOICE_DESIGN_PRESETS: dict[str, dict[str, object]] = {
    "1.7B": {
        "model_repo": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
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
) -> dict[str, object]:
    """Return a copy of the VoiceDesign preset settings, mirroring :func:`get_preset`.

    ``main_compression`` overrides the preset default main-core compression (e.g. from
    ``VOICE_DESIGN_MAIN_COMPRESSION``) for export-time experiments — e.g. comparing an
    INT8 main core against the default INT4 for accent fidelity. It only affects which IR
    variant scripts/export.py promotes; it does not change the IR output path, so re-running
    export with a different override overwrites the previous VoiceDesign IR in place.
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
    preset.update(_voice_design_ir_paths(key, capacity))
    return preset


def normalize_size(model_size: str | None) -> str:
    """Return the canonical preset key for a user-supplied MODEL_SIZE (case-insensitive)."""
    key = (model_size or "0.6B").strip()
    for preset_key in PRESETS:
        if preset_key.lower() == key.lower():
            return preset_key
    choices = ", ".join(PRESETS)
    raise ValueError(f"Unsupported MODEL_SIZE={model_size!r}; choose one of: {choices}")


def get_preset(model_size: str | None, max_speech_seconds: float | None = None) -> dict[str, object]:
    """Return a copy of the preset settings for the given MODEL_SIZE.

    ``max_speech_seconds`` overrides the preset default (e.g. from ``TTS_MAX_SPEECH_SECONDS``)
    and drives both the derived ``stateful_capacity`` (frames) and the ``main_stateful_model``
    IR path, which is capacity-keyed so different capacities never collide on disk.
    """
    key = normalize_size(model_size)
    preset = dict(PRESETS[key])
    seconds = max_speech_seconds if max_speech_seconds is not None else preset["max_speech_seconds"]
    capacity = capacity_for_seconds(seconds)
    preset["max_speech_seconds"] = seconds
    preset["stateful_capacity"] = capacity
    preset.update(_ir_paths(key, capacity))
    return preset

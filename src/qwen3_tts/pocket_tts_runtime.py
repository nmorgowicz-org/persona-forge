"""Pocket TTS runtime adapter (kyutai-labs/pocket-tts).

Provides a thin, self-contained interface for loading Pocket TTS models, building
voice states from reference audio, and generating speech. Designed to plug into
the repo's existing hotswap/executor infrastructure without pulling in heavy Qwen3-TTS
or OpenVINO symbols at import time.

Public API:
    - load_pocket_tts_model(...)
    - build_default_voice_state(...)
    - get_pocket_tts_voice_state(...)
    - generate_pocket_tts(...)
    - unload_pocket_tts()
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from pocket_tts import TTSModel

if TYPE_CHECKING:
    # Imported inside functions at runtime to avoid drag-in.
    import torch


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

pocket_tts_model: TTSModel | None = None
pocket_tts_default_voice_state: dict[str, Any] | None = None
pocket_tts_voice_state_cache: dict[str, Any] = {}

pocket_tts_cloning_available: bool = False
pocket_tts_cloning_status_message: str = ""

# Extra audio frames to keep after the last speech frame (post-EOS tail control).
# 1 frame ≈ 1/12 s of audio at 24 kHz (~2000 samples).
# Controlled by POCKET_TTS_FRAMES_AFTER_EOS env var (default 4).
pocket_tts_frames_after_eos: int = 4


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def load_pocket_tts_model(
    language: str,
    temp: float,
    lsd_decode_steps: int,
    eos_threshold: float,
    *,
    quantize: bool = False,
    noise_clamp: float | None = None,
    frames_after_eos: int | None = None,
) -> TTSModel:
    """Load (or reload) the Pocket TTS model into the global handle.

    Args:
        language: Pocket TTS language config (e.g. "english", "french_24l").
        temp: Sampling temperature.
        lsd_decode_steps: Number of LSD refinement steps per audio frame.
        eos_threshold: Logits-based EOS threshold.
        quantize: Whether to enable int8 quantization.
        noise_clamp: Optional noise magnitude cap.
        frames_after_eos: Optional extra frames to keep after EOS.

    Returns:
        The loaded TTSModel instance.

    Raises:
        RuntimeError: If the model fails to load.
    """
    global pocket_tts_model

    # Unload any previous instance first (hotswap-safe).
    unload_pocket_tts()

    print(
        f"[pocket_tts] Loading model — language={language!r}, "
        f"temp={temp}, lsd_decode_steps={lsd_decode_steps}, "
        f"eos_threshold={eos_threshold}, quantize={quantize}"
    )

    try:
        pocket_tts_model = TTSModel.load_model(
            language=language,
            temp=temp,
            lsd_decode_steps=lsd_decode_steps,
            eos_threshold=eos_threshold,
            quantize=quantize,
        )
    except Exception as exc:
        pocket_tts_model = None
        raise RuntimeError(f"[pocket_tts] Failed to load TTSModel: {exc}") from exc

    # Store advanced knobs for use during generation.
    global pocket_tts_frames_after_eos
    if noise_clamp is not None:
        print(f"[pocket_tts] noise_clamp set to {noise_clamp} (noted; runtime wiring TBD)")
    if frames_after_eos is not None:
        pocket_tts_frames_after_eos = max(0, frames_after_eos)
        print(f"[pocket_tts] frames_after_eos set to {pocket_tts_frames_after_eos}")
    else:
        pocket_tts_frames_after_eos = 4
        print(f"[pocket_tts] frames_after_eos defaulted to {pocket_tts_frames_after_eos}")

    print("[pocket_tts] Model loaded and ready.")
    return pocket_tts_model


# ---------------------------------------------------------------------------
# Default voice state from REF_AUDIO
# ---------------------------------------------------------------------------

def build_default_voice_state(
    model: TTSModel,
    ref_audio_path: str | None,
) -> dict[str, Any] | None:
    """Build a Pocket TTS voice_state from the configured reference audio.

    This voice_state becomes the default when no voice_id is requested.

    Args:
        model: Loaded Pocket TTS TTSModel.
        ref_audio_path: Absolute path to a reference WAV.

    Returns:
        voice_state dict, or None if no valid ref_audio_path.
    """
    global pocket_tts_default_voice_state, pocket_tts_cloning_available, pocket_tts_cloning_status_message

    if not ref_audio_path:
        print("[pocket_tts] No REF_AUDIO_PATH configured; default voice_state = None.")
        pocket_tts_default_voice_state = None
        return None

    if not os.path.isfile(ref_audio_path):
        print(
            f"[pocket_tts] REF_AUDIO_PATH exists but is not a file: {ref_audio_path!r}; "
            "default voice_state = None."
        )
        pocket_tts_default_voice_state = None
        return None

    print(f"[pocket_tts] Building default voice_state from {ref_audio_path!r}")
    try:
        pocket_tts_default_voice_state = model.get_state_for_audio_prompt(ref_audio_path)
        pocket_tts_cloning_available = True
        pocket_tts_cloning_status_message = ""
        print("[pocket_tts] Default voice_state built successfully.")
        return pocket_tts_default_voice_state
    except Exception as exc:
        pocket_tts_default_voice_state = None
        msg = str(exc)

        if "We could not download the weights for the model with voice cloning" in msg:
            pocket_tts_cloning_available = False
            pocket_tts_cloning_status_message = (
                "Voice cloning model unavailable. "
                "Accept the terms at https://huggingface.co/kyutai/pocket-tts with the account "
                "used for HF_TOKEN, then restart the container."
            )
        else:
            pocket_tts_cloning_available = False
            pocket_tts_cloning_status_message = f"Voice cloning unavailable: {msg}"

        print(
            f"[pocket_tts] Failed to build default voice_state: {exc}. "
            "Continuing without a default voice_state."
        )
        return None


# ---------------------------------------------------------------------------
# Voice selection (default, library, or custom)
# ---------------------------------------------------------------------------

def get_pocket_tts_voice_state(
    model: TTSModel,
    voice_id: str | None,
    default_voice_state: dict[str, Any] | None,
    ref_audio_path: str | None,
) -> dict[str, Any]:
    """Resolve the Pocket TTS voice_state for a generation request.

    Priority:
        1. If voice_id is None or empty -> use default_voice_state.
        2. If voice_id is in cache -> use cached state.
        3. If voice_id matches a library voice -> load from its WAV, cache it.
        4. If none of the above -> raise RuntimeError.

    Args:
        model: Loaded Pocket TTS TTSModel.
        voice_id: Optional voice library ID (e.g. "vd_123abc456def").
        default_voice_state: The default state derived from REF_AUDIO.
        ref_audio_path: Fallback reference audio path.

    Returns:
        A voice_state dict for use with generate_audio.

    Raises:
        RuntimeError: If no valid voice_state can be resolved.
    """
    # 1) No specific voice requested -> default.
    if not voice_id:
        if default_voice_state is not None:
            return default_voice_state
        # Last-ditch: try to rebuild from ref_audio_path.
        if ref_audio_path and os.path.isfile(ref_audio_path):
            print(
                f"[pocket_tts] No default_voice_state; falling back to ref_audio_path={ref_audio_path!r}"
            )
            return model.get_state_for_audio_prompt(ref_audio_path)
        raise RuntimeError(
            "[pocket_tts] Voice cloning model not available (likely missing or gated HF token). "
            "Set an HF_TOKEN with access to kyutai/pocket-tts via Runtime → HF_TOKEN "
            "or in your startup config."
        )

    # 2) Cached voice_state.
    cached = pocket_tts_voice_state_cache.get(voice_id)
    if cached is not None:
        return cached

    # 3) Look up in voice_library.
    from qwen3_tts import voice_library

    meta = voice_library.get_voice(voice_id)
    if meta is None:
        raise ValueError(
            f"[pocket_tts] voice_id not found in voice_library: {voice_id!r}"
        )

    wav_path = meta.get("wav_path")
    if not wav_path or not os.path.isfile(wav_path):
        raise RuntimeError(
            f"[pocket_tts] voice_id={voice_id!r} exists but wav_path is invalid: "
            f"{wav_path!r}"
        )

    state = model.get_state_for_audio_prompt(wav_path)
    pocket_tts_voice_state_cache[voice_id] = state
    return state


# ---------------------------------------------------------------------------
# Audio generation
# ---------------------------------------------------------------------------

def _trim_post_eos_tail(audio: torch.Tensor, sr: int, frames_after_eos: int) -> torch.Tensor:
    """Trim trailing dead air after the last speech frame, respecting frames_after_eos.

    Uses a per-frame energy heuristic:
    - 1 frame ≈ 2000 samples at 24 kHz (12 fps codec).
    - Finds the last frame where energy exceeds a fraction of the peak frame energy.
    - Keeps up to frames_after_eos extra frames after that point.
    - On any error, returns the original audio unchanged.
    """
    try:
        import torch.nn.functional as F

        if frames_after_eos < 0 or audio.numel() == 0:
            return audio

        # Work on CPU float
        x = audio.float().cpu().flatten()
        frame_samples = max(1, sr // 12)
        if len(x) <= frame_samples:
            return audio

        # Per-frame energy (L2 norm) via unfold
        frames = x.unfold(0, frame_samples, frame_samples)
        energies = (frames * frames).sum(dim=1).sqrt()
        peak = energies.max().item()
        if peak <= 1e-9:
            return audio

        # Speech threshold: 3% of peak frame energy
        thresh = peak * 0.03
        # Last speech frame index (energy above threshold)
        speech_mask = (energies >= thresh).nonzero(as_tuple=True)[0]
        if speech_mask.numel() == 0:
            return audio
        last_speech_frame = int(speech_mask[-1])

        # Effective endpoint: allow extra frames_after_eos beyond last speech frame
        limit_frame = last_speech_frame + frames_after_eos
        limit_sample = min(len(x), (limit_frame + 1) * frame_samples)

        if limit_sample < len(x):
            return x[:limit_sample]
        return audio
    except Exception:
        # Defensive: never break generation on trimming issues
        return audio


def generate_pocket_tts(
    model: TTSModel,
    voice_state: dict[str, Any],
    text: str,
) -> tuple[Any, int]:
    """Generate speech audio from text using the loaded Pocket TTS model.

    Args:
        model: Loaded Pocket TTS TTSModel.
        voice_state: Voice state dict (from get_state_for_audio_prompt).
        text: Input text to synthesize.

    Returns:
        (audio_tensor, sample_rate)
            - audio_tensor: 1D torch.Tensor (PCM float, 24 kHz).
            - sample_rate: int (24000).
    """
    import torch

    if not model:
        raise RuntimeError("[pocket_tts] Model is not loaded; call load_pocket_tts_model first.")
    if not voice_state:
        raise RuntimeError("[pocket_tts] voice_state is missing; cannot generate.")
    if not text:
        raise ValueError("[pocket_tts] Input text is empty.")

    audio = model.generate_audio(voice_state, text)

    # Normalize to expected shape.
    if isinstance(audio, torch.Tensor):
        if audio.dim() == 1:
            audio = audio  # already mono 1D
        else:
            audio = audio.squeeze()
    else:
        audio = torch.tensor(audio, dtype=torch.float32)

    sample_rate = getattr(model, "sample_rate", 24000)

    # Apply post-EOS tail trim if configured
    audio = _trim_post_eos_tail(audio, int(sample_rate), pocket_tts_frames_after_eos)

    return audio, int(sample_rate)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def unload_pocket_tts() -> None:
    """Unload Pocket TTS model and clear all cached voice states."""
    global pocket_tts_model, pocket_tts_default_voice_state, pocket_tts_voice_state_cache

    if pocket_tts_model is None and not pocket_tts_voice_state_cache:
        return

    print("[pocket_tts] Unloading Pocket TTS model and clearing cache...")

    pocket_tts_model = None
    pocket_tts_default_voice_state = None
    pocket_tts_voice_state_cache.clear()

    print("[pocket_tts] Unloaded.")

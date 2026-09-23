"""Shared WAV decoding/WAV-writing helpers for the fake-model fixtures.

Both fake tiers (``tests/fixtures/fake_runtime.py`` and
``tests/ui/fixtures/fake_model_server.py``) need the same operation: turn an
arbitrary PCM16 WAV payload into float32 mono at 24 kHz so fixture audio can
stand in for synthesized speech with no broken downstream waveform. Keeping the
decode in one place means a future format change (a different sample width, a
different target rate) lands everywhere at once instead of drifting apart.
"""

from __future__ import annotations

import io
import wave

import numpy as np

SAMPLE_RATE = 24_000


def decode_pcm16_wav_to_float32(wav_bytes: bytes, target_rate: int = SAMPLE_RATE) -> np.ndarray | None:
    """Decode bytes/bytesIO-backed PCM16 WAV to float32 mono @ ``target_rate``.

    Returns ``None`` when the payload is not usable PCM16 (not WAV, other sample
    widths, empty). Stereo payloads are downmixed by averaging channels; other
    sample rates are linearly resampled, keeping duration honest (linear
    resample is enough for a fixture stand-in).
    """
    try:
        reader = wave.open(io.BytesIO(wav_bytes), "rb")
    except (OSError, wave.Error, EOFError):
        return None
    with reader:
        frames = reader.readframes(reader.getnframes())
        channels = reader.getnchannels()
        width = reader.getsampwidth()
        rate = reader.getframerate()
    if width != 2 or not frames:
        return None
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != target_rate:
        target_len = max(1, int(round(samples.size * target_rate / rate)))
        # np.interp needs an increasing x grid; linspace supplies it directly.
        samples = np.interp(
            np.linspace(0.0, samples.size - 1.0, target_len),
            np.arange(samples.size),
            samples,
        ).astype(np.float32)
    return samples


def encode_pcm16_wav(samples: np.ndarray, target_rate: int = SAMPLE_RATE) -> bytes:
    """Encode float32 mono (values in [-1.0, 1.0]) as a PCM16 WAV at ``target_rate``."""
    pcm = np.clip(samples, -1.0, 1.0)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(target_rate)
        writer.writeframes((pcm * 32767.0).astype(np.int16).tobytes())
    return buf.getvalue()

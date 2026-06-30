"""Incremental code capture for the existing chunked OpenVINO vocoder.

Qwen3-TTS exposes each completed 16-codebook frame on the outer talker's
``forward`` result.  This module observes that existing return value without
changing the Transformers generation contract, then decodes only completed
300-frame vocoder prefixes and a final partial prefix.

The implementation is intentionally transport-agnostic.  It establishes the
generation-to-vocoder seam needed by a later HTTP streaming endpoint while the
existing batch endpoints remain unchanged.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

import numpy as np


class StreamingVocoderSession:
    """Capture generated codec frames and emit parity-preserving PCM tails.

    The decoder callback receives a complete ``[frames, 16]`` prefix and must
    return the corresponding one-dimensional waveform.  Reference codes are
    included because the stock voice-clone path prepends them before vocoder
    decode and removes their samples afterwards.
    """

    def __init__(
        self,
        talker: Any,
        decode_prefix: Callable[[np.ndarray], np.ndarray],
        on_audio_chunk: Callable[[np.ndarray], None],
        *,
        reference_codes: Any | None = None,
        eos_token_id: int | None = None,
        chunk_frames: int = 300,
        samples_per_frame: int = 1920,
    ) -> None:
        if chunk_frames <= 0:
            raise ValueError("chunk_frames must be positive")
        if samples_per_frame <= 0:
            raise ValueError("samples_per_frame must be positive")

        self._talker = talker
        self._decode_prefix = decode_prefix
        self._on_audio_chunk = on_audio_chunk
        self._reference_codes = self._normalize_codes(reference_codes, allow_empty=True)
        self._eos_token_id = eos_token_id
        self._chunk_frames = chunk_frames
        self._samples_per_frame = samples_per_frame

        self._generated: list[np.ndarray] = []
        self._decoded_total_frames = 0
        self._decode_boundaries: list[int] = []
        self._emitted_samples = 0
        self._last_waveform: np.ndarray | None = None
        self._original_forward: Any = None

    @staticmethod
    def _normalize_codes(codes: Any | None, *, allow_empty: bool = False) -> np.ndarray:
        if codes is None:
            if allow_empty:
                return np.empty((0, 16), dtype=np.int64)
            raise ValueError("codec IDs are missing")
        if hasattr(codes, "detach"):
            codes = codes.detach()
        if hasattr(codes, "cpu"):
            codes = codes.cpu()
        if hasattr(codes, "numpy"):
            codes = codes.numpy()

        arr = np.asarray(codes, dtype=np.int64)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        elif arr.ndim == 3 and arr.shape[0] == 1:
            arr = arr[0]
        if arr.ndim != 2 or arr.shape[1] != 16:
            raise ValueError(f"expected codec IDs shaped [frames, 16], got {arr.shape}")
        return arr

    def __enter__(self) -> "StreamingVocoderSession":
        if self._original_forward is not None:
            raise RuntimeError("streaming vocoder session is already active")

        original_forward = getattr(self._talker, "forward", None)
        if not callable(original_forward):
            raise RuntimeError("talker.forward is not callable")
        self._original_forward = original_forward

        def streaming_forward(*args: Any, **kwargs: Any) -> Any:
            result = original_forward(*args, **kwargs)
            hidden_states = getattr(result, "hidden_states", None)
            if not isinstance(hidden_states, tuple) or len(hidden_states) < 2:
                raise RuntimeError("talker output is missing the codec-ID hidden-state slot")

            codec_ids = hidden_states[-1]
            if codec_ids is not None:  # prefill intentionally returns None
                self._capture(codec_ids)
            return result

        # GenerationMixin validates kwargs using inspect.signature(forward).
        # Preserve the original bound-method signature while observing returns.
        streaming_forward.__signature__ = inspect.signature(original_forward)  # type: ignore[attr-defined]
        self._talker.forward = streaming_forward
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._original_forward is not None:
            self._talker.forward = self._original_forward
            self._original_forward = None

        # Do not emit a misleading final chunk after failed generation. Bytes
        # already emitted at complete boundaries remain a transport concern.
        if exc_type is None:
            self.flush()

    @property
    def generated_frames(self) -> int:
        return len(self._generated)

    @property
    def reference_frames(self) -> int:
        return int(self._reference_codes.shape[0])

    @property
    def total_frames(self) -> int:
        return self.reference_frames + self.generated_frames

    @property
    def decode_boundaries(self) -> tuple[int, ...]:
        return tuple(self._decode_boundaries)

    @property
    def full_waveform(self) -> np.ndarray:
        if self._last_waveform is None:
            raise RuntimeError("streaming vocoder has not decoded a prefix")
        return self._last_waveform

    def matches_codes(self, codes: Any) -> bool:
        """Return whether an upstream terminal decode uses the captured prefix."""
        try:
            normalized = self._normalize_codes(codes)
        except (TypeError, ValueError):
            return False
        return np.array_equal(normalized, self._all_codes())

    def _capture(self, codec_ids: Any) -> None:
        rows = self._normalize_codes(codec_ids)
        for row in rows:
            if self._eos_token_id is not None and int(row[0]) == self._eos_token_id:
                continue
            self._generated.append(np.array(row, dtype=np.int64, copy=True))

        total_frames = self._reference_codes.shape[0] + len(self._generated)
        ready_frames = (total_frames // self._chunk_frames) * self._chunk_frames
        if ready_frames > self._decoded_total_frames:
            self._decode_and_emit(ready_frames)

    def flush(self) -> None:
        total_frames = self._reference_codes.shape[0] + len(self._generated)
        if total_frames > self._decoded_total_frames:
            self._decode_and_emit(total_frames)

    def _all_codes(self) -> np.ndarray:
        if self._generated:
            generated = np.stack(self._generated, axis=0)
        else:
            generated = np.empty((0, 16), dtype=np.int64)
        return np.concatenate((self._reference_codes, generated), axis=0)

    def _decode_and_emit(self, total_frames: int) -> None:
        codes = self._all_codes()[:total_frames]
        wav = np.asarray(self._decode_prefix(codes), dtype=np.float32).reshape(-1)
        expected_samples = total_frames * self._samples_per_frame
        if wav.size != expected_samples:
            raise RuntimeError(
                f"vocoder returned {wav.size} samples for {total_frames} frames; "
                f"expected {expected_samples}"
            )
        self._last_waveform = wav

        reference_samples = self._reference_codes.shape[0] * self._samples_per_frame
        start = max(reference_samples, self._emitted_samples)
        if wav.size > start:
            chunk = wav[start:].astype(np.float32, copy=False)
            self._on_audio_chunk(chunk)
            self._emitted_samples = wav.size
        self._decoded_total_frames = total_frames
        self._decode_boundaries.append(total_frames)

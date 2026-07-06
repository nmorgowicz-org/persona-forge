from __future__ import annotations

from typing import Any


class FakeWhisperModel:
    """Zero-cost stand-in for faster-whisper.

    Used only by asr_check_text normalisation / matching tests.
    """

    def __init__(self, transcript: str | None = None) -> None:
        self.transcript = transcript or "This is a fake transcript."

    def transcribe(
        self,
        audio: Any,
        language: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {"segments": [{"text": self.transcript}]}

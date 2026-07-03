"""Fast Whisper-based no-speech gate for OmniVoice candidate takes.

Nick's feedback, 2026-07-03: audio_post.analyze_take's spectral-flatness heuristic catches
narrowband drones fast and cheaply, but it's a proxy — it can miss other dead-air/SFX
signatures (broadband hiss, non-speech babble, clipped garbage) that don't happen to have a
tonal signature. Running a tiny Whisper model and checking whether it transcribes to
*anything* is a much more direct "is there actually speech here" signal. This is layered on
top of (not instead of) analyze_take: analyze_take stays a free, always-run first pass; this
only runs on takes that already passed it, since it's the more expensive check.

faster-whisper (CTranslate2 backend) rather than openai-whisper: this is a CPU-only box, and
CTranslate2's int8 CPU path is materially faster than torch-based whisper for a model this
small, so the added latency per candidate stays negligible next to OmniVoice's own generation
time.
"""

from __future__ import annotations

import numpy as np

_WHISPER_TARGET_SR = 16000

_whisper_model = None


def _get_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        # tiny.en: this only needs to answer "is there speech at all", not produce an accurate
        # transcript, so the smallest English-only model is plenty and keeps load/decode cost
        # low. int8 is the fastest CPU compute type CTranslate2 offers.
        _whisper_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    return _whisper_model


def has_speech(audio: np.ndarray, sr: int) -> tuple[bool, str]:
    """Return (has_speech, transcript). Empty/whitespace-only transcript means Whisper found
    nothing to transcribe (silence, drone, noise, SFX) — treated as "no speech". Uses
    faster-whisper's built-in VAD filter so pure silence/noise short-circuits fast instead of
    wasting decode steps on it."""
    x = np.asarray(audio, dtype=np.float32).ravel()
    if x.size == 0:
        return False, ""

    if sr != _WHISPER_TARGET_SR:
        import librosa

        x = librosa.resample(x, orig_sr=sr, target_sr=_WHISPER_TARGET_SR)

    model = _get_model()
    segments, _info = model.transcribe(
        x,
        language="en",
        vad_filter=True,
        beam_size=1,
        condition_on_previous_text=False,
    )
    text = " ".join(seg.text for seg in segments).strip()
    return bool(text), text

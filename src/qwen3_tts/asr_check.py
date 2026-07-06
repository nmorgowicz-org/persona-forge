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


def has_speech(
    audio: np.ndarray,
    sr: int,
) -> tuple[bool, str, float | None]:
    """Return (has_speech, transcript, avg_logprob).
    
    - has_speech: True if Whisper produced any non-empty transcript.
    - transcript: concatenated text.
    - avg_logprob: approximate average log-prob across segments (None if not available
      or no segments). Used as a secondary quality signal, not as a hard gate.
    
    Uses faster-whisper's built-in VAD filter so pure silence/noise short-circuits fast.
    """
    x = np.asarray(audio, dtype=np.float32).ravel()
    if x.size == 0:
        return False, "", None

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
    parts: list[str] = []
    logprobs: list[float] = []

    for seg in segments:
        parts.append(seg.text.strip())
        # faster-whisper segments expose `avg_logprob`
        lp = getattr(seg, "avg_logprob", None)
        if lp is not None and not np.isnan(lp):
            logprobs.append(float(lp))

    text = " ".join(parts).strip()
    avg_logprob = (float(np.mean(logprobs)) if logprobs else None)
    return bool(text), text, avg_logprob


import re
import os

# Tunable thresholds (overridable via env).
# These are initial conservative settings — to be refined with listening tests.
_MIN_MATCH_SCORE_SHORT = float(os.environ.get("ASR_MIN_MATCH_SHORT", "0.70"))
_MIN_MATCH_SCORE_LONG = float(os.environ.get("ASR_MIN_MATCH_LONG", "0.80"))
_MAX_WORDS_SHORT = int(os.environ.get("ASR_SHORT_SEGMENT_WORDS", "5"))
_MAX_SOFT_MATCH_SCORE = float(os.environ.get("ASR_SOFT_MAX_SCORE", "0.75"))
_SOFT_REJECT_IF_LOGPROB_BELOW = float(os.environ.get("ASR_SOFT_LOGPROB", "-1.5"))


def _normalize_for_match(text: str) -> list[str]:
    """Normalize text for fuzzy transcript matching: remove brackets/non-verbals,
    punctuation, lowercase, tokenize to words."""
    # Remove bracketed non-verbals: [sigh], [laughter], etc.
    s = re.sub(r"\[.*?\]", "", text, flags=re.IGNORECASE)
    # Lowercase
    s = s.lower()
    # Remove non-alphanumeric characters except spaces and basic punctuation we'll strip.
    s = re.sub(r"[^a-z0-9\s']", " ", s)
    # Tokenize into words (apostrophe kept to avoid splitting contractions).
    words = s.split()
    return [w.strip("'") for w in words if w]


def compute_transcript_match_score(
    reference_text: str,
    whisper_text: str,
) -> float:
    """Compute an in-order word match score between reference and Whisper transcript.
    
    Returns a value in [0, 1]:
      - 1.0: all reference words appear in order in the transcript.
      - 0.0: no alignment.
    
    This is intentionally fuzzy: small variations and fillers are tolerated;
    the goal is to catch obviously wrong/garbled takes.
    """
    ref_words = _normalize_for_match(reference_text)
    hyp_words = _normalize_for_match(whisper_text)

    if not ref_words:
        # Nothing to match against → treat as pass (don't over-constrain).
        return 1.0

    ref_idx = 0
    hyp_idx = 0
    matched = 0

    while ref_idx < len(ref_words) and hyp_idx < len(hyp_words):
        if hyp_words[hyp_idx] == ref_words[ref_idx]:
            matched += 1
            ref_idx += 1
        hyp_idx += 1

    return matched / len(ref_words)


def validate_reference_text(
    wav_path: str,
    expected_text: str,
    *,
    warn_threshold: float = 0.70,
    fail_threshold: float = 0.50,
) -> dict:
    """Transcribe reference audio with Whisper and compare to expected_text.

    Returns:
        {
            "ok": bool,
            "severity": "ok" | "warn" | "fail" | "no_speech" | "error",
            "match_score": float|None,
            "whisper_transcript": str,
            "suggestion": str|None
        }
    """
    import soundfile as sf

    try:
        audio, sr = sf.read(wav_path)
    except Exception as e:
        return {
            "ok": False,
            "severity": "error",
            "match_score": None,
            "whisper_transcript": "",
            "suggestion": f"Failed to read reference audio: {e}",
        }

    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    has_speech_result, transcript, _logprob = has_speech(audio, sr)

    if not has_speech_result or not transcript.strip():
        return {
            "ok": False,
            "severity": "no_speech",
            "match_score": 0.0,
            "whisper_transcript": transcript,
            "suggestion": "Reference audio contains no detectable speech.",
        }

    score = compute_transcript_match_score(expected_text, transcript)

    if score >= warn_threshold:
        return {
            "ok": True,
            "severity": "ok",
            "match_score": score,
            "whisper_transcript": transcript,
            "suggestion": None,
        }
    if score >= fail_threshold:
        return {
            "ok": False,
            "severity": "warn",
            "match_score": score,
            "whisper_transcript": transcript,
            "suggestion": (
                "The transcript is partially mismatched. Verify REF_TEXT (or this voice's reference text) "
                "exactly matches what's spoken."
            ),
        }
    return {
        "ok": False,
        "severity": "fail",
        "match_score": score,
        "whisper_transcript": transcript,
        "suggestion": (
            "Severe mismatch: the reference text does not match the audio. "
            "Speech quality will likely be degraded. "
            "Fix REF_TEXT in your .env or Compose file, or update this voice's sample_text."
        ),
    }

"""
Forced-alignment engine (Phase 2 of the boundary-aware pause re-architecture).

Given reference audio and its known transcript, produce frame-accurate word
boundaries with per-word confidence and punctuation ownership. This is pure
forced alignment (audio + known text), not ASR — the transcript is stored, so we
never need Whisper.

The runtime is an ONNX MMS-300M CTC aligner via `onnxruntime` (portable CPU
execution provider baseline; see plan §5.2). The heavy model path is isolated
behind an injectable `emit` callback so every deterministic piece — transcript
normalization, CTC Viterbi, boundary derivation, punctuation ownership,
confidence-based divergence handling, and cache identity — is unit-testable
without loading the 302 MB model. Importing this module never imports
`onnxruntime`; the session is created lazily on first real alignment.

Design mirrors the validated Phase 0 spike (`docs/spikes/phase0_alignment/`).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from dataclasses import asdict, dataclass
from typing import Any, Callable, List, Optional, Tuple

import numpy as np
from scipy.signal import resample_poly
from scipy.special import log_softmax

logger = logging.getLogger(__name__)

# --- Identity / versioning (every field participates in the cache key) ---

ENGINE_ID = "mms-onnx-v1"
MODEL_ID = "onnx-community/mms-300m-1130-forced-aligner-ONNX"
MODEL_REVISION = "2100fb247d8e43962eef24491597fbeb8b469531"  # immutable pin
MODEL_ONNX_FILE = "onnx/model_int8.onnx"  # INT8 aligner weights within the repo
PREPROCESS_VERSION = 1
SCHEMA_VERSION = 1
DEFAULT_LANGUAGE = "en"
TARGET_SR = 16000
DEFAULT_GRANULARITY = "word"

# Per-boundary confidence floor. Below it a word is "uncertain" — the transcript
# and audio diverge there (user edited text but not audio, accent-driven
# mismatch, …). Phase 3 will VAD-search around an uncertain boundary rather than
# cut blindly; here we only flag it.
CONF_MIN = 0.6

BLANK = 0
# MMS-300M CTC vocabulary (from the Phase 0 spike). <star> is an added
# zero-log-score class for audio/transcript divergence.
VOCAB = {
    "<blank>": 0, "<pad>": 1, "</s>": 2, "<unk>": 3,
    "a": 4, "i": 5, "e": 6, "n": 7, "o": 8, "u": 9, "t": 10,
    "s": 11, "r": 12, "m": 13, "k": 14, "l": 15, "d": 16,
    "g": 17, "h": 18, "y": 19, "b": 20, "p": 21, "w": 22,
    "c": 23, "v": 24, "j": 25, "z": 26, "f": 27, "'": 28,
    "q": 29, "x": 30, "<star>": 31,
}
STAR = VOCAB["<star>"]

_WORD_RE = re.compile(r"[A-Za-z']+")
# Group 1: ellipsis, 2: sentence enders, 3: clause-level marks.
_PUNCT = re.compile(r"(\.{3,}|…)|([.!?])|([,;:]|—|–)")

# An emitter maps preprocessed 16 kHz mono audio to raw CTC logits [T, 31].
Emitter = Callable[[np.ndarray], np.ndarray]


@dataclass
class Boundary:
    """One aligned word. `kind` is 'word', 'sentence_split' (owns interior
    sentence punctuation), or 'uncertain' (confidence below CONF_MIN)."""

    text: str
    start: float
    end: float
    score: float
    kind: str
    owns_clause: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --- Transcript normalization + punctuation ownership -------------------------

def normalize_transcript(transcript: str) -> List[dict[str, Any]]:
    """Tokenize into spoken words while retaining source offsets and attaching
    trailing punctuation to the preceding word (deterministic ownership).

    Decimals (``3.5``) and common abbreviations (``Dr.``) do not own a sentence
    boundary. Only *interior* marks (text follows) can — a terminal mark has no
    downstream word to segment.
    """
    from .prosody_triage import is_non_boundary_dot

    text = transcript or ""
    trimmed_len = len(text.rstrip())
    tokens: List[dict[str, Any]] = []
    for match in _WORD_RE.finditer(text):
        tokens.append({
            "word": match.group(0).lower(),
            "src_start": match.start(),
            "src_end": match.end(),
            "owns_sentence_end": False,
            "owns_clause": False,
        })
    if not tokens:
        return tokens

    for pm in _PUNCT.finditer(text):
        # Owner = last word ending at or before this mark.
        owner = None
        for tok in tokens:
            if tok["src_end"] <= pm.start():
                owner = tok
            else:
                break
        if owner is None:
            continue
        interior = pm.end() < trimmed_len
        if not interior:
            continue
        if pm.group(1):
            owner["owns_sentence_end"] = True
        elif pm.group(2):
            if pm.group(2) == "." and is_non_boundary_dot(text, pm.start()):
                continue
            owner["owns_sentence_end"] = True
        elif pm.group(3):
            owner["owns_clause"] = True
    return tokens


# --- Tokenization + CTC Viterbi (from the Phase 0 spike) ----------------------

def _targets(words: List[str]) -> Tuple[np.ndarray, List[Tuple[int, int]]]:
    """Build the star-bracketed target id sequence and per-word (first, last)
    index ranges into it."""
    ids = [STAR]
    ranges: List[Tuple[int, int]] = []
    for word in words:
        start = len(ids)
        ids.extend(VOCAB.get(ch, VOCAB["<unk>"]) for ch in word)
        ranges.append((start, len(ids) - 1))
    ids.append(STAR)
    return np.asarray(ids, dtype=np.int64), ranges


def forced_align(log_probs: np.ndarray, targets: np.ndarray, blank: int = BLANK):
    """Viterbi over the standard CTC blank-interleaved state graph."""
    t_count = log_probs.shape[0]
    states = np.empty(2 * len(targets) + 1, dtype=np.int64)
    states[0::2] = blank
    states[1::2] = targets
    neg = -np.inf
    scores = np.full((t_count, len(states)), neg, dtype=np.float32)
    back = np.zeros((t_count, len(states)), dtype=np.int8)
    scores[0, 0] = log_probs[0, blank]
    scores[0, 1] = log_probs[0, targets[0]]
    for t in range(1, t_count):
        for s, label in enumerate(states):
            candidates = [(scores[t - 1, s], 0)]
            if s:
                candidates.append((scores[t - 1, s - 1], 1))
            if s > 1 and label != blank and label != states[s - 2]:
                candidates.append((scores[t - 1, s - 2], 2))
            previous, step = max(candidates, key=lambda item: item[0])
            scores[t, s] = previous + log_probs[t, label]
            back[t, s] = step
    state = len(states) - 1 if scores[-1, -1] >= scores[-1, -2] else len(states) - 2
    state_path = np.empty(t_count, dtype=np.int64)
    for t in range(t_count - 1, -1, -1):
        state_path[t] = state
        if t:
            state -= int(back[t, state])
    labels = states[state_path]
    frame_scores = log_probs[np.arange(t_count), labels]
    return state_path, frame_scores


# --- Preprocessing (never mutates the saved master) ---------------------------

def preprocess(wav: np.ndarray, sr: int) -> np.ndarray:
    """Downmix, resample to the model rate, and normalize for the emission pass."""
    wav = np.asarray(wav, dtype=np.float32)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    wav = wav.ravel()
    if sr != TARGET_SR:
        wav = resample_poly(wav, TARGET_SR, sr).astype(np.float32)
    mean = float(wav.mean())
    std = float(wav.std())
    return ((wav - mean) / np.sqrt(std * std + 1e-7)).astype(np.float32)


# --- Lazy ONNX session (isolated; import-safe) --------------------------------

_session = None
_session_lock = threading.Lock()


def _providers() -> List[str]:
    env = os.getenv("ALIGNER_PROVIDERS", "").strip()
    if env:
        return [p.strip() for p in env.split(",") if p.strip()]
    return ["CPUExecutionProvider"]  # portable baseline; accelerators are opt-in


def _model_path() -> str:
    return os.getenv("ALIGNER_MODEL_PATH", "").strip()


def resolve_model_path() -> str:
    """Return a filesystem path to the aligner ONNX weights, downloading them on
    first use if necessary.

    Resolution order:
      1. ``ALIGNER_MODEL_PATH`` — explicit override (offline/air-gapped hosts,
         locally-exported IR). Honored verbatim; must point at an existing file.
      2. Hugging Face hub — download ``MODEL_ONNX_FILE`` from ``MODEL_ID`` pinned
         to the immutable ``MODEL_REVISION`` into the shared HF cache. This
         mirrors how the base / Pocket-TTS checkpoints self-provision on first
         run, so a fresh deploy needs zero manual model placement.
    """
    override = _model_path()
    if override:
        if not os.path.isfile(override):
            raise RuntimeError(
                f"ALIGNER_MODEL_PATH is set to {override!r} but no file exists there."
            )
        return override

    from huggingface_hub import hf_hub_download  # noqa: PLC0415 — deferred import

    logger.info(
        "Fetching forced-aligner weights %s@%s:%s (first-run cache warm)",
        MODEL_ID, MODEL_REVISION, MODEL_ONNX_FILE,
    )
    # HF caches by (repo, revision, file); subsequent calls resolve to the cached
    # copy without a network round-trip. The revision pin keeps the cache
    # identity stamped into meta.json valid across restarts.
    return hf_hub_download(
        repo_id=MODEL_ID,
        filename=MODEL_ONNX_FILE,
        revision=MODEL_REVISION,
    )


def load_session():
    """Lazily construct the ONNX session (imports onnxruntime only here)."""
    global _session
    with _session_lock:
        if _session is None:
            import onnxruntime as ort  # noqa: PLC0415 — deferred heavy import

            path = resolve_model_path()
            logger.info("Loading forced-aligner ONNX model: %s (providers=%s)", path, _providers())
            _session = ort.InferenceSession(path, providers=_providers())
        return _session


def unload_session() -> bool:
    """Drop the ONNX session to release RSS (idle-unload / LOW_RAM). Returns True
    if a session was actually released."""
    global _session
    with _session_lock:
        released = _session is not None
        _session = None
    if released:
        logger.info("Released forced-aligner ONNX session.")
    return released


def _default_emit(wav16k: np.ndarray) -> np.ndarray:
    session = load_session()
    return session.run(["logits"], {"input_values": wav16k[None, :]})[0][0]


# --- Public alignment entry point ---------------------------------------------

def align(
    wav: np.ndarray,
    sr: int,
    transcript: str,
    *,
    granularity: str = DEFAULT_GRANULARITY,
    language: str = DEFAULT_LANGUAGE,
    emit: Optional[Emitter] = None,
    conf_min: float = CONF_MIN,
) -> List[Boundary]:
    """Align `transcript` to `wav`, returning per-word boundaries in seconds.

    `emit` overrides the model (raw logits [T, 31] from 16 kHz audio) — the real
    ONNX session by default, an injected function in tests.
    """
    tokens = normalize_transcript(transcript)
    if not tokens:
        return []

    wav16k = preprocess(wav, sr)
    emitter = emit or _default_emit
    logits = np.asarray(emitter(wav16k), dtype=np.float32)
    emissions = log_softmax(logits, axis=-1)
    # Upstream ctc-forced-aligner defines <star> as an added zero-log-score class.
    emissions = np.concatenate(
        [emissions, np.zeros((emissions.shape[0], 1), dtype=np.float32)], axis=1
    )

    words = [tok["word"] for tok in tokens]
    targets, ranges = _targets(words)
    state_path, frame_scores = forced_align(emissions, targets, BLANK)
    stride = len(wav16k) / TARGET_SR / emissions.shape[0]

    boundaries: List[Boundary] = []
    for tok, (first, last) in zip(tokens, ranges):
        target_states = np.arange(first * 2 + 1, last * 2 + 2, 2)
        frames = np.flatnonzero(np.isin(state_path, target_states))
        if not len(frames):
            # Word never claimed a frame → treat as a divergence at zero width.
            boundaries.append(Boundary(tok["word"], 0.0, 0.0, 0.0, "uncertain", tok["owns_clause"]))
            continue
        mean_log = float(frame_scores[frames].mean())
        score = float(np.exp(mean_log))
        if score < conf_min:
            kind = "uncertain"
        elif tok["owns_sentence_end"]:
            kind = "sentence_split"
        else:
            kind = "word"
        boundaries.append(Boundary(
            text=tok["word"],
            start=round(float(frames[0] * stride), 3),
            end=round(float((frames[-1] + 1) * stride), 3),
            score=round(score, 4),
            kind=kind,
            owns_clause=tok["owns_clause"],
        ))
    return boundaries


# --- Cache identity + hashing -------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# Every field here is part of the cache key: a difference in any of them
# invalidates a cached alignment (plan §5.4).
IDENTITY_KEYS = (
    "engine", "audio_sha256", "transcript_sha256", "language",
    "model_id", "model_revision", "preprocess_version", "schema_version",
    "sample_rate", "granularity",
)


def cache_identity(
    audio_sha256: str,
    transcript_sha256: str,
    *,
    language: str = DEFAULT_LANGUAGE,
    granularity: str = DEFAULT_GRANULARITY,
) -> dict[str, Any]:
    return {
        "engine": ENGINE_ID,
        "audio_sha256": audio_sha256,
        "transcript_sha256": transcript_sha256,
        "language": language,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "preprocess_version": PREPROCESS_VERSION,
        "schema_version": SCHEMA_VERSION,
        "sample_rate": TARGET_SR,
        "granularity": granularity,
    }


def identity_matches(cached: Optional[dict[str, Any]], current: dict[str, Any]) -> bool:
    """True only if every identity field of a cached alignment matches `current`."""
    if not isinstance(cached, dict):
        return False
    return all(cached.get(key) == current.get(key) for key in IDENTITY_KEYS)


def build_alignment_record(
    boundaries: List[Boundary], identity: dict[str, Any]
) -> dict[str, Any]:
    """Assemble the persisted alignment record (identity + boundaries)."""
    return {**identity, "boundaries": [b.to_dict() for b in boundaries]}

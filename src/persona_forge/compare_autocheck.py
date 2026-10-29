"""Compare-tab "auto-check" hints: word error rate and speaker similarity for one generated clip.

Both numbers are *hints*, never ratings (plan §5.10): the similarity model is not calibrated for
synthetic voices and a small Whisper mishears things a person would not. They exist so a listener
can see "the engine skipped a word" or "this clone is far from the reference" next to their own
rating.

Policy (plan §0): offline only. Nothing here downloads while a request is served or while the page
is browsed. A model that is not already on disk is reported as unavailable, and the only way to get
it is ``DownloadJob.start()``, which the UI calls from an explicit button. A metric that cannot run
is ``None`` with a note; it is never estimated.

Models (pinned revisions, looked up in the app's model cache first, then the default Hugging Face
cache so an existing ``faster-whisper`` download is reused):

* word error rate: ``Systran/faster-whisper-tiny.en`` (the same engine/model/settings as
  ``asr_check``; the already-loaded instance is reused when there is one);
* speaker similarity: ``microsoft/wavlm-base-plus-sv`` x-vector cosine to the saved voice's
  reference clip (the metric the Phase B bake-off used).

Scheduling: the repository has no priority mechanism for ``model.executor``, so auto-check never
enters it. It runs on the request thread under its own non-blocking lock (one check at a time, a
second click is refused rather than queued so it cannot hold the gunicorn threads that serve
endpoint requests) and only when the user clicks Check. It does not touch process-wide thread
settings; Whisper is capped at two CPU threads.
"""

from __future__ import annotations

import io
import logging
import math
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from persona_forge import paths, text_normalizer

logger = logging.getLogger(__name__)

TARGET_SR = 16000
MAX_CLIP_SECONDS = 120.0
MAX_REFERENCE_SECONDS = 30.0
MIN_EMBED_SECONDS = 0.5

DISCLAIMER = (
    "Auto-check is a hint, not a rating. It is not calibrated for synthetic voices and never "
    "replaces your rating."
)


class ClipError(ValueError):
    """The uploaded clip cannot be checked; the message is safe to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_message = message


class AutoCheckUnavailable(RuntimeError):
    """None of the requested metrics can run because their models are not on disk."""


class AutoCheckBusy(RuntimeError):
    """Another check is already running."""


class _NotInstalled(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    purpose: str
    repo: str
    revision: str
    files: tuple[str, ...]
    size_bytes: int

    @property
    def size_label(self) -> str:
        return f"{round(self.size_bytes / 1e6)} MB"


WHISPER_TINY_EN = ModelSpec(
    id="whisper-tiny-en",
    label="Speech-to-text (Whisper tiny.en)",
    purpose="word_error_rate",
    repo="Systran/faster-whisper-tiny.en",
    revision="0d3d19a32d3338f10357c0889762bd8d64bbdeba",
    files=("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"),
    size_bytes=78_090_594,
)
WAVLM_SV = ModelSpec(
    id="wavlm-base-plus-sv",
    label="Speaker similarity (WavLM-SV)",
    purpose="speaker_similarity",
    repo="microsoft/wavlm-base-plus-sv",
    revision="feb593a6c23c1cc3d9510425c29b0a14d2b07b1e",
    files=("config.json", "preprocessor_config.json", "pytorch_model.bin"),
    size_bytes=404_605_907,
)
SPECS = (WHISPER_TINY_EN, WAVLM_SV)


# --- text metrics ------------------------------------------------------------------------------


_CLOCK_WITH_PERIOD = re.compile(r"\b(\d{1,2})\.(\d{2})(?=\s?[ap]\.?m\b)", re.IGNORECASE)


def normalize_words(text: str) -> list[str]:
    """Lower-case words with numbers, money, times and codes spelled out the way they are spoken.

    Applied to both the sample text and the transcript, so "10 minutes" (what Whisper writes) and
    "ten minutes" (what the engine said) compare equal, and punctuation, case, hyphens and
    apostrophes never count as errors. Two more spellings Whisper varies are folded together: a
    time written "3.30 pm" (only before am/pm, so decimals stay decimals) reads as "3:30 pm", and a
    run of single letters ("A B", "p m", "U.S.A.") becomes one token ("ab", "pm", "usa"), so
    "AB-104" and "AB 104" agree. A lone "a" or "I" is untouched.
    """
    text = (text or "").replace("\u2019", "'").replace("\u2018", "'")
    text = _CLOCK_WITH_PERIOD.sub(r"\1:\2", text)
    words = re.findall(r"[^\W_]+", text_normalizer.normalize(text).lower().replace("'", ""))
    merged: list[str] = []
    letters: list[str] = []
    for word in [*words, ""]:
        if len(word) == 1 and word.isalpha():
            letters.append(word)
            continue
        if letters:
            merged.append("".join(letters))
            letters = []
        if word:
            merged.append(word)
    return merged


def word_error_rate(reference: str, hypothesis: str) -> dict[str, Any]:
    """Word error rate of ``hypothesis`` against ``reference`` after normalisation.

    ``wer`` is ``None`` when the reference has no words. It can exceed 1.0 (many insertions).
    """
    ref, hyp = normalize_words(reference), normalize_words(hypothesis)
    n, m = len(ref), len(hyp)
    # cost[i][j]: edit distance between ref[:i] and hyp[:j].
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = i
    for j in range(1, m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            swap = 0 if ref[i - 1] == hyp[j - 1] else 1
            cost[i][j] = min(cost[i - 1][j - 1] + swap, cost[i - 1][j] + 1, cost[i][j - 1] + 1)
    substitutions = deletions = insertions = 0
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and cost[i][j] == cost[i - 1][j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1):
            substitutions += 0 if ref[i - 1] == hyp[j - 1] else 1
            i, j = i - 1, j - 1
        elif i > 0 and cost[i][j] == cost[i - 1][j] + 1:
            deletions += 1
            i -= 1
        else:
            insertions += 1
            j -= 1
    return {
        "wer": (substitutions + deletions + insertions) / n if n else None,
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "reference_words": n,
        "hypothesis_words": m,
    }


def cosine(a: np.ndarray, b: np.ndarray) -> float | None:
    """Cosine similarity, or ``None`` when either vector has no length."""
    a, b = np.asarray(a, dtype=np.float64).ravel(), np.asarray(b, dtype=np.float64).ravel()
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    if not math.isfinite(norm) or norm == 0.0:
        return None
    return float(np.dot(a, b) / norm)


# --- audio -------------------------------------------------------------------------------------


def _to_16k_mono(data: np.ndarray, sr: int) -> np.ndarray:
    from scipy.signal import resample_poly

    mono = data.mean(axis=1) if data.ndim > 1 else data
    mono = np.asarray(mono, dtype=np.float32)
    if sr != TARGET_SR:
        factor = math.gcd(TARGET_SR, int(sr))
        mono = resample_poly(mono, TARGET_SR // factor, int(sr) // factor).astype(np.float32)
    return mono


def decode_clip(data: bytes) -> np.ndarray:
    """Decode an uploaded clip to 16 kHz mono float32. Raises ``ValueError`` for anything unusable."""
    import soundfile as sf

    if not data:
        raise ClipError("The audio clip is empty.")
    try:
        samples, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    except Exception as exc:  # noqa: BLE001 - soundfile raises several unrelated types
        raise ClipError("The audio clip could not be read as audio.") from exc
    if samples.shape[0] == 0:
        raise ClipError("The audio clip is empty.")
    if samples.shape[0] / sr > MAX_CLIP_SECONDS:
        raise ClipError(f"The audio clip is too long (over {MAX_CLIP_SECONDS:.0f} seconds).")
    return _to_16k_mono(samples, sr)


def _read_reference(path: str) -> np.ndarray:
    import soundfile as sf

    samples, sr = sf.read(path, dtype="float32", always_2d=True, frames=int(MAX_REFERENCE_SECONDS * 48000))
    clip = _to_16k_mono(samples, sr)
    return clip[: int(MAX_REFERENCE_SECONDS * TARGET_SR)]


# --- model lookup (offline) --------------------------------------------------------------------


def default_cache_dirs() -> list[Path]:
    """The app's model cache first, then the default Hugging Face cache (read-only reuse)."""
    dirs = [Path(paths.model_cache_dir())]
    try:
        from huggingface_hub import constants

        dirs.append(Path(constants.HF_HUB_CACHE))
    except Exception:  # noqa: BLE001 - lookup only; absence just means one fewer place to look
        pass
    seen: list[Path] = []
    for item in dirs:
        if item not in seen:
            seen.append(item)
    return seen


def find_snapshot(spec: ModelSpec, cache_dirs: Sequence[Path]) -> Path | None:
    """A complete snapshot of ``spec`` on disk (pinned revision preferred), or ``None``. No network."""
    folder = "models--" + spec.repo.replace("/", "--")
    for cache in cache_dirs:
        snapshots = Path(cache) / folder / "snapshots"
        try:
            revisions = sorted(p for p in snapshots.iterdir() if p.is_dir())
        except OSError:
            continue
        revisions.sort(key=lambda p: p.name != spec.revision)
        for snapshot in revisions:
            if all((snapshot / name).is_file() for name in spec.files):
                return snapshot
    return None


# --- checker -----------------------------------------------------------------------------------


class AutoChecker:
    """Runs the two metrics for one clip. Models load lazily from disk and unload when idle.

    ``stt`` / ``embedder`` inject stand-ins (tests): ``stt(audio16k) -> text`` and
    ``embedder(audio16k) -> vector``.
    """

    def __init__(
        self,
        *,
        stt: Callable[[np.ndarray], str] | None = None,
        embedder: Callable[[np.ndarray], np.ndarray] | None = None,
        cache_dirs: Sequence[Path] | None = None,
        idle_unload_seconds: float = 120.0,
    ) -> None:
        self._stt_injected = stt
        self._embed_injected = embedder
        self._cache_dirs = list(cache_dirs) if cache_dirs is not None else None
        self._idle = idle_unload_seconds
        self._run_lock = threading.Lock()
        self._load_lock = threading.Lock()
        self._stt_loaded: Callable[[np.ndarray], str] | None = None
        self._stt_owned = False
        self._embed_loaded: Callable[[np.ndarray], np.ndarray] | None = None
        self._timer: threading.Timer | None = None
        self._refs: dict[tuple[str, int, int], np.ndarray] = {}

    # -- discovery

    def _dirs(self) -> list[Path]:
        return self._cache_dirs if self._cache_dirs is not None else default_cache_dirs()

    def models_status(self) -> list[dict[str, Any]]:
        out = []
        for spec in SPECS:
            snapshot = find_snapshot(spec, self._dirs())
            injected = (self._stt_injected if spec is WHISPER_TINY_EN else self._embed_injected) is not None
            out.append(
                {
                    "id": spec.id,
                    "label": spec.label,
                    "purpose": spec.purpose,
                    "repo": spec.repo,
                    "revision": spec.revision,
                    "available": snapshot is not None or injected,
                    "size_bytes": spec.size_bytes,
                    "size_label": spec.size_label,
                    "path": str(snapshot) if snapshot else None,
                }
            )
        return out

    # -- loading

    def _get_stt(self) -> Callable[[np.ndarray], str]:
        if self._stt_injected is not None:
            return self._stt_injected
        with self._load_lock:
            if self._stt_loaded is None:
                self._stt_loaded, self._stt_owned = self._load_whisper()
            return self._stt_loaded

    def _load_whisper(self) -> tuple[Callable[[np.ndarray], str], bool]:
        from persona_forge import asr_check

        model, owned = asr_check._whisper_model, False
        if model is None:
            snapshot = find_snapshot(WHISPER_TINY_EN, self._dirs())
            if snapshot is None:
                raise _NotInstalled(WHISPER_TINY_EN.id)
            from faster_whisper import WhisperModel

            model = WhisperModel(
                str(snapshot), device="cpu", compute_type="int8", cpu_threads=2, local_files_only=True
            )
            owned = True

        def transcribe(audio: np.ndarray) -> str:
            # No VAD: the point is to see what the engine really said, including a dropped word.
            segments, _info = model.transcribe(
                audio, language="en", vad_filter=False, beam_size=1, condition_on_previous_text=False
            )
            return " ".join(seg.text.strip() for seg in segments).strip()

        return transcribe, owned

    def _get_embedder(self) -> Callable[[np.ndarray], np.ndarray]:
        if self._embed_injected is not None:
            return self._embed_injected
        with self._load_lock:
            if self._embed_loaded is None:
                self._embed_loaded = self._load_wavlm()
            return self._embed_loaded

    def _load_wavlm(self) -> Callable[[np.ndarray], np.ndarray]:
        snapshot = find_snapshot(WAVLM_SV, self._dirs())
        if snapshot is None:
            raise _NotInstalled(WAVLM_SV.id)
        import torch
        from transformers import AutoFeatureExtractor, WavLMForXVector

        extractor = AutoFeatureExtractor.from_pretrained(str(snapshot), local_files_only=True)
        net = WavLMForXVector.from_pretrained(str(snapshot), local_files_only=True).eval()

        def embed(audio: np.ndarray) -> np.ndarray:
            inputs = extractor(audio, sampling_rate=TARGET_SR, return_tensors="pt", padding=True)
            with torch.inference_mode():
                vector = net(**inputs).embeddings
            return torch.nn.functional.normalize(vector, dim=-1)[0].cpu().numpy()

        return embed

    def unload(self) -> bool:
        """Drop models this checker loaded. Returns True if anything was released."""
        with self._load_lock:
            released = self._stt_loaded is not None and self._stt_owned or self._embed_loaded is not None
            if self._stt_owned:
                self._stt_loaded = None
                self._stt_owned = False
            self._embed_loaded = None
            self._refs.clear()
        if released:
            logger.info("Released auto-check models.")
        return bool(released)

    def _arm_idle_unload(self) -> None:
        if self._idle <= 0:
            return
        with self._load_lock:
            if self._timer is not None:
                self._timer.cancel()
            owns = (self._stt_loaded is not None and self._stt_owned) or self._embed_loaded is not None
            if not owns:
                self._timer = None
                return
            self._timer = threading.Timer(self._idle, self.unload)
            self._timer.daemon = True
            self._timer.start()

    # -- the check

    def _try(self, getter: Callable[[], Any]) -> tuple[Any, str | None]:
        """(callable, None) or (None, reason) where reason is ``missing`` or ``failed``."""
        try:
            return getter(), None
        except _NotInstalled:
            return None, "missing"
        except Exception:  # noqa: BLE001 - a broken model install must degrade to a note
            logger.exception("Auto-check model failed to load")
            return None, "failed"

    def check(self, clip: bytes, text: str, reference_path: str | None = None) -> dict[str, Any]:
        """Score one clip. Raises ``ValueError`` (bad audio), ``AutoCheckBusy`` or
        ``AutoCheckUnavailable`` (no requested metric can run)."""
        audio = decode_clip(clip)
        if not self._run_lock.acquire(blocking=False):
            raise AutoCheckBusy("Another auto-check is still running.")
        try:
            return self._check(audio, text, reference_path)
        finally:
            self._run_lock.release()
            self._arm_idle_unload()

    def _check(self, audio: np.ndarray, text: str, reference_path: str | None) -> dict[str, Any]:
        notes: list[str] = []
        result: dict[str, Any] = {
            "wer": None,
            "transcript": None,
            "similarity": None,
            "details": None,
            "notes": notes,
            "disclaimer": DISCLAIMER,
        }
        stt, stt_why = self._try(self._get_stt)
        wants_similarity = bool(reference_path)
        embed, embed_why = self._try(self._get_embedder) if wants_similarity else (None, None)
        if stt is None and (embed is None):
            raise AutoCheckUnavailable("The auto-check models are not downloaded.")

        if stt is None:
            notes.append(_missing_note(WHISPER_TINY_EN, stt_why, "Word error rate"))
        else:
            try:
                transcript = stt(audio)
            except Exception:  # noqa: BLE001
                logger.exception("Auto-check transcription failed")
                notes.append("Word error rate: the speech-to-text model could not transcribe this clip.")
            else:
                score = word_error_rate(text, transcript)
                result["transcript"] = transcript
                result["wer"] = score.pop("wer")
                result["details"] = score
                if result["wer"] is None:
                    notes.append("Word error rate: the sample text has no words to compare.")
                elif not transcript.strip():
                    notes.append("No speech was recognised in this clip.")
                notes.append("Numbers, money, times and codes are spelled out the same way on both sides before comparing.")

        if not wants_similarity:
            notes.append("Speaker similarity needs a cloned voice: this slot has no reference clip to compare against.")
        elif embed is None:
            notes.append(_missing_note(WAVLM_SV, embed_why, "Speaker similarity"))
        else:
            result["similarity"] = self._similarity(embed, audio, reference_path or "", notes)
        return result

    def _similarity(
        self, embed: Callable[[np.ndarray], np.ndarray], audio: np.ndarray, reference_path: str, notes: list[str]
    ) -> float | None:
        if len(audio) < MIN_EMBED_SECONDS * TARGET_SR:
            notes.append("Speaker similarity: the clip is too short to measure.")
            return None
        try:
            stat = Path(reference_path).stat()
            key = (reference_path, stat.st_mtime_ns, stat.st_size)
            ref_vec = self._refs.get(key)
            if ref_vec is None:
                ref_vec = np.asarray(embed(_read_reference(reference_path)))
                if len(self._refs) >= 8:
                    self._refs.clear()
                self._refs[key] = ref_vec
            score = cosine(np.asarray(embed(audio)), ref_vec)
        except Exception:  # noqa: BLE001
            logger.exception("Auto-check similarity failed")
            notes.append("Speaker similarity: the reference clip or the model could not be used.")
            return None
        notes.append(
            "Speaker similarity is a cosine of WavLM-SV voice embeddings (1 is identical). Different voices "
            "can still score high; the Phase B bake-off's different-speaker floor was 0.85."
        )
        return score


def _missing_note(spec: ModelSpec, why: str | None, metric: str) -> str:
    if why == "failed":
        return f"{metric}: the {spec.label} model is on disk but could not be loaded (see the server log)."
    return f"{metric}: needs the {spec.label} model ({spec.size_label}). Enable auto-check to download it."


# --- opt-in download ---------------------------------------------------------------------------


def _hf_fetch(spec: ModelSpec, cache_dir: Path) -> None:
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=spec.repo,
        revision=spec.revision,
        allow_patterns=list(spec.files),
        cache_dir=str(cache_dir),
    )


class DownloadJob:
    """Background download of the auto-check models. Only ``start()`` touches the network, and the
    UI only calls it from an explicit button. Mirrors the pack install job: ``state`` is one of
    idle / running / done / error, polled until it settles."""

    def __init__(self, cache_dir: Path, fetch: Callable[[ModelSpec, Path], None] | None = None) -> None:
        self._cache_dir = Path(cache_dir)
        self._fetch = fetch or _hf_fetch
        self._lock = threading.Lock()
        self._finished = threading.Event()
        self._finished.set()
        self._job: dict[str, Any] = _idle_job()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._job)

    def wait(self, timeout: float | None = None) -> bool:
        return self._finished.wait(timeout)

    def start(self, specs: Sequence[ModelSpec]) -> bool:
        specs = list(specs)
        with self._lock:
            if self._job["state"] == "running" or not specs:
                return False
            self._finished.clear()
            self._job = {
                "state": "running",
                "step": "Starting",
                "step_index": 0,
                "step_count": len(specs),
                "error": None,
                "started_at": time.time(),
            }
        threading.Thread(target=self._run, args=(specs,), name="autocheck-download", daemon=True).start()
        return True

    def _set(self, **changes: Any) -> None:
        with self._lock:
            self._job.update(changes)

    def _run(self, specs: list[ModelSpec]) -> None:
        try:
            for index, spec in enumerate(specs, start=1):
                self._set(step=f"Downloading {spec.label} ({spec.size_label})", step_index=index)
                try:
                    self._fetch(spec, self._cache_dir)
                except OSError:
                    logger.exception("Auto-check model download failed: %s", spec.id)
                    self._set(
                        state="error",
                        error="Could not reach Hugging Face. Check your internet connection and try again.",
                    )
                    return
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Auto-check model download failed: %s", spec.id)
                    self._set(state="error", error=f"The download failed ({type(exc).__name__}); see the server log.")
                    return
            self._set(state="done", step="Downloaded")
        finally:
            self._finished.set()


def _idle_job() -> dict[str, Any]:
    return {"state": "idle", "step": "", "step_index": 0, "step_count": 0, "error": None}


# --- process-wide instances --------------------------------------------------------------------

_checker: AutoChecker | None = None
_download: DownloadJob | None = None
_singleton_lock = threading.Lock()


def get_checker() -> AutoChecker:
    global _checker
    with _singleton_lock:
        if _checker is None:
            import os

            try:
                idle = float(os.environ.get("AUTOCHECK_IDLE_UNLOAD_SECONDS", "120"))
            except ValueError:
                idle = 120.0
            _checker = AutoChecker(idle_unload_seconds=idle)
        return _checker


def get_download_job() -> DownloadJob:
    global _download
    with _singleton_lock:
        if _download is None:
            _download = DownloadJob(Path(paths.model_cache_dir()))
        return _download

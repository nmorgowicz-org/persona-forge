"""Kitten TTS 2 serving adapter (Phase C4).

Drives ``kitten2_worker`` in the pack's own virtualenv through ``PackProcess``. The worker starts
on first use, prepares each saved voice once per reference file, and exits after an idle period so
GPU/unified memory comes back. Pocket-TTS is never touched.
"""

from __future__ import annotations

import io
import json
import os
import threading
import wave
from pathlib import Path
from typing import Any, Callable, Iterator

import numpy as np

from persona_forge import (
    engine_packs,
    kitten2_pack,
    kitten2_worker,
    pack_logs,
    voice_bindings,
    voice_library,
)
from persona_forge.engine_lifecycle import (
    IN_FLIGHT,
    IdleUnloader,
    LoadTracker,
    wait_until_ready,
    warm_wait_s,
)
from persona_forge.pack_process import PackProcess, PackProcessError

ENGINE_ID = "kitten2"
PRESET_PREFIX = "kitten2:"
# Cloning needs the reference transcript (checked again at request time).
CLONE_NEEDS_TRANSCRIPT = True
# Loading reads the weights; the first compiled CUDA call is a separate ``warmup`` request, so a
# request that arrives meanwhile can be told to retry instead of queueing behind the compile.
LOAD_TIMEOUT_S = 300.0
WARMUP_TIMEOUT_S = 600.0
WARMUP_ESTIMATE_S = 35.0  # measured: about 33 s for the first compiled call on a 5090
REQUEST_TIMEOUT_S = 240.0
PREPARE_TIMEOUT_S = 120.0  # one ``prepare`` op on a loaded worker; it only records the reference


class EngineUnavailable(RuntimeError):
    """The pack is missing or the machine cannot run the engine."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.public_message = message


class InvalidVoice(ValueError):
    """The requested voice or preset does not exist for this engine."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.public_message = message


class EngineWarming(EngineUnavailable):
    """The engine is loading or warming up; the same request will work shortly.

    The speech route answers 503 with ``Retry-After`` and error code ``engine_warming``.
    """

    def __init__(self, label: str, state: str, retry_after_s: int) -> None:
        phrase = "warming up (compiling its first call)" if state == "warming" else "loading"
        super().__init__(f"{label} is {phrase}; retry in about {retry_after_s} s.")
        self.label = label
        self.state = state
        self.retry_after_s = retry_after_s


def pack_directory(root: Path | None = None) -> Path | None:
    return engine_packs.find_pack_dir(ENGINE_ID, root)


def pack_python(root: Path | None = None) -> Path | None:
    """Interpreter of the installed pack, or the ``KITTEN2_PYTHON`` development override.

    A pack only counts once its provisioner has published the verified stamp, so a half-finished
    install is never started.
    """
    override = os.environ.get("KITTEN2_PYTHON")
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    directory = pack_directory(root)
    if directory is None:
        return None
    if engine_packs.inspect_pack(directory).status != "verified":
        return None
    python = kitten2_pack.venv_python(directory)
    return python if python.is_file() else None


def is_installed(root: Path | None = None) -> bool:
    return pack_python(root) is not None


def list_presets(root: Path | None = None) -> list[str]:
    """Names of the built-in voices, read from the downloaded weights (no model load needed)."""
    directory = pack_directory(root)
    if directory is None or not is_installed(root):
        return []
    for catalog in sorted((directory / "hf").glob("models--*kitten-tts-2/snapshots/*/voices/voices.json")):
        try:
            data = json.loads(catalog.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            return sorted(str(name) for name in data)
    return []


_NON_ENGLISH = {"ar", "zh", "fr", "de", "hi", "it", "pt", "ru", "es"}

# Many voices carry no id prefix but are named for their language ("KoreanNewsAnchor").
_LANGUAGE_WORDS = {
    "Arabic": "ar", "Chinese": "zh", "Dutch": "nl", "French": "fr", "German": "de", "Hindi": "hi",
    "Indonesian": "id", "Italian": "it", "Japanese": "ja", "Korean": "ko", "Polish": "pl",
    "Portuguese": "pt", "Russian": "ru", "Spanish": "es", "Turkish": "tr",
}  # fmt: skip


def language_from_name(name: str) -> str | None:
    """Language code when the voice name starts with a language word, else ``None``."""
    for word, code in _LANGUAGE_WORDS.items():
        if name.startswith(word):
            return code
    return None


def preset_language(name: str, root: Path | None = None) -> str:
    """Language code of a preset: the catalog ``voice_id`` prefix (``fr_...``), else the name's
    leading language word, else ``en``."""
    named = language_from_name(name)
    directory = pack_directory(root)
    if directory is None:
        return named or "en"
    for catalog in (directory / "hf").glob("models--*kitten-tts-2/snapshots/*/voices/voices.json"):
        try:
            entry = json.loads(catalog.read_text(encoding="utf-8")).get(name, {})
        except (OSError, ValueError):
            continue
        prefix = str(entry.get("voice_id", ""))[:3]
        if prefix[2:] == "_" and prefix[:2] in _NON_ENGLISH:
            return prefix[:2]
        return named or "en"
    return named or "en"


def _decode_wav(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data)) as handle:
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0, rate


class Kitten2Engine:
    id = ENGINE_ID
    label = "Kitten TTS 2"

    idle_env = "KITTEN2_IDLE_UNLOAD_S"

    def __init__(
        self,
        idle_unload_s: float | None = None,
        *,
        timer_factory: Callable[..., Any] = threading.Timer,
    ) -> None:
        self._idle = IdleUnloader(
            env_name=self.idle_env,
            default_s=kitten2_pack.IDLE_UNLOAD_AFTER_S,
            on_idle=self.unload,
            manifest_value=lambda: engine_packs.idle_unload_after(self.id),
            override=idle_unload_s,
            timer_factory=timer_factory,
        )
        self._lock = threading.RLock()
        self._process: PackProcess | None = None
        # Use the exact binding identity for both lazy and explicit preparation.
        self._prepared: dict[str, dict[str, str]] = {}
        self._load_info: dict[str, Any] = {}
        # idle | loading | warming | ready | error, with elapsed time while loading or warming.
        self._tracker = LoadTracker(estimates={"warming": WARMUP_ESTIMATE_S})

    def status(self) -> dict[str, Any]:
        """Load state plus the speed mode and, when fast mode is unavailable, why."""
        seconds, source = self._idle.resolve()
        return {
            **self._load_info,
            **self._tracker.snapshot(),
            "idle_unload_after": seconds,
            "idle_unload_source": source,
        }

    @property
    def idle_unload_after(self) -> float:
        """Effective idle-unload seconds (0 = never)."""
        return self._idle.seconds

    def recheck(self) -> bool:
        """Reload the worker in the background so a newly installed compiler is picked up.

        Returns False when a load is already running.
        """
        if not self._tracker.claim_load():
            return False
        self._start_load(reload=True, name="kitten2-recheck")
        return True

    def _start_load(self, *, reload: bool, name: str) -> None:
        threading.Thread(
            target=self._load_in_background, kwargs={"reload": reload}, name=name, daemon=True
        ).start()

    def _load_in_background(self, *, reload: bool = False) -> None:
        try:
            if reload:
                self.unload()
            with self._lock:
                self._ensure_started()
                self._arm_idle_timer()
        except Exception as exc:  # the failure is on the card and in the next request's 503
            self._tracker.fail(str(exc))

    def describe(self) -> dict[str, Any]:
        from persona_forge import speech_engines

        info = speech_engines.ENGINES[self.id].as_dict()
        info["installed"] = is_installed()
        info["status"] = self.status()
        return info

    # -- lifecycle -----------------------------------------------------------------------------

    def _not_installed(self) -> EngineUnavailable:
        return EngineUnavailable(
            "The Kitten TTS 2 engine pack is not installed; install it in Runtime → "
            "Speech engines."
        )

    def _await_ready(self) -> None:
        """Return once the worker can serve. A cold or warming engine is loaded in the background
        and the request waits at most ``ENGINE_WARM_WAIT_S`` for it, then gets ``EngineWarming``.
        """
        process = self._process
        if pack_python() is None:
            if process is not None:
                self.unload()  # the pack was removed under a running worker
            raise self._not_installed()  # not a load state: nothing is starting
        if process is not None and process.is_alive and self._tracker.state == "ready":
            return
        if self._tracker.claim_load():
            self._start_load(reload=False, name="kitten2-load")
        state = self._tracker.wait_settled(warm_wait_s())
        if state in IN_FLIGHT:
            raise EngineWarming(self.label, state, self._tracker.retry_after_s())
        if state == "error":
            raise EngineUnavailable(self._tracker.error or f"{self.label} failed to load.")

    def _ensure_started(self) -> PackProcess:
        if self._process is not None and self._process.is_alive:
            self._tracker.enter("ready")
            return self._process
        try:
            return self._spawn()
        except Exception as exc:
            self._tracker.fail(str(exc))
            raise

    def _spawn(self) -> PackProcess:
        self._process = None
        self._prepared.clear()
        self._load_info = {"mode": None, "fast_mode_issue": None}
        python = pack_python()
        if python is None:
            raise self._not_installed()
        self._tracker.enter("loading")
        env: dict[str, str] = {}
        # The worker only loads here; ``warmup`` below is the compile-heavy first call.
        load_request: dict[str, Any] = {"op": "load", "warmup": False}
        directory = None if os.environ.get("KITTEN2_PYTHON") else pack_directory()
        if directory is not None:
            # Serve from the pack's own weights and never download mid-request: a missing file
            # must fail fast and explain itself, not stall a request for minutes.
            weights = kitten2_pack.weights_dir(directory)
            env = {"HF_HOME": str(weights), "HF_HUB_OFFLINE": "1"}
            load_request["cache_dir"] = str(weights)
        process = PackProcess(
            [str(python), str(Path(kitten2_worker.__file__).resolve())],
            env=env,
            request_timeout=REQUEST_TIMEOUT_S,
            log=pack_logs.worker_sink(ENGINE_ID),
        )
        process.start()
        try:
            loaded = process.request(load_request, timeout=LOAD_TIMEOUT_S)
            if loaded.get("warmup_pending"):
                self._tracker.enter("warming")
                loaded = {**loaded, **process.request({"op": "warmup"}, timeout=WARMUP_TIMEOUT_S)}
        except PackProcessError as exc:
            process.close()
            raise EngineUnavailable(str(exc)) from exc
        self._process = process
        self._load_info = {
            "mode": loaded.get("mode"),
            "fast_mode_issue": loaded.get("fast_mode_issue"),
        }
        self._tracker.enter("ready")
        return process

    def _arm_idle_timer(self) -> None:
        self._idle.arm()

    def unload(self) -> None:
        with self._lock:
            self._idle.cancel()
            process, self._process = self._process, None
            self._prepared.clear()
            if self._tracker.state == "ready":
                self._tracker.enter("idle")
        if process is not None:
            process.close()

    # -- synthesis -----------------------------------------------------------------------------

    def _prepare_saved_voice(
        self, process: PackProcess, voice_id: str, *, force: bool = False
    ) -> bool:
        """Prepare a saved voice for cloning. Returns False when ``voice_id`` is not saved.

        The worker's copy is keyed by reference file *and* transcript, so editing the words
        re-prepares it. Each successful prepare records a binding marker (``voice_bindings``);
        ``force`` re-runs it even when the worker already holds the voice, which is what an
        explicit Prepare needs so a stale marker is refreshed.
        """
        meta = voice_library.get_voice(voice_id)
        if meta is None:
            return False
        wav_path = Path(meta["wav_path"])
        if wav_path.is_symlink():
            wav_path = wav_path.resolve()
        if not wav_path.is_file():
            raise InvalidVoice(
                f"The reference clip for voice {voice_id!r} is missing. "
                "Restore the clip or save the voice again in Voice Library."
            )
        transcript = (meta.get("sample_text") or "").strip()
        if not transcript:
            # Without a transcript Kitten would load a speech-recognition model mid-request, which
            # an offline pack cannot do. Say what to do instead of failing with a network error.
            raise InvalidVoice(
                "This voice has no transcript, which Kitten TTS 2 needs to clone it. Open the "
                "voice in Voice Library and choose Transcribe (or type the words), then try again."
            )
        if voice_bindings.transcript_unreviewed(meta):
            raise InvalidVoice(
                "Review the transcript in Voice Library and confirm or edit the words before "
                "preparing this voice for Kitten TTS 2."
            )
        key = voice_bindings.current_key(meta, ENGINE_ID)
        if force or self._prepared.get(voice_id) != key:
            process.request(
                {
                    "op": "prepare",
                    "voice_id": voice_id,
                    "reference_path": str(wav_path),
                    "reference_text": transcript,
                },
                timeout=PREPARE_TIMEOUT_S,
            )
            fresh = voice_bindings.meta_with_path(voice_id)
            if fresh is None or voice_bindings.current_key(fresh, ENGINE_ID) != key:
                self._prepared.pop(voice_id, None)
                raise InvalidVoice("The voice changed during preparation. Prepare it again.")
            self._prepared[voice_id] = key
            voice_bindings.write_marker(voice_id, ENGINE_ID, key)
        return True

    def prepare_voice(self, voice_id: str, *, cancel: threading.Event | None = None) -> None:
        """Prepare a saved voice now, instead of at its first synthesis.

        Waits for a cold engine to load (an explicit preparation is a background job, not a
        request that can be told to retry), then runs the worker's ``prepare`` bounded by
        ``PREPARE_TIMEOUT_S``. Raises ``InvalidVoice`` for an unknown voice or a missing
        transcript, so the transcript is resolved here and never during a request.
        """
        wait_until_ready(self._await_ready, EngineWarming, cancel=cancel)
        with self._lock:
            process = self._ensure_started()
            try:
                prepared = self._prepare_saved_voice(process, voice_id)
            except PackProcessError:
                if not process.is_alive:
                    self._process = None
                    self._prepared.clear()
                raise
            if not prepared:
                raise InvalidVoice(
                    f"{voice_id!r} is not a saved voice, or its reference clip is missing."
                )
            self._arm_idle_timer()

    def synthesize(
        self,
        text: str,
        language: str,
        *,
        voice_id: str | None = None,
        voice_variant_id: str | None = None,
        style_preset: str | None = None,
        postprocess: bool | dict[str, Any] | None = None,
        prosody_repair: bool = False,
        seed_value: int | None = None,
        instruct: str | None = None,
        speed: float | None = None,
    ) -> tuple[Any, int, str | None]:
        # Pocket-only options (style presets, prosody repair, instruct) do not apply to this
        # engine; they are accepted so the shared route can stay engine-agnostic.
        del language, style_preset, postprocess, prosody_repair, instruct, speed
        requested = (voice_variant_id or voice_id or "").strip()
        self._await_ready()
        with self._lock:
            process = self._ensure_started()
            request: dict[str, Any] = {"op": "synthesize", "text": text}
            if seed_value is not None:
                request["seed"] = int(seed_value)
            if requested and self._prepare_saved_voice(process, requested):
                request["voice_id"] = requested
            elif requested and not requested.startswith("pocket:"):
                request["preset"] = (
                    requested[len(PRESET_PREFIX) :]
                    if requested.startswith(PRESET_PREFIX)
                    else requested
                )
            try:
                audio = process.synthesize(request)
            except PackProcessError as exc:
                if str(exc).startswith("unknown preset"):
                    raise InvalidVoice(str(exc)) from exc
                # A timed-out worker is killed by the transport; drop it so the next request
                # starts a fresh one instead of reusing a dead handle.
                if not process.is_alive:
                    self._process = None
                    self._prepared.clear()
                raise
            self._arm_idle_timer()
        wav, rate = _decode_wav(audio)
        return wav, rate, None

    def stream_pcm(
        self,
        text: str,
        language: str,
        *,
        voice_id: str | None = None,
        seed_value: int | None = None,
        speed: float | None = None,
    ) -> Iterator[bytes]:
        # Kitten 2 has no frame streaming; return the whole utterance as one PCM chunk.
        wav, _rate, _job = self.synthesize(text, language, voice_id=voice_id, seed_value=seed_value)
        yield (np.clip(wav, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()

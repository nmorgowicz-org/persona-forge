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
from typing import Any, Iterator

import numpy as np

from persona_forge import engine_packs, kitten2_pack, kitten2_worker, voice_library
from persona_forge.pack_process import PackProcess, PackProcessError

ENGINE_ID = "kitten2"
PRESET_PREFIX = "kitten2:"
# Compiled CUDA decoding compiles on first use; the worker's warm-up absorbs it at load.
LOAD_TIMEOUT_S = 600.0
REQUEST_TIMEOUT_S = 240.0


class EngineUnavailable(RuntimeError):
    """The pack is missing or the machine cannot run the engine."""


class InvalidVoice(ValueError):
    """The requested voice or preset does not exist for this engine."""


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


def preset_language(name: str, root: Path | None = None) -> str:
    """Language code of a preset, from its catalog ``voice_id`` prefix (``fr_...``); default ``en``."""
    directory = pack_directory(root)
    if directory is None:
        return "en"
    for catalog in (directory / "hf").glob("models--*kitten-tts-2/snapshots/*/voices/voices.json"):
        try:
            entry = json.loads(catalog.read_text(encoding="utf-8")).get(name, {})
        except (OSError, ValueError):
            continue
        prefix = str(entry.get("voice_id", ""))[:3]
        return prefix[:2] if prefix[2:] == "_" and prefix[:2] in _NON_ENGLISH else "en"
    return "en"


def _decode_wav(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data)) as handle:
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0, rate


def _idle_from_env(default: float = 600.0) -> float:
    try:
        return float(os.environ.get("KITTEN2_IDLE_UNLOAD_S", default))
    except ValueError:
        return default


class Kitten2Engine:
    id = ENGINE_ID

    def __init__(self, idle_unload_s: float | None = None) -> None:
        self._idle_s = idle_unload_s if idle_unload_s is not None else _idle_from_env()
        self._lock = threading.RLock()
        self._process: PackProcess | None = None
        self._prepared: dict[str, tuple[str, float]] = {}
        self._timer: threading.Timer | None = None
        self._load_info: dict[str, Any] = {}
        self._load_state = "idle"  # idle | loading | ready | error
        self._load_error: str | None = None

    def status(self) -> dict[str, Any]:
        """Load state plus the speed mode and, when fast mode is unavailable, why."""
        return {**self._load_info, "state": self._load_state, "error": self._load_error}

    def recheck(self) -> bool:
        """Reload the worker in the background so a newly installed compiler is picked up.

        Returns False when a load is already running.
        """
        with self._lock:
            if self._load_state == "loading":
                return False
            self._load_state = "loading"
            self._load_error = None
        threading.Thread(target=self._load_in_background, name="kitten2-recheck", daemon=True).start()
        return True

    def _load_in_background(self) -> None:
        try:
            self.unload()
            with self._lock:
                self._ensure_started()
                self._arm_idle_timer()
        except EngineUnavailable as exc:
            self._load_state = "error"
            self._load_error = str(exc)
        else:
            self._load_state = "ready"

    def describe(self) -> dict[str, Any]:
        from persona_forge import speech_engines

        info = speech_engines.ENGINES[self.id].as_dict()
        info["installed"] = is_installed()
        info["status"] = self.status()
        return info

    # -- lifecycle -----------------------------------------------------------------------------

    def _ensure_started(self) -> PackProcess:
        if self._process is not None and self._process.is_alive:
            return self._process
        self._process = None
        self._prepared.clear()
        python = pack_python()
        if python is None:
            raise EngineUnavailable(
                "The Kitten TTS 2 engine pack is not installed; install it in Settings → "
                "Speech engines."
            )
        env: dict[str, str] = {}
        load_request: dict[str, Any] = {"op": "load"}
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
        )
        process.start()
        try:
            loaded = process.request(load_request, timeout=LOAD_TIMEOUT_S)
        except PackProcessError as exc:
            process.close()
            raise EngineUnavailable(str(exc)) from exc
        self._process = process
        self._load_state = "ready"
        self._load_info = {
            "mode": loaded.get("mode"),
            "fast_mode_issue": loaded.get("fast_mode_issue"),
        }
        return process

    def _arm_idle_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        if self._idle_s <= 0:
            return
        self._timer = threading.Timer(self._idle_s, self.unload)
        self._timer.daemon = True
        self._timer.start()

    def unload(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            process, self._process = self._process, None
            self._prepared.clear()
        if process is not None:
            process.close()

    # -- synthesis -----------------------------------------------------------------------------

    def _prepare_saved_voice(self, process: PackProcess, voice_id: str) -> bool:
        """Prepare a saved voice for cloning. Returns False when ``voice_id`` is not saved."""
        meta = voice_library.get_voice(voice_id)
        if meta is None:
            return False
        wav_path = Path(meta["wav_path"])
        if wav_path.is_symlink():
            wav_path = wav_path.resolve()
        if not wav_path.is_file():
            return False
        stamp = wav_path.stat().st_mtime
        cached = self._prepared.get(voice_id)
        if cached is None or cached != (str(wav_path), stamp):
            process.request(
                {
                    "op": "prepare",
                    "voice_id": voice_id,
                    "reference_path": str(wav_path),
                    "reference_text": (meta.get("sample_text") or "").strip() or None,
                }
            )
            self._prepared[voice_id] = (str(wav_path), stamp)
        return True

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

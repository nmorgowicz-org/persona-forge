"""Phonon 31M adapter: English preset voices from a pack child process.

Phonon cannot clone from a recording, so it serves only its built-in catalog. A request that names
a saved library voice gets a clear 400 instead of a silent fallback to some other voice.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Iterator


from persona_forge import engine_packs, phonon_pack, phonon_worker, voice_library
from persona_forge.kitten2_engine import EngineUnavailable, InvalidVoice, _decode_wav
from persona_forge.pack_process import PackProcess, PackProcessError

ENGINE_ID = phonon_pack.ENGINE_ID
PRESET_PREFIX = "phonon:"
LOAD_TIMEOUT_S = 120.0
REQUEST_TIMEOUT_S = 120.0

__all__ = ["EngineUnavailable", "InvalidVoice", "PhononEngine", "is_installed", "list_presets"]


def pack_directory(root: Path | None = None) -> Path | None:
    return engine_packs.find_pack_dir(ENGINE_ID, root)


def pack_python(root: Path | None = None) -> Path | None:
    """Interpreter of the installed pack, or the ``PHONON_PYTHON`` development override."""
    override = os.environ.get("PHONON_PYTHON")
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    directory = pack_directory(root)
    if directory is None or engine_packs.inspect_pack(directory).status != "verified":
        return None
    python = phonon_pack.venv_python(directory)
    return python if python.is_file() else None


def is_installed(root: Path | None = None) -> bool:
    return pack_python(root) is not None


def list_presets(root: Path | None = None) -> list[str]:
    """English voice names from the downloaded catalog (no model load needed)."""
    directory = pack_directory(root)
    if directory is None or not is_installed(root):
        return []
    for catalog in sorted((directory / "hf").glob("**/models--*phonon-voices/snapshots/*/voices.jsonl")):
        names: list[str] = []
        try:
            for line in catalog.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                if entry.get("language") == "en" and entry.get("name"):
                    names.append(str(entry["name"]))
        except (OSError, ValueError):
            continue
        if names:
            return sorted(names)
    return []


def _idle_from_env(default: float = 600.0) -> float:
    try:
        return float(os.environ.get("PHONON_IDLE_UNLOAD_S", default))
    except ValueError:
        return default


class PhononEngine:
    id = ENGINE_ID

    def __init__(self, idle_unload_s: float | None = None) -> None:
        self._idle_s = idle_unload_s if idle_unload_s is not None else _idle_from_env()
        self._lock = threading.RLock()
        self._process: PackProcess | None = None
        self._timer: threading.Timer | None = None
        self._load_info: dict[str, Any] = {}
        self._load_state = "idle"  # idle | loading | ready | error
        self._load_error: str | None = None

    def status(self) -> dict[str, Any]:
        return {**self._load_info, "state": self._load_state, "error": self._load_error}

    def recheck(self) -> bool:
        """Reload the worker in the background. Returns False when a load is already running."""
        with self._lock:
            if self._load_state == "loading":
                return False
            self._load_state = "loading"
            self._load_error = None
        threading.Thread(target=self._load_in_background, name="phonon-recheck", daemon=True).start()
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

    def _ensure_started(self) -> PackProcess:
        if self._process is not None and self._process.is_alive:
            return self._process
        self._process = None
        python = pack_python()
        if python is None:
            raise EngineUnavailable(
                "The Phonon 31M engine pack is not installed; install it in Settings → "
                "Speech engines."
            )
        env: dict[str, str] = {}
        directory = None if os.environ.get("PHONON_PYTHON") else pack_directory()
        if directory is not None:
            # Serve from the pack's own files and never download mid-request.
            env = {"HF_HOME": str(phonon_pack.weights_dir(directory)), "HF_HUB_OFFLINE": "1"}
        process = PackProcess(
            [str(python), str(Path(phonon_worker.__file__).resolve())],
            env=env,
            request_timeout=REQUEST_TIMEOUT_S,
        )
        process.start()
        try:
            loaded = process.request({"op": "load"}, timeout=LOAD_TIMEOUT_S)
        except PackProcessError as exc:
            process.close()
            raise EngineUnavailable(str(exc)) from exc
        self._process = process
        self._load_state = "ready"
        self._load_info = {"mode": loaded.get("mode"), "fast_mode_issue": None}
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
        if process is not None:
            process.close()

    @staticmethod
    def _fill_request(
        request: dict[str, Any], requested: str, seed_value: int | None, speed: float | None
    ) -> None:
        if seed_value is not None:
            request["seed"] = int(seed_value)
        if speed is not None:
            request["speed"] = float(speed)
        if requested and not requested.startswith("pocket:"):
            request["preset"] = (
                requested[len(PRESET_PREFIX) :] if requested.startswith(PRESET_PREFIX) else requested
            )

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
        # Pocket-only options do not apply here; they are accepted so the route stays generic.
        del language, style_preset, postprocess, prosody_repair, instruct
        requested = (voice_variant_id or voice_id or "").strip()
        if requested and voice_library.get_voice(requested) is not None:
            raise InvalidVoice(
                "Phonon 31M cannot clone a saved voice; choose a 'phonon:<Name>' voice or use "
                "an engine that clones."
            )
        with self._lock:
            process = self._ensure_started()
            request: dict[str, Any] = {"op": "synthesize", "text": text}
            self._fill_request(request, requested, seed_value, speed)
            try:
                audio = process.synthesize(request)
            except PackProcessError as exc:
                if str(exc).startswith("unknown preset"):
                    raise InvalidVoice(str(exc)) from exc
                if not process.is_alive:
                    self._process = None
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
        """Yield int16 PCM chunks as the model produces them (first audio in a few ms)."""
        del language
        requested = (voice_id or "").strip()
        if requested and voice_library.get_voice(requested) is not None:
            raise InvalidVoice(
                "Phonon 31M cannot clone a saved voice; choose a 'phonon:<Name>' voice or use "
                "an engine that clones."
            )
        request: dict[str, Any] = {"text": text}
        self._fill_request(request, requested, seed_value, speed)
        with self._lock:
            process = self._ensure_started()
        try:
            yield from process.stream(request)
        except PackProcessError as exc:
            if str(exc).startswith("unknown preset"):
                raise InvalidVoice(str(exc)) from exc
            raise
        finally:
            if not process.is_alive:
                with self._lock:
                    if self._process is process:
                        self._process = None
            self._arm_idle_timer()

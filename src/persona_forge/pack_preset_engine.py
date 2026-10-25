"""Shared adapter for preset-only engines served by a pack child process (Phonon, Kokoro).

Cloning is unsupported, so a request naming a saved library voice gets a clear 400 instead of a
silent fallback. Subclasses supply the pack paths, the ``load`` request and a few labels.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from persona_forge import voice_library
from persona_forge.kitten2_engine import EngineUnavailable, InvalidVoice, _decode_wav
from persona_forge.pack_process import PackProcess, PackProcessError

LOAD_TIMEOUT_S = 120.0
REQUEST_TIMEOUT_S = 120.0


class PackPresetEngine:
    """Shared adapter for preset-only engines served by a pack child process.

    Subclasses set the class attributes and override ``_load_request``/``_env``/``_idle_env``.
    """

    id = ""
    label = ""
    idle_env = ""
    worker_file = ""
    preset_prefix = ""
    streams = False

    # -- hooks ---
    def _pack_python(self) -> Path | None:
        raise NotImplementedError

    def _load_request(self) -> tuple[dict[str, Any], dict[str, str]]:
        """The ``load`` request and the worker's environment."""
        raise NotImplementedError

    def _seed(self, request: dict[str, Any], seed_value: int | None) -> None:
        if seed_value is not None:
            request["seed"] = int(seed_value)

    def __init__(self, idle_unload_s: float | None = None) -> None:
        self._idle_s = idle_unload_s if idle_unload_s is not None else self._idle_from_env()
        self._lock = threading.RLock()
        self._process: PackProcess | None = None
        self._timer: threading.Timer | None = None
        self._load_info: dict[str, Any] = {}
        self._load_state = "idle"  # idle | loading | ready | error
        self._load_error: str | None = None

    def _idle_from_env(self, default: float = 600.0) -> float:
        try:
            return float(os.environ.get(self.idle_env, default))
        except ValueError:
            return default

    def status(self) -> dict[str, Any]:
        return {**self._load_info, "state": self._load_state, "error": self._load_error}

    def recheck(self) -> bool:
        """Reload the worker in the background. Returns False when a load is already running."""
        with self._lock:
            if self._load_state == "loading":
                return False
            self._load_state = "loading"
            self._load_error = None
        threading.Thread(target=self._load_in_background, name=f"{self.id}-recheck", daemon=True).start()
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
        info["installed"] = self._pack_python() is not None
        info["status"] = self.status()
        return info

    def _ensure_started(self) -> PackProcess:
        if self._process is not None and self._process.is_alive:
            return self._process
        self._process = None
        python = self._pack_python()
        if python is None:
            raise EngineUnavailable(
                f"The {self.label} engine pack is not installed; install it in Settings → "
                "Speech engines."
            )
        load_request, env = self._load_request()
        process = PackProcess(
            [str(python), self.worker_file],
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

    def _refuse_clone(self, requested: str) -> None:
        if requested and voice_library.get_voice(requested) is not None:
            raise InvalidVoice(
                f"{self.label} cannot clone a saved voice; choose a '{self.preset_prefix}<voice>' "
                "voice or use an engine that clones."
            )

    def _fill_request(
        self,
        request: dict[str, Any], requested: str, seed_value: int | None, speed: float | None
    ) -> None:
        self._seed(request, seed_value)
        if speed is not None:
            request["speed"] = float(speed)
        if requested and not requested.startswith("pocket:"):
            request["preset"] = (
                requested[len(self.preset_prefix) :]
                if requested.startswith(self.preset_prefix)
                else requested
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
        self._refuse_clone(requested)
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
        """Yield int16 PCM: chunks as produced when the worker streams, else one whole clip."""
        if not self.streams:
            wav, _rate, _job = self.synthesize(
                text, language, voice_id=voice_id, seed_value=seed_value, speed=speed
            )
            yield (np.clip(wav, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
            return
        del language
        requested = (voice_id or "").strip()
        self._refuse_clone(requested)
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

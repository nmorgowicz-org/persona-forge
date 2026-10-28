"""Shared adapter for preset-only engines served by a pack child process (Phonon, Kokoro).

Cloning is unsupported, so a request naming a saved library voice gets a clear 400 instead of a
silent fallback. Subclasses supply the pack paths, the ``load`` request and a few labels.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Iterator

import numpy as np

from persona_forge import engine_packs, pack_logs, voice_library
from persona_forge.engine_lifecycle import (
    IN_FLIGHT,
    IdleUnloader,
    LoadTracker,
    wait_until_ready,
    warm_wait_s,
)
from persona_forge.kitten2_engine import (
    EngineUnavailable,
    EngineWarming,
    InvalidVoice,
    _decode_wav,
)
from persona_forge.pack_process import PackProcess, PackProcessError

LOAD_TIMEOUT_S = 120.0
WARMUP_TIMEOUT_S = 600.0
REQUEST_TIMEOUT_S = 120.0


class PackPresetEngine:
    """Shared adapter for preset-only engines served by a pack child process.

    Subclasses set the class attributes and override ``_load_request``/``_env``/``_idle_env``.
    """

    id = ""
    label = ""
    idle_env = ""
    # Used when neither the env override nor the pack manifest sets ``idle_unload_after``.
    idle_default_s = 600.0
    worker_file = ""
    preset_prefix = ""
    streams = False
    # Expected length of the worker's ``warmup`` step, when it has one and the figure is measured.
    warmup_estimate_s: float | None = None

    # -- hooks ---
    def _pack_python(self) -> Path | None:
        raise NotImplementedError

    def _load_request(self) -> tuple[dict[str, Any], dict[str, str]]:
        """The ``load`` request and the worker's environment."""
        raise NotImplementedError

    def _seed(self, request: dict[str, Any], seed_value: int | None) -> None:
        if seed_value is not None:
            request["seed"] = int(seed_value)

    def __init__(
        self,
        idle_unload_s: float | None = None,
        *,
        timer_factory: Callable[..., Any] = threading.Timer,
    ) -> None:
        self._lock = threading.RLock()
        self._process: PackProcess | None = None
        self._active = 0  # streams in flight; an idle timer must not stop a worker mid-stream
        self._idle = IdleUnloader(
            env_name=self.idle_env,
            default_s=self.idle_default_s,
            on_idle=self._unload_if_idle,
            manifest_value=lambda: engine_packs.idle_unload_after(self.id),
            override=idle_unload_s,
            timer_factory=timer_factory,
        )
        self._load_info: dict[str, Any] = {}
        # idle | loading | warming | ready | error, with elapsed time while loading or warming.
        estimates = {"warming": self.warmup_estimate_s} if self.warmup_estimate_s else {}
        self._tracker = LoadTracker(estimates=estimates)

    @property
    def idle_unload_after(self) -> float:
        """Effective idle-unload seconds (0 = never)."""
        return self._idle.seconds

    def status(self) -> dict[str, Any]:
        seconds, source = self._idle.resolve()
        return {
            **self._load_info,
            **self._tracker.snapshot(),
            "idle_unload_after": seconds,
            "idle_unload_source": source,
        }

    def recheck(self) -> bool:
        """Reload the worker in the background. Returns False when a load is already running."""
        if not self._tracker.claim_load():
            return False
        self._start_load(reload=True, name=f"{self.id}-recheck")
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
        info["installed"] = self._pack_python() is not None
        info["status"] = self.status()
        return info

    def _not_installed(self) -> EngineUnavailable:
        return EngineUnavailable(
            f"The {self.label} engine pack is not installed; install it in Settings → "
            "Speech engines."
        )

    def _await_ready(self) -> None:
        """Return once the worker can serve. A cold or warming engine is loaded in the background
        and the request waits at most ``ENGINE_WARM_WAIT_S`` for it, then gets ``EngineWarming``.
        """
        process = self._process
        if process is not None and process.is_alive and self._tracker.state == "ready":
            return
        if self._pack_python() is None:
            raise self._not_installed()  # not a load state: nothing is starting
        if self._tracker.claim_load():
            self._start_load(reload=False, name=f"{self.id}-load")
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
        self._on_process_lost()
        self._load_info = {"mode": None, "fast_mode_issue": None}
        python = self._pack_python()
        if python is None:
            raise self._not_installed()
        self._tracker.enter("loading")
        load_request, env = self._load_request()
        process = PackProcess(
            [str(python), self.worker_file],
            env=env,
            request_timeout=REQUEST_TIMEOUT_S,
            log=pack_logs.worker_sink(self.id),
        )
        process.start()
        try:
            loaded = process.request(load_request, timeout=LOAD_TIMEOUT_S)
            if loaded.get("warmup_pending"):
                self._tracker.enter("warming")
                loaded = {**loaded, **process.request({"op": "warmup"}, timeout=WARMUP_TIMEOUT_S)}
            self._on_loaded(load_request, loaded)
        except PackProcessError as exc:
            process.close()
            raise EngineUnavailable(str(exc)) from exc
        self._process = process
        self._load_info = {"mode": loaded.get("mode"), "fast_mode_issue": None}
        self._tracker.enter("ready")
        return process

    def _on_loaded(self, request: dict[str, Any], reply: dict[str, Any]) -> None:
        """Inspect per-voice load results before publishing the worker as ready."""

    def _arm_idle_timer(self) -> None:
        self._idle.arm()

    def _unload_if_idle(self) -> None:
        with self._lock:
            if self._active:
                return  # a stream is running; its end re-arms the timer
        self.unload()

    def unload(self) -> None:
        with self._lock:
            self._idle.cancel()
            process, self._process = self._process, None
            if self._tracker.state == "ready":
                self._tracker.enter("idle")
        if process is not None:
            process.close()

    def _check_voice(self, requested: str) -> None:
        """Called before the worker starts; engines that clone override this to allow saved voices."""
        self._refuse_clone(requested)

    def _prepare_voice(self, process: PackProcess, requested: str, *, force: bool = False) -> bool:
        """Clone-capable engines prepare a saved voice here and return True; presets return False.

        ``force`` re-runs the worker's prepare even if it already holds the voice (an explicit
        Prepare, which must refresh the binding marker).
        """
        del process, requested, force
        return False

    def _on_process_lost(self) -> None:
        """The worker died; engines that remember prepared voices forget them here."""

    def prepare_voice(self, voice_id: str, *, cancel: threading.Event | None = None) -> None:
        """Prepare a saved voice now, instead of at its first synthesis (clone-capable engines).

        Waits for a cold engine to load (this is a background job, not a request that can be
        told to retry) and stops early when ``cancel`` is set. Preset-only engines refuse.
        """
        self._check_voice(voice_id)
        wait_until_ready(self._await_ready, EngineWarming, cancel=cancel)
        with self._lock:
            process = self._ensure_started()
            try:
                prepared = self._prepare_voice(process, voice_id)
            except PackProcessError:
                if not process.is_alive:
                    self._process = None
                    self._on_process_lost()
                raise
            if not prepared:
                raise InvalidVoice(
                    f"{voice_id!r} is not a saved voice, or {self.label} cannot clone it."
                )
            self._arm_idle_timer()

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
        self._check_voice(requested)
        self._await_ready()
        with self._lock:
            process = self._ensure_started()
            request: dict[str, Any] = {"op": "synthesize", "text": text}
            cloned = self._prepare_voice(process, requested)
            if cloned:
                request["voice_id"] = requested
            self._fill_request(request, "" if cloned else requested, seed_value, speed)
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
        self._check_voice(requested)
        request: dict[str, Any] = {"text": text}
        self._await_ready()
        with self._lock:
            process = self._ensure_started()
            self._idle.cancel()
            self._active += 1
        try:
            with self._lock:
                cloned = self._prepare_voice(process, requested)
                if cloned:
                    request["voice_id"] = requested
                self._fill_request(request, "" if cloned else requested, seed_value, speed)
            yield from process.stream(request)
        except PackProcessError as exc:
            if str(exc).startswith("unknown preset"):
                raise InvalidVoice(str(exc)) from exc
            raise
        finally:
            with self._lock:
                self._active -= 1
                if not process.is_alive and self._process is process:
                    self._process = None
                self._arm_idle_timer()

"""Kitten TTS 2 worker (Phase C4).

Runs inside the ``kitten2`` pack environment, never in the web process. It speaks the
newline-delimited JSON protocol that ``pack_process.PackProcess`` drives: one request per line on
stdin, one response per line on stdout. ``kittenml`` is imported lazily so the protocol can be
tested with a stub model and no weights.

Ops: ``ping``, ``load``, ``prepare``, ``synthesize``, ``unload``.
"""

from __future__ import annotations

import base64
import io
import json
import os
import platform as py_platform
import sys
import wave
from typing import Any, Callable, Mapping

import numpy as np

MODEL_NAME = "KittenML/kitten-tts-2"
DEFAULT_PRESET = "Bruno"


class WorkerError(RuntimeError):
    """A request failed; the message is returned to the caller."""


def _torch_cuda_available() -> bool:
    import torch

    return bool(torch.cuda.is_available())


def choose_runtime(
    platform: str | None = None,
    machine: str | None = None,
    cuda_available: Callable[[], bool] = _torch_cuda_available,
) -> dict[str, Any]:
    """Pick the backend and device for this machine, or raise with an actionable message."""
    platform = platform or sys.platform
    machine = machine or py_platform.machine()
    if platform == "darwin" and machine in ("arm64", "aarch64"):
        return {"backend": "mlx", "device": None, "static_cache": False}
    if cuda_available():
        return {"backend": None, "device": "cuda", "static_cache": True}
    raise WorkerError(
        "Kitten TTS 2 needs Apple silicon (MLX) or an NVIDIA GPU; CPU runs at about 1.7x slower "
        "than real time and is not supported."
    )


BUILD_TOOLS_URL = "https://visualstudio.microsoft.com/visual-cpp-build-tools/"


def explain_compile_failure(
    error: str, platform: str | None = None, *, triton_missing: bool | None = None
) -> dict[str, Any]:
    """Turn a raw compile failure into a message a user can act on.

    The raw text stays in ``detail`` for support; ``message`` and ``action`` are for the UI.
    """
    platform = platform or sys.platform
    text = (error or "").strip()
    lowered = text.lower()
    if triton_missing is None:
        triton_missing = "no module named 'triton'" in lowered or "no module named triton" in lowered
    if triton_missing:
        return {
            "code": "triton_missing",
            "message": "Fast mode needs a component that is missing from this engine install.",
            "action": "Use Repair on the engine card to reinstall it.",
            "help_url": None,
            "detail": text,
        }
    if platform == "win32" and (
        "winerror 2" in lowered
        or "cl.exe" in lowered
        or "vcvars" in lowered
        or "visual studio" in lowered
        or "c compiler" in lowered
        or "cannot find a c" in lowered
        or "failed to find" in lowered
    ):
        return {
            "code": "needs_build_tools",
            "message": (
                "Fast mode needs the Microsoft C++ Build Tools, which are not installed. "
                "Kitten TTS 2 is running in standard mode, which is slower than real time."
            ),
            "action": (
                "Install 'Build Tools for Visual Studio' with the 'Desktop development with "
                "C++' workload, then choose Re-check on the engine card. No restart is needed."
            ),
            "help_url": BUILD_TOOLS_URL,
            "detail": text,
        }
    if platform.startswith("linux") and (
        "c compiler" in lowered or "gcc" in lowered or "cc" in lowered.split() or "nvcc" in lowered
    ):
        return {
            "code": "needs_build_tools",
            "message": (
                "Fast mode needs a C compiler, which is not installed. Kitten TTS 2 is running "
                "in standard mode, which is slower than real time."
            ),
            "action": (
                "Install one (for example 'sudo apt install build-essential'), then choose "
                "Re-check on the engine card."
            ),
            "help_url": None,
            "detail": text,
        }
    return {
        "code": "fast_mode_failed",
        "message": (
            "Fast mode could not start, so Kitten TTS 2 is running in standard mode, which is "
            "slower than real time."
        ),
        "action": "Choose Re-check on the engine card to try again.",
        "help_url": None,
        "detail": text,
    }


def _wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    samples = np.clip(np.asarray(audio, dtype=np.float32).ravel(), -1.0, 1.0)
    pcm = (samples * 32767.0).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()


def _default_factory(cache_dir: str | None, runtime: Mapping[str, Any]) -> Any:
    from kittenml import KittenTTS  # pyright: ignore[reportMissingImports]

    model = KittenTTS(
        MODEL_NAME,
        cache_dir=cache_dir,
        backend=runtime.get("backend"),
        device=runtime.get("device"),
    )
    if runtime.get("static_cache"):
        # Lets transformers compile the decode step: about 4x faster than eager on CUDA.
        model.model.generation_config.cache_implementation = "static"
    return model


class Kitten2Worker:
    def __init__(
        self,
        factory: Callable[[str | None, Mapping[str, Any]], Any] | None = None,
        runtime_chooser: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._factory = factory or _default_factory
        self._choose = runtime_chooser or choose_runtime
        self._model: Any = None
        self._runtime: dict[str, Any] = {}
        self._voices: dict[str, dict[str, str | None]] = {}

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        op = request.get("op")
        handler = getattr(self, f"_op_{op}", None) if isinstance(op, str) else None
        if handler is None:
            raise WorkerError(f"unknown op {op!r}")
        return handler(request)

    def _op_ping(self, _request: Mapping[str, Any]) -> dict[str, Any]:
        return {"ok": True, "loaded": self._model is not None}

    def _op_load(self, request: Mapping[str, Any]) -> dict[str, Any]:
        fast_issue: dict[str, Any] | None = None
        if self._model is None:
            self._runtime = self._choose()
            if request.get("fast_mode") is False:
                self._runtime = {**self._runtime, "static_cache": False}
            self._model = self._factory(request.get("cache_dir"), self._runtime)
        if request.get("warmup", True):
            # The first compiled CUDA call takes about 33 s; pay it here, not on a request.
            try:
                self._model.generate("Ready.", voice=DEFAULT_PRESET)
            except Exception as exc:
                if not self._runtime.get("static_cache"):
                    raise
                # Compiling needs a C/C++ toolchain (Triton). Without one, run eager: about
                # 1.4x slower than real time instead of 0.3x, but it works with no setup.
                raw = f"{type(exc).__name__}: {exc}".strip()
                fast_issue = explain_compile_failure(
                    raw.splitlines()[0][:300] if raw else "",
                    triton_missing=isinstance(exc, ModuleNotFoundError)
                    and "triton" in str(exc).lower(),
                )
                self._model = None
                self._runtime = {**self._runtime, "static_cache": False}
                self._model = self._factory(request.get("cache_dir"), self._runtime)
                self._model.generate("Ready.", voice=DEFAULT_PRESET)
        if self._runtime.get("backend") == "mlx":
            mode = "mlx"
        elif self._runtime.get("static_cache"):
            mode = "compiled"
        else:
            mode = "eager"
        return {
            "ok": True,
            "backend": self._runtime.get("backend") or self._runtime.get("device"),
            "mode": mode,
            "fast_mode_issue": fast_issue,
            "sample_rate": int(self._model.sample_rate),
        }

    def _require_model(self) -> Any:
        if self._model is None:
            raise WorkerError("model is not loaded")
        return self._model

    def _op_prepare(self, request: Mapping[str, Any]) -> dict[str, Any]:
        self._require_model()
        voice_id = request.get("voice_id")
        reference = request.get("reference_path")
        if not isinstance(voice_id, str) or not voice_id:
            raise WorkerError("prepare needs voice_id")
        if not isinstance(reference, str) or not os.path.isfile(reference):
            raise WorkerError("prepare needs an existing reference_path")
        text = request.get("reference_text")
        # Without a transcript kittenml loads Whisper on first use, so callers should send one.
        self._voices[voice_id] = {
            "reference": reference,
            "reference_text": text if isinstance(text, str) and text.strip() else None,
        }
        return {"ok": True, "voice_id": voice_id, "has_transcript": bool(text)}

    def _op_synthesize(self, request: Mapping[str, Any]) -> dict[str, Any]:
        model = self._require_model()
        text = request.get("text")
        if not isinstance(text, str) or not text.strip():
            raise WorkerError("synthesize needs text")
        voice_id = request.get("voice_id")
        kwargs: dict[str, Any] = {}
        seed = request.get("seed")
        if isinstance(seed, int):
            kwargs["advanced"] = {"seed": seed}
        if isinstance(voice_id, str) and voice_id in self._voices:
            prepared = self._voices[voice_id]
            kwargs["reference"] = prepared["reference"]
            if prepared["reference_text"]:
                kwargs["reference_text"] = prepared["reference_text"]
        else:
            preset = request.get("preset") or DEFAULT_PRESET
            if preset not in model.available_voices:
                raise WorkerError(f"unknown preset {preset!r}")
            kwargs["voice"] = preset
        audio = model.generate(text, **kwargs)
        rate = int(model.sample_rate)
        return {
            "ok": True,
            "audio_b64": base64.b64encode(_wav_bytes(np.asarray(audio), rate)).decode("ascii"),
            "sample_rate": rate,
            "format": "wav",
        }

    def _op_unload(self, _request: Mapping[str, Any]) -> dict[str, Any]:
        self._model = None
        self._voices.clear()
        try:
            import gc

            gc.collect()
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        return {"ok": True}


def serve(worker: Kitten2Worker, stdin: Any, stdout: Any) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            response = worker.handle(json.loads(line))
        except Exception as exc:  # report, never die: the parent decides whether to restart
            response = {"ok": False, "error": str(exc) or type(exc).__name__}
        stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
        stdout.flush()


def main() -> None:
    real_stdout = sys.stdout
    sys.stdout = sys.stderr  # library prints must not corrupt the JSON channel
    serve(Kitten2Worker(), sys.stdin, real_stdout)


if __name__ == "__main__":
    main()

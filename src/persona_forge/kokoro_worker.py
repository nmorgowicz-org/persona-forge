"""Kokoro 82M worker (``kokoro-onnx``).

Runs inside the ``kokoro`` pack environment, never in the web process, so it is self-contained.
Same newline-delimited JSON protocol as the other pack workers.

Ops: ``ping``, ``load``, ``synthesize``, ``unload``.

Threads are pinned: ONNX Runtime's default oversubscribes small CPUs, and measured on an Intel
i7-1360P that cost 2-3x (RTF 1.4-1.7 by default against 0.64-0.70 with four intra-op threads).
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import wave
from typing import Any, Callable, Mapping

import numpy as np

SAMPLE_RATE = 24000
MAX_THREADS = 4
# Voice-name prefix (language letter) to the espeak language Kokoro expects. Japanese and Chinese
# voices exist in the catalogue but need extra packages, so they are not served.
LANGUAGES = {
    "a": "en-us",
    "b": "en-gb",
    "e": "es",
    "f": "fr-fr",
    "h": "hi",
    "i": "it",
    "p": "pt-br",
}
MIN_SPEED = 0.5
MAX_SPEED = 2.0


class WorkerError(RuntimeError):
    """A request failed; the message is returned to the caller."""


def language_for(voice: str) -> str | None:
    return LANGUAGES.get(voice[:1]) if len(voice) > 2 and voice[1] in "fm" else None


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


def _default_factory(model_path: str, voices_path: str, threads: int) -> tuple[Any, list[str]]:
    import onnxruntime as ort
    from kokoro_onnx import Kokoro

    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(model_path, sess_options=options, providers=["CPUExecutionProvider"])
    model = Kokoro.from_session(session, voices_path)
    voices = [name for name in model.get_voices() if language_for(name)]
    return model, sorted(voices)


class KokoroWorker:
    def __init__(self, factory: Callable[[str, str, int], tuple[Any, list[str]]] | None = None) -> None:
        self._factory = factory or _default_factory
        self._model: Any = None
        self._voices: list[str] = []
        self._threads = 1

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        op = request.get("op")
        handler = getattr(self, f"_op_{op}", None) if isinstance(op, str) else None
        if handler is None:
            raise WorkerError(f"unknown op {op!r}")
        return handler(request)

    def _op_ping(self, _request: Mapping[str, Any]) -> dict[str, Any]:
        return {"ok": True, "loaded": self._model is not None}

    def _op_load(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if self._model is None:
            model_path, voices_path = request.get("model_path"), request.get("voices_path")
            if not isinstance(model_path, str) or not isinstance(voices_path, str):
                raise WorkerError("load needs model_path and voices_path")
            threads = max(1, min(MAX_THREADS, os.cpu_count() or 1))
            self._model, self._voices = self._factory(model_path, voices_path, threads)
            self._threads = threads
        return {"ok": True, "mode": f"cpu, {self._threads} threads", "voices": len(self._voices)}

    def _op_synthesize(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if self._model is None:
            raise WorkerError("load the model first")
        text = request.get("text")
        if not isinstance(text, str) or not text.strip():
            raise WorkerError("synthesize needs text")
        voice = request.get("preset") or "af_heart"
        if voice not in self._voices:
            raise WorkerError(f"unknown preset {voice!r}")
        speed = request.get("speed")
        speed = min(max(float(speed), MIN_SPEED), MAX_SPEED) if isinstance(speed, (int, float)) else 1.0
        audio, rate = self._model.create(text, voice=voice, speed=speed, lang=language_for(voice))
        return {
            "ok": True,
            "audio_b64": base64.b64encode(_wav_bytes(np.asarray(audio), int(rate))).decode("ascii"),
            "sample_rate": int(rate),
            "format": "wav",
        }

    def _op_unload(self, _request: Mapping[str, Any]) -> dict[str, Any]:
        self._model = None
        self._voices = []
        return {"ok": True}


def serve(worker: KokoroWorker, stdin: Any, stdout: Any) -> None:
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
    serve(KokoroWorker(), sys.stdin, real_stdout)


if __name__ == "__main__":
    main()

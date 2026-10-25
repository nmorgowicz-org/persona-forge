"""Phonon 31M worker.

Runs inside the ``phonon-31m`` pack environment, never in the web process, so it is
self-contained (``persona_forge`` is not importable there). It speaks the same newline-delimited
JSON protocol as the Kitten 2 worker: one request per line on stdin, one response per line on
stdout. ``ptts`` is imported lazily so the protocol can be tested with a stub model.

Ops: ``ping``, ``load``, ``synthesize``, ``unload``. Phonon has no local cloning, so there is no
``prepare``.
"""

from __future__ import annotations

import base64
import io
import json
import sys
import wave
from typing import Any, Callable, Mapping

import numpy as np

LANGUAGE = "en"
QUANT = "q8"
SAMPLE_RATE = 24000


class WorkerError(RuntimeError):
    """A request failed; the message is returned to the caller."""


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


def _default_factory() -> tuple[Any, list[str]]:
    import ptts

    model = ptts.TTS(ptts.DEFAULT_MODEL, lang=LANGUAGE, quant=QUANT)
    names = [v["name"] for v in ptts.catalog_voices() if str(v.get("language")) == LANGUAGE]
    return model, sorted(names)


class PhononWorker:
    def __init__(self, factory: Callable[[], tuple[Any, list[str]]] | None = None) -> None:
        self._factory = factory or _default_factory
        self._model: Any = None
        self._voices: list[str] = []

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        op = request.get("op")
        handler = getattr(self, f"_op_{op}", None) if isinstance(op, str) else None
        if handler is None:
            raise WorkerError(f"unknown op {op!r}")
        return handler(request)

    def _op_ping(self, _request: Mapping[str, Any]) -> dict[str, Any]:
        return {"ok": True, "loaded": self._model is not None}

    def _op_load(self, _request: Mapping[str, Any]) -> dict[str, Any]:
        if self._model is None:
            self._model, self._voices = self._factory()
        return {"ok": True, "mode": "cpu", "voices": len(self._voices)}

    def _op_synthesize(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if self._model is None:
            raise WorkerError("load the model first")
        text = request.get("text")
        if not isinstance(text, str) or not text.strip():
            raise WorkerError("synthesize needs text")
        kwargs: dict[str, Any] = {}
        preset = request.get("preset")
        if preset:
            if preset not in self._voices:
                raise WorkerError(f"unknown preset {preset!r}")
            kwargs["voice"] = preset
        seed = request.get("seed")
        if isinstance(seed, int):
            kwargs["seed"] = seed
        audio = self._model.synth(text, **kwargs)
        rate = int(getattr(self._model, "sample_rate", SAMPLE_RATE))
        return {
            "ok": True,
            "audio_b64": base64.b64encode(_wav_bytes(np.asarray(audio), rate)).decode("ascii"),
            "sample_rate": rate,
            "format": "wav",
        }

    def _op_unload(self, _request: Mapping[str, Any]) -> dict[str, Any]:
        self._model = None
        self._voices = []
        return {"ok": True}


def serve(worker: PhononWorker, stdin: Any, stdout: Any) -> None:
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
    serve(PhononWorker(), sys.stdin, real_stdout)


if __name__ == "__main__":
    main()

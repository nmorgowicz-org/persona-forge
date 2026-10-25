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
from typing import Any, Callable, Iterator, Mapping

import numpy as np

LANGUAGE = "en"
QUANT = "q8"
SAMPLE_RATE = 24000


# Measured on phonon-31m-en (seeded, 3 runs each): positive ``duration_delta`` slows speech and
# saturates near 0.73x; negative speeds it up to about 1.5x and breaks below -1 (it doubles the
# duration). Pairs are (speed, delta); anything outside is clamped, not extrapolated.
_SPEED_TO_DELTA = ((0.73, 2.0), (0.82, 0.5), (1.0, 0.0), (1.34, -0.5), (1.51, -1.0))
MIN_SPEED = _SPEED_TO_DELTA[0][0]
MAX_SPEED = _SPEED_TO_DELTA[-1][0]


def speed_to_delta(speed: float) -> float:
    speed = min(max(speed, MIN_SPEED), MAX_SPEED)
    for (s0, d0), (s1, d1) in zip(_SPEED_TO_DELTA, _SPEED_TO_DELTA[1:]):
        if s0 <= speed <= s1:
            return d0 + (d1 - d0) * (speed - s0) / (s1 - s0)
    return 0.0


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
        kwargs = self._prepare(request)
        audio = self._model.synth(text, **kwargs)
        rate = int(getattr(self._model, "sample_rate", SAMPLE_RATE))
        return {
            "ok": True,
            "audio_b64": base64.b64encode(_wav_bytes(np.asarray(audio), rate)).decode("ascii"),
            "sample_rate": rate,
            "format": "wav",
        }

    def _prepare(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Validate voice, seed and speed; conditions persist on the model, so always set them."""
        kwargs: dict[str, Any] = {}
        preset = request.get("preset")
        if preset:
            if preset not in self._voices:
                raise WorkerError(f"unknown preset {preset!r}")
            kwargs["voice"] = preset
        seed = request.get("seed")
        if isinstance(seed, int):
            kwargs["seed"] = seed
        speed = request.get("speed")
        delta = speed_to_delta(float(speed)) if isinstance(speed, (int, float)) else 0.0
        self._model.set_conditions({"duration_delta": delta})
        return kwargs

    def stream(self, request: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
        """Yield one message per audio chunk, then a final ``done`` message."""
        if self._model is None:
            raise WorkerError("load the model first")
        text = request.get("text")
        if not isinstance(text, str) or not text.strip():
            raise WorkerError("stream needs text")
        kwargs = self._prepare(request)
        stream = self._model.stream(text, **kwargs)
        try:
            for chunk in stream:
                pcm = (np.clip(np.asarray(chunk, dtype=np.float32), -1.0, 1.0) * 32767.0).astype("<i2")
                yield {"ok": True, "chunk_b64": base64.b64encode(pcm.tobytes()).decode("ascii")}
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        yield {"ok": True, "done": True}

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
            request = json.loads(line)
            if request.get("op") == "stream":
                for message in worker.stream(request):
                    stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
                    stdout.flush()
                continue
            responses = [worker.handle(request)]
        except Exception as exc:  # report, never die: the parent decides whether to restart
            responses = [{"ok": False, "error": str(exc) or type(exc).__name__}]
        for response in responses:
            stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            stdout.flush()


def main() -> None:
    real_stdout = sys.stdout
    sys.stdout = sys.stderr  # library prints must not corrupt the JSON channel
    serve(PhononWorker(), sys.stdin, real_stdout)


if __name__ == "__main__":
    main()

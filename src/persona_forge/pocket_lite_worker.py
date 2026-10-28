"""Pocket Lite worker: the 18M-parameter Pocket-TTS checkpoint (``english_18m_2026-10``).

Runs in a child process so the standard Pocket runtime in the web process is never touched, and so
the model's memory is returned when the engine idles out. Same newline-delimited JSON protocol as
the other pack workers.

Ops: ``ping``, ``load``, ``prepare`` (clone a saved voice from its reference clip), ``synthesize``,
``stream`` (int16 PCM chunks as they are produced, then a ``done`` message), ``unload``.

Voice states are specific to a checkpoint: the 18M model has its own built-in voice files and a
state made by the standard model cannot be reused, so nothing is shared with the main runtime.
"""

from __future__ import annotations

import base64
import io
import json
import sys
import wave
from typing import Any, Callable, Iterator, Mapping

import numpy as np

MODEL_NAME = "english_18m_2026-10"
# The English names in the upstream catalogue. The checkpoint ships other-language voices too; they
# are left out so nothing here needs the language filter.
ENGLISH_PRESETS = (
    "alba", "anna", "azelma", "bill_boerst", "caro_davy", "charles", "cosette", "eponine", "eve",
    "fantine", "george", "jane", "javert", "jean", "marius", "mary", "michael", "paul",
    "peter_yearsley", "stuart_bell", "vera",
)  # fmt: skip


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


def _apply_seed(seed: int) -> None:
    """Seed every generator the model draws from, as the standard Pocket path does."""
    import random

    import torch

    torch.manual_seed(seed)
    np.random.seed(seed % (2**32))
    random.seed(seed)


def _default_factory() -> Any:
    from pocket_tts import TTSModel

    return TTSModel.load_model(language=MODEL_NAME)


class PocketLiteWorker:
    def __init__(self, factory: Callable[[], Any] | None = None) -> None:
        self._factory = factory or _default_factory
        self._model: Any = None
        self._states: dict[str, Any] = {}

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
            model = self._factory()
            if not getattr(model, "has_voice_cloning", True):
                raise WorkerError(
                    "The cloning weights for Pocket Lite are not installed. Repair the engine in "
                    "Runtime → Speech engines (it needs a Hugging Face token for kyutai/pocket-tts)."
                )
            self._model = model
        return {"ok": True, "mode": "cpu"}

    def _loaded(self) -> Any:
        if self._model is None:
            raise WorkerError("load the model first")
        return self._model

    def _op_prepare(self, request: Mapping[str, Any]) -> dict[str, Any]:
        model = self._loaded()
        voice_id, path = request.get("voice_id"), request.get("reference_path")
        if not isinstance(voice_id, str) or not isinstance(path, str):
            raise WorkerError("prepare needs voice_id and reference_path")
        self._states[voice_id] = model.get_state_for_audio_prompt(path)
        return {"ok": True}

    def _state_for(self, request: Mapping[str, Any]) -> Any:
        model = self._loaded()
        voice_id = request.get("voice_id")
        if isinstance(voice_id, str):
            if voice_id not in self._states:
                raise WorkerError(f"voice {voice_id!r} has not been prepared")
            return self._states[voice_id]
        preset = request.get("preset") or "alba"
        if preset not in ENGLISH_PRESETS:
            raise WorkerError(f"unknown preset {preset!r}")
        key = f"preset:{preset}"
        if key not in self._states:
            self._states[key] = model.get_state_for_audio_prompt(preset)
        return self._states[key]

    def _op_synthesize(self, request: Mapping[str, Any]) -> dict[str, Any]:
        text = request.get("text")
        if not isinstance(text, str) or not text.strip():
            raise WorkerError("synthesize needs text")
        state = self._state_for(request)
        seed = request.get("seed")
        if isinstance(seed, int):
            _apply_seed(seed)
        audio = self._loaded().generate_audio(state, text)
        samples = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
        rate = int(self._loaded().sample_rate)
        return {
            "ok": True,
            "audio_b64": base64.b64encode(_wav_bytes(samples, rate)).decode("ascii"),
            "sample_rate": rate,
            "format": "wav",
        }

    def stream(self, request: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
        """Yield one message per audio chunk, then a final ``done`` message."""
        text = request.get("text")
        if not isinstance(text, str) or not text.strip():
            raise WorkerError("stream needs text")
        state = self._state_for(request)
        seed = request.get("seed")
        if isinstance(seed, int):
            _apply_seed(seed)
        chunks = self._loaded().generate_audio_stream(state, text)
        try:
            for chunk in chunks:
                samples = chunk.detach().cpu().numpy() if hasattr(chunk, "detach") else np.asarray(chunk)
                pcm = (np.clip(samples.astype(np.float32).ravel(), -1.0, 1.0) * 32767.0).astype("<i2")
                yield {"ok": True, "chunk_b64": base64.b64encode(pcm.tobytes()).decode("ascii")}
        finally:
            close = getattr(chunks, "close", None)
            if callable(close):
                close()
        yield {"ok": True, "done": True}

    def _op_unload(self, _request: Mapping[str, Any]) -> dict[str, Any]:
        self._model = None
        self._states.clear()
        return {"ok": True}


def serve(worker: PocketLiteWorker, stdin: Any, stdout: Any) -> None:
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
    serve(PocketLiteWorker(), sys.stdin, real_stdout)


if __name__ == "__main__":
    main()

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
import hashlib
import io
import json
import os
import re
import stat
import sys
import tempfile
import wave
from pathlib import Path
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


# Imported prepared voices are registered under a namespaced name the app generated; nothing else
# is accepted, so an import can never replace a built-in voice or smuggle in a path.
_IMPORT_NAME = re.compile(r"^imported-[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
_MAX_IMPORT_BYTES = 1 << 20


def _verified_import_bytes(path: str, digest: str | None) -> bytes:
    """Read the original, not a substituted symlink/FIFO/device, and verify the parent's digest.

    Keep this boundary self-contained: the pack worker runs as a script in its own environment,
    without importing the application or its dependency stack. A ``digest`` is enforced when the
    parent supplies one; without it the read is still bounded and symlink-safe.
    """
    source = Path(path)
    directory_fd = None
    try:
        if source.is_symlink() or source.resolve() != source:
            raise OSError("import paths must not contain symlinks")
        before = source.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_IMPORT_BYTES:
            raise OSError("not a bounded regular voice file")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        if os.open in os.supports_dir_fd:
            directory_fd = os.open(
                source.parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            fd = os.open(source.name, flags, dir_fd=directory_fd)
        else:
            fd = os.open(source, flags)
        with os.fdopen(fd, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_size > _MAX_IMPORT_BYTES
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            ):
                raise OSError("voice file changed while opening it")
            data = handle.read(_MAX_IMPORT_BYTES + 1)
        if len(data) > _MAX_IMPORT_BYTES or (
            digest is not None and hashlib.sha256(data).hexdigest() != digest
        ):
            raise OSError("voice file no longer matches its verified SHA-256")
        return data
    except (OSError, ValueError, RuntimeError) as exc:
        raise WorkerError(f"import needs an existing verified .safetensors file: {exc}") from exc
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


class PhononWorker:
    def __init__(self, factory: Callable[[], tuple[Any, list[str]]] | None = None) -> None:
        self._factory = factory or _default_factory
        self._model: Any = None
        self._voices: list[str] = []
        self._catalog_voices: frozenset[str] = frozenset()
        self._imported: dict[str, tuple[str, str | None]] = {}

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
            self._model, self._voices = self._factory()
            self._catalog_voices = frozenset(self._voices)
            self._imported = {}
        failed: list[str] = []
        for entry in request.get("imported") or []:
            try:
                self._register_import(entry.get("name"), entry.get("path"), entry.get("sha256"))
            except (WorkerError, AttributeError):
                failed.append(str(entry.get("name") if isinstance(entry, dict) else entry))
        reply: dict[str, Any] = {"ok": True, "mode": "cpu", "voices": len(self._voices)}
        if failed:
            reply["imported_failed"] = failed
        return reply

    def _drop_import(self, name: str) -> None:
        self._imported.pop(name, None)
        if name not in self._catalog_voices:
            self._voices = [voice for voice in self._voices if voice != name]

    def _check_import(self, name: Any) -> None:
        if isinstance(name, str) and name in self._imported:
            path, digest = self._imported[name]
            try:
                _verified_import_bytes(path, digest)
            except WorkerError as exc:
                self._drop_import(name)
                raise WorkerError(f"unknown preset {name!r}: imported voice changed: {exc}") from exc

    def _register_import(self, name: Any, path: Any, digest: Any) -> None:
        """Register a prepared voice file; the native parser's refusal is the final word.

        With a digest the parse is pinned to the exact verified bytes: they are re-read once,
        checked, and handed to the model as a private read-only copy, so substituting the file
        between verification and parse cannot change what is served. Without a digest (a direct
        registration) the file is only bounded-read and symlink-checked, and the path itself is
        parsed; every later synthesis re-checks it either way (``_check_import``).
        """
        if self._model is None:
            raise WorkerError("load the model first")
        if not isinstance(name, str) or not _IMPORT_NAME.fullmatch(name):
            raise WorkerError("an imported voice is named imported-<name>")
        if name in self._catalog_voices:
            raise WorkerError(f"{name!r} is a built-in voice name")
        # Invalidate first: a failed replacement must never leave the old cached voice usable.
        self._drop_import(name)
        if (
            not isinstance(path, str)
            or not os.path.isabs(path)
            or not path.endswith(".safetensors")
            or not os.path.exists(path)
        ):
            raise WorkerError("import needs an existing .safetensors file at an absolute path")
        if digest is not None and (not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
            raise WorkerError("import needs the verified SHA-256 of the prepared voice")
        pinned = digest is not None
        data = _verified_import_bytes(path, digest)
        try:
            if pinned:
                with tempfile.TemporaryDirectory(prefix="phonon-voice-") as directory:
                    snapshot = Path(directory) / "voice.safetensors"
                    snapshot.write_bytes(data)
                    snapshot.chmod(0o400)
                    try:
                        self._model.add_voice(name, str(snapshot))
                    finally:
                        # Windows cannot unlink a read-only file.
                        snapshot.chmod(0o600)
            else:
                self._model.add_voice(name, path)
        except Exception as exc:  # the native loader's own message is the useful part
            raise WorkerError(f"Phonon could not read this voice file: {exc}") from exc
        self._imported[name] = (path, digest if isinstance(digest, str) else None)
        if name not in self._voices:
            self._voices = sorted([*self._voices, name])

    def _op_import_voice(self, request: Mapping[str, Any]) -> dict[str, Any]:
        self._register_import(request.get("name"), request.get("path"), request.get("sha256"))
        return {"ok": True, "voice": request.get("name")}

    def _op_synthesize(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if self._model is None:
            raise WorkerError("load the model first")
        text = request.get("text")
        if not isinstance(text, str) or not text.strip():
            raise WorkerError("synthesize needs text")
        kwargs = self._prepare(request)
        audio = self._model.synth(text, **kwargs)
        self._check_import(request.get("preset"))
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
            self._check_import(preset)
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
                self._check_import(request.get("preset"))
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
        self._catalog_voices = frozenset()
        self._imported = {}
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

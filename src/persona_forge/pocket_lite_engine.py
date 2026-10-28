"""Pocket Lite adapter: the 18M Pocket checkpoint, served from a pack child process.

Clones a saved library voice from its reference clip (no transcript needed) and serves the English
preset voices. It shares nothing with the standard Pocket runtime: separate weights, separate
voice states, separate process. Listening tests found this size close to the standard model; the
7M and 2M checkpoints were rejected for audible artifacts.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from persona_forge import (
    engine_packs,
    pocket_lite_pack,
    pocket_lite_worker,
    voice_bindings,
    voice_library,
)
from persona_forge.kitten2_engine import EngineUnavailable, InvalidVoice
from persona_forge.pack_preset_engine import PackPresetEngine
from persona_forge.pack_process import PackProcess

ENGINE_ID = pocket_lite_pack.ENGINE_ID
PRESET_PREFIX = "pocket-lite:"
PREPARE_TIMEOUT_S = 120.0  # encoding one reference clip on CPU takes seconds, not minutes

__all__ = ["EngineUnavailable", "InvalidVoice", "PocketLiteEngine", "is_installed", "list_presets"]


def pack_directory(root: Path | None = None) -> Path | None:
    return engine_packs.find_pack_dir(ENGINE_ID, root)


def pack_python(root: Path | None = None) -> Path | None:
    """The interpreter that runs the worker: the application's own, once the pack is verified."""
    directory = pack_directory(root)
    if directory is None or engine_packs.inspect_pack(directory).status != "verified":
        return None
    return Path(sys.executable)


def is_installed(root: Path | None = None) -> bool:
    return pack_python(root) is not None


def list_presets(root: Path | None = None) -> list[str]:
    return list(pocket_lite_worker.ENGLISH_PRESETS) if is_installed(root) else []


def preset_language(name: str, root: Path | None = None) -> str:
    del name, root
    return "en"


class PocketLiteEngine(PackPresetEngine):
    id = ENGINE_ID
    label = "Pocket Lite (18M)"
    idle_env = "POCKET_LITE_IDLE_UNLOAD_S"
    idle_default_s = pocket_lite_pack.IDLE_UNLOAD_AFTER_S
    worker_file = str(Path(pocket_lite_worker.__file__).resolve())
    preset_prefix = PRESET_PREFIX
    streams = True

    def __init__(self, idle_unload_s: float | None = None, **kwargs: Any) -> None:
        super().__init__(idle_unload_s, **kwargs)
        self._prepared: dict[str, dict[str, str]] = {}

    def _pack_python(self) -> Path | None:
        return pack_python()

    def _load_request(self) -> tuple[dict[str, Any], dict[str, str]]:
        directory = pack_directory()
        if directory is None:
            raise EngineUnavailable(
                "The Pocket Lite engine pack is not installed; install it in Runtime → "
                "Speech engines."
            )
        installed_with = self._installed_with(directory)
        current = pocket_lite_pack.pocket_tts_version()
        if installed_with and installed_with != current:
            # Each pocket-tts release pins its own weight revisions, so the offline cache from the
            # old release no longer matches; say so instead of surfacing a Hub lookup error.
            raise EngineUnavailable(
                f"Pocket Lite was installed with pocket-tts {installed_with} but the app now has "
                f"{current}. Choose Repair in Runtime → Speech engines to download the matching "
                "weights."
            )
        env = pocket_lite_pack.worker_env(directory, offline=True)
        # Keep the standard Pocket runtime's settings from leaking into this model.
        env.setdefault("POCKET_TTS_MODEL_SOURCE", "auto")
        return {"op": "load"}, env

    @staticmethod
    def _installed_with(directory: Path) -> str | None:
        try:
            requirements = engine_packs.load_manifest(directory).requirements
        except (engine_packs.PackManifestError, OSError):
            return None
        return next((r.split("==", 1)[1] for r in requirements if r.startswith("pocket-tts==")), None)

    def unload(self) -> None:
        super().unload()
        self._prepared.clear()

    def _fill_request(
        self,
        request: dict[str, Any],
        requested: str,
        seed_value: int | None,
        speed: float | None,
    ) -> None:
        del speed  # Pocket has no speed control
        self._seed(request, seed_value)
        if "voice_id" in request:
            return
        for prefix in (PRESET_PREFIX, "pocket:"):
            if requested.startswith(prefix):
                requested = requested[len(prefix) :]
                break
        if requested:
            request["preset"] = requested

    def _check_voice(self, requested: str) -> None:
        del requested  # saved voices are cloned here, so nothing is refused up front

    def _on_process_lost(self) -> None:
        self._prepared.clear()

    def _prepare_voice(self, process: PackProcess, requested: str, *, force: bool = False) -> bool:
        meta = voice_library.get_voice(requested) if requested else None
        if meta is None:
            return False
        wav_path = Path(meta["wav_path"])
        if wav_path.is_symlink():
            wav_path = wav_path.resolve()
        if not wav_path.is_file():
            raise InvalidVoice(
                f"The reference clip for voice {requested!r} is missing. "
                "Restore the clip or save the voice again in Voice Library."
            )
        key = voice_bindings.current_key(meta, ENGINE_ID)
        if force or self._prepared.get(requested) != key:
            process.request(
                {"op": "prepare", "voice_id": requested, "reference_path": str(wav_path)},
                timeout=PREPARE_TIMEOUT_S,
            )
            fresh = voice_bindings.meta_with_path(requested)
            if fresh is None or voice_bindings.current_key(fresh, ENGINE_ID) != key:
                self._prepared.pop(requested, None)
                raise InvalidVoice("The voice changed during preparation. Prepare it again.")
            self._prepared[requested] = key
            voice_bindings.write_marker(requested, ENGINE_ID, key)
        return True

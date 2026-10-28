"""Phonon 31M adapter: English preset voices from a pack child process.

Phonon cannot clone from a recording, so it serves only its built-in catalog. A request that names
a saved library voice gets a clear 400 instead of a silent fallback to some other voice.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


from persona_forge import engine_packs, imported_voices, phonon_pack, phonon_worker
from persona_forge.engine_lifecycle import wait_until_ready
from persona_forge.kitten2_engine import EngineUnavailable, EngineWarming, InvalidVoice
from persona_forge.pack_preset_engine import PackPresetEngine
from persona_forge.pack_process import PackProcessError

ENGINE_ID = phonon_pack.ENGINE_ID
PRESET_PREFIX = "phonon:"
IMPORT_TIMEOUT_S = 30.0  # the worker only parses one small embedding file
IMPORT_PATIENCE_S = 120.0  # how long an import waits for a cold worker before giving up

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


def list_imported() -> list[str]:
    """Names of the user's imported prepared voices (``imported-<name>``), kept beside the presets."""
    return imported_voices.names(ENGINE_ID)


def preset_language(name: str, root: Path | None = None) -> str:
    return "en"  # only English voices are listed


class PhononEngine(PackPresetEngine):
    id = ENGINE_ID
    label = "Phonon 31M"
    idle_env = "PHONON_IDLE_UNLOAD_S"
    idle_default_s = phonon_pack.IDLE_UNLOAD_AFTER_S
    worker_file = str(Path(phonon_worker.__file__).resolve())
    preset_prefix = PRESET_PREFIX
    streams = True

    def _pack_python(self) -> Path | None:
        return pack_python()

    def _load_request(self) -> tuple[dict[str, Any], dict[str, str]]:
        env: dict[str, str] = {}
        directory = None if os.environ.get("PHONON_PYTHON") else pack_directory()
        if directory is not None:
            # Serve from the pack's own files and never download mid-request.
            env = {"HF_HOME": str(phonon_pack.weights_dir(directory)), "HF_HUB_OFFLINE": "1"}
        request: dict[str, Any] = {"op": "load"}
        entries = imported_voices.serving_entries(ENGINE_ID)
        if entries:
            request["imported"] = entries  # re-registered every time the worker starts
        return request, env

    def _on_process_lost(self) -> None:
        self._worker_imports: dict[str, dict[str, str]] = {}

    def _on_loaded(self, request: dict[str, Any], reply: dict[str, Any]) -> None:
        entries = request.get("imported", [])
        failed = set(reply.get("imported_failed", []))
        imported_voices.reject_entries(
            ENGINE_ID, [entry for entry in entries if entry["name"] in failed]
        )
        self._worker_imports = {
            entry["name"]: entry for entry in entries if entry["name"] not in failed
        }

    def _import_entry(self, requested: str) -> dict[str, str] | None:
        name = requested.removeprefix(PRESET_PREFIX)
        if not name.startswith(imported_voices.SLUG_PREFIX):
            return None
        for entry in imported_voices.serving_entries(ENGINE_ID):
            if entry["name"] == name:
                return entry
        raise InvalidVoice(f"unknown preset {name!r}: the imported voice is missing or broken")

    def _check_voice(self, requested: str) -> None:
        super()._check_voice(requested)
        self._import_entry(requested)

    def _prepare_voice(self, process: Any, requested: str, *, force: bool = False) -> bool:
        # The pre-load check is not enough: the store may change while waiting for the worker
        # or the inference lock. This hook runs inside that lock for both batch and streaming.
        del process, force
        entry = self._import_entry(requested)
        if entry is not None and self._worker_imports.get(entry["name"]) != entry:
            raise InvalidVoice(f"unknown preset {entry['name']!r}: the loaded import is stale")
        return False

    def import_voice(self, slug: str, path: Path | str, *, sha256: str | None = None) -> None:
        """Have the worker register a prepared voice file; its parser has the final say.

        The adapter only transports: the worker enforces the path, extension, size and digest
        rules, and its refusal (or the native parser's) surfaces as ``InvalidVoice``;
        ``EngineUnavailable`` when the worker could not be reached. ``sha256``, when the caller
        has already verified the bytes (the app's import flow has), is forwarded so the worker
        pins the parse to exactly those bytes.
        """
        request: dict[str, Any] = {"op": "import_voice", "name": slug, "path": str(path)}
        if sha256:
            request["sha256"] = sha256
        wait_until_ready(self._await_ready, EngineWarming, patience_s=IMPORT_PATIENCE_S)
        with self._lock:
            process = self._ensure_started()
            try:
                process.request(request, timeout=IMPORT_TIMEOUT_S)
            except PackProcessError as exc:
                if not process.is_alive:
                    self._process = None
                    raise EngineUnavailable(str(exc)) from exc
                raise InvalidVoice(str(exc)) from exc
            self._arm_idle_timer()
            entry: dict[str, str] = {"name": slug, "path": str(path)}
            if sha256:
                entry["sha256"] = sha256
            entry["engine_revision"] = imported_voices._engine_revision(ENGINE_ID)
            self._worker_imports[slug] = entry

    def forget_imported(self, slug: str) -> None:
        """A removed import must stop being served: the model cannot drop a voice, so restart it."""
        del slug
        self.unload()

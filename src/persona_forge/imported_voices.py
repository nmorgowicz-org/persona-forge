"""Imported prepared voices (plan §4.1, §5.4): untrusted files an engine can add as built-in voices.

Only engines that declare the ``import_prepared_voice`` capability and have a pinned file schema
here can import. Today that is Phonon 31M, whose runtime loads a precomputed speaker embedding
(``TTS.add_voice(name, file)``). Its catalog voices are exactly such files, so an import is a real,
checkable round trip. Kitten's ``voices.json`` entries are not importable: the model reads them from
its pinned snapshot at construction (reference clip plus an ``.npz`` archive), with no runtime
add-voice call, and accepting that format would mean unpickling-capable archives from strangers.

Everything about a file is checked before an engine sees it:

- extension allowlist (``.safetensors``), size cap, and a filename that carries no path or URL;
- the safetensors container is parsed by hand: header length, JSON header, exactly one tensor with
  the schema's name, dtype and shape, byte offsets that cover the file exactly, finite values of
  sane magnitude, string-only bounded metadata that does not name a path or URL. The format has no
  executable content, and anything else (pickle, zip/npz, torch files) fails the header checks;
- the user's filename is recorded as provenance text only. The stored path is built from a slug
  generated here, never from the upload.

After validation the engine itself must accept the file (a real worker round trip), and only then
is the voice kept: under the app data directory with its provenance (source filename, SHA-256, size,
date, engine revision). It is served as ``<engine prefix><slug>`` and can be removed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import struct
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from persona_forge import paths, speech_engines, voice_bindings

MAX_FILE_BYTES = 1 << 20  # shipped Phonon voices are 256 kB
MAX_HEADER_BYTES = 4096
MAX_RECORD_BYTES = 16 << 10
MAX_METADATA_KEYS = 16
MAX_METADATA_TEXT = 128
MAX_ABS_VALUE = 1000.0  # shipped voices peak near 4
MAX_FILENAME = 120
EXTENSIONS = (".safetensors",)
SLUG_PREFIX = "imported-"

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}$")
_SLUG_RE = re.compile(r"^imported-[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
_lock = threading.RLock()
# Loader failures are scoped to the exact bytes and revision, not just a reusable voice name.
# This is deliberately independent of _lock: background loads run while import holds _lock.
_rejections: set[tuple[str, str, str, str]] = set()


@dataclass(frozen=True)
class Schema:
    tensor: str
    dtype: str
    shape: tuple[int, ...]


# What a file must look like per engine, pinned from the files the engine ships (Phonon 31M:
# every one of its 37 catalog voices is one F32 tensor of this shape).
SCHEMAS: dict[str, Schema] = {
    "phonon-31m": Schema(tensor="speaker_wavs", dtype="F32", shape=(1, 512, 125)),
}


class ImportRefused(Exception):
    """An import cannot go ahead. ``code`` is stable for clients; ``status`` is the HTTP status."""

    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.public_message = message
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ValidatedVoice:
    sha256: str
    size: int
    shape: tuple[int, ...]
    metadata: dict[str, str]


# -- seams the tests replace -------------------------------------------------------------------------


def _is_installed(engine_id: str) -> bool:
    from persona_forge import provisioned_engines

    provisioned = provisioned_engines.get(engine_id)
    return provisioned is not None and bool(provisioned.engine.is_installed())


def _engine_revision(engine_id: str) -> str:
    return voice_bindings.engine_revision(engine_id)


def _catalog_names(engine_id: str) -> set[str]:
    from persona_forge import provisioned_engines

    provisioned = provisioned_engines.get(engine_id)
    return set(provisioned.engine.list_presets()) if provisioned is not None else set()


def _prefix(engine_id: str) -> str:
    from persona_forge import provisioned_engines

    provisioned = provisioned_engines.get(engine_id)
    return str(provisioned.engine.PRESET_PREFIX) if provisioned is not None else f"{engine_id}:"


# -- validation --------------------------------------------------------------------------------------


def _bad(message: str) -> ImportRefused:
    return ImportRefused("invalid_voice_file", message, 422)


def _looks_like_path_or_url(text: str) -> bool:
    return (
        "/" in text
        or "\\" in text
        or text.startswith("~")
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", text) is not None
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in text)
    )


def _check_metadata(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise _bad("The file's metadata is not a map of text values.")
    if len(value) > MAX_METADATA_KEYS:
        raise _bad(f"The file carries more than {MAX_METADATA_KEYS} metadata entries.")
    for key, text in value.items():
        if not isinstance(key, str) or not isinstance(text, str):
            raise _bad("The file's metadata must be text only.")
        if len(key) > MAX_METADATA_TEXT or len(text) > MAX_METADATA_TEXT:
            raise _bad("The file carries an oversized metadata entry.")
        if _looks_like_path_or_url(key) or _looks_like_path_or_url(text):
            raise _bad("The file's metadata names a path or URL, which is not accepted.")
    return dict(value)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def validate_bytes(engine_id: str, data: bytes) -> ValidatedVoice:
    """Check an uploaded prepared-voice file against the engine's pinned schema, or refuse it."""
    schema = SCHEMAS.get(engine_id)
    if schema is None:
        raise ImportRefused(
            "import_unsupported", f"{engine_id} has no prepared-voice format that can be imported.", 400
        )
    if len(data) > MAX_FILE_BYTES:
        raise ImportRefused(
            "file_too_large", f"A prepared voice is at most {MAX_FILE_BYTES // 1024} kB.", 413
        )
    if len(data) < 8:
        raise _bad("This is not a safetensors voice file.")
    (header_len,) = struct.unpack("<Q", data[:8])
    if not 0 < header_len <= MAX_HEADER_BYTES or 8 + header_len > len(data):
        raise _bad("This is not a safetensors voice file (bad header).")
    try:
        raw_header = data[8 : 8 + header_len]
        if not raw_header.startswith(b"{"):
            raise ValueError("safetensors headers start with '{'")
        header = json.loads(raw_header.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise _bad("This is not a safetensors voice file (the header is not valid JSON).") from None
    if not isinstance(header, dict):
        raise _bad("This is not a safetensors voice file (the header is not an object).")

    metadata: dict[str, str] = {}
    unexpected = set(header) - {schema.tensor, "__metadata__"}
    if unexpected or schema.tensor not in header:
        raise _bad(f"A voice file holds exactly one tensor named {schema.tensor!r}.")
    if "__metadata__" in header:
        metadata = _check_metadata(header["__metadata__"])

    entry = header[schema.tensor]
    if not isinstance(entry, dict) or set(entry) != {"dtype", "shape", "data_offsets"}:
        raise _bad("The tensor entry has unexpected fields.")
    if entry["dtype"] != schema.dtype:
        raise _bad(f"The tensor must be {schema.dtype}, not {entry['dtype']!r}.")
    shape = entry["shape"]
    if (
        not isinstance(shape, list)
        or not all(type(dim) is int for dim in shape)
        or tuple(shape) != schema.shape
    ):
        raise _bad(f"The tensor shape must be {list(schema.shape)} for this engine.")
    data_bytes = int(np.prod(schema.shape)) * 4
    offsets = entry["data_offsets"]
    if (
        not isinstance(offsets, list)
        or not all(type(offset) is int for offset in offsets)
        or offsets != [0, data_bytes]
    ):
        raise _bad("The tensor's byte offsets do not match its shape.")
    if 8 + header_len + data_bytes != len(data):
        raise _bad("The file is truncated or has trailing bytes.")

    values = np.frombuffer(data, dtype="<f4", count=data_bytes // 4, offset=8 + header_len)
    if not bool(np.isfinite(values).all()) or float(np.abs(values).max()) > MAX_ABS_VALUE:
        raise _bad("The voice data contains non-finite or implausibly large values.")

    return ValidatedVoice(
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
        shape=schema.shape,
        metadata=metadata,
    )


def check_filename(filename: str) -> str:
    """The upload's name as provenance text, or a refusal. Never used to build a path."""
    name = (filename or "").strip()
    if not name or len(name) > MAX_FILENAME or any(ord(ch) < 32 for ch in name) or any(
        ch in name for ch in "/\\:"
    ) or ".." in name:
        raise ImportRefused(
            "invalid_filename", "The file name must be a plain name, not a path or URL.", 400
        )
    if Path(name).suffix.lower() not in EXTENSIONS:
        raise ImportRefused(
            "bad_extension", "Only .safetensors prepared-voice files can be imported.", 400
        )
    return name


def slug_for(display_name: str) -> str:
    """``Zoey copy`` -> ``imported-zoey-copy``; refuses names that are not plain words."""
    name = (display_name or "").strip()
    if not _NAME_RE.fullmatch(name):
        raise ImportRefused(
            "invalid_name",
            "Name the voice with 1-40 letters, digits, spaces, dots, dashes or underscores.",
            400,
        )
    core = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    slug = SLUG_PREFIX + core
    if not core or not _SLUG_RE.fullmatch(slug):
        raise ImportRefused("invalid_name", "That name has no letters or digits to build an id from.", 400)
    return slug


# -- store -------------------------------------------------------------------------------------------


def root() -> Path:
    """``IMPORTED_VOICES_DIR`` else ``<app data>/imported-voices``."""
    override = os.environ.get("IMPORTED_VOICES_DIR", "").strip()
    return Path(override).expanduser() if override else paths.app_data_root() / "imported-voices"


def _engine_dir(engine_id: str) -> Path:
    return root().resolve() / engine_id


def _safe_engine_dir(engine_id: str) -> Path:
    if engine_id not in SCHEMAS:
        raise _bad("Not an imported-voice engine.")
    base = _engine_dir(engine_id)
    if base.is_symlink() or base.resolve() != base:
        raise _bad("The imported-voice directory must not be a symlink.")
    return base


def _read_regular(path: Path, cap: int) -> bytes:
    """Bounded, non-following reads; never block on a substituted FIFO/device."""
    if path.is_symlink() or path.parent.is_symlink() or path.resolve() != path:
        raise OSError("Imported voice paths must not contain symlinks.")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > cap:
        raise OSError("Not a bounded regular imported-voice file.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    directory_fd = None
    try:
        if os.open in os.supports_dir_fd:
            directory_fd = os.open(
                path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            )
            fd = os.open(path.name, flags, dir_fd=directory_fd)
        else:
            fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_size > cap
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            ):
                raise OSError("Imported voice changed while opening it.")
            data = handle.read(cap + 1)
        if len(data) > cap:
            raise OSError("Imported voice exceeds its size limit.")
        return data
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


def _write_atomic(path: Path, payload: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".partial-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass


def _require_importer(engine_id: str) -> speech_engines.EngineInfo:
    engine = speech_engines.ENGINES.get(engine_id)
    if engine is None:
        raise ImportRefused("unknown_engine", f"Unknown engine {engine_id!r}.", 404)
    if not engine.capabilities.import_prepared_voice or engine_id not in SCHEMAS:
        raise ImportRefused(
            "import_unsupported", f"{engine.label} cannot import prepared voices.", 400
        )
    return engine


def _record_paths(engine_id: str, slug: str) -> tuple[Path, Path]:
    base = os.path.normpath(str(_engine_dir(engine_id)))
    paths_out: list[Path] = []
    for suffix in (".safetensors", ".json"):
        full = os.path.normpath(os.path.join(base, slug + suffix))
        # The slug is already limited to [a-z0-9-]; this keeps the path inside the engine folder
        # even if that ever changes.
        if not full.startswith(base + os.sep):
            raise _bad("That name would leave the imported-voice folder.")
        paths_out.append(Path(full))
    return paths_out[0], paths_out[1]


def import_voice(
    engine_id: str, *, filename: str, data: bytes, display_name: str
) -> dict[str, Any]:
    """Validate, have the engine accept, then keep an imported prepared voice. Returns its record."""
    engine = _require_importer(engine_id)
    source_name = check_filename(filename)
    slug = slug_for(display_name)
    validated = validate_bytes(engine_id, data)
    if not _is_installed(engine_id):
        raise ImportRefused(
            "engine_not_installed",
            f"Install {engine.label} first: the engine checks every imported voice before it is kept.",
            409,
        )

    with _lock:
        _safe_engine_dir(engine_id)
        voice_path, record_path = _record_paths(engine_id, slug)
        if slug in _catalog_names(engine_id) or any(
            path.exists() or path.is_symlink() for path in (voice_path, record_path)
        ):
            raise ImportRefused("name_taken", f"A voice named {slug!r} is already imported.", 409)
        revision = _engine_revision(engine_id)
        voice_path.parent.mkdir(parents=True, exist_ok=True)
        _safe_engine_dir(engine_id)
        _write_atomic(voice_path, data)
        accepted = False
        try:
            _engine_accepts(engine_id, slug, voice_path, validated.sha256)
            accepted = True
            if _engine_revision(engine_id) != revision:
                raise _bad("The engine revision changed while checking the voice; import it again.")
            if validate_bytes(engine_id, _read_regular(voice_path, MAX_FILE_BYTES)) != validated:
                raise _bad("The voice changed while the engine was checking it.")
            record = {
                "engine": engine_id,
                "slug": slug,
                "voice_id": f"{_prefix(engine_id)}{slug}",
                "display_name": display_name.strip(),
                "source_filename": source_name,
                "sha256": validated.sha256,
                "size": validated.size,
                "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "engine_revision": revision,
                "schema": {
                    "tensor": SCHEMAS[engine_id].tensor,
                    "dtype": SCHEMAS[engine_id].dtype,
                    "shape": list(validated.shape),
                },
                "metadata": validated.metadata,
            }
            _write_atomic(record_path, json.dumps(record, indent=2).encode("utf-8"))
        except BaseException:
            for leftover in (voice_path, record_path):
                try:
                    leftover.unlink()
                except OSError:
                    pass
            if accepted:
                _forget_imported(engine_id, slug)
            raise
    return record


def _engine_accepts(engine_id: str, slug: str, path: Path, sha256: str) -> None:
    """Ask the engine's own loader to take the file; its refusal is the final word.

    ``sha256`` is the digest of the bytes already validated and stored, forwarded so the
    engine's worker can pin its parse to exactly them.
    """
    from persona_forge.kitten2_engine import EngineUnavailable, InvalidVoice

    adapter = speech_engines.get_adapter(engine_id)
    importer = getattr(adapter, "import_voice", None)
    if importer is None:
        raise ImportRefused("import_unsupported", f"{engine_id} cannot import prepared voices.", 400)
    try:
        importer(slug, path, sha256=sha256)
    except InvalidVoice as exc:
        raise ImportRefused("engine_rejected", str(exc), 422) from exc
    except EngineUnavailable as exc:
        raise ImportRefused("engine_unavailable", str(exc), 503) from exc


def _forget_imported(engine_id: str, slug: str) -> None:
    forget = getattr(speech_engines.get_adapter(engine_id), "forget_imported", None)
    if forget is not None:
        forget(slug)


def _rejection_key(engine_id: str, entry: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(_engine_dir(engine_id)),
        entry["name"],
        entry["sha256"],
        entry["engine_revision"],
    )


def reject_entries(engine_id: str, entries: list[dict[str, str]]) -> None:
    """Remember a native parser refusal for exactly the worker's attempted snapshot.

    No store mutation lock here: a background load can report failures while an import waits
    for that load with the mutation lock held.
    """
    for entry in entries:
        _rejections.add(_rejection_key(engine_id, entry))


def _load_record(
    engine_id: str, record_path: Path, voice_path: Path
) -> dict[str, Any] | None:
    try:
        record = json.loads(
            _read_regular(record_path, MAX_RECORD_BYTES).decode("utf-8"),
            object_pairs_hook=_unique_object,
        )
        if not isinstance(record, dict):
            return None
        slug = record_path.stem
        schema = SCHEMAS[engine_id]
        display = record.get("display_name")
        source = record.get("source_filename")
        digest = record.get("sha256")
        revision = record.get("engine_revision")
        size = record.get("size")
        if (
            record.get("engine") != engine_id
            or record.get("slug") != slug
            or record.get("voice_id") != f"{_prefix(engine_id)}{slug}"
            or not isinstance(display, str)
            or slug_for(display) != slug
            or not isinstance(source, str)
            or check_filename(source) != source
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or not isinstance(revision, str)
            or not revision
            or len(revision) > 256
            or type(size) is not int
            or not 8 < size <= MAX_FILE_BYTES
            or record.get("schema") != {
                "tensor": schema.tensor, "dtype": schema.dtype, "shape": list(schema.shape)
            }
        ):
            return None
        timestamp = record.get("imported_at")
        if not isinstance(timestamp, str) or datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        ).tzinfo is None:
            return None
        metadata = _check_metadata(record.get("metadata"))
    except (OSError, ValueError, TypeError, RecursionError, ImportRefused):
        return None

    broken = revision != _engine_revision(engine_id) or slug in _catalog_names(engine_id)
    try:
        validated = validate_bytes(engine_id, _read_regular(voice_path, MAX_FILE_BYTES))
        broken = broken or (
            validated.sha256 != digest or validated.size != size or validated.metadata != metadata
        )
    except (OSError, ValueError, ImportRefused):
        broken = True
    entry = {"name": slug, "sha256": digest, "engine_revision": revision}
    return {**record, "broken": broken or _rejection_key(engine_id, entry) in _rejections}


def list_imported(engine_id: str, *, include_broken: bool = False) -> list[dict[str, Any]]:
    """Imported voices of an engine, by slug. A file changed since import is ``broken`` and not served."""
    # Reads deliberately do not take _lock; imports wait for a background worker load.
    try:
        base = _safe_engine_dir(engine_id)
    except (OSError, ValueError, ImportRefused):
        return []
    if not base.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for record_path in sorted(base.glob(f"{SLUG_PREFIX}*.json")):
        slug = record_path.stem
        if not _SLUG_RE.fullmatch(slug):
            continue
        record = _load_record(engine_id, record_path, record_path.with_suffix(".safetensors"))
        if record is not None and record.get("slug") == slug and (include_broken or not record["broken"]):
            records.append(record)
    return records


def names(engine_id: str) -> list[str]:
    return [record["slug"] for record in list_imported(engine_id)]


def serving_entries(engine_id: str) -> list[dict[str, str]]:
    """Verified provenance sent to a worker; its digest must match before the native parse."""
    return [
        {
            "name": record["slug"],
            "path": str(_record_paths(engine_id, record["slug"])[0]),
            "sha256": record["sha256"],
            "engine_revision": record["engine_revision"],
        }
        for record in list_imported(engine_id)
    ]


def remove(engine_id: str, slug: str) -> bool:
    """Delete an imported voice. Only a slug this module would generate is accepted."""
    _require_importer(engine_id)
    if not _SLUG_RE.fullmatch(slug or ""):
        raise ImportRefused("invalid_name", "Not an imported voice id.", 400)
    with _lock:
        _safe_engine_dir(engine_id)
        removed = False
        for path in _record_paths(engine_id, slug):
            try:
                path.unlink()
                removed = True
            except FileNotFoundError:
                pass
        if removed:
            _forget_imported(engine_id, slug)
    return removed

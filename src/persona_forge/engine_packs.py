"""Engine packs (Phase C3): manifests, discovery and local verification.

A pack is a directory under ``ENGINE_PACKS_DIR`` (default ``<data>/engine-packs``) containing a
``manifest.json`` plus its pinned artifacts. This module owns only what can be decided locally:
is the manifest valid, are the artifacts present, do their hashes match, how much disk do they
use. Downloading, virtualenv creation and process management stay out of this layer so the API can
report an honest state before any install exists.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from persona_forge import install_check, paths, speech_engines

MANIFEST_FILENAME = "manifest.json"
VERIFIED_FILENAME = ".verified.json"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PackManifestError(ValueError):
    """A manifest is malformed. The message is safe to show to the user."""


class PackInstallError(RuntimeError):
    """An install cannot proceed (bad source, disk space, hash mismatch)."""


@dataclass(frozen=True)
class PackArtifact:
    path: str
    sha256: str
    size: int
    source: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size": self.size,
            "source": self.source,
        }


@dataclass(frozen=True)
class PackManifest:
    id: str
    engine_id: str
    version: str
    label: str
    description: str
    runtime: str
    requirements: tuple[str, ...]
    artifacts: tuple[PackArtifact, ...]
    revision: str | None = None
    notes: str | None = None
    # Packs built by running installers (venv + packages + weights) instead of hashed downloads
    # name their provisioner here; they may then declare no artifacts.
    provisioner: str | None = None
    # Seconds of inactivity before the engine's worker is stopped; 0 = never. None = the pack
    # predates the field, so the adapter uses its own default.
    idle_unload_after: float | None = None
    manifest_sha256: str = ""
    raw: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "engine_id": self.engine_id,
            "version": self.version,
            "label": self.label,
            "description": self.description,
            "runtime": self.runtime,
            "requirements": list(self.requirements),
            "artifacts": [artifact.as_dict() for artifact in self.artifacts],
            "revision": self.revision,
            "notes": self.notes,
            "provisioner": self.provisioner,
            "idle_unload_after": self.idle_unload_after,
            "manifest_sha256": self.manifest_sha256,
        }


def packs_root() -> Path:
    """Directory holding engine packs; overridable for tests and non-default installs."""
    override = os.environ.get("ENGINE_PACKS_DIR")
    if override:
        return Path(override).expanduser()
    return paths.runtime_data_dir() / "engine-packs"


def _safe_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PackManifestError("artifact path must be a non-empty string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise PackManifestError(f"artifact path must stay inside the pack: {value!r}")
    return value


def parse_manifest(payload: Mapping[str, Any], manifest_sha256: str = "") -> PackManifest:
    """Validate a raw manifest mapping and return its typed form."""
    pack_id = payload.get("id")
    if not isinstance(pack_id, str) or not _ID_RE.match(pack_id):
        raise PackManifestError("id must be a lowercase slug (a-z, 0-9, '.', '_', '-')")
    engine_id = payload.get("engine_id")
    if not isinstance(engine_id, str) or not _ID_RE.match(engine_id):
        raise PackManifestError("engine_id must be a lowercase slug")

    version = payload.get("version")
    if not isinstance(version, str) or not version.strip():
        raise PackManifestError("version must be a non-empty string")

    provisioner = payload.get("provisioner")
    if provisioner is not None and (
        not isinstance(provisioner, str) or not _ID_RE.match(provisioner)
    ):
        raise PackManifestError("provisioner must be a lowercase slug")
    artifacts_raw = payload.get("artifacts", [] if provisioner else None)
    if not isinstance(artifacts_raw, list) or (not artifacts_raw and not provisioner):
        raise PackManifestError("artifacts must be a non-empty list")
    artifacts: list[PackArtifact] = []
    for index, item in enumerate(artifacts_raw):
        if not isinstance(item, Mapping):
            raise PackManifestError(f"artifacts[{index}] must be an object")
        path = _safe_relative_path(item.get("path"))
        sha256 = item.get("sha256")
        if not isinstance(sha256, str) or not _SHA256_RE.match(sha256):
            raise PackManifestError(f"artifacts[{index}].sha256 must be 64 lowercase hex chars")
        size = item.get("size")
        if not isinstance(size, int) or size < 0:
            raise PackManifestError(f"artifacts[{index}].size must be a non-negative integer")
        source = item.get("source")
        if source is not None and not isinstance(source, str):
            raise PackManifestError(f"artifacts[{index}].source must be a string")
        artifacts.append(PackArtifact(path=path, sha256=sha256, size=size, source=source))

    requirements_raw = payload.get("requirements", [])
    if not isinstance(requirements_raw, list) or any(
        not isinstance(item, str) or not item.strip() for item in requirements_raw
    ):
        raise PackManifestError("requirements must be a list of non-empty strings")

    idle_unload_after = payload.get("idle_unload_after")
    if idle_unload_after is not None:
        if (
            isinstance(idle_unload_after, bool)
            or not isinstance(idle_unload_after, (int, float))
            or not math.isfinite(idle_unload_after)
            or idle_unload_after < 0
        ):
            raise PackManifestError("idle_unload_after must be a non-negative number of seconds")
        idle_unload_after = float(idle_unload_after)

    return PackManifest(
        id=pack_id,
        engine_id=engine_id,
        version=version,
        label=str(payload.get("label") or pack_id),
        description=str(payload.get("description") or ""),
        runtime=str(payload.get("runtime") or "python"),
        requirements=tuple(requirements_raw),
        artifacts=tuple(artifacts),
        revision=payload.get("revision") if isinstance(payload.get("revision"), str) else None,
        notes=payload.get("notes") if isinstance(payload.get("notes"), str) else None,
        provisioner=provisioner,
        idle_unload_after=idle_unload_after,
        manifest_sha256=manifest_sha256,
        raw=payload,
    )


def load_manifest(pack_dir: Path) -> PackManifest:
    manifest_path = pack_dir / MANIFEST_FILENAME
    try:
        raw_bytes = manifest_path.read_bytes()
    except OSError:
        raise PackManifestError(f"cannot read {MANIFEST_FILENAME}") from None
    try:
        payload = json.loads(raw_bytes)
    except ValueError as exc:
        raise PackManifestError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise PackManifestError("manifest must be a JSON object")
    return parse_manifest(payload, hashlib.sha256(raw_bytes).hexdigest())


@dataclass
class PackStatus:
    pack: PackManifest
    directory: Path
    errors: list[str] = field(default_factory=list)
    artifacts_present: int = 0
    artifacts_total: int = 0
    disk_bytes: int = 0
    verified: bool = False

    @property
    def status(self) -> str:
        if self.errors:
            return "invalid"
        if self.artifacts_present < self.artifacts_total:
            return "not-installed"
        if self.pack.provisioner and not self.verified:
            return "not-installed"
        return "verified" if self.verified else "installed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "artifacts_present": self.artifacts_present,
            "artifacts_total": self.artifacts_total,
            "disk_bytes": self.disk_bytes,
            "verified": self.verified,
            "errors": list(self.errors),
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verification_stamp(pack_dir: Path) -> dict[str, Any]:
    try:
        payload = json.loads((pack_dir / VERIFIED_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_verification_stamp(pack_dir: Path, manifest_sha256: str) -> None:
    payload = {"manifest_sha256": manifest_sha256, "verified_at": time.time()}
    try:
        (pack_dir / VERIFIED_FILENAME).write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        # A read-only pack is still usable; the next verify just re-hashes it.
        pass


def inspect_pack(pack_dir: Path, *, verify: bool = False) -> PackStatus:
    """Compute a pack's local status, optionally hashing every artifact."""
    try:
        manifest = load_manifest(pack_dir)
    except PackManifestError as exc:
        placeholder = PackManifest(
            id=pack_dir.name,
            engine_id=pack_dir.name,
            version="",
            label=pack_dir.name,
            description="",
            runtime="python",
            requirements=(),
            artifacts=(),
        )
        return PackStatus(
            pack=placeholder, directory=pack_dir, errors=[str(exc)], artifacts_total=0
        )

    status = PackStatus(
        pack=manifest,
        directory=pack_dir,
        artifacts_total=len(manifest.artifacts),
    )
    stamp = _verification_stamp(pack_dir)
    stamp_current = stamp.get("manifest_sha256") == manifest.manifest_sha256
    all_present = True
    hashes_ok = True
    for artifact in manifest.artifacts:
        artifact_path = pack_dir / artifact.path
        if not artifact_path.is_file():
            all_present = False
            hashes_ok = False
            continue
        status.artifacts_present += 1
        try:
            status.disk_bytes += artifact_path.stat().st_size
        except OSError:
            pass
        if verify:
            try:
                if _sha256_file(artifact_path) != artifact.sha256:
                    hashes_ok = False
                    status.errors.append(f"hash mismatch: {artifact.path}")
            except OSError:
                hashes_ok = False
                status.errors.append(f"cannot read {artifact.path}")

    if manifest.provisioner:
        # Only the provisioner publishes the stamp, after its steps succeed. Verify must never
        # mint one, or an empty pack directory would look installed.
        status.verified = all_present and not status.errors and stamp_current
        return status
    status.verified = (
        all_present
        and not status.errors
        and (hashes_ok if verify else stamp_current)
    )
    if verify and status.verified:
        _write_verification_stamp(pack_dir, manifest.manifest_sha256)
    return status


def find_pack_dir(engine_id: str, root: Path | None = None) -> Path | None:
    """Return the pack directory whose manifest claims ``engine_id``."""
    root = root or packs_root()
    if not root.is_dir():
        return None
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        try:
            manifest = load_manifest(entry)
        except PackManifestError:
            continue
        if manifest.engine_id == engine_id:
            return entry
    return None


def idle_unload_after(engine_id: str, root: Path | None = None) -> float | None:
    """The installed pack's ``idle_unload_after`` seconds, or None (no pack, or an older pack)."""
    directory = find_pack_dir(engine_id, root)
    if directory is None:
        return None
    try:
        return load_manifest(directory).idle_unload_after
    except PackManifestError:
        return None


def _download_artifact(url: str, dest: Path, artifact: PackArtifact, *, allow_file: bool) -> None:
    """Download with byte-range resume, then verify size and hash before publishing."""
    parsed = urlparse(url)
    scheme_ok = parsed.scheme in ("http", "https") or (parsed.scheme == "file" and allow_file)
    if not scheme_ok:
        raise PackInstallError(
            f"{artifact.path}: unsupported source scheme {parsed.scheme!r}"
        )

    part = dest.with_name(dest.name + ".part")
    offset = part.stat().st_size if part.is_file() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=60) as response:
            status = getattr(response, "status", 200)
            if offset and status != 206:
                offset = 0
                part.unlink(missing_ok=True)
            written = offset
            with part.open("ab" if offset else "wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    written += len(chunk)
    except (OSError, ValueError) as exc:
        raise PackInstallError(f"{artifact.path}: download failed: {exc}") from exc

    if written != artifact.size:
        part.unlink(missing_ok=True)
        raise PackInstallError(
            f"{artifact.path}: expected {artifact.size} bytes, received {written}"
        )
    if _sha256_file(part) != artifact.sha256:
        part.unlink(missing_ok=True)
        raise PackInstallError(f"{artifact.path}: hash mismatch after download")
    os.replace(part, dest)


def install_pack(
    engine_id: str, root: Path | None = None, *, allow_file: bool | None = None
) -> PackStatus:
    """Fetch a pack's artifacts, verify them, and publish the verified stamp.

    The manifest must already exist in the pack directory (packs ship metadata separately from
    their bytes). Downloads resume from ``.part`` files; failures leave the partial file for a
    later retry and never publish an unverified artifact.
    """
    root = root or packs_root()
    pack_dir = find_pack_dir(engine_id, root)
    if pack_dir is None:
        raise PackInstallError(f"no pack manifest for engine {engine_id!r}")
    manifest = load_manifest(pack_dir)
    if allow_file is None:
        allow_file = os.environ.get("ENGINE_PACKS_ALLOW_FILE_SOURCES") == "1"

    missing_bytes = 0
    for artifact in manifest.artifacts:
        dest = pack_dir / artifact.path
        if dest.is_file() and dest.stat().st_size == artifact.size:
            continue
        missing_bytes += artifact.size
    free_bytes = shutil.disk_usage(root).free
    if missing_bytes > free_bytes:
        raise PackInstallError(
            f"not enough free disk: need {missing_bytes} bytes, {free_bytes} available"
        )

    lock_path = pack_dir / ".install.lock"
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise PackInstallError("an install is already running for this pack") from exc
    os.close(lock_fd)
    try:
        for artifact in manifest.artifacts:
            dest = pack_dir / artifact.path
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_file():
                try:
                    if _sha256_file(dest) == artifact.sha256:
                        continue
                except OSError:
                    pass
                dest.unlink(missing_ok=True)
            if not artifact.source:
                raise PackInstallError(f"{artifact.path}: manifest has no source URL")
            _download_artifact(artifact.source, dest, artifact, allow_file=allow_file)
        status = inspect_pack(pack_dir, verify=True)
        if not status.verified:
            detail = "; ".join(status.errors) or "unknown verification failure"
            raise PackInstallError(f"verification failed: {detail}")
        return status
    finally:
        lock_path.unlink(missing_ok=True)


def remove_pack(engine_id: str, root: Path | None = None) -> bool:
    """Delete a pack directory. Built-in engines are not removable."""
    root = root or packs_root()
    pack_dir = find_pack_dir(engine_id, root)
    if pack_dir is None:
        return False
    try:
        shutil.rmtree(pack_dir)
    except OSError as exc:
        raise PackInstallError(f"could not remove pack: {exc}") from exc
    return True


def discover_packs(root: Path | None = None) -> list[PackStatus]:
    root = root or packs_root()
    if not root.is_dir():
        return []
    packs: list[PackStatus] = []
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and (entry / MANIFEST_FILENAME).is_file():
            packs.append(inspect_pack(entry))
    return packs


def _engine_card(engine: speech_engines.EngineInfo, backend: str | None) -> dict[str, Any]:
    active = speech_engines.engine_for_backend(backend)
    return {
        "id": engine.id,
        "label": engine.label,
        "description": engine.description,
        "kind": "pack" if engine.pack_only else "builtin",
        "version": None,
        "runtime": engine.runtime,
        "source": engine.source,
        "license": engine.license,
        "active": active is not None and engine.id == active.id,
        "capabilities": engine.capabilities.as_dict(),
        "state": {
            "status": "not-installed" if engine.pack_only else "built-in",
            "artifacts_present": 0,
            "artifacts_total": 0,
            "disk_bytes": 0,
            "verified": not engine.pack_only,
            "errors": [],
        },
        "requirements": [],
        "pack": None,
    }


def engine_cards(backend: str | None, root: Path | None = None) -> list[dict[str, Any]]:
    """Built-in engines plus installed packs, one card per engine."""
    cards: dict[str, dict[str, Any]] = {
        engine.id: _engine_card(engine, backend)
        for engine in speech_engines.list_engines()
    }
    install_checks: dict[str, dict[str, Any] | None] = {}
    for pack_status in discover_packs(root):
        install_checks[pack_status.pack.engine_id] = install_check.read_record(pack_status.directory)
        card = cards.get(pack_status.pack.engine_id)
        if card is None:
            card = {
                "id": pack_status.pack.engine_id,
                "label": pack_status.pack.label,
                "description": pack_status.pack.description,
                "kind": "pack",
                "version": pack_status.pack.version,
                "runtime": pack_status.pack.runtime,
                "source": None,
                "license": None,
                "active": False,
                "capabilities": {},
                "state": pack_status.as_dict(),
                "requirements": list(pack_status.pack.requirements),
                "pack": pack_status.pack.as_dict(),
            }
            cards[pack_status.pack.engine_id] = card
        else:
            card["kind"] = "builtin+pack"
            card["version"] = pack_status.pack.version
            card["state"] = pack_status.as_dict()
            card["requirements"] = list(pack_status.pack.requirements)
            card["pack"] = pack_status.pack.as_dict()
    from persona_forge import provisioned_engines

    for provisioned in provisioned_engines.all_engines():
        card = cards.get(provisioned.engine_id)
        if card is None:
            continue
        adapter = speech_engines.get_managed_adapter(provisioned.engine_id)
        card["install_job"] = provisioned.pack.job_status()
        card["load_status"] = adapter.status() if adapter is not None else {}
    from persona_forge import hardware_fit

    facts = hardware_fit.machine_facts()
    saved = hardware_fit.load()
    for engine_id, card in cards.items():
        card["hardware_fit"] = hardware_fit.fit_for(engine_id, facts)
        card["benchmark"] = saved.get(engine_id)
        card["install_check"] = install_checks.get(engine_id)
    return list(cards.values())


def verify_engine(engine_id: str, backend: str | None, root: Path | None = None) -> dict[str, Any] | None:
    """Re-verify one engine card; built-ins are always verified."""
    cards = engine_cards(backend, root)
    card = next((item for item in cards if item["id"] == engine_id), None)
    if card is None:
        return None
    if card["kind"] == "builtin":
        return card
    root = root or packs_root()
    for entry in sorted(root.iterdir()) if root.is_dir() else []:
        if not entry.is_dir():
            continue
        try:
            manifest = load_manifest(entry)
        except PackManifestError:
            continue
        if manifest.engine_id == engine_id:
            refreshed = inspect_pack(entry, verify=True)
            card = dict(card)
            card["state"] = refreshed.as_dict()
            card["version"] = refreshed.pack.version
            card["pack"] = refreshed.pack.as_dict()
            return card
    return card

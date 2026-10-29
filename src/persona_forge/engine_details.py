"""The "Details" payload behind an engine card: what is pinned, what is installed, how it runs.

Everything here is read from the machine: the pack manifest, the pack's own virtualenv, the
Hugging Face cache inside the pack folder, the install speed check, the adapter's load status and
the bounded logs. Nothing is assumed from the manifest alone. A fact that cannot be read is null,
never guessed.

No token ever appears in this payload: the token has its own status route that returns only
``set``, and log lines are redacted when they are stored (``pack_logs``).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable

from persona_forge import engine_packs, hf_access, pack_logs, provisioned_engines

_PIN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)(?:\[[^\]]*\])?\s*==\s*([^\s;]+)")


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name).lower()


def _site_packages(directory: Path) -> list[Path]:
    venv = directory / "venv"
    found = list(venv.glob("lib/python*/site-packages")) + list(venv.glob("Lib/site-packages"))
    return [path for path in found if path.is_dir()]


def installed_version(directory: Path, name: str) -> str | None:
    """The version of ``name`` installed in the pack's own virtualenv (from its ``.dist-info``)."""
    wanted = normalise(name)
    for site in _site_packages(directory):
        try:
            entries = os.listdir(site)
        except OSError:
            continue
        for entry in entries:
            if not entry.endswith(".dist-info"):
                continue
            stem = entry[: -len(".dist-info")]
            dist, _, version = stem.rpartition("-")
            if dist and normalise(dist) == wanted:
                return version
    return None


def _app_version(name: str) -> str | None:
    from importlib import metadata

    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def package_pins(directory: Path, requirements: tuple[str, ...] | list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Split manifest requirements into ``name==version`` pins and free-text pins (a checkpoint)."""
    has_venv = (directory / "venv").is_dir()
    packages: list[dict[str, Any]] = []
    other: list[str] = []
    for requirement in requirements:
        match = _PIN.match(requirement)
        if match is None:
            other.append(requirement)
            continue
        name, pinned = match.group(1), match.group(2)
        installed = installed_version(directory, name) if has_venv else _app_version(name)
        packages.append(
            {
                "name": name,
                "pinned": pinned,
                "installed": installed,
                "where": "pack environment" if has_venv else "application environment",
            }
        )
    return packages, other


def _blob_bytes(model_dir: Path) -> int:
    blobs = model_dir / "blobs"
    total = 0
    try:
        for entry in os.scandir(blobs):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat(follow_symlinks=False).st_size
    except OSError:
        pass
    return total


def huggingface_weights(directory: Path) -> list[dict[str, Any]]:
    """Models in the pack's private Hugging Face cache: repo, commit revision(s), size on disk."""
    weights: list[dict[str, Any]] = []
    for cache in (directory / "hf", directory / "hf" / "hub"):
        if not cache.is_dir():
            continue
        for model_dir in sorted(cache.glob("models--*")):
            if not model_dir.is_dir():
                continue
            repo = model_dir.name[len("models--") :].replace("--", "/")
            revisions: list[str] = []
            refs = model_dir / "refs"
            if refs.is_dir():
                for ref in sorted(refs.iterdir()):
                    try:
                        value = ref.read_text(encoding="utf-8").strip()
                    except OSError:
                        continue
                    if value:
                        revisions.append(value)
            if not revisions:
                snapshots = model_dir / "snapshots"
                if snapshots.is_dir():
                    revisions = sorted(entry.name for entry in snapshots.iterdir() if entry.is_dir())
            weights.append(
                {
                    "kind": "huggingface",
                    "name": repo,
                    "revision": revisions[0] if revisions else None,
                    "size_bytes": _blob_bytes(model_dir),
                    "sha256": None,
                    "present": True,
                }
            )
    return weights


def directory_bytes(directory: Path) -> int:
    """Disk used by a pack folder, not following links (a cache's symlinks would double count)."""
    total = 0
    stack = [str(directory)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def weights_report(directory: Path, pack_module: Any | None) -> list[dict[str, Any]]:
    """Weights the pack pins itself (``weight_pins``) plus whatever sits in its Hugging Face cache."""
    weights: list[dict[str, Any]] = []
    hook: Callable[[Path], list[dict[str, Any]]] | None = getattr(pack_module, "weight_pins", None)
    if callable(hook):
        weights.extend(hook(directory))
    weights.extend(huggingface_weights(directory))
    return weights


def build(engine_id: str, backend: str | None, root: Path | None = None) -> dict[str, Any] | None:
    """Details for one pack engine, or None when the id is unknown or has no pack (built-ins)."""
    cards = engine_packs.engine_cards(backend, root)
    card = next((item for item in cards if item["id"] == engine_id), None)
    if card is None or card["kind"] == "builtin":
        return None
    provisioned = provisioned_engines.get(engine_id)
    pack_module = provisioned.pack if provisioned is not None else None
    directory = engine_packs.find_pack_dir(engine_id, root)
    manifest = card.get("pack") or {}
    load_status = card.get("load_status") or {}
    check = card.get("install_check")

    packages: list[dict[str, Any]] = []
    other_pins: list[str] = []
    weights: list[dict[str, Any]] = []
    disk_bytes: int | None = None
    if directory is not None:
        packages, other_pins = package_pins(directory, tuple(card.get("requirements") or ()))
        weights = weights_report(directory, pack_module)
        disk_bytes = directory_bytes(directory)

    gate = getattr(pack_module, "HF_GATE", None)
    return {
        "id": engine_id,
        "label": card["label"],
        "installed": directory is not None and card["state"]["status"] in ("verified", "installed"),
        "engine": {
            "pack_id": manifest.get("id"),
            "pack_version": manifest.get("version"),
            "revision": manifest.get("revision"),
            "provisioner": manifest.get("provisioner"),
            "manifest_sha256": manifest.get("manifest_sha256") or None,
            "source": card.get("source"),
            "license": card.get("license"),
        },
        "packages": packages,
        "other_pins": other_pins,
        "weights": weights,
        "artifacts": manifest.get("artifacts") or [],
        "runtime": {
            "variant": manifest.get("runtime") or card.get("runtime"),
            "device": (check or {}).get("device"),
            "mode": load_status.get("mode") or (check or {}).get("mode"),
            "load_state": load_status.get("state"),
            "hardware_fit": card.get("hardware_fit"),
        },
        "install_check": check,
        "idle_unload": {
            "seconds": load_status.get("idle_unload_after"),
            "source": load_status.get("idle_unload_source"),
            "manifest_seconds": manifest.get("idle_unload_after"),
        },
        "disk_bytes": disk_bytes,
        "install_job": card.get("install_job"),
        "hf_gate": (
            {**gate, "token": hf_access.status()} if isinstance(gate, dict) else None
        ),
        "logs": pack_logs.read(engine_id, directory),
    }

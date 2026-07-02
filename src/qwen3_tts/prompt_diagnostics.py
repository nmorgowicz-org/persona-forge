"""Opt-in diagnostics for comparing voice-clone prompt construction."""

from __future__ import annotations

import hashlib
import json
import os
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np


def reference_codes(prompt: Any) -> Any | None:
    """Return the first reference-code tensor from supported qwen-tts prompt shapes."""
    if isinstance(prompt, list) and prompt:
        return getattr(prompt[0], "ref_code", None)
    if isinstance(prompt, dict):
        values = prompt.get("ref_code")
        if values is not None and len(values):
            return values[0]
    return None


def _version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def dump_reference_prompt(prompt: Any, output_dir: str | os.PathLike[str]) -> Path:
    """Save reference codes and comparison metadata without recording audio or text."""
    codes = reference_codes(prompt)
    if codes is None:
        raise RuntimeError("voice clone prompt does not contain ref_code")

    if hasattr(codes, "detach"):
        codes = codes.detach()
    if hasattr(codes, "cpu"):
        codes = codes.cpu()
    array = np.asarray(codes)

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    codes_path = destination / "ref_code.npy"
    np.save(codes_path, array, allow_pickle=False)

    raw = array.tobytes(order="C")
    manifest = {
        "artifact": codes_path.name,
        "dtype": str(array.dtype),
        "shape": list(array.shape),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "versions": {
            "qwen-tts": _version("qwen-tts"),
            "torch": _version("torch"),
            "transformers": _version("transformers"),
        },
    }
    manifest_path = destination / "ref_code.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def dump_talker_parameter_manifest(talker: Any, output_dir: str | os.PathLike[str]) -> Path:
    """Fingerprint conditioning-related talker parameters without storing weights."""
    import torch

    selected = {}
    markers = ("embed", "projection", "codec_head")
    for name, parameter in talker.named_parameters():
        if not any(marker in name for marker in markers):
            continue
        tensor = parameter.detach().cpu().contiguous()
        raw = tensor.view(torch.uint8).numpy().tobytes()
        selected[name] = {
            "dtype": str(tensor.dtype),
            "shape": list(tensor.shape),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / "talker_parameters.json"
    manifest_path.write_text(json.dumps(selected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path

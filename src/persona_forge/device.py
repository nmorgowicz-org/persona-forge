"""Runtime device auto-detection (Phase A4, D9 axis a).

One helper resolves which physical device a torch-backed model should load onto — auto-detected
(``cuda`` > ``xpu`` > ``mps`` > ``cpu``) by default, or forced via ``TTS_DEVICE`` (falling back to
the legacy ``DEVICE`` var for compat). A forced-but-unavailable device logs a warning and falls back
to ``cpu`` rather than failing silently.
"""

from __future__ import annotations

import os
import warnings
from collections.abc import MutableMapping

_VALID_DEVICES = ("cuda", "xpu", "mps", "cpu")


def _cuda_available() -> bool:
    try:
        import torch
    except ImportError:
        return False

    return bool(torch.cuda.is_available())


def _xpu_available() -> bool:
    try:
        import torch
    except ImportError:
        return False

    return bool(getattr(torch, "xpu", None) is not None and torch.xpu.is_available())


def _mps_available() -> bool:
    try:
        import torch
    except ImportError:
        return False

    return bool(torch.backends.mps.is_available())


def auto_detect_device() -> str:
    """Return the best available device: ``cuda`` > ``xpu`` > ``mps`` > ``cpu``."""
    if _cuda_available():
        return "cuda"
    if _xpu_available():
        return "xpu"
    if _mps_available():
        return "mps"
    return "cpu"


def resolve_device(environ: MutableMapping[str, str] = os.environ) -> str:
    """Resolve the torch device to load onto.

    An explicit ``TTS_DEVICE`` (or legacy ``DEVICE``) wins; otherwise auto-detect the best
    available device. A forced device that isn't actually available falls back to ``cpu`` with a
    warning — never a silent, unexplained downgrade.
    """
    forced = (environ.get("TTS_DEVICE") or environ.get("DEVICE") or "").strip().lower()
    if not forced:
        return auto_detect_device()

    if forced not in _VALID_DEVICES:
        warnings.warn(
            f"Unrecognized TTS_DEVICE={forced!r}; falling back to auto-detect.",
            stacklevel=2,
        )
        return auto_detect_device()

    available = {
        "cuda": _cuda_available,
        "xpu": _xpu_available,
        "mps": _mps_available,
        "cpu": lambda: True,
    }[forced]()
    if not available:
        warnings.warn(
            f"TTS_DEVICE={forced!r} requested but not available on this host; falling back to cpu.",
            stacklevel=2,
        )
        return "cpu"
    return forced


def xpu_needs_fp64_emulation() -> bool:
    """True if the current xpu device lacks native fp64 (Phase A6a, A6.2).

    All Xe-LP iGPUs need NEO's fp64 software emulation for torch's dtype-cast kernels to build;
    Arc discretes have native fp64 and don't. Import-safe / False on any non-xpu host.
    """
    if not _xpu_available():
        return False
    import torch

    return not bool(torch.xpu.get_device_properties(0).has_fp64)


def apply_fp64_emulation_env(environ: MutableMapping[str, str] = os.environ) -> None:
    """Set the three NEO debug keys that enable fp64 software emulation (Phase A6a, A6.2).

    Must run before any xpu context/alloc (i.e. before a model's ``from_pretrained``/``.to("xpu")``).
    ``OverrideDefaultFP64Settings`` is a NEO debug key NEO ignores unless ``NEOReadDebugKeys`` is also
    set — both are required together. Uses ``setdefault`` so an explicitly-set var is never clobbered.
    """
    environ.setdefault("NEOReadDebugKeys", "1")
    environ.setdefault("OverrideDefaultFP64Settings", "1")
    environ.setdefault("IGC_EnableDPEmulation", "1")

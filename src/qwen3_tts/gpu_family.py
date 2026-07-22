"""GPU-family detection (Phase A6c, D9/D11 install axis).

Family (which torch wheel to install: ``cpu``/``cuda``/``rocm``/``intel-xpu``) is distinct from
device (the runtime target resolved by ``device.py::resolve_device``, Phase A4). Selection here is
torch-independent (A6.4a "chicken-and-egg": inside a CPU-base image, ``torch.<accel>.is_available()``
is always False even with a GPU passed through, because the CPU wheel has no accel support compiled
in — so family selection must never depend on it). All probes are pure filesystem reads and are
import-safe on any platform.
"""

from __future__ import annotations

import glob
import os
import warnings
from collections.abc import MutableMapping
from typing import Callable, NamedTuple

_VALID_FAMILIES = ("cpu", "cuda", "rocm", "intel-xpu")

# PCI vendor IDs as they appear in /sys/bus/pci/devices/*/vendor (lowercase hex, "0x" prefix).
_PCI_VENDOR_NVIDIA = "0x10de"
_PCI_VENDOR_AMD = "0x1002"
_PCI_VENDOR_INTEL = "0x8086"


def _glob_any(pattern: str) -> bool:
    return bool(glob.glob(pattern))


def _pci_vendor_present(vendor_id: str) -> bool:
    try:
        for vendor_path in glob.glob("/sys/bus/pci/devices/*/vendor"):
            with open(vendor_path) as f:
                if f.read().strip().lower() == vendor_id:
                    return True
    except OSError:
        pass
    return False


def cuda_device_node_present() -> bool:
    return _glob_any("/dev/nvidia*")


def nvidia_pci_present() -> bool:
    return _pci_vendor_present(_PCI_VENDOR_NVIDIA)


def rocm_device_node_present() -> bool:
    # /dev/kfd is ROCm's own kernel interface — unlike /dev/dri/renderD*, it is AMD-exclusive.
    return _glob_any("/dev/kfd")


def amd_pci_present() -> bool:
    return _pci_vendor_present(_PCI_VENDOR_AMD)


def intel_xpu_device_node_present() -> bool:
    return _glob_any("/dev/dri/renderD*")


def intel_pci_present() -> bool:
    return _pci_vendor_present(_PCI_VENDOR_INTEL)


class Probes(NamedTuple):
    """Injectable presence/capability probes — unit-testable without hardware."""

    cuda_device_node: Callable[[], bool]
    nvidia_pci: Callable[[], bool]
    rocm_device_node: Callable[[], bool]
    amd_pci: Callable[[], bool]
    intel_device_node: Callable[[], bool]
    intel_pci: Callable[[], bool]


def default_probes() -> Probes:
    return Probes(
        cuda_device_node=cuda_device_node_present,
        nvidia_pci=nvidia_pci_present,
        rocm_device_node=rocm_device_node_present,
        amd_pci=amd_pci_present,
        intel_device_node=intel_xpu_device_node_present,
        intel_pci=intel_pci_present,
    )


def _detect_best(probes: Probes) -> tuple[str, bool, bool]:
    """Return (family, present, capable) for the highest-priority vendor whose PCI device is seen.

    ``present`` = the vendor's PCI device is visible in sysfs (survives without device-node mapping).
    ``capable`` = the matching device node is *also* present (i.e. actually usable right now). This
    is the exact present/capable split the A7c coach needs.
    """
    if probes.nvidia_pci():
        return "cuda", True, probes.cuda_device_node()
    if probes.amd_pci():
        return "rocm", True, probes.rocm_device_node()
    if probes.intel_pci():
        return "intel-xpu", True, probes.intel_device_node()
    return "cpu", False, False


def resolve_gpu_family(
    environ: MutableMapping[str, str] = os.environ,
    probes: Probes | None = None,
) -> str:
    """Resolve which torch wheel family to install: ``cpu``/``cuda``/``rocm``/``intel-xpu``.

    An explicit ``GPU_FAMILY`` (any value other than ``auto``) always wins, regardless of probes —
    including ``GPU_FAMILY=cpu``. ``auto`` (the default) picks the highest-priority vendor
    (``cuda`` > ``rocm`` > ``intel-xpu``) whose device node is actually present (capable), never a
    PCI-only presence match — that stays ``cpu`` until the hardware is actually mapped in.
    """
    probes = probes or default_probes()
    forced = (environ.get("GPU_FAMILY") or "auto").strip().lower()

    if forced == "auto":
        family, _present, capable = _detect_best(probes)
        return family if capable else "cpu"

    if forced not in _VALID_FAMILIES:
        warnings.warn(
            f"Unrecognized GPU_FAMILY={forced!r}; falling back to auto-detect.",
            stacklevel=2,
        )
        family, _present, capable = _detect_best(probes)
        return family if capable else "cpu"

    return forced


def describe_accelerator(
    environ: MutableMapping[str, str] = os.environ,
    probes: Probes | None = None,
) -> dict[str, object]:
    """Return ``{family, detected_family, device, has_fp64, emu_active, present, capable}`` for
    health/the A7 panel.

    ``present``/``capable``/``detected_family`` reflect the *actual detected* hardware
    (independent of any ``GPU_FAMILY`` override) — this is what drives the A7c coach ("you have
    the hardware, map it"). ``family`` is the *resolved* family (override-aware) used for the
    torch wheel; it can differ from ``detected_family`` when an override is forced or the detected
    vendor isn't capable yet (auto falls back to ``cpu``).
    """
    from qwen3_tts.device import resolve_device, xpu_needs_fp64_emulation

    probes = probes or default_probes()
    family = resolve_gpu_family(environ, probes)
    detected_family, present, capable = _detect_best(probes)
    device = resolve_device(environ)

    has_fp64: bool | None = None
    emu_active = False
    if device == "xpu":
        needs_emu = xpu_needs_fp64_emulation()
        has_fp64 = not needs_emu
        emu_active = needs_emu and environ.get("NEOReadDebugKeys") == "1"

    return {
        "family": family,
        "detected_family": detected_family,
        "device": device,
        "has_fp64": has_fp64,
        "emu_active": emu_active,
        "present": present,
        "capable": capable,
    }

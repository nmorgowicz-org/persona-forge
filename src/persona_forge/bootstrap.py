"""Native process bootstrap: env defaults applied before heavyweight imports.

docs/plans/20260829-no_more_docker_architecture.md §5. Every setting here uses ``setdefault``
so an explicit operator value always wins — this mirrors ``scripts/entrypoint.sh``'s
LOW_RAM_MODE/NEO tuning for native (non-Docker) runs, so the two surfaces agree on every
default. ``apply_env_defaults`` must run before importing Torch/OpenVINO, creating an XPU
context, or importing ``persona_forge.model`` — the CLI's ``serve``/``setup`` commands call it
first, before any of those happen.
"""

from __future__ import annotations

import sys
from pathlib import Path

from persona_forge import paths
from persona_forge.config import DEFAULT_TTS_BACKEND
from persona_forge.gpu_family import resolve_gpu_family
from persona_forge.paths import Environ


def apply_env_defaults(environ: Environ, *, platform: str = sys.platform) -> None:
    """Populate low-level runtime env vars with ``setdefault`` only; never overwrite.

    Portable across every OS: the product default backend and (when ``LOW_RAM_MODE=1``) the
    idle-unload timer. Linux-only: glibc malloc tuning — never ``LD_PRELOAD``, which conflicts
    with OpenVINO's native allocator under transformers 5.x (see ``scripts/entrypoint.sh``).
    Intel NEO fp64-emulation variables are set only when the resolved accelerator family is
    ``intel-xpu``, and only via ``setdefault`` so an operator override always wins.
    """
    environ.setdefault("TTS_BACKEND", DEFAULT_TTS_BACKEND)

    if environ.get("LOW_RAM_MODE", "").strip() == "1":
        environ.setdefault("IDLE_UNLOAD_SECONDS", "1800")
        if platform.startswith("linux"):
            environ.setdefault("MALLOC_MMAP_THRESHOLD_", "65536")
            environ.setdefault("MALLOC_ARENA_MAX", "1")

    if resolve_gpu_family(environ) == "intel-xpu":
        environ.setdefault("NEOReadDebugKeys", "1")
        environ.setdefault("OverrideDefaultFP64Settings", "1")
        environ.setdefault("IGC_EnableDPEmulation", "1")
        environ.setdefault("OPENVINO_DEVICE", "GPU")


def prepare_writable_state(environ: Environ) -> list[Path]:
    """Create every app-data directory ``setup``/``serve`` need. ``doctor`` never calls this."""
    return paths.ensure_writable_dirs(environ)

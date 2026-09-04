"""Single source of truth for native accelerator wheel selection (Phase 4).

docs/plans/20260829-no_more_docker_architecture.md §7 locks these exact pins after a live check
against download.pytorch.org's real cp313 wheel index (2026-08-29; re-verified 2026-09-03 — see
scripts/verify_torch_wheel_matrix.py for a live re-check). Both ``pyproject.toml``'s static
``[project.optional-dependencies]``/``[tool.uv.sources]``/``[[tool.uv.index]]`` entries (native
``uv sync --extra <name>`` installs) and ``scripts/entrypoint.sh``'s first-boot installer
(container installs) read their defaults from here, so a version or index change is made once.

``rocm`` and ``xpu`` cannot share the base project's ``torch==2.14.0`` pin: the rocm6.4 index has
no 2.14.0 cp313 wheel at all, and 2.14.0+xpu declares ``triton-xpu~=3.8.0`` while the xpu index's
newest cp313 triton-xpu build is 3.7.2 — both live-verified against the wheels' own METADATA, not
just their filename listings. Each pins the newest version its index can actually satisfy end to
end. This is a real, intentional per-extra version divergence, not index-only routing;
``pyproject.toml`` expresses it via a loose range in ``dependencies`` (wide enough to admit every
extra's pin) narrowed by an exact pin in each extra, not via self-referential ``extra`` markers on
the base dependency (untested, implementation-defined pip/uv behavior — not worth the risk here).

Known uv limitation: ``rocm``/``xpu``'s optional-dependency entries carry a ``sys_platform``
marker — required so ``uv lock``'s universal resolution (one lockfile valid across every
``[tool.uv] environments`` platform) can find a solution at all, since neither has a wheel for
every declared platform. That marker also means ``uv sync --extra rocm`` on an unsupported
platform (e.g. macOS) does not hard-fail: the marker makes the extra's pin inapplicable there, so
resolution quietly falls back to the base ``torch`` range instead of erroring. There is no uv
mechanism that hard-fails an out-of-platform extra without breaking universal locking, so this is
a documented soft spot, not a resolver guarantee — ``persona-forge doctor`` and
``scripts/verify_torch_wheel_matrix.py`` are the actual detection points, and platform validity is
covered by ``ACCELERATOR_PINS[...].platforms`` for callers that want to check before syncing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_TORCH_VERSION = "2.14.0"
DEFAULT_TORCHAUDIO_VERSION = "2.11.0"


@dataclass(frozen=True)
class AcceleratorPin:
    """One native accelerator's uv-extra/index/version selection.

    ``extra`` is the ``[project.optional-dependencies]`` key (``uv sync --extra <extra>``).
    ``gpu_family`` is the corresponding ``persona_forge.gpu_family`` family value — several
    extras can share one family (``cuda12``/``cuda13`` both map to ``cuda``; the container's
    entrypoint only ever resolves a family, not a uv extra, since it doesn't run ``uv sync``).
    ``platforms`` lists the ``sys_platform`` values this extra is ever valid on.
    """

    extra: str
    gpu_family: str
    index_name: str
    index_url: str
    torch_version: str
    torchaudio_version: str
    platforms: tuple[str, ...]
    # Extra same-index packages a family needs pinned alongside torch/torchaudio (package name ->
    # exact version), e.g. xpu's triton-xpu. Empty for families with no such extra pin.
    extra_pins: dict[str, str] = field(default_factory=dict)


ACCELERATOR_PINS: dict[str, AcceleratorPin] = {
    "cuda12": AcceleratorPin(
        extra="cuda12",
        gpu_family="cuda",
        index_name="pytorch-cu126",
        index_url="https://download.pytorch.org/whl/cu126",
        torch_version=DEFAULT_TORCH_VERSION,
        torchaudio_version=DEFAULT_TORCHAUDIO_VERSION,
        platforms=("linux", "win32"),
    ),
    "cuda13": AcceleratorPin(
        extra="cuda13",
        gpu_family="cuda",
        index_name="pytorch-cu130",
        index_url="https://download.pytorch.org/whl/cu130",
        torch_version=DEFAULT_TORCH_VERSION,
        torchaudio_version=DEFAULT_TORCHAUDIO_VERSION,
        platforms=("linux", "win32"),
    ),
    "xpu": AcceleratorPin(
        extra="xpu",
        gpu_family="intel-xpu",
        index_name="pytorch-xpu",
        index_url="https://download.pytorch.org/whl/xpu",
        # torch==2.14.0+xpu requires triton-xpu~=3.8.0 (live-verified via the wheel's own
        # METADATA), and no triton-xpu cp313 wheel above 3.7.2 is published on this index —
        # 2.14.0 is not installable on xpu at all right now. 2.13.0+xpu pins triton-xpu==3.7.2,
        # which the index does carry, so xpu tracks that older torch pending a 3.8.x build.
        torch_version="2.13.0",
        torchaudio_version=DEFAULT_TORCHAUDIO_VERSION,
        platforms=("linux", "win32"),
        extra_pins={"triton-xpu": "3.7.2"},
    ),
    "rocm": AcceleratorPin(
        extra="rocm",
        gpu_family="rocm",
        index_name="pytorch-rocm64",
        index_url="https://download.pytorch.org/whl/rocm6.4",
        # rocm6.4 has no 2.14.0 cp313 wheel; 2.9.1 is the newest cp313 build that index carries
        # (live-verified) — see the module docstring.
        torch_version="2.9.1",
        torchaudio_version="2.9.1",
        platforms=("linux",),
        extra_pins={"pytorch-triton-rocm": "3.5.1"},
    ),
}

# cu129/cu132 are reachable only via the ACCEL_TORCH_INDEX_URL/ACCEL_TORCH_VERSION escape
# hatches (entrypoint.sh) or a manual --index-url override, never as first-class extras: cu129
# has no cp313 torch==2.14.0 wheel (would silently diverge from the base pin) and cu132 is not
# yet a distinct CUDA generation persona-forge targets.


def pin_for_family(gpu_family: str) -> AcceleratorPin | None:
    """Return the first pin whose ``gpu_family`` matches, or ``None`` for ``cpu``/unknown."""
    for pin in ACCELERATOR_PINS.values():
        if pin.gpu_family == gpu_family:
            return pin
    return None

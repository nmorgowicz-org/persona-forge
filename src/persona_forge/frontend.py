"""Frontend UI resolution shared by ``app.py`` and ``cli.py``.

Precedence (docs/plans/20260829-no_more_docker_architecture.md §6):
``FRONTEND_DIST_DIR`` override > checkout ``frontend/dist`` > package-local built UI > API-only.

When a standard wheel build leaves its ignored package-local staging directory in a source
checkout, the checkout tier deliberately wins. This keeps local ``build-ui`` output authoritative
without affecting an installed wheel, which has no adjacent checkout ``frontend/dist``.
Pure: no I/O beyond the ``.is_dir()``/``.is_file()`` checks needed to decide precedence — callers
still check the returned path's own presence to decide UI vs. API-only mode.
"""

from __future__ import annotations

import os
from pathlib import Path

from persona_forge.paths import Environ

# This module's own directory works identically for a source checkout (src/persona_forge) and
# an installed wheel (site-packages/persona_forge) — the package-local UI, when present, always
# lives at <package dir>/static.
PACKAGE_DIR = Path(__file__).resolve().parent
PACKAGE_STATIC_DIR = PACKAGE_DIR / "static"
CHECKOUT_DIST_DIR = PACKAGE_DIR.parent.parent / "frontend" / "dist"


def frontend_enabled(environ: Environ = os.environ) -> bool:
    return environ.get("FRONTEND_ENABLED", "1").strip().lower() not in ("0", "false")


def resolve_frontend_dir(
    environ: Environ = os.environ,
    *,
    package_static_dir: Path | None = None,
    checkout_dist_dir: Path | None = None,
) -> Path:
    """Return the highest-precedence UI directory. Callers check ``.is_dir()`` for enablement.

    An explicit ``FRONTEND_DIST_DIR`` override is returned as-is, even if it does not exist —
    it is the operator's explicit choice, not a hint to keep searching.
    """
    override = environ.get("FRONTEND_DIST_DIR", "").strip()
    if override:
        return Path(override)
    checkout_dist_dir = checkout_dist_dir if checkout_dist_dir is not None else CHECKOUT_DIST_DIR
    if (checkout_dist_dir / "index.html").is_file():
        return checkout_dist_dir
    package_static_dir = package_static_dir if package_static_dir is not None else PACKAGE_STATIC_DIR
    if (package_static_dir / "index.html").is_file():
        return package_static_dir
    return checkout_dist_dir

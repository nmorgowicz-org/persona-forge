"""Hatch build hook: bake the built Studio UI into the wheel (Phase 3).

docs/plans/20260829-no_more_docker_architecture.md §5a/§6. Runs only for a *standard*
(non-editable) wheel build — `version == "editable"` is what `uv sync`/`pip install -e .` use
for local dev, and must never require Node/npm just to sync dependencies; the checkout tier of
`persona_forge.frontend.resolve_frontend_dir` already serves an editable install's UI straight
out of `frontend/dist` once a developer runs `persona-forge build-ui` themselves. A sdist build
also skips this — sources and the lockfile are enough there, per Hatchling's default
VCS-respecting sdist inclusion.

A standard wheel build always builds fresh (no stamp-skip here — that convenience lives only in
`persona_forge.cli`'s `build-ui`/`setup`) and fails loudly rather than shipping a UI-less wheel.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

_ROOT = Path(__file__).resolve().parent
_FRONTEND_DIR = _ROOT / "frontend"
_FRONTEND_DIST_DIR = _FRONTEND_DIR / "dist"
_PACKAGE_STATIC_DIR = _ROOT / "src" / "persona_forge" / "static"


class FrontendBuildHook(BuildHookInterface):
    PLUGIN_NAME = "frontend"

    def initialize(self, version: str, build_data: dict) -> None:
        if self.target_name != "wheel" or version != "standard":
            return
        npm = "npm.cmd" if os.name == "nt" else "npm"
        for step in (
            [npm, "ci"],
            [npm, "run", "check"],
            [npm, "run", "build"],
        ):
            subprocess.run(step, cwd=_FRONTEND_DIR, check=True)
        if not (_FRONTEND_DIST_DIR / "index.html").is_file():
            raise RuntimeError(
                f"frontend build did not produce {_FRONTEND_DIST_DIR}/index.html; "
                "refusing to package a Studio-less wheel"
            )
        if _PACKAGE_STATIC_DIR.exists():
            shutil.rmtree(_PACKAGE_STATIC_DIR)
        shutil.copytree(_FRONTEND_DIST_DIR, _PACKAGE_STATIC_DIR)

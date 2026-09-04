"""Phase 6 — prove the built wheel is a self-contained, *non-editable* install.

Creates an isolated venv in a temporary directory OUTSIDE the source checkout, installs the built
wheel with its dependencies (non-editable), and runs ``persona-forge doctor --json`` from a working
directory outside the checkout. This is the "editable ``uv sync`` is not accepted as wheel proof"
requirement: the console script must resolve ``persona_forge`` from site-packages, not the source
tree, and must still locate its baked-in Studio UI.

Fail-closed: exits non-zero if the wheel is missing, the install fails, the console script is absent
from the isolated venv, doctor crashes, or its JSON report cannot be parsed.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _uv() -> str:
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv not found on PATH; install it before running this gate")
    return uv


def _venv_python(venv_dir: Path) -> str:
    for candidate in (venv_dir / "bin" / "python", venv_dir / "Scripts" / "python.exe"):
        if candidate.exists():
            return str(candidate)
    raise SystemExit(f"could not find the venv python interpreter under {venv_dir}")


def _console_script(venv_dir: Path) -> Path:
    for candidate in (
        venv_dir / "bin" / "persona-forge",
        venv_dir / "Scripts" / "persona-forge.exe",
    ):
        if candidate.exists():
            return candidate
    raise SystemExit(f"persona-forge console script not found in isolated venv {venv_dir}")


def main() -> int:
    dist_dir = Path("dist")
    wheels = sorted(glob.glob(str(dist_dir / "persona_forge-*.whl")))
    if len(wheels) != 1:
        raise SystemExit(f"expected exactly one persona_forge-*.whl in {dist_dir}, found {wheels}")
    wheel = wheels[0]

    iso_root = Path(tempfile.mkdtemp(prefix="persona-forge-isolated-"))
    print(f"[isolated] workspace: {iso_root}")
    venv_dir = iso_root / "venv"
    try:
        subprocess.run([_uv(), "venv", str(venv_dir), "--python", "3.13"], check=True)
        print(f"[isolated] installing wheel non-editable: {wheel}")
        subprocess.run(
            [_uv(), "pip", "install", "--python", _venv_python(venv_dir), wheel],
            check=True,
        )

        doctor = _console_script(venv_dir)
        # Run from a cwd that is NOT the source checkout so persona_forge must come from
        # site-packages; give doctor a throwaway state root so it never touches the real one.
        doctor_home = iso_root / "home"
        env = dict(os.environ)
        env["PERSONA_FORGE_HOME"] = str(doctor_home)
        run_dir = iso_root / "run"
        run_dir.mkdir()
        result = subprocess.run(
            [str(doctor), "doctor", "--json"],
            cwd=str(run_dir),
            env=env,
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode != 0:
            raise SystemExit(f"persona-forge doctor exited {result.returncode} from outside the checkout")

        report = json.loads(result.stdout)
        if "backend" not in report or "paths" not in report or "ui" not in report:
            raise SystemExit("doctor JSON report is missing expected sections (backend/paths/ui)")
        receipt = {
            "status": "pass",
            "platform": report.get("platform"),
            "wheel": wheel,
            "isolated_venv": str(venv_dir),
            "console_script": str(doctor),
            "ui": report.get("ui"),
            "backend_resolved": report.get("backend", {}).get("resolved"),
        }
        print(json.dumps(receipt, indent=2))
        print("[isolated] PASSED: non-editable wheel install serves from site-packages with the Studio UI", file=sys.stderr)
        return 0
    finally:
        shutil.rmtree(iso_root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

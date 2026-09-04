"""Native console entry point: ``persona-forge`` (docs/plans/20260829-no_more_docker_architecture.md §5).

This module and everything it imports at top level must stay free of Torch, OpenVINO,
Transformers, and ``persona_forge.model`` — ``doctor`` must survive a broken or missing Torch
install, and importing this module alone must never trigger those heavyweight imports. Only
``serve`` reaches a heavy import, and even then indirectly: it replaces this process with a WSGI
server that imports ``persona_forge.app`` (which imports ``persona_forge.model``) in a fresh
process image, never inside this one.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from persona_forge import bootstrap, paths
from persona_forge.config import DEFAULT_TTS_BACKEND
from persona_forge.gpu_family import describe_accelerator

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FRONTEND_DIST_DIR_DEFAULT = _REPO_ROOT / "frontend" / "dist"
_DEFAULT_PORT = 8318


def _probe_import(name: str) -> dict[str, Any]:
    """Report whether ``name`` is installed/importable without leaving it imported for callers
    who only wanted the diagnostic (the module stays in sys.modules either way; that's fine here
    because doctor is its own process invocation, not the "import cli only" contract)."""
    if importlib.util.find_spec(name) is None:
        return {"installed": False, "importable": False, "error": None}
    try:
        __import__(name)
    except Exception as exc:  # pragma: no cover - depends on local environment
        return {"installed": True, "importable": False, "error": str(exc)}
    return {"installed": True, "importable": True, "error": None}


def _frontend_dist_dir(environ: paths.Environ) -> Path:
    override = environ.get("FRONTEND_DIST_DIR", "").strip()
    return Path(override) if override else _FRONTEND_DIST_DIR_DEFAULT


def _ui_diagnostics(environ: paths.Environ) -> dict[str, Any]:
    dist_dir = _frontend_dist_dir(environ)
    enabled = environ.get("FRONTEND_ENABLED", "1").strip().lower() not in ("0", "false")
    return {
        "dist_dir": str(dist_dir),
        "dist_dir_present": dist_dir.is_dir(),
        "frontend_enabled_env": enabled,
        "mode": "ui" if (enabled and dist_dir.is_dir()) else "api-only",
    }


def _patch_diagnostics() -> dict[str, Any]:
    try:
        importlib.import_module("persona_forge.transformers_compat")
        return {"transformers_compat_available": True}
    except Exception as exc:  # pragma: no cover - should not happen for a packaged install
        return {"transformers_compat_available": False, "error": str(exc)}


def _resolved_backend(environ: paths.Environ) -> str:
    from persona_forge.config import normalize_backend

    return normalize_backend(environ.get("TTS_BACKEND")) or DEFAULT_TTS_BACKEND


def _doctor_report(environ: paths.Environ | None = None) -> dict[str, Any]:
    environ = environ if environ is not None else os.environ
    return {
        "platform": {
            "sys_platform": sys.platform,
            "python_version": sys.version,
        },
        "dependencies": {
            "torch": _probe_import("torch"),
            "openvino": _probe_import("openvino"),
            "transformers": _probe_import("transformers"),
        },
        "paths": paths.describe_paths(environ),
        "accelerator": describe_accelerator(environ),
        "backend": {
            "resolved": _resolved_backend(environ),
            "default": DEFAULT_TTS_BACKEND,
        },
        "ui": _ui_diagnostics(environ),
        "patches": _patch_diagnostics(),
    }


def cmd_doctor(args: argparse.Namespace) -> int:
    report = _doctor_report()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"platform: {report['platform']['sys_platform']}")
        print(f"torch installed: {report['dependencies']['torch']['installed']}")
        print(f"openvino installed: {report['dependencies']['openvino']['installed']}")
        print(f"app data root: {report['paths']['app_data_root']}")
        print(f"accelerator family: {report['accelerator']['family']}")
        print(f"resolved backend: {report['backend']['resolved']}")
        print(f"ui mode: {report['ui']['mode']}")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    environ = os.environ
    created = bootstrap.prepare_writable_state(environ)
    for directory in created:
        print(f"[setup] ensured {directory}")
    if args.no_ui:
        print("[setup] --no-ui: skipping frontend build")
    else:
        dist_dir = _frontend_dist_dir(environ)
        if dist_dir.is_dir():
            print(f"[setup] frontend already built at {dist_dir}")
        else:
            print(f"[setup] frontend not built at {dist_dir}; run 'persona-forge build-ui'")
    return 0


def cmd_build_ui(args: argparse.Namespace) -> int:
    frontend_dir = _REPO_ROOT / "frontend"
    dist_dir = _frontend_dist_dir(os.environ)
    if not frontend_dir.is_dir():
        print(f"[build-ui] no frontend/ source directory at {frontend_dir}; nothing to build")
        return 1
    if dist_dir.is_dir() and not args.force:
        print(f"[build-ui] {dist_dir} already exists; pass --force to rebuild")
        return 0
    for step in (["npm", "ci"], ["npm", "run", "build"]):
        print(f"[build-ui] running: {' '.join(step)}")
        result = subprocess.run(step, cwd=frontend_dir)
        if result.returncode != 0:
            print(f"[build-ui] {' '.join(step)} failed with exit code {result.returncode}")
            return result.returncode
    print(f"[build-ui] built {dist_dir}")
    return 0


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _server_command(host: str, port: int, *, platform: str = sys.platform) -> list[str]:
    """Exact POSIX/Windows argv per docs/plans/20260829-no_more_docker_architecture.md §5.

    POSIX: one Gunicorn worker, gthread, four threads, 300s timeout, no preload. Windows:
    Waitress, four threads. The WSGI target is overridable via ``PERSONA_FORGE_WSGI_TARGET``
    only for the model-free acceptance fixture (Task 8) — production always uses the default.
    """
    target = os.environ.get("PERSONA_FORGE_WSGI_TARGET", "persona_forge.app:app")
    if platform.startswith("win"):
        return [
            "waitress-serve",
            f"--host={host}",
            f"--port={port}",
            "--threads=4",
            target,
        ]
    return [
        "gunicorn",
        target,
        "-w",
        "1",
        "-k",
        "gthread",
        "--threads",
        "4",
        "--timeout",
        "300",
        "--bind",
        f"{host}:{port}",
        "--log-level",
        "info",
    ]


def cmd_serve(args: argparse.Namespace) -> int:
    environ = os.environ
    bootstrap.apply_env_defaults(environ, platform=sys.platform)
    bootstrap.prepare_writable_state(environ)

    dist_dir = _frontend_dist_dir(environ)
    if not dist_dir.is_dir():
        print(
            f"[serve] warning: no frontend build at {dist_dir}; serving API-only "
            "(run 'persona-forge build-ui' for the full UI)"
        )

    if _port_in_use(args.host, args.port):
        print(f"[serve] warning: {args.host}:{args.port} already appears to be in use")

    command = _server_command(args.host, args.port, platform=sys.platform)
    print(f"[serve] backend={environ.get('TTS_BACKEND')} exec: {' '.join(command)}")
    os.execvp(command[0], command)
    raise RuntimeError("unreachable: os.execvp replaces the process")  # pragma: no cover


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="persona-forge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="Read-only environment diagnostics")
    doctor_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    doctor_parser.set_defaults(func=cmd_doctor)

    setup_parser = subparsers.add_parser("setup", help="Create state directories (idempotent)")
    setup_parser.add_argument("--no-ui", action="store_true", help="Skip the frontend build step")
    setup_parser.set_defaults(func=cmd_setup)

    build_ui_parser = subparsers.add_parser("build-ui", help="Build the frontend from source")
    build_ui_parser.add_argument(
        "--force", action="store_true", help="Rebuild even if a dist/ directory already exists"
    )
    build_ui_parser.set_defaults(func=cmd_build_ui)

    serve_parser = subparsers.add_parser("serve", help="Run the WSGI server")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument(
        "--port", type=int, default=int(os.environ.get("PERSONA_FORGE_PORT", _DEFAULT_PORT))
    )
    serve_parser.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

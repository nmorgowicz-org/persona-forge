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
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from persona_forge import bootstrap, frontend, paths
from persona_forge.config import DEFAULT_TTS_BACKEND
from persona_forge.gpu_family import describe_accelerator

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FRONTEND_SOURCE_DIR = _REPO_ROOT / "frontend"
_CHECKOUT_DIST_DIR = _FRONTEND_SOURCE_DIR / "dist"
_BUILD_STAMP_NAME = ".persona-forge-build-stamp"
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


def _torch_runtime_device(torch_probe: dict[str, Any]) -> str | None:
    """Best-effort ``device.auto_detect_device()`` — the unforced device torch itself would pick,
    with zero env overrides applied. Deliberately distinct from ``accelerator.device``
    (``resolve_device(environ)``, Task 3): that one is override-aware and reflects what the active
    backend will actually run on; this one is the raw torch-capability signal underneath it, useful
    for spotting e.g. a ``TTS_DEVICE`` override masking a torch build with no accelerator support at
    all. ``None`` when torch isn't importable — this must never raise doctor's own report."""
    if not torch_probe["importable"]:
        return None
    try:
        from persona_forge.device import auto_detect_device

        return auto_detect_device()
    except Exception:  # pragma: no cover - depends on local torch/accelerator state
        return None


def _frontend_dist_dir(environ: paths.Environ) -> Path:
    return frontend.resolve_frontend_dir(environ)


def _ui_diagnostics(environ: paths.Environ) -> dict[str, Any]:
    dist_dir = _frontend_dist_dir(environ)
    enabled = frontend.frontend_enabled(environ)
    present = dist_dir.is_dir()
    return {
        "dist_dir": str(dist_dir),
        "dist_dir_present": present,
        "frontend_enabled_env": enabled,
        "source": (
            "package"
            if dist_dir == frontend.PACKAGE_STATIC_DIR
            else "checkout"
            if dist_dir == frontend.CHECKOUT_DIST_DIR
            else "override"
        ),
        "mode": "ui" if (enabled and present) else "api-only",
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
    torch_probe = _probe_import("torch")
    torch_probe["runtime_device"] = _torch_runtime_device(torch_probe)
    return {
        "platform": {
            "sys_platform": sys.platform,
            "python_version": sys.version,
        },
        "dependencies": {
            "torch": torch_probe,
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


def _package_lock_hash() -> str:
    lock_path = _FRONTEND_SOURCE_DIR / "package-lock.json"
    return hashlib.sha256(lock_path.read_bytes()).hexdigest()


def _checkout_build_current(dist_dir: Path, lock_hash: str) -> bool:
    if not (dist_dir / "index.html").is_file():
        return False
    stamp_file = dist_dir / _BUILD_STAMP_NAME
    return stamp_file.is_file() and stamp_file.read_text().strip() == lock_hash


def _run_frontend_build_steps(frontend_dir: Path) -> int:
    # `shutil.which` resolves npm.CMD on Windows, but bare `subprocess.run(["npm", ...])`
    # still raises FileNotFoundError there: CreateProcess doesn't resolve extensionless
    # names to .cmd/.bat shims without going through a shell. Resolving the executable
    # ourselves works on every platform and avoids `shell=True`.
    npm = shutil.which("npm")
    if npm is None:
        print("[build-ui] npm not found on PATH; install Node.js/npm to build the Studio UI")
        return 1
    for args in (["ci"], ["run", "check"], ["run", "build"]):
        step = [npm, *args]
        print(f"[build-ui] running: npm {' '.join(args)}")
        try:
            result = subprocess.run(step, cwd=frontend_dir)
        except FileNotFoundError:
            print("[build-ui] npm not found on PATH; install Node.js/npm to build the Studio UI")
            return 1
        if result.returncode != 0:
            print(f"[build-ui] npm {' '.join(args)} failed with exit code {result.returncode}")
            return result.returncode
    return 0


def _build_checkout_frontend(*, force: bool) -> int:
    """Build `frontend/dist` from source, skipping when the package-lock hash stamp is current.

    Only ever targets the checkout `frontend/dist` tier — the package-local UI (an installed
    wheel's baked-in Studio) is produced at wheel-build time by `hatch_build.py`, not here.
    """
    if not _FRONTEND_SOURCE_DIR.is_dir():
        print(f"[build-ui] no frontend/ source directory at {_FRONTEND_SOURCE_DIR}; nothing to build")
        return 1
    lock_hash = _package_lock_hash()
    if not force and _checkout_build_current(_CHECKOUT_DIST_DIR, lock_hash):
        print(f"[build-ui] {_CHECKOUT_DIST_DIR} already up to date; pass --force to rebuild")
        return 0
    status = _run_frontend_build_steps(_FRONTEND_SOURCE_DIR)
    if status != 0:
        return status
    if not (_CHECKOUT_DIST_DIR / "index.html").is_file():
        print(f"[build-ui] build completed but {_CHECKOUT_DIST_DIR}/index.html is missing")
        return 1
    (_CHECKOUT_DIST_DIR / _BUILD_STAMP_NAME).write_text(lock_hash)
    print(f"[build-ui] built {_CHECKOUT_DIST_DIR}")
    return 0


def _qwen_patch_setup(*, apply: bool) -> int:
    """Task 5/6: default installs are clean no-ops. Only when qwen_tts is actually installed do
    we even look at patch status; only with the explicit ``--apply-qwen-patches`` flag do we
    write anything. Windows + qwen is an unsupported combination (architecture.md line 47) and
    gets a clear diagnostic rather than a silent attempt."""
    if importlib.util.find_spec("qwen_tts") is None:
        return 0

    if sys.platform == "win32":
        print(
            "[setup] qwen_tts is installed, but Qwen3-TTS/OpenVINO are not supported on "
            "Windows by this project — skipping compat-patch verification. See "
            "docs/plans/20260829-no_more_docker_architecture.md."
        )
        return 0

    from persona_forge.compat_patch import apply_qwen_patches, verify_qwen_patches

    if apply:
        report = apply_qwen_patches()
        action = "apply"
    else:
        report = verify_qwen_patches()
        action = "verify"

    for patch in report["patches"]:
        print(f"[setup] qwen-patch {action} [{patch['status']}] {patch['name']}")

    if report["status"] == "failed":
        print(
            "[setup] qwen compat-patch verification failed — installed qwen_tts/transformers "
            "versions may have drifted from the pinned ones this project patches for. Run "
            "`persona-forge setup --apply-qwen-patches` for details, or re-run with "
            "--apply-qwen-patches to attempt the patch.",
            file=sys.stderr,
        )
        return 1
    if not apply and report["status"] == "applied":
        print(
            "[setup] qwen compat patches are not yet applied to this environment — re-run with "
            "`persona-forge setup --apply-qwen-patches` to apply them."
        )
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    environ = os.environ
    created = bootstrap.prepare_writable_state(environ)
    for directory in created:
        print(f"[setup] ensured {directory}")

    patch_status = _qwen_patch_setup(apply=args.apply_qwen_patches)
    if patch_status != 0:
        return patch_status

    if args.no_ui:
        print("[setup] --no-ui: skipping frontend build")
        return 0
    if (frontend.PACKAGE_STATIC_DIR / "index.html").is_file():
        print(f"[setup] package-local UI already present at {frontend.PACKAGE_STATIC_DIR}")
        return 0
    return _build_checkout_frontend(force=False)


def cmd_build_ui(args: argparse.Namespace) -> int:
    return _build_checkout_frontend(force=args.force)


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
    setup_parser.add_argument(
        "--apply-qwen-patches",
        action="store_true",
        help=(
            "Apply the qwen_tts/transformers compat patches (persona_forge.compat_patch) if "
            "qwen_tts is installed. Without this flag, setup only verifies patch status "
            "(no-op when qwen_tts isn't installed)."
        ),
    )
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

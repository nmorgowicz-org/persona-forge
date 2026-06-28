"""Run the API and model worker with signal-aware process supervision."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass


@dataclass
class Service:
    name: str
    command: list[str]
    process: subprocess.Popen[bytes] | None = None


SERVICES = (
    Service(
        "worker",
        [
            "gunicorn",
            "app_worker:app",
            "-w",
            "1",
            "-k",
            "gthread",
            "--threads",
            "4",
            "--timeout",
            "300",
            "--bind",
            "0.0.0.0:8319",
            "--preload",
            "--log-level",
            "info",
        ],
    ),
    Service(
        "api",
        [
            "gunicorn",
            "app_api:app",
            "-w",
            "1",
            "-k",
            "gthread",
            "--threads",
            "2",
            "--timeout",
            "300",
            "--bind",
            "0.0.0.0:8318",
            "--log-level",
            "info",
        ],
    ),
)


def _signal_process_group(service: Service, signum: int) -> None:
    process = service.process
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def _stop_services(services: tuple[Service, ...], timeout: float) -> None:
    for service in services:
        _signal_process_group(service, signal.SIGTERM)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(service.process is None or service.process.poll() is not None for service in services):
            return
        time.sleep(0.1)

    for service in services:
        _signal_process_group(service, signal.SIGKILL)


def main() -> int:
    shutdown_requested = False
    shutdown_timeout = float(os.getenv("SHUTDOWN_TIMEOUT_SECONDS", "30"))
    if shutdown_timeout < 0:
        raise ValueError("SHUTDOWN_TIMEOUT_SECONDS must be non-negative")
    previous_handlers = {
        signal.SIGTERM: signal.getsignal(signal.SIGTERM),
        signal.SIGINT: signal.getsignal(signal.SIGINT),
    }

    def request_shutdown(signum: int, _frame: object) -> None:
        nonlocal shutdown_requested
        print(f"[supervisor] received signal {signum}", flush=True)
        shutdown_requested = True

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    try:
        for service in SERVICES:
            print(f"[supervisor] starting {service.name}", flush=True)
            service.process = subprocess.Popen(service.command, start_new_session=True)

        while not shutdown_requested:
            for service in SERVICES:
                process = service.process
                if process is not None and process.poll() is not None:
                    print(
                        f"[supervisor] {service.name} exited with status {process.returncode}",
                        file=sys.stderr,
                        flush=True,
                    )
                    return process.returncode or 1
            time.sleep(0.25)
        return 0
    finally:
        _stop_services(SERVICES, shutdown_timeout)
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())

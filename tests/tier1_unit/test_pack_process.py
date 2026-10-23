"""Managed pack worker process transport (Phase C3b)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from persona_forge.pack_process import PackProcess, PackProcessError

WORKER_SOURCE = """
import base64
import json
import sys
import time

for line in sys.stdin:
    message = json.loads(line)
    op = message.get("op")
    if op == "ping":
        print(json.dumps({"ok": True}), flush=True)
    elif op == "synthesize":
        payload = base64.b64encode(b"pcm").decode()
        print(json.dumps({"ok": True, "audio_b64": payload}), flush=True)
    elif op == "fail":
        print(json.dumps({"ok": False, "error": "boom"}), flush=True)
    elif op == "sleep":
        time.sleep(5)
        print(json.dumps({"ok": True}), flush=True)
"""


@pytest.fixture()
def worker_command(tmp_path: Path) -> list[str]:
    script = tmp_path / "worker.py"
    script.write_text(WORKER_SOURCE, encoding="utf-8")
    return [sys.executable, str(script)]


def test_ping_and_synthesize(worker_command):
    with PackProcess(worker_command, request_timeout=5) as worker:
        worker.ping()

        assert worker.synthesize({}) == b"pcm"
        assert worker.is_alive is True


def test_worker_error_is_raised(worker_command):
    with PackProcess(worker_command, request_timeout=5) as worker:
        with pytest.raises(PackProcessError, match="boom"):
            worker.request({"op": "fail"})


def test_timeout_kills_the_worker(worker_command):
    worker = PackProcess(worker_command, request_timeout=0.2)
    worker.start()

    with pytest.raises(PackProcessError, match="timed out"):
        worker.request({"op": "sleep"})

    assert worker.is_alive is False


def test_close_is_idempotent(worker_command):
    worker = PackProcess(worker_command, request_timeout=5)
    worker.start()
    worker.close()
    worker.close()

    assert worker.is_alive is False


def test_missing_binary_is_reported(tmp_path):
    with pytest.raises(PackProcessError, match="could not start worker"):
        PackProcess([str(tmp_path / "does-not-exist")]).start()

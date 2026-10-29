"""Install-time speed check for engine packs (plan §4.6 item 2).

After a pack's install verifies, one short real synthesis runs through the pack's own worker and is
timed: RTF is compute seconds over audio seconds. The result is written next to the pack as
``.install_check.json`` and shown on the engine card.

A slow machine is a labelled outcome, not an error. Nothing here can fail an install: every problem
becomes an ``unavailable`` record. The record is separate from the verification stamp, which only
the provisioner mints, so measuring can never make a pack look verified.

Outcomes: ``ok`` (RTF at or under 1), ``slow`` (slower than real time on this machine) and
``unavailable`` (the worker could not be measured; ``error`` says why).
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import time
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from persona_forge import hardware_fit
from persona_forge.pack_process import PackProcess

RECORD_FILENAME = ".install_check.json"
ENV_SWITCH = "ENGINE_INSTALL_SPEED_CHECK"
# One short sentence: long enough to be a fair timing, short enough to add seconds, not minutes.
CHECK_TEXT = "This is a quick speed check of the voice engine on your computer."
# An untimed first call for engines with no warm-up of their own, so lazy start-up work is not
# counted as speed.
PRIME_TEXT = "Ready."
SLOW_RTF = 1.0
LOAD_TIMEOUT_S = 600.0
WARMUP_TIMEOUT_S = 600.0
SYNTH_TIMEOUT_S = 180.0


@dataclass(frozen=True)
class SpeedCheckSpec:
    """How to start a pack's worker and load it, exactly as the engine adapter does."""

    command: tuple[str, ...]
    env: Mapping[str, str]
    load_request: Mapping[str, Any]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _audio_seconds(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes)) as handle:
        rate = handle.getframerate()
        return handle.getnframes() / rate if rate else 0.0


def _unavailable(message: str, load_average: float | None) -> dict[str, Any]:
    return {
        "outcome": "unavailable",
        "rtf": None,
        "compute_seconds": None,
        "audio_seconds": None,
        "device": None,
        "mode": None,
        "warmup_seconds": None,
        "load_average": load_average,
        "note": None,
        "error": message,
        "at": _now(),
    }


def run(
    spec: SpeedCheckSpec,
    *,
    process_factory: Callable[..., Any] = PackProcess,
    clock: Callable[[], float] = time.perf_counter,
    load_average: Callable[[], float | None] = hardware_fit.load_average,
) -> dict[str, Any]:
    """Load the worker, warm it up, and time one short synthesis. Never raises."""
    process = process_factory(list(spec.command), env=dict(spec.env), request_timeout=SYNTH_TIMEOUT_S)
    try:
        process.start()
        loaded = process.request(dict(spec.load_request), timeout=LOAD_TIMEOUT_S)
        warmup_seconds: float | None = None
        if loaded.get("warmup_pending"):
            # The adapter's "warming" state: the first compiled call (about 33 s for Kitten on
            # CUDA) is paid here and kept out of the timing.
            started = clock()
            loaded = {**loaded, **process.request({"op": "warmup"}, timeout=WARMUP_TIMEOUT_S)}
            warmup_seconds = round(clock() - started, 2)
        else:
            process.synthesize({"text": PRIME_TEXT})
        started = clock()
        audio = process.synthesize({"text": CHECK_TEXT})
        compute = clock() - started
        seconds = _audio_seconds(audio)
        if seconds <= 0:
            return _unavailable("the worker returned no audio", load_average())
        rtf = compute / seconds
        issue = loaded.get("fast_mode_issue")
        note = issue.get("message") if isinstance(issue, dict) else None
        mode = loaded.get("mode")
        return {
            "outcome": "slow" if rtf > SLOW_RTF else "ok",
            "rtf": round(rtf, 3),
            "compute_seconds": round(compute, 3),
            "audio_seconds": round(seconds, 3),
            "device": loaded.get("backend") or mode,
            "mode": mode,
            "warmup_seconds": warmup_seconds,
            "load_average": load_average(),
            "note": note if isinstance(note, str) else None,
            "error": None,
            "at": _now(),
        }
    except Exception as exc:  # a slow or odd machine must never fail an install
        return _unavailable(str(exc) or type(exc).__name__, load_average())
    finally:
        try:
            process.close()
        except Exception:
            pass


def record_path(directory: Path) -> Path:
    return directory / RECORD_FILENAME


def write_record(directory: Path, result: Mapping[str, Any]) -> None:
    """Atomically write the record. A read-only pack just goes without one."""
    try:
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=f"{RECORD_FILENAME}.", suffix=".tmp")
    except OSError:
        return
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(result), handle)
        os.replace(tmp, record_path(directory))
    except OSError:
        Path(tmp).unlink(missing_ok=True)


def read_record(directory: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(record_path(directory).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def enabled() -> bool:
    return os.environ.get(ENV_SWITCH, "1").strip().lower() not in {"0", "false", "no", "off"}


def check_and_record(
    directory: Path,
    spec: SpeedCheckSpec,
    measure: Callable[[SpeedCheckSpec], dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """The install step: measure and record. Returns the record, or None when switched off.

    ``measure`` is the test seam; passing one bypasses the ``ENGINE_INSTALL_SPEED_CHECK`` switch.
    """
    if measure is None and not enabled():
        return None
    try:
        result = (measure or run)(spec)
    except Exception as exc:
        result = _unavailable(str(exc) or type(exc).__name__, hardware_fit.load_average())
    directory.mkdir(parents=True, exist_ok=True)
    write_record(directory, result)
    return result

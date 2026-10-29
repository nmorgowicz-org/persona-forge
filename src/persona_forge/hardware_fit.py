"""Per-engine "does this machine suit it" verdicts and saved quick-benchmark results.

Verdicts use only facts this machine reports (OS, CPU architecture and count, NVIDIA GPU) and
claim only what has been tested. Anything else is reported as unknown rather than guessed.
"""

from __future__ import annotations

import json
import os
import platform as py_platform
import statistics
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

from persona_forge import paths

_FILENAME = "engine_benchmarks.json"
_lock = threading.Lock()

BENCH_TEXT = "The quick brown fox jumps over the lazy dog, and then it takes a short rest."


def load_average() -> float | None:
    """One-minute load average, or None where the OS does not report it (Windows)."""
    try:
        return round(os.getloadavg()[0], 2)
    except (OSError, AttributeError):
        return None


def machine_facts() -> dict[str, Any]:
    from persona_forge import kitten2_pack

    capability, cuda_major = kitten2_pack._cuda_facts()
    return {
        "platform": sys.platform,
        "machine": py_platform.machine(),
        "cores": os.cpu_count() or 0,
        "cuda_capability": capability,
        "cuda_major": cuda_major,
    }


def _verdict(level: str, text: str) -> dict[str, str]:
    return {"level": level, "text": text}


def fit_for(engine_id: str, facts: dict[str, Any] | None = None) -> dict[str, str]:
    """level is one of recommended, ok, unsupported, unknown."""
    facts = facts or machine_facts()
    apple = facts["platform"] == "darwin" and facts["machine"] in ("arm64", "aarch64")
    cores = facts["cores"]
    if engine_id == "kitten2":
        from persona_forge import kitten2_pack

        try:
            target = kitten2_pack.detect_target(
                facts["platform"], facts["machine"], lambda: (facts["cuda_capability"], facts["cuda_major"])
            )
        except kitten2_pack.UnsupportedMachine as exc:
            return _verdict("unsupported", exc.public_message)
        if target.kind == "mlx":
            return _verdict("recommended", "Recommended for Apple silicon (runs on MLX).")
        return _verdict("recommended", "Recommended for your NVIDIA GPU (needs a compiler for fast mode; falls back otherwise).")
    if engine_id in ("phonon-31m", "kokoro", "pocket-lite"):
        tested = apple or facts["platform"] == "win32" or facts["platform"].startswith("linux")
        note = "" if tested else " Not tested on this operating system."
        return _verdict("ok" if tested else "unknown", f"Runs on CPU ({cores} cores); no GPU needed.{note}")
    if engine_id == "pocket-tts":
        return _verdict("ok", f"Runs on CPU ({cores} cores); a GPU is optional." if cores else "Runs on CPU.")
    return _verdict("unknown", "No hardware guidance for this engine.")


def first_run_nudge(facts: dict[str, Any], pack_installed: bool) -> dict[str, Any] | None:
    """The one-line hint for a machine with no pack engine installed, or None.

    It says only what ``fit_for`` reports: an NVIDIA GPU or Apple silicon is what Kitten TTS 2
    needs, and the CPU engines run without a GPU. It makes no claim about quality, and none about
    speed here (nothing has been measured until an engine is installed). Unknown fit gives no hint.
    """
    if pack_installed:
        return None
    gpu = fit_for("kitten2", facts)
    if gpu["level"] == "recommended":
        apple = facts["platform"] == "darwin"
        return {
            "kind": "apple" if apple else "gpu",
            "engines": ["kitten2"],
            "text": (
                "Your Mac's Apple silicon can run Kitten TTS 2 (on MLX)."
                if apple
                else "Your NVIDIA GPU can run Kitten TTS 2 (a GPU engine)."
            ),
            "basis": gpu["text"],
        }
    cpu = fit_for("phonon-31m", facts)
    if cpu["level"] == "ok":
        return {
            "kind": "cpu",
            "engines": ["phonon-31m", "kokoro", "pocket-lite"],
            "text": (
                "No supported GPU was found, but light engines like Phonon, Kokoro and Pocket "
                "Lite run on this CPU without one. Install one to measure its speed here."
            ),
            "basis": cpu["text"],
        }
    return None


def _path() -> Path:
    return Path(paths.runtime_data_dir()) / _FILENAME


def load(path: Path | None = None) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads((path or _path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def save_result(engine_id: str, result: dict[str, Any], path: Path | None = None) -> None:
    p = path or _path()
    with _lock:
        data = load(p)
        data[engine_id] = result
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{_FILENAME}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            os.replace(tmp, p)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def summarise_runs(runs: list[tuple[float, float]], load_average: float | None) -> dict[str, Any]:
    """runs: (seconds taken, seconds of audio) with the cold run first."""
    cold, warm = runs[0], runs[1:] or runs[:1]
    rtfs = [taken / audio for taken, audio in warm if audio > 0]
    return {
        "cold_seconds": round(cold[0], 2),
        "rtf_median": round(statistics.median(rtfs), 3) if rtfs else None,
        "rtf_worst": round(max(rtfs), 3) if rtfs else None,
        "warm_runs": len(warm),
        "load_average": load_average,
    }

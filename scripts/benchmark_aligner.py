#!/usr/bin/env python3
"""Fail-closed latency gate for the real ONNX forced aligner.

Run on the target CPU with a representative reference WAV and its exact transcript. Audio
stays outside Git; the command emits only timing/model metadata unless --json-output is used.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import resource
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from persona_forge import forced_alignment


def _percentile(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _transcript(args: argparse.Namespace) -> str:
    if args.transcript_file:
        return Path(args.transcript_file).read_text(encoding="utf-8").strip()
    return (args.transcript or "").strip()


def _run_once(wav: np.ndarray, sr: int, transcript: str) -> tuple[float, int]:
    started = time.perf_counter()
    boundaries = forced_alignment.align(wav, sr, transcript)
    return time.perf_counter() - started, len(boundaries)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, help="Representative WAV; never committed")
    transcript_group = parser.add_mutually_exclusive_group(required=True)
    transcript_group.add_argument("--transcript")
    transcript_group.add_argument("--transcript-file")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument(
        "--budget-seconds",
        type=float,
        default=float(os.getenv("ALIGNER_LATENCY_BUDGET_SECONDS", "5.0")),
    )
    parser.add_argument("--json-output", help="Optional path for a non-audio result record")
    args = parser.parse_args()

    if args.iterations < 1 or args.warmup < 0 or args.budget_seconds <= 0:
        parser.error("iterations must be >=1, warmup >=0, and budget-seconds >0")
    transcript = _transcript(args)
    if not transcript:
        parser.error("transcript must not be empty")

    wav, sr = sf.read(args.audio, dtype="float32", always_2d=False)
    wav = np.asarray(wav, dtype=np.float32)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)

    forced_alignment.unload_session()
    cold_seconds, boundary_count = _run_once(wav, int(sr), transcript)
    for _ in range(args.warmup):
        _run_once(wav, int(sr), transcript)

    warm_samples = [_run_once(wav, int(sr), transcript)[0] for _ in range(args.iterations)]
    p50 = _percentile(warm_samples, 0.50)
    p95 = _percentile(warm_samples, 0.95)
    within_budget = p95 < args.budget_seconds
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_rss_mib = rss / 1024.0 if sys.platform != "darwin" else rss / (1024.0 * 1024.0)

    result = {
        "engine": forced_alignment.ENGINE_ID,
        "model_id": forced_alignment.MODEL_ID,
        "model_revision": forced_alignment.MODEL_REVISION,
        "providers": forced_alignment._providers(),
        "host": platform.node(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "audio_duration_seconds": round(wav.size / float(sr), 3),
        "boundary_count": boundary_count,
        "cold_seconds": round(cold_seconds, 6),
        "warm_iterations": args.iterations,
        "warm_p50_seconds": round(p50, 6),
        "warm_p95_seconds": round(p95, 6),
        "budget_seconds": args.budget_seconds,
        "within_budget": within_budget,
        "peak_process_rss_mib": round(peak_rss_mib, 1),
    }
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.json_output:
        Path(args.json_output).write_text(rendered + "\n", encoding="utf-8")
    return 0 if within_budget else 1


if __name__ == "__main__":
    raise SystemExit(main())

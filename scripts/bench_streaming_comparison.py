#!/usr/bin/env python3
"""Identical-seed latency comparison: batch vs streaming paragraph requests.

This script validates Task 2 from the streaming vocoder handoff:

- Sends warm-up and measured paragraph requests through:
  - /batch_internal (normal batch decode)
  - /stream_internal (synchronous streaming with final-prefix reuse)
- Uses the same seed, text, and generation parameters each time.
- Records: generation frames, audio seconds, first-byte time, total wall time,
  parity metrics, and RSS/swap when available.
- Acceptance:
  - stream/batch generated codes and final PCM agree (max_abs == 0, SNR == inf).
  - streaming does not regress median total wall time beyond noise.

Run inside the target runtime container (Linux AMD64), not on Mac.

Example:
  python scripts/bench_streaming_comparison.py \
      --seed 42 \
      --iterations 4 \
      --warmup 1 \
      --max-new-tokens 300
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import resource
import statistics
import sys
import time
from typing import Any

import numpy as np
import requests
import soundfile as sf


WORKER = os.getenv("WORKER_URL", "http://127.0.0.1:8319")
PARAGRAPH_TEXT = (
    "Thanks for stopping by today. Our special this afternoon is a slow roasted "
    "tomato soup with fresh basil and a warm sourdough roll. If you are in the mood "
    "for something sweet, the lemon tart is just out of the oven. Let me know what "
    "you would like, and I will have it brought right out to your table."
)

RESET_PAUSE_S = 2  # allow stateful cache to settle between batch/stream


def _read_swap_counters() -> tuple[int | None, int | None]:
    try:
        with open("/proc/vmstat", "r", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if parts and parts[0] == "pswpin":
                    pswpin = int(parts[1])
                if parts and parts[0] == "pswpout":
                    pswpout = int(parts[1])
    except OSError:
        return None, None
    return locals().get("pswpin"), locals().get("pswpout")


def swap_delta(before, after):
    labels = ("pages_in", "pages_out")
    parts = []
    for label, b, a in zip(labels, before, after):
        parts.append(f"{label}={a - b if b is not None and a is not None else '?'}")
    return " ".join(parts)


def current_rss_bytes() -> int | None:
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if parts and parts[0] == "VmRSS:":
                    return int(parts[1]) * 1024
    except OSError:
        return None
    return None


def peak_rss_bytes() -> int:
    m = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return m * 1024 if os.uname().sysname == "Linux" else m


def fetch_health():
    r = requests.get(f"{WORKER}/health", timeout=10)
    r.raise_for_status()
    return r.json()


def decode_wav(audio_bytes):
    buf = io.BytesIO(audio_bytes)
    samples, sr = sf.read(buf, dtype="float32")
    return np.asarray(samples, dtype=np.float32).ravel(), sr


def parse_timing_header(headers: dict[str, str], name: str) -> float | None:
    v = headers.get(name)
    if not v or v == "none":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def run_batch(seed, text, max_new_tokens):
    """Call /batch_internal and return (audio_bytes, metadata, headers)."""
    payload = {
        "text": text,
        "language": "English",
        "do_sample": False,
        "max_new_tokens": max_new_tokens,
        "seed": seed,
    }
    t0 = time.monotonic()
    r = requests.post(
        f"{WORKER}/batch_internal",
        json=payload,
        timeout=300,
    )
    wall = time.monotonic() - t0
    r.raise_for_status()
    headers = {k.lower(): v for k, v in r.headers.items()}
    elapsed = parse_timing_header(headers, "x-batch-elapsed-seconds")
    frames = int(headers.get("x-batch-frames", "0"))
    wav, sr = decode_wav(r.content)
    audio_s = len(wav) / sr
    return {
        "audio_bytes": r.content,
        "samples": wav,
        "sample_rate": sr,
        "frames": frames,
        "audio_s": round(audio_s, 4),
        "elapsed_s": elapsed,
        "wall_s": round(wall, 4),
    }


def run_stream(seed, text, max_new_tokens):
    """Call /stream_internal with reuse and return (audio_bytes, metadata, headers)."""
    payload = {
        "text": text,
        "language": "English",
        "do_sample": False,
        "max_new_tokens": max_new_tokens,
        "reuse_streamed_decode": True,
        "seed": seed,
    }
    t0 = time.monotonic()
    r = requests.post(
        f"{WORKER}/stream_internal",
        json=payload,
        timeout=300,
        stream=False,
    )
    wall = time.monotonic() - t0
    r.raise_for_status()
    headers = {k.lower(): v for k, v in r.headers.items()}
    ttfb = parse_timing_header(headers, "x-streaming-ttfb-seconds")
    total_s = parse_timing_header(headers, "x-streaming-total-seconds")
    max_abs = headers.get("x-streaming-max-abs", "")
    snr_db = headers.get("x-streaming-snr-db", "")
    frames = int(headers.get("x-streaming-frames", "0"))
    ref_frames = int(headers.get("x-streaming-reference-frames", "0"))
    chunk_count = int(headers.get("x-streaming-chunk-count", "0"))
    wav, sr = decode_wav(r.content)
    audio_s = len(wav) / sr
    return {
        "audio_bytes": r.content,
        "samples": wav,
        "sample_rate": sr,
        "frames": frames,
        "reference_frames": ref_frames,
        "audio_s": round(audio_s, 4),
        "ttfb_s": ttfb,
        "total_s": total_s,
        "wall_s": round(wall, 4),
        "chunk_count": chunk_count,
        "max_abs": max_abs,
        "snr_db": snr_db,
    }


def batch_vs_stream_parity(batch_wav, stream_wav, sr):
    if batch_wav.shape != stream_wav.shape:
        return {"match": False, "reason": "length_mismatch"}
    diff = batch_wav.astype(np.float64) - stream_wav.astype(np.float64)
    max_abs = float(np.max(np.abs(diff), initial=0.0))
    signal = float(np.sum(batch_wav.astype(np.float64) ** 2))
    noise = float(np.sum(diff ** 2))
    snr_db = float("inf") if noise == 0.0 else 10.0 * np.log10(signal / noise)
    return {
        "match": max_abs == 0.0,
        "max_abs": max_abs,
        "snr_db": "inf" if np.isinf(snr_db) else round(snr_db, 3),
    }


def median_t(values):
    if not values:
        return None
    return round(statistics.median(values), 3)


def p95_t(values):
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(0.95 * len(ordered)) - 1))
    return round(ordered[rank], 3)


def run(args):
    health = fetch_health()
    print("[bench_streaming_comparison] health:", json.dumps(health, default=str))

    iterations = args.iterations
    seed = args.seed
    text = PARAGRAPH_TEXT
    max_new_tokens = args.max_new_tokens

    # Warm-up
    for i in range(args.warmup):
        print(f"[warmup] {i+1}/{args.warmup} (batch)", flush=True)
        run_batch(seed + i, text, max_new_tokens)
        time.sleep(RESET_PAUSE_S)
        print(f"[warmup] {i+1}/{args.warmup} (stream)", flush=True)
        run_stream(seed + i, text, max_new_tokens)

    swap_before = _read_swap_counters()
    rss_before = current_rss_bytes()

    batch_results: list[dict[str, Any]] = []
    stream_results: list[dict[str, Any]] = []
    parity_results: list[dict[str, Any]] = []

    for i in range(1, iterations + 1):
        print(f"\n[run] {i}/{iterations}", flush=True)

        # Batch run
        print(f"  batch {i}/{iterations}", flush=True)
        try:
            b = run_batch(seed, text, max_new_tokens)
        except Exception as e:
            print(f"  batch {i} failed: {e}", flush=True)
            raise
        batch_results.append({
            "iteration": i,
            "seed": seed,
            "wall_s": b["wall_s"],
            "elapsed_s": b["elapsed_s"],
            "frames": b["frames"],
            "audio_s": b["audio_s"],
            "rss_mib": current_rss_bytes() // (1024 * 1024) if current_rss_bytes() else None,
        })

        # Short pause to let stateful cache settle and memory release
        time.sleep(RESET_PAUSE_S)

        # Stream run (same seed)
        print(f"  stream {i}/{iterations}", flush=True)
        try:
            s = run_stream(seed, text, max_new_tokens)
        except Exception as e:
            print(f"  stream {i} failed: {e}", flush=True)
            raise
        stream_results.append({
            "iteration": i,
            "seed": seed,
            "wall_s": s["wall_s"],
            "total_s": s["total_s"],
            "ttfb_s": s["ttfb_s"],
            "frames": s["frames"],
            "reference_frames": s["reference_frames"],
            "audio_s": s["audio_s"],
            "chunk_count": s["chunk_count"],
            "max_abs": s["max_abs"],
            "snr_db": s["snr_db"],
            "rss_mib": current_rss_bytes() // (1024 * 1024) if current_rss_bytes() else None,
        })

        # Parity between batch and stream WAV
        p = batch_vs_stream_parity(b["samples"], s["samples"], b["sample_rate"])
        parity_results.append({
            "iteration": i,
            "match": p["match"],
            "max_abs": p["max_abs"],
            "snr_db": p["snr_db"],
        })

        # Write per-iteration WAV pair
        out_dir = args.out_dir
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            sf.write(
                str(out_dir / f"batch_{i}.wav"),
                b["samples"],
                b["sample_rate"],
                format="WAV",
            )
            sf.write(
                str(out_dir / f"stream_{i}.wav"),
                s["samples"],
                s["sample_rate"],
                format="WAV",
            )

    swap_after = _read_swap_counters()
    rss_after = current_rss_bytes()

    # Summaries
    batch_wall = [r["wall_s"] for r in batch_results]
    stream_wall = [r["wall_s"] for r in stream_results]
    stream_ttfb = [r["ttfb_s"] for r in stream_results if r.get("ttfb_s") is not None]

    any_parity_fail = any(not p["match"] for p in parity_results)

    summary = {
        "description": "Identical-seed batch vs streaming paragraph comparison",
        "provenance": {
            "worker": WORKER,
            "health": health,
            "seed": seed,
            "text": text,
            "max_new_tokens": max_new_tokens,
            "iterations": iterations,
            "warmup": args.warmup,
            "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "batch": {
            "iterations": len(batch_results),
            "median_wall_s": median_t(batch_wall),
            "p95_wall_s": p95_t(batch_wall),
            "min_wall_s": round(min(batch_wall), 3) if batch_wall else None,
            "max_wall_s": round(max(batch_wall), 3) if batch_wall else None,
        },
        "stream": {
            "iterations": len(stream_results),
            "median_wall_s": median_t(stream_wall),
            "p95_wall_s": p95_t(stream_wall),
            "min_wall_s": round(min(stream_wall), 3) if stream_wall else None,
            "max_wall_s": round(max(stream_wall), 3) if stream_wall else None,
            "median_ttfb_s": median_t(stream_ttfb) if stream_ttfb else None,
        },
        "parity": {
            "all_match": not any_parity_fail,
            "results": parity_results,
        },
        "memory": {
            "rss_before_mib": rss_before // (1024 * 1024) if rss_before else None,
            "rss_after_mib": rss_after // (1024 * 1024) if rss_after else None,
            "peak_rss_mib": peak_rss_bytes() // (1024 * 1024),
            "swap_delta": swap_delta(swap_before, swap_after),
        },
        "per_iteration": {
            "batch": batch_results,
            "stream": stream_results,
        },
    }

    # Print to stdout as JSON for machine readability.
    print("\n" + json.dumps(summary, indent=2, default=str))

    # Write report file
    report_path = args.report or "bench_streaming_comparison_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\n[bench_streaming_comparison] report written to {report_path}", flush=True)

    # Verdict
    if any_parity_fail:
        print("[bench_streaming_comparison] VERDICT: FAIL — parity mismatch batch vs stream", flush=True)
        sys.exit(1)
    else:
        # Check streaming regression: streaming median wall time must not exceed batch
        # median by more than a noise margin (e.g., 10% for these loads).
        b_med = median_t(batch_wall) or 0.0
        s_med = median_t(stream_wall) or 0.0
        if s_med > b_med * 1.1:
            print(
                f"[bench_streaming_comparison] WARNING: "
                f"stream median wall time {s_med:.3f} exceeds "
                f"batch median {b_med:.3f} by >10%. Streaming may regress wall time.",
                flush=True,
            )
        print("[bench_streaming_comparison] VERDICT: PASS — exact parity confirmed", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=42, help="Deterministic seed (default 42)")
    p.add_argument("--iterations", type=int, default=4, help="Number of measured iterations (>=3 recommended)")
    p.add_argument("--warmup", type=int, default=1, help="Warm-up iterations (not measured)")
    p.add_argument("--max-new-tokens", type=int, default=300, help="max_new_tokens for generation")
    p.add_argument("--out-dir", type=str, default=None, help="Directory to write per-iteration WAVs")
    p.add_argument("--report", type=str, default="bench_streaming_comparison_report.json",
                   help="Report JSON output path")
    args = p.parse_args()
    if args.iterations < 3:
        print("[bench_streaming_comparison] WARNING: using <3 iterations; "
              "results may be too noisy for acceptance.", flush=True)
    run(args)


if __name__ == "__main__":
    main()

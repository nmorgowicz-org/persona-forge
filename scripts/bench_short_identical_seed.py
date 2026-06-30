#!/usr/bin/env python3
"""Short identical-seed batch vs streaming comparison."""

import io
import json
import statistics
import time

import numpy as np
import requests
import soundfile as sf

WORKER = "http://127.0.0.1:8319"
SEED = 42
TEXT = "Thanks for stopping by. Your order will be ready in just a few minutes."
ITERATIONS = 3
RESET_PAUSE = 2


def run_batch(seed, text):
    t0 = time.monotonic()
    r = requests.post(
        f"{WORKER}/batch_internal",
        json={"text": text, "language": "English", "do_sample": False, "seed": seed},
        timeout=300,
    )
    wall = time.monotonic() - t0
    r.raise_for_status()
    h = {k.lower(): v for k, v in r.headers.items()}
    wav, sr = sf.read(io.BytesIO(r.content), dtype="float32")
    wav = np.asarray(wav, dtype=np.float32).ravel()
    return {
        "samples": wav,
        "sr": sr,
        "wall_s": round(wall, 3),
        "elapsed_s": float(h.get("x-batch-elapsed-seconds", "0")),
        "frames": int(h.get("x-batch-frames", "0")),
        "audio_s": round(len(wav) / sr, 3),
    }


def run_stream(seed, text):
    t0 = time.monotonic()
    r = requests.post(
        f"{WORKER}/stream_internal",
        json={
            "text": text,
            "language": "English",
            "do_sample": False,
            "reuse_streamed_decode": True,
            "seed": seed,
        },
        timeout=300,
    )
    wall = time.monotonic() - t0
    r.raise_for_status()
    h = {k.lower(): v for k, v in r.headers.items()}
    wav, sr = sf.read(io.BytesIO(r.content), dtype="float32")
    wav = np.asarray(wav, dtype=np.float32).ravel()
    ttfb_raw = h.get("x-streaming-ttfb-seconds", "none")
    ttfb = float(ttfb_raw) if ttfb_raw and ttfb_raw != "none" else None
    total_s = float(h.get("x-streaming-total-seconds", "0"))
    return {
        "samples": wav,
        "sr": sr,
        "wall_s": round(wall, 3),
        "total_s": total_s,
        "ttfb_s": ttfb,
        "frames": int(h.get("x-streaming-frames", "0")),
        "audio_s": round(len(wav) / sr, 3),
        "max_abs": h.get("x-streaming-max-abs", ""),
        "snr_db": h.get("x-streaming-snr-db", ""),
        "chunk_count": int(h.get("x-streaming-chunk-count", "0")),
    }


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(pct / 100 * len(ordered)) - 1))
    return ordered[rank]


def main():
    results = []

    for i in range(1, ITERATIONS + 1):
        print(f"[run] {i}/{ITERATIONS} batch", flush=True)
        b = run_batch(SEED, TEXT)
        time.sleep(RESET_PAUSE)
        print(f"[run] {i}/{ITERATIONS} stream", flush=True)
        s = run_stream(SEED, TEXT)

        # Parity between batch and stream for same seed
        match = b["samples"].shape == s["samples"].shape
        if match:
            diff = b["samples"].astype(np.float64) - s["samples"].astype(np.float64)
            max_abs = float(np.max(np.abs(diff), initial=0.0))
            signal = float(np.sum(b["samples"].astype(np.float64) ** 2))
            noise = float(np.sum(diff ** 2))
            snr = float("inf") if noise == 0.0 else 10.0 * np.log10(signal / noise)
        else:
            max_abs = float("nan")
            snr = float("nan")

        row = {
            "iteration": i,
            "batch": {k: v for k, v in b.items() if k != "samples"},
            "stream": {k: v for k, v in s.items() if k != "samples"},
            "parity": {
                "match": bool(match and max_abs == 0.0),
                "max_abs": max_abs,
                "snr_db": "inf" if isinstance(snr, float) and np.isinf(snr) else snr,
            },
        }
        results.append(row)
        print(json.dumps(row, indent=2, default=str))

    # Summary
    batch_walls = [r["batch"]["wall_s"] for r in results]
    stream_walls = [r["stream"]["wall_s"] for r in results]
    stream_ttfbs = [r["stream"]["ttfb_s"] for r in results if r["stream"].get("ttfb_s") is not None]

    summary = {
        "mode": "short-prompt-identical-seed",
        "text": TEXT,
        "seed": SEED,
        "iterations": ITERATIONS,
        "batch": {
            "median_wall_s": round(statistics.median(batch_walls), 3),
            "p95_wall_s": round(percentile(batch_walls, 95), 3),
            "min_wall_s": round(min(batch_walls), 3),
            "max_wall_s": round(max(batch_walls), 3),
        },
        "stream": {
            "median_wall_s": round(statistics.median(stream_walls), 3),
            "p95_wall_s": round(percentile(stream_walls, 95), 3),
            "min_wall_s": round(min(stream_walls), 3),
            "max_wall_s": round(max(stream_walls), 3),
            "median_ttfb_s": round(statistics.median(stream_ttfbs), 3) if stream_ttfbs else None,
        },
        "parity_all_match": all(r["parity"]["match"] for r in results),
    }

    print("=" * 60)
    print("SUMMARY:")
    print(json.dumps(summary, indent=2))

    report_path = "/tmp/bench_short_identical_seed_report.json"
    with open(report_path, "w") as f:
        json.dump({"per_iteration": results, "summary": summary}, f, indent=2, default=str)
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()

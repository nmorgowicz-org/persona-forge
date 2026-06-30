#!/usr/bin/env python3
"""Single paragraph identical-seed batch vs streaming comparison."""

import io
import json
import time

import numpy as np
import requests
import soundfile as sf

WORKER = "http://127.0.0.1:8319"
SEED = 42
MAX_TOKENS = 200
TEXT = (
    "Thanks for stopping by today. Our special this afternoon is a slow roasted "
    "tomato soup with fresh basil and a warm sourdough roll. If you are in the mood "
    "for something sweet, the lemon tart is just out of the oven. Let me know what "
    "you would like, and I will have it brought right out to your table."
)


def run_batch():
    t0 = time.monotonic()
    r = requests.post(
        f"{WORKER}/batch_internal",
        json={"text": TEXT, "language": "English", "do_sample": False, "max_new_tokens": MAX_TOKENS, "seed": SEED},
        timeout=600,
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


def run_stream():
    t0 = time.monotonic()
    r = requests.post(
        f"{WORKER}/stream_internal",
        json={
            "text": TEXT,
            "language": "English",
            "do_sample": False,
            "max_new_tokens": MAX_TOKENS,
            "reuse_streamed_decode": True,
            "seed": SEED,
        },
        timeout=600,
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
        "ref_frames": int(h.get("x-streaming-reference-frames", "0")),
        "boundaries": h.get("x-streaming-decode-boundaries", ""),
        "audio_s": round(len(wav) / sr, 3),
        "max_abs": h.get("x-streaming-max-abs", ""),
        "snr_db": h.get("x-streaming-snr-db", ""),
        "chunk_count": int(h.get("x-streaming-chunk-count", "0")),
    }


def main():
    # Batch run
    print("[paragraph] batch", flush=True)
    b = run_batch()
    print(json.dumps({k: v for k, v in b.items() if k != "samples"}, indent=2))
    time.sleep(3)

    # Stream run
    print("[paragraph] stream", flush=True)
    s = run_stream()
    print(json.dumps({k: v for k, v in s.items() if k != "samples"}, indent=2))

    # Parity
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

    parity = {
        "match": bool(match and max_abs == 0.0),
        "max_abs": max_abs,
        "snr_db": "inf" if isinstance(snr, float) and np.isinf(snr) else snr,
    }
    print("=" * 60)
    print("PARAGRAPH RESULT:")
    result = {
        "mode": "paragraph-identical-seed",
        "max_new_tokens": MAX_TOKENS,
        "seed": SEED,
        "batch": {k: v for k, v in b.items() if k != "samples"},
        "stream": {k: v for k, v in s.items() if k != "samples"},
        "parity": parity,
    }
    print(json.dumps(result, indent=2))

    report_path = "/tmp/bench_paragraph_identical_seed_report.json"
    with open(report_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()

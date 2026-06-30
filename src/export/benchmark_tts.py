#!/usr/bin/env python3
"""Milestone 0 latency / RTF / memory benchmark for the PyTorch baseline.

Run with the prod qwen3-tts container stopped so the model load does not contend for
memory. Reports warm median and p95 latency, real-time factor, peak RSS, and swap
activity per prompt. Defaults to production sampling; use --deterministic for the
greedy settings used by parity tests.
"""

from __future__ import annotations

import argparse
import json
import time

import bench_common  # noqa: F401  (sets the thread budget before torch is imported)
from bench_common import (
    PROMPTS,
    current_rss_bytes,
    fmt_mib,
    load_model,
    peak_rss_bytes,
    read_swap_counters,
    summarize,
    swap_delta,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=6, help="measured iterations per prompt")
    parser.add_argument("--warmup", type=int, default=1, help="warm-up iterations per prompt (untimed)")
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="greedy decoding (do_sample=False) for parity-style runs",
    )
    parser.add_argument(
        "--prompts",
        nargs="*",
        choices=sorted(PROMPTS),
        default=sorted(PROMPTS),
        help="which prompts to run",
    )
    parser.add_argument("--json-out", default=None, help="write the summary as JSON to this path")
    return parser.parse_args()


def run() -> dict:
    args = parse_args()
    gen_kwargs: dict[str, object] = {}
    if args.deterministic:
        # Greedy on both the main talker and the code predictor.
        gen_kwargs.update(do_sample=False, subtalker_dosample=False)

    loaded = load_model()
    model, prompt = loaded.model, loaded.voice_clone_prompt

    results: dict[str, dict] = {}
    for name in args.prompts:
        text, language = PROMPTS[name]

        for _ in range(args.warmup):
            model.generate_voice_clone(
                text=text, language=language, voice_clone_prompt=prompt, **gen_kwargs
            )

        times_s: list[float] = []
        audio_s: list[float] = []
        swap_before = read_swap_counters()
        for i in range(args.iterations):
            start = time.perf_counter()
            wavs, sr = model.generate_voice_clone(
                text=text, language=language, voice_clone_prompt=prompt, **gen_kwargs
            )
            elapsed = time.perf_counter() - start
            audio = len(wavs[0]) / sr
            times_s.append(elapsed)
            audio_s.append(audio)
            print(
                f"[{name}] iter {i + 1}/{args.iterations}: {elapsed:.1f}s "
                f"for {audio:.1f}s audio (RTF {elapsed / audio:.1f})",
                flush=True,
            )
        swap_after = read_swap_counters()

        summary = summarize(times_s, audio_s)
        summary["swap"] = swap_delta(swap_before, swap_after)
        summary["rss_after"] = fmt_mib(current_rss_bytes())
        results[name] = summary
        print(f"\n[{name}] {json.dumps(summary)}", flush=True)

    report = {
        "mode": "deterministic" if args.deterministic else "sampling",
        "peak_rss": fmt_mib(peak_rss_bytes()),
        "prompts": results,
    }
    print("\n=== summary ===")
    print(json.dumps(report, indent=2))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        print(f"wrote {args.json_out}")
    return report


if __name__ == "__main__":
    run()

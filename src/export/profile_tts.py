#!/usr/bin/env python3
"""Milestone 0 component profiler: where does generation time actually go?

Wraps the two transformer-core forwards and the speech-tokenizer decode with timers
and call counters, then runs one generation. Establishes the main-talker vs.
code-predictor vs. tokenizer split (the plan assumes the 5-layer code predictor, run
15x per frame, dominates) and the per-side step counts, so optimization effort lands
on the right core. Run with the prod persona-forge container stopped.
"""

from __future__ import annotations

import argparse
import functools
import time

import bench_common  # noqa: F401  (sets the thread budget before torch is imported)
from bench_common import PROMPTS, load_model


class Probe:
    """Accumulates wall time and call count for one wrapped callable.

    Set progress_every>0 to emit a live heartbeat every N calls — wrapping the
    main-talker forward this way turns step count into a real progress signal,
    since one main step is produced per audio frame.
    """

    def __init__(self, label: str, progress_every: int = 0) -> None:
        self.label = label
        self.calls = 0
        self.total_s = 0.0
        self.progress_every = progress_every
        self._wall_start = time.perf_counter()

    def wrap(self, fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                self.calls += 1
                self.total_s += time.perf_counter() - start
                if self.progress_every and self.calls % self.progress_every == 0:
                    wall = time.perf_counter() - self._wall_start
                    print(
                        f"[progress] {self.label}: {self.calls} steps, "
                        f"{wall:.0f}s elapsed ({wall / self.calls:.2f}s/step)",
                        flush=True,
                    )

        return wrapper


def _resolve(root, dotted: str):
    """Resolve a dotted attribute path from root, or return None if any hop is missing."""

    obj = root
    for part in dotted.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def attach_probes(model) -> dict[str, Probe]:
    """Monkeypatch the cores and tokenizer decode on the loaded model. Returns probes.

    Paths verified against qwen-tts==0.1.1:
      model.model.talker.model                -> 28-layer main transformer core
      model.model.talker.code_predictor.model -> 5-layer code-predictor core
    The speech tokenizer attribute name is discovered defensively across candidates.
    """

    probes: dict[str, Probe] = {}

    targets = [
        # Heartbeat on the main forward: one call per audio frame.
        ("main_forward", "model.talker.model", "forward", 25),
        ("predictor_forward", "model.talker.code_predictor.model", "forward", 0),
    ]
    # Speech tokenizer location is less certain; try a few candidates.
    tokenizer_candidates = ["model.speech_tokenizer", "speech_tokenizer", "model.code2wav"]
    for cand in tokenizer_candidates:
        if _resolve(model, cand) is not None:
            targets.append(("tokenizer_decode", cand, "decode", 0))
            break

    for label, dotted, method, progress_every in targets:
        owner = _resolve(model, dotted)
        if owner is None or not hasattr(owner, method):
            print(f"[profile] WARNING: could not locate {dotted}.{method}; skipping {label}")
            continue
        probe = Probe(label, progress_every=progress_every)
        setattr(owner, method, probe.wrap(getattr(owner, method)))
        probes[label] = probe
        print(f"[profile] probing {dotted}.{method} as {label}")

    if "tokenizer_decode" not in probes:
        print("[profile] WARNING: speech tokenizer decode not found; report excludes it")
    return probes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", choices=sorted(PROMPTS), default="short")
    parser.add_argument("--deterministic", action="store_true", help="greedy decoding")
    return parser.parse_args()


def run() -> None:
    args = parse_args()
    gen_kwargs: dict[str, object] = {}
    if args.deterministic:
        gen_kwargs.update(do_sample=False, subtalker_dosample=False)

    loaded = load_model()
    model = loaded.model
    probes = attach_probes(model)

    text, language = PROMPTS[args.prompt]
    # Warm-up (untimed) so lazy initialization does not skew the split.
    model.generate_voice_clone(text=text, language=language, voice_clone_prompt=loaded.voice_clone_prompt, **gen_kwargs)
    for probe in probes.values():
        probe.calls = 0
        probe.total_s = 0.0

    start = time.perf_counter()
    wavs, sr = model.generate_voice_clone(
        text=text, language=language, voice_clone_prompt=loaded.voice_clone_prompt, **gen_kwargs
    )
    total_s = time.perf_counter() - start
    audio_s = len(wavs[0]) / sr

    print(f"\n=== profile [{args.prompt}] ===")
    print(f"end-to-end: {total_s:.3f} s for {audio_s:.3f} s audio (RTF {total_s / audio_s:.3f})")
    accounted = 0.0
    for label, probe in probes.items():
        pct = 100 * probe.total_s / total_s if total_s else 0.0
        accounted += probe.total_s
        avg_ms = 1000 * probe.total_s / probe.calls if probe.calls else 0.0
        print(f"  {label:18s} {probe.total_s:7.3f} s  {pct:5.1f}%  calls={probe.calls:<5d} avg={avg_ms:6.2f} ms")
    other = total_s - accounted
    print(f"  {'other/glue':18s} {other:7.3f} s  {100 * other / total_s if total_s else 0:5.1f}%")

    main = probes.get("main_forward")
    pred = probes.get("predictor_forward")
    if main and pred and main.calls:
        print(f"\nmain-talker steps: {main.calls}   predictor steps: {pred.calls}   "
              f"predictor/main ratio: {pred.calls / main.calls:.1f}")


if __name__ == "__main__":
    run()

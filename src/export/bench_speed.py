"""Single-backend warm-latency / RTF driver for the 1.7B speed gate (M1.7B-A).

Measures ONE backend per process so the 15 GiB box never has to hold the PyTorch
1.7B model and the OV graphs generating at the same time (test_ov_generation.py's
coupled greedy block does, and OOM-kills at 1.7B). Run it twice and divide:

    python bench_speed.py --backend pytorch ...        # PT median + RTF
    python bench_speed.py --backend ov --model-dir ... # OV median + RTF
    speedup = PT_median_s / OV_median_s

Production sampling (do_sample=True), fixed seed per iter, warm-up discarded.
Reports median/mean seconds, audio seconds, and RTF (s_compute / s_audio).
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import qwen3_tts.openvino.runtime_config as ov_runtime_config  # noqa: F401
from bench_common import load_model


def _generate(model, prompt, text, language):
    wavs, sr = model.generate_voice_clone(
        text=text, language=language, voice_clone_prompt=prompt, do_sample=True
    )
    return wavs[0], sr


def main() -> None:
    import torch

    p = argparse.ArgumentParser()
    p.add_argument("--backend", choices=["pytorch", "ov"], required=True)
    p.add_argument("--model-dir", type=Path, default=None,
                   help="IR dir (required for --backend ov)")
    p.add_argument("--compression", choices=["fp32", "int8"], default="int8")
    p.add_argument("--text", default="The quick brown fox jumps over the lazy dog.")
    p.add_argument("--language", default="English")
    p.add_argument("--threads", type=int, default=6)
    p.add_argument("--warmup", type=int, default=1)
    p.add_argument("--iters", type=int, default=4)
    p.add_argument("--seed", type=int, default=20260628)
    p.add_argument("--release-torch", action="store_true",
                   help="for --backend ov: free PyTorch core layers after install")
    p.add_argument("--output-json", type=Path)
    args = p.parse_args()

    torch.set_num_threads(args.threads)

    loaded = load_model()
    model, prompt = loaded.model, loaded.voice_clone_prompt
    talker = model.model.talker

    runtime = None
    if args.backend == "ov":
        if args.model_dir is None:
            p.error("--model-dir is required for --backend ov")
        from qwen3_tts.openvino.talker import OVTalkerRuntime

        runtime = OVTalkerRuntime(
            args.model_dir, talker, compression=args.compression,
            speech_tokenizer=model.model.speech_tokenizer,
        )
        runtime.install()
        if args.release_torch:
            # one-way; uninstall is suppressed once released
            getattr(runtime, "_release_torch_core_weights", lambda: None)()

    times_s, audio_s = [], []
    try:
        for i in range(args.warmup + args.iters):
            torch.manual_seed(args.seed + i)
            t0 = time.perf_counter()
            wav, sr = _generate(model, prompt, args.text, args.language)
            dt = time.perf_counter() - t0
            dur = len(wav) / sr
            tag = "warmup" if i < args.warmup else f"iter{i - args.warmup}"
            print(f"[{args.backend}] {tag}: {dt:.2f}s compute, {dur:.2f}s audio, "
                  f"RTF {dt / dur:.2f}", flush=True)
            if i >= args.warmup:
                times_s.append(dt)
                audio_s.append(dur)
    finally:
        if runtime is not None:
            try:
                runtime.uninstall()
            except Exception:
                pass

    median = statistics.median(times_s)
    mean = statistics.mean(times_s)
    audio_med = statistics.median(audio_s)
    rtf = median / audio_med
    result = {
        "backend": args.backend,
        "compression": args.compression if args.backend == "ov" else "fp32-pytorch",
        "median_s": round(median, 3),
        "mean_s": round(mean, 3),
        "audio_median_s": round(audio_med, 3),
        "rtf": round(rtf, 3),
        "iters": args.iters,
        "times_s": [round(t, 3) for t in times_s],
        "release_torch": bool(args.release_torch),
    }
    print("[result] " + json.dumps(result), flush=True)
    if args.output_json:
        args.output_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"[result] wrote {args.output_json}", flush=True)


if __name__ == "__main__":
    main()

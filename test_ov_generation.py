#!/usr/bin/env python3
"""Generation-level parity and warm-latency harness for the M4 OpenVINO talker runtime.

This is the harness the plan's M3/M4 framing calls for: it drives the *real*
`generate_voice_clone` path (not synthetic core inputs) once on PyTorch and once with the
OpenVINO cores installed, and reports two things the synthetic core parity could not:

  1. Bounded generated-code agreement under greedy decoding (do_sample=False). Codes are
     captured at the vocoder seam (`speech_tokenizer.decode`), so the comparison is on the
     exact 16-codebook frames that drive the waveform. We report frame agreement, first-
     codebook agreement, the first divergent frame, and the waveform SNR between the two
     greedy outputs.
  2. Warm latency under production sampling: median / p95 / RTF for PyTorch vs OpenVINO,
     the FP32 (or INT8) speedup, and peak RSS / swap delta. This is the early Gate-5 check
     — if the FP32 speedup lands well under 2x, INT8 is load-bearing.

Run on dockermisc1 in the exporter image against a full five-graph export directory, with
the prod qwen3-tts container stopped so the full model load does not swap-thrash:

    MODEL_SIZE=0.6B python test_ov_generation.py --model-dir /ov_output/<versioned-dir>

Greedy decoding does not emit EOS (it runs to max_new_tokens), so --code-steps bounds the
deterministic comparison. Writes ov_generation_report.json beside the IR files.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

# Sets thread env before torch/openvino import (import side effect).
import ov_runtime_config  # noqa: F401
from bench_common import (
    fmt_mib,
    load_model,
    peak_rss_bytes,
    read_swap_counters,
    summarize,
    swap_delta,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--compression", choices=["fp32", "int8"], default=None,
                        help="which IR set to load; defaults to the metadata's declared compression")
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--text", default="The quick brown fox jumps over the lazy dog.",
                        help="prompt used for both code-agreement and latency")
    parser.add_argument("--language", default="English")
    parser.add_argument("--code-steps", type=int, default=96,
                        help="bounded max_new_tokens for the deterministic greedy code comparison")
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--iters", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260628)
    parser.add_argument("--min-frame-agreement", type=float, default=0.98,
                        help="soft gate: frame agreement up to first divergence (report-only unless --strict)")
    parser.add_argument("--min-waveform-snr", type=float, default=30.0,
                        help="soft gate: greedy PyTorch-vs-OV waveform SNR in dB")
    parser.add_argument("--strict", action="store_true",
                        help="exit nonzero if a soft gate fails")
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args()


class _CodeCapture:
    """Record the 16-codebook frames handed to speech_tokenizer.decode for one generation."""

    def __init__(self, speech_tokenizer):
        self._st = speech_tokenizer
        self._orig = speech_tokenizer.decode
        self.codes: list[np.ndarray] = []

    def __enter__(self) -> "_CodeCapture":
        def capturing_decode(inputs, *args, **kwargs):
            self.codes = []
            for item in inputs:
                codes = item["audio_codes"]
                arr = codes.detach().cpu().numpy() if hasattr(codes, "detach") else np.asarray(codes)
                self.codes.append(np.array(arr, copy=True))
            return self._orig(inputs, *args, **kwargs)

        self._st.decode = capturing_decode
        return self

    def __exit__(self, *exc) -> None:
        self._st.decode = self._orig


def _generate(model, prompt, text, language, **gen_kwargs):
    wavs, sr = model.generate_voice_clone(
        text=text, language=language, voice_clone_prompt=prompt, **gen_kwargs
    )
    return wavs[0], sr


def _waveform_snr(reference: np.ndarray, candidate: np.ndarray) -> float:
    n = min(len(reference), len(candidate))
    reference, candidate = reference[:n], candidate[:n]
    error_rms = float(np.sqrt(np.mean(np.square(reference - candidate))))
    signal_rms = float(np.sqrt(np.mean(np.square(reference))))
    return float(20.0 * np.log10(max(signal_rms, 1e-12) / max(error_rms, 1e-12)))


def _compare_codes(pt_codes: np.ndarray, ov_codes: np.ndarray) -> dict:
    """Frame/codebook agreement and first divergence between two [16, frames] code tensors."""
    pt = np.squeeze(pt_codes)
    ov = np.squeeze(ov_codes)
    frames = min(pt.shape[-1], ov.shape[-1])
    pt, ov = pt[..., :frames], ov[..., :frames]

    frame_equal = np.all(pt == ov, axis=0)  # all 16 codebooks agree at each frame
    first_codebook_equal = pt[0] == ov[0]
    diverged = np.where(~frame_equal)[0]
    first_divergence = int(diverged[0]) if diverged.size else -1
    pre = first_divergence if first_divergence >= 0 else frames

    return {
        "frames_compared": int(frames),
        "pt_frames": int(pt.shape[-1]),
        "ov_frames": int(ov.shape[-1]),
        "frame_agreement": float(np.mean(frame_equal)),
        "first_codebook_agreement": float(np.mean(first_codebook_equal)),
        "first_divergence_frame": first_divergence,
        "agreement_before_divergence": 1.0 if pre == frames else float(pre) / max(frames, 1),
    }


def _measure_latency(model, prompt, text, language, *, warmup, iters, seed):
    import torch

    audio_s, times_s = [], []
    for i in range(warmup + iters):
        torch.manual_seed(seed + i)
        started = time.perf_counter()
        wav, sr = _generate(model, prompt, text, language, do_sample=True)
        elapsed = time.perf_counter() - started
        if i >= warmup:
            times_s.append(elapsed)
            audio_s.append(len(wav) / sr)
    return summarize(times_s, audio_s)


def run() -> int:
    args = parse_args()
    import torch

    torch.set_num_threads(args.threads)

    loaded = load_model()
    model, prompt = loaded.model, loaded.voice_clone_prompt
    hf_model = model.model
    talker = hf_model.talker
    speech_tokenizer = hf_model.speech_tokenizer

    from ov_talker_runtime import OVTalkerRuntime

    runtime = OVTalkerRuntime(args.model_dir, talker, compression=args.compression)
    metadata = json.loads((args.model_dir / "metadata.json").read_text(encoding="utf-8"))

    # ── Greedy generated-code agreement (bounded) ───────────────────────────────
    print("[gen-parity] greedy PyTorch reference ...", flush=True)
    with _CodeCapture(speech_tokenizer) as cap:
        pt_wav, sr = _generate(
            model, prompt, args.text, args.language,
            do_sample=False, max_new_tokens=args.code_steps,
        )
        pt_codes = cap.codes[0]

    print("[gen-parity] greedy OpenVINO candidate ...", flush=True)
    runtime.install()
    try:
        with _CodeCapture(speech_tokenizer) as cap:
            ov_wav, _ = _generate(
                model, prompt, args.text, args.language,
                do_sample=False, max_new_tokens=args.code_steps,
            )
            ov_codes = cap.codes[0]
    finally:
        runtime.uninstall()

    code_agreement = _compare_codes(pt_codes, ov_codes)
    waveform_snr = _waveform_snr(pt_wav, ov_wav)

    # ── Warm latency: PyTorch baseline vs OpenVINO (production sampling) ─────────
    print("[latency] PyTorch baseline ...", flush=True)
    swap_before = read_swap_counters()
    pt_latency = _measure_latency(
        model, prompt, args.text, args.language,
        warmup=args.warmup, iters=args.iters, seed=args.seed,
    )

    print(f"[latency] OpenVINO ({runtime.compression}) ...", flush=True)
    runtime.install()
    try:
        ov_latency = _measure_latency(
            model, prompt, args.text, args.language,
            warmup=args.warmup, iters=args.iters, seed=args.seed,
        )
    finally:
        runtime.uninstall()
    swap_after = read_swap_counters()

    speedup = (pt_latency["median_s"] / ov_latency["median_s"]
               if ov_latency["median_s"] else float("nan"))
    peak_rss = peak_rss_bytes()

    failures = []
    if code_agreement["agreement_before_divergence"] < args.min_frame_agreement:
        failures.append(
            f"frame agreement before divergence {code_agreement['agreement_before_divergence']:.3f}"
            f" below {args.min_frame_agreement}"
        )
    if waveform_snr < args.min_waveform_snr:
        failures.append(f"greedy waveform SNR {waveform_snr:.1f} dB below {args.min_waveform_snr} dB")

    report = {
        "model_repo": metadata["model_repo"],
        "model_revision": metadata["model_revision"],
        "source_commit": metadata.get("source_commit"),
        "compression": runtime.compression,
        "threads": args.threads,
        "seed": args.seed,
        "prompt": args.text,
        "code_steps": args.code_steps,
        "greedy_code_agreement": code_agreement,
        "greedy_waveform_snr_db": round(waveform_snr, 2),
        "latency": {
            "pytorch": pt_latency,
            "openvino": ov_latency,
            "speedup_median": round(speedup, 3),
            "gate5_2x_met": speedup >= 2.0,
        },
        "peak_rss_mib": round(peak_rss / (1024 * 1024), 1),
        "swap_delta": swap_delta(swap_before, swap_after),
        "failures": failures,
        "NOTE": (
            "Greedy comparison is bounded (no EOS under do_sample=False). FP32 numerical "
            "differences can cause argmax divergence that cascades through code feedback; "
            "agreement_before_divergence and waveform SNR are the load-bearing signals. "
            "Speedup is the early Gate-5 check: FP32 well under 2x makes INT8 load-bearing."
        ),
    }

    output_path = args.output_json or args.model_dir / "ov_generation_report.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(
        f"\n[summary] code frames {code_agreement['frames_compared']}, "
        f"first divergence {code_agreement['first_divergence_frame']}, "
        f"waveform SNR {waveform_snr:.1f} dB | "
        f"speedup {speedup:.2f}x (PyTorch {pt_latency['median_s']}s -> "
        f"OV {ov_latency['median_s']}s), peak RSS {fmt_mib(peak_rss)}",
        flush=True,
    )
    return 1 if (args.strict and failures) else 0


if __name__ == "__main__":
    raise SystemExit(run())

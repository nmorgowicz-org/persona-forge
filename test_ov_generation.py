#!/usr/bin/env python3
"""Generation-level parity, sampled-audio quality, and warm-latency harness for the M4 OpenVINO talker runtime.

Modes:
  greedy (default):
    - Bounded generated-code agreement under do_sample=False.
    - Warm latency under production sampling.
    - Greedy is a debug signal, NOT the ship gate.

  sampled-quality:
    - Production-sampling (do_sample=True) quality check: for each iteration with the same
      seed, compare PyTorch and OV on codes, waveform SNR, duration, and energy.
    - Acceptance criteria are conservative red-flag filters; listening tests are still mandatory.

  all:
    - Runs both greedy and sampled-quality.

Writes ov_generation_report.json beside the IR files.
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
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

# Qwen3-TTS 12 Hz uses 16 acoustic codebooks per frame; used only to orient captured
# code tensors (the codebook axis is fixed-size, the frame axis is long/variable).
NUM_CODEBOOKS = 16


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

    # Mode selection
    parser.add_argument("--mode",
                        choices=["greedy", "sampled-quality", "logits-parity", "all"],
                        default="greedy",
                        help=(
                            "run mode: "
                            "greedy (debug-only), "
                            "sampled-quality (production-sampling), "
                            "logits-parity (diagnose frame-160 divergence), "
                            "or all (greedy+sampled-quality+logits-parity)"
                        ))
    parser.add_argument("--sampled-iters", type=int, default=10,
                        help="number of sampled-quality iterations (default: 10)")
    parser.add_argument("--strict-greedy", action="store_true",
                        help="treat greedy gates as hard (off by default; greedy is debug-only)")

    # Legacy: map --strict to --strict-greedy when greedy is run
    parser.add_argument("--min-frame-agreement", type=float, default=0.98,
                        help="soft gate: frame agreement up to first divergence (report-only unless --strict-greedy)")
    parser.add_argument("--min-waveform-snr", type=float, default=30.0,
                        help="soft gate: greedy PyTorch-vs-OV waveform SNR in dB")
    parser.add_argument("--strict", action="store_true",
                        help="(legacy alias: same as --strict-greedy)")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument(
        "--logits-max-frames",
        type=int,
        default=170,
        help="max frames to compare in logits-parity mode before stopping",
    )
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


def _as_frames_by_codebooks(codes: np.ndarray) -> np.ndarray:
    """Normalize a captured code tensor to [frames, codebooks].

    The capture point yields [frames, codebooks] (e.g. [255, 16]); some code paths
    emit the transpose [codebooks, frames]. Orient by the codebook axis, which has the
    fixed small size NUM_CODEBOOKS while frames is the long, variable axis.
    """
    a = np.asarray(codes)
    # Remove leading batch dim(s) safely (e.g. [1, frames, 16] -> [frames, 16]).
    if a.ndim == 3 and a.shape[0] == 1:
        a = a[0]
    if a.ndim == 4 and a.shape[0] == 1 and a.shape[1] == 1:
        a = a[0, 0]
    # Now enforce 2D: [frames, codebooks] or [codebooks, frames].
    if a.ndim != 2:
        raise ValueError(
            f"_as_frames_by_codebooks: unexpected shape {a.shape} after squeeze"
        )
    if a.shape[0] == NUM_CODEBOOKS and a.shape[1] != NUM_CODEBOOKS:
        a = a.T
    return a


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a = a.ravel()
    b = b.ravel()
    dot = float(np.dot(a, b))
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return dot / (na * nb)


def _compare_codes(pt_codes: np.ndarray, ov_codes: np.ndarray) -> dict:
    """Frame/codebook agreement and first divergence between two code tensors.

    Greedy PyTorch and OpenVINO decodes can terminate at different frame counts when
    numerical drift flips an argmax (which cascades through autoregression and shifts
    EOS). Agreement is measured over the common frame prefix; the differing total
    lengths are reported separately so an early divergence is not hidden.
    """
    pt = _as_frames_by_codebooks(pt_codes)
    ov = _as_frames_by_codebooks(ov_codes)
    pt_frames, ov_frames = pt.shape[0], ov.shape[0]
    frames = min(pt_frames, ov_frames)
    pt, ov = pt[:frames], ov[:frames]

    frame_equal = np.all(pt == ov, axis=1)  # all codebooks agree at each frame
    first_codebook_equal = pt[:, 0] == ov[:, 0]
    diverged = np.where(~frame_equal)[0]
    first_divergence = int(diverged[0]) if diverged.size else -1
    pre = first_divergence if first_divergence >= 0 else frames

    return {
        "frames_compared": int(frames),
        "pt_frames": int(pt_frames),
        "ov_frames": int(ov_frames),
        "length_match": bool(pt_frames == ov_frames),
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


def _compute_sampled_run_metrics(
    pt_wav: np.ndarray,
    ov_wav: np.ndarray,
    pt_codes: np.ndarray,
    ov_codes: np.ndarray,
    sr: int,
) -> dict:
    """Per-iteration metrics for one sampled (do_sample=True) quality run."""
    # Waveform SNR
    waveform_snr_db = _waveform_snr(pt_wav, ov_wav)

    # RMS energy
    rms_energy_pt = float(np.sqrt(np.mean(np.square(pt_wav))))
    rms_energy_ov = float(np.sqrt(np.mean(np.square(ov_wav))))

    # Duration
    duration_pt = len(pt_wav) / sr
    duration_ov = len(ov_wav) / sr

    # Codebook-level match
    pt_c = _as_frames_by_codebooks(pt_codes)
    ov_c = _as_frames_by_codebooks(ov_codes)
    frames = min(pt_c.shape[0], ov_c.shape[0])
    pt_c, ov_c = pt_c[:frames], ov_c[:frames]

    total = frames * pt_c.shape[1]
    matches = int(np.sum(pt_c == ov_c))
    overall_codebook_match_rate = matches / max(total, 1)

    per_codebook_match_rates = []
    for cb in range(pt_c.shape[1]):
        m = float(np.mean(pt_c[:, cb] == ov_c[:, cb]))
        per_codebook_match_rates.append(round(m, 4))

    # Per-codebook entropy (token diversity).
    def _codebook_entropy(codes_col: np.ndarray) -> float:
        unique, counts = np.unique(codes_col, return_counts=True)
        probs = counts / max(counts.sum(), 1)
        return float(-np.sum(probs * np.log(probs + 1e-12)))

    per_codebook_entropy_pt = []
    per_codebook_entropy_ov = []
    for cb in range(pt_c.shape[1]):
        per_codebook_entropy_pt.append(round(_codebook_entropy(pt_c[:, cb]), 4))
        per_codebook_entropy_ov.append(round(_codebook_entropy(ov_c[:, cb]), 4))

    return {
        "waveform_snr_db": round(waveform_snr_db, 2),
        "overall_codebook_match_rate": round(overall_codebook_match_rate, 4),
        "rms_energy_pt": round(rms_energy_pt, 6),
        "rms_energy_ov": round(rms_energy_ov, 6),
        "duration_pt": round(duration_pt, 3),
        "duration_ov": round(duration_ov, 3),
        "per_codebook_match_rates": per_codebook_match_rates,
        "per_codebook_entropy_pt": per_codebook_entropy_pt,
        "per_codebook_entropy_ov": per_codebook_entropy_ov,
    }


def run_sampled_quality(args, model, prompt, runtime) -> dict:
    """Sampled-audio quality check (Step 3).

    For each iteration i:
      - torch.manual_seed(base_seed + i)
      - PyTorch: generate_voice_clone(do_sample=True)
      - same seed
      - OV: generate_voice_clone(do_sample=True)
      - compare codes, waveform, duration, energy

    Aggregates across iterations and applies conservative red-flag acceptance criteria.
    """
    import torch

    base_seed = args.seed
    n = args.sampled_iters

    per_run = []
    for i in range(n):
        print(f"[sampled-quality] run {i+1}/{n} PyTorch ...", flush=True)
        torch.manual_seed(base_seed + i)
        with _CodeCapture(model.model.speech_tokenizer) as cap_pt:
            pt_wav, pt_sr = _generate(
                model, prompt, args.text, args.language,
                do_sample=True,
            )
            pt_codes = cap_pt.codes[0]

        print(f"[sampled-quality] run {i+1}/{n} OpenVINO ...", flush=True)
        torch.manual_seed(base_seed + i)
        runtime.install()
        try:
            with _CodeCapture(model.model.speech_tokenizer) as cap_ov:
                ov_wav, ov_sr = _generate(
                    model, prompt, args.text, args.language,
                    do_sample=True,
                )
                ov_codes = cap_ov.codes[0]
        finally:
            runtime.uninstall()

        m = _compute_sampled_run_metrics(pt_wav, ov_wav, pt_codes, ov_codes, pt_sr)
        per_run.append(m)
        print(
            f"  SNR={m['waveform_snr_db']} dB | "
            f"match={m['overall_codebook_match_rate']:.3f} | "
            f"dur_pt={m['duration_pt']}s dur_ov={m['duration_ov']}s",
            flush=True,
        )

    # Aggregate
    snrs = [r["waveform_snr_db"] for r in per_run]
    match_rates = [r["overall_codebook_match_rate"] for r in per_run]
    duration_ratios = [
        r["duration_ov"] / r["duration_pt"]
        if r["duration_pt"] > 0 else float("nan")
        for r in per_run
    ]
    energy_ratios = [
        r["rms_energy_ov"] / r["rms_energy_pt"]
        if r["rms_energy_pt"] > 0 else float("nan")
        for r in per_run
    ]

    # Per-codebook mean and minimum across all runs
    per_cb_all = np.array([r["per_codebook_match_rates"] for r in per_run])
    per_cb_mean = per_cb_all.mean(axis=0).tolist()
    min_per_cb = float(per_cb_all.min())

    agg = {
        "iterations": n,
        "median_waveform_snr_db": round(statistics.median(snrs), 2),
        "mean_overall_codebook_match_rate": round(float(np.mean(match_rates)), 4),
        "mean_duration_ratio": round(float(np.mean(duration_ratios)), 4),
        "mean_energy_ratio": round(float(np.mean(energy_ratios)), 4),
        "min_per_codebook_match_rate": round(min_per_cb, 4),
        "per_codebook_match_rates": [round(v, 4) for v in per_cb_mean],
    }

    # Acceptance criteria (conservative red-flag filters)
    failures = []

    if agg["median_waveform_snr_db"] < 15.0:
        failures.append(
            f"median_waveform_snr_db {agg['median_waveform_snr_db']:.2f} < 15 dB"
        )
    if agg["mean_overall_codebook_match_rate"] < 0.70:
        failures.append(
            f"mean_overall_codebook_match_rate {agg['mean_overall_codebook_match_rate']:.3f} < 0.70"
        )
    if agg["min_per_codebook_match_rate"] < 0.55:
        failures.append(
            f"min_per_codebook_match_rate {agg['min_per_codebook_match_rate']:.3f} < 0.55"
        )

    dr = agg["mean_duration_ratio"]
    if not (0.85 <= dr <= 1.15):
        failures.append(f"mean_duration_ratio {dr:.3f} outside [0.85, 1.15]")

    er = agg["mean_energy_ratio"]
    if not (0.7 <= er <= 1.4):
        failures.append(f"mean_energy_ratio {er:.3f} outside [0.7, 1.4]")

    agg["failures"] = failures
    agg["per_run"] = per_run
    return agg


def run_logits_parity(args, model, prompt, runtime) -> dict:
    """Logits-parity mode (Step 4).

    Non-invasive: monkey-patches talker.codec_head.forward to capture first-
    codebook logits at each autoregressive step. Greedy mode, same inputs for
    PyTorch and OV. For each step up to --logits-max-frames, compares:

      - max_abs_diff
      - mean_abs_diff
      - cosine_sim
      - argmax_pt vs argmax_ov

    The first step where argmax differs is the argmax-flip frame.
    """
    import torch

    talker = model.model.talker
    codec_head = talker.codec_head
    max_frames = args.logits_max_frames
    max_tokens = max(max_frames + 10, args.code_steps)

    # --- (A) PyTorch logits ---
    pt_logits_list: list[np.ndarray] = []
    orig_forward = codec_head.forward

    def _capture_pt(x, *a, **kw):
        out = orig_forward(x, *a, **kw)
        pt_logits_list.append(
            np.array(out[0, -1, :].detach().cpu().numpy(),
                     dtype=np.float32, copy=True)
        )
        return out

    codec_head.forward = _capture_pt
    torch.manual_seed(args.seed)

    try:
        _generate(
            model, prompt, args.text, args.language,
            do_sample=False, max_new_tokens=max_tokens,
        )
    finally:
        codec_head.forward = orig_forward

    # --- (B) OV logits ---
    ov_logits_list: list[np.ndarray] = []
    runtime.install()
    orig_forward = codec_head.forward

    def _capture_ov(x, *a, **kw):
        out = orig_forward(x, *a, **kw)
        ov_logits_list.append(
            np.array(out[0, -1, :].detach().cpu().numpy(),
                     dtype=np.float32, copy=True)
        )
        return out

    codec_head.forward = _capture_ov
    torch.manual_seed(args.seed)

    try:
        _generate(
            model, prompt, args.text, args.language,
            do_sample=False, max_new_tokens=max_tokens,
        )
    finally:
        codec_head.forward = orig_forward
        runtime.uninstall()

    # --- (C) Compare per step ---
    steps = min(len(pt_logits_list), len(ov_logits_list), max_frames)
    per_step = []
    first_argmax_mismatch = None
    max_drift_step = 0
    max_drift_max_abs = 0.0

    for s in range(steps):
        l_pt = pt_logits_list[s]
        l_ov = ov_logits_list[s]

        argmax_pt = int(np.argmax(l_pt))
        argmax_ov = int(np.argmax(l_ov))
        agree = bool(argmax_pt == argmax_ov)

        if not agree and first_argmax_mismatch is None:
            first_argmax_mismatch = s

        mad = float(np.max(np.abs(l_pt - l_ov)))
        mae = float(np.mean(np.abs(l_pt - l_ov)))
        cs = _cosine_similarity(l_pt, l_ov)

        if mad > max_drift_max_abs:
            max_drift_max_abs = mad
            max_drift_step = s

        per_step.append({
            "step": s,
            "max_abs_diff": round(mad, 8),
            "mean_abs_diff": round(mae, 8),
            "cosine_sim": round(cs, 6),
            "argmax_agree": agree,
        })

    # --- Determine NOTE ---
    note = ""
    if first_argmax_mismatch is not None:
        # Simple smoothness check: if drift at mismatch is within 10x the
        # early average, treat as accumulated drift; else anomaly.
        n_sample = max(1, steps // 5)
        early_avg = float(np.mean(
            [p["max_abs_diff"] for p in per_step[:n_sample]]
        ))
        mismatch_mad = per_step[first_argmax_mismatch]["max_abs_diff"]
        if early_avg > 0 and mismatch_mad < 10.0 * early_avg:
            note = (
                "Consistent with accumulated FP32 drift; "
                "sampled-audio quality is the correct ship gate."
            )
        else:
            note = "Anomaly detected; investigate mask/seam."
    else:
        note = (
            f"No argmax divergence within {steps} frames; "
            f"max frames reached."
        )

    return {
        "iterations": 1,
        "max_frames": max_frames,
        "steps_compared": steps,
        "per_step": per_step,
        "first_argmax_mismatch_frame": first_argmax_mismatch,
        "max_drift_step": max_drift_step,
        "max_drift_max_abs_diff": round(max_drift_max_abs, 8),
        "NOTE": note,
    }


def run() -> int:
    args = parse_args()
    import torch

    # Normalize legacy --strict to --strict-greedy (always)
    if args.strict:
        args.strict_greedy = True

    torch.set_num_threads(args.threads)

    loaded = load_model()
    model, prompt = loaded.model, loaded.voice_clone_prompt
    hf_model = model.model
    talker = hf_model.talker
    speech_tokenizer = hf_model.speech_tokenizer

    from ov_talker_runtime import OVTalkerRuntime

    runtime = OVTalkerRuntime(args.model_dir, talker, compression=args.compression)
    metadata = json.loads((args.model_dir / "metadata.json").read_text(encoding="utf-8"))

    exit_code = 0
    all_failures: list[str] = []

    run_greedy = args.mode in ("greedy", "all")
    run_sampled = args.mode in ("sampled-quality", "all")
    run_logits = args.mode in ("logits-parity", "all")

    # ── Greedy mode (unchanged behavior) ─────────────────────────────────────────
    greedy_section = {}
    if run_greedy:
        print("[gen-parity] greedy PyTorch reference ...", flush=True)
        torch.manual_seed(args.seed)
        with _CodeCapture(speech_tokenizer) as cap:
            pt_wav, sr = _generate(
                model, prompt, args.text, args.language,
                do_sample=False, max_new_tokens=args.code_steps,
            )
            pt_codes = cap.codes[0]

        print("[gen-parity] greedy OpenVINO candidate ...", flush=True)
        runtime.install()
        torch.manual_seed(args.seed)
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

        # Warm latency: PyTorch baseline vs OpenVINO (production sampling)
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

        greedy_failures = []
        if code_agreement["agreement_before_divergence"] < args.min_frame_agreement:
            greedy_failures.append(
                f"frame agreement before divergence {code_agreement['agreement_before_divergence']:.3f}"
                f" below {args.min_frame_agreement}"
            )
        if waveform_snr < args.min_waveform_snr:
            greedy_failures.append(
                f"greedy waveform SNR {waveform_snr:.1f} dB below {args.min_waveform_snr} dB"
            )

        if args.strict_greedy:
            all_failures.extend(greedy_failures)

        greedy_section = {
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
            "failures": greedy_failures,
        }

        print(
            f"\n[greedy-summary] code frames {code_agreement['frames_compared']}, "
            f"first divergence {code_agreement['first_divergence_frame']}, "
            f"waveform SNR {waveform_snr:.1f} dB | "
            f"speedup {speedup:.2f}x (PyTorch {pt_latency['median_s']}s -> "
            f"OV {ov_latency['median_s']}s), peak RSS {fmt_mib(peak_rss)}",
            flush=True,
        )

    # ── Sampled-quality mode ────────────────────────────────────────────────────
    sampled_section = {}
    if run_sampled:
        # Help with memory when --mode=all and both PT+OV models are loaded.
        gc.collect()
        sampled_section = run_sampled_quality(args, model, prompt, runtime)
        if sampled_section["failures"]:
            all_failures.extend(sampled_section["failures"])

    # ── Logits-parity mode ──────────────────────────────────────────────────────
    logits_section = {}
    if run_logits:
        # Help with memory when --mode=all and both PT+OV models are loaded.
        gc.collect()
        print("[logits-parity] running ...", flush=True)
        logits_section = run_logits_parity(args, model, prompt, runtime)
        if logits_section["first_argmax_mismatch_frame"] is not None:
            print(
                f"[logits-parity] first_argmax_mismatch_frame="
                f"{logits_section['first_argmax_mismatch_frame']}",
                flush=True,
            )
        print(f"[logits-parity] {logits_section['NOTE']}", flush=True)

    # ── Compose report ──────────────────────────────────────────────────────────
    report = {
        "mode": args.mode,
        "model_repo": metadata["model_repo"],
        "model_revision": metadata["model_revision"],
        "source_commit": metadata.get("source_commit"),
        "compression": runtime.compression,
        "threads": args.threads,
        "seed": args.seed,
        "prompt": args.text,
        "code_steps": args.code_steps,
    }

    if greedy_section:
        report.update(greedy_section)

    if sampled_section:
        report["sampled_quality"] = sampled_section

    if logits_section:
        report["logits_parity"] = logits_section

    report["failures"] = all_failures
    report["NOTE"] = (
        "Greedy comparison is debug-only (no EOS under do_sample=False). "
        "Greedy argmax divergence cascades through code feedback and should not be used "
        "as the sole ship gate. "
        "For ship decisions, rely on sampled_quality (production sampling) plus listening tests. "
        "For diagnosing frame-160 divergence, use mode=logits-parity."
    )

    output_path = args.output_json or args.model_dir / "ov_generation_report.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    if all_failures:
        print("\n[FAILURES]", flush=True)
        for f in all_failures:
            print(f"  - {f}", flush=True)
        exit_code = 1
    else:
        print("\n[OK] all active gates passed (listening tests still required)", flush=True)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(run())

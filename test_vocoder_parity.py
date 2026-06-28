#!/usr/bin/env python3
"""Validate stock PyTorch, export-wrapper, FP32 IR, and INT8 IR vocoder outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from export_openvino import _resolve_vocoder_decoder, _set_eager_attention
from model_config import configure_hf_token
from ov_export_wrappers import VocoderDecoderWrapper


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--sequence-lengths", nargs="+", type=int, default=[8, 32, 300, 325])
    parser.add_argument("--seed", type=int, default=20260628)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--int8-model", default="vocoder_decoder_int8.xml")
    parser.add_argument("--fp32-max-abs", type=float, default=1e-4)
    parser.add_argument("--int8-max-abs", type=float, default=5e-3)
    # SNR gates override max-abs for architectures (e.g. GAN vocoder) where floating-point
    # accumulation reordering in conv layers causes legitimate single-sample outliers that
    # don't represent perceptible audio degradation.  When set, a sequence length passes if
    # SNR >= threshold even if max_abs exceeds the max-abs threshold.
    parser.add_argument("--fp32-min-snr", type=float, default=None,
                        help="minimum acceptable FP32 SNR (dB); overrides --fp32-max-abs when set")
    parser.add_argument("--int8-min-snr", type=float, default=None,
                        help="minimum acceptable INT8 SNR (dB); overrides --int8-max-abs when set")
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args()


def _metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    absolute = np.abs(reference - candidate)
    relative = absolute / np.maximum(np.abs(reference), 1e-6)
    error_rms = float(np.sqrt(np.mean(np.square(reference - candidate))))
    signal_rms = float(np.sqrt(np.mean(np.square(reference))))
    snr_db = float(20.0 * np.log10(max(signal_rms, 1e-12) / max(error_rms, 1e-12)))
    return {
        "max_abs": float(absolute.max(initial=0.0)),
        "mean_abs": float(absolute.mean()),
        "p99_abs": float(np.percentile(absolute, 99)),
        "p999_abs": float(np.percentile(absolute, 99.9)),
        "error_rms": error_rms,
        "signal_rms": signal_rms,
        "snr_db": snr_db,
        "max_rel": float(relative.max(initial=0.0)),
        "mean_rel": float(relative.mean()),
    }


def _timed(callable_):
    started = time.perf_counter()
    value = callable_()
    return value, time.perf_counter() - started


def _infer(compiled_model, codes: np.ndarray) -> np.ndarray:
    return np.asarray(compiled_model([codes])[0])


def run() -> int:
    args = parse_args()
    if not args.sequence_lengths or any(length <= 0 for length in args.sequence_lengths):
        raise SystemExit("--sequence-lengths must contain positive integers")

    metadata_path = args.model_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    fixed_input_frames = metadata["vocoder_input_frames"]
    if any(length > fixed_input_frames for length in args.sequence_lengths):
        raise SystemExit(
            f"sequence lengths cannot exceed fixed vocoder input {fixed_input_frames}"
        )
    required_graphs = {"vocoder_decoder.xml", args.int8_model}
    missing = sorted(name for name in required_graphs if not (args.model_dir / name).is_file())
    if missing:
        raise SystemExit(f"missing vocoder IR files: {missing}")

    configure_hf_token()
    import openvino as ov
    import torch
    from qwen_tts import Qwen3TTSModel

    torch.set_num_threads(args.threads)
    wrapped = Qwen3TTSModel.from_pretrained(
        metadata["model_repo"],
        revision=metadata["model_revision"],
        device_map="cpu",
        dtype=torch.float32,
        attn_implementation="eager",
    )
    decoder = _resolve_vocoder_decoder(wrapped.model.speech_tokenizer).eval()
    _set_eager_attention(decoder)
    export_wrapper = VocoderDecoderWrapper(decoder).eval()

    ov_config = {
        "PERFORMANCE_HINT": "LATENCY",
        "NUM_STREAMS": "1",
        "INFERENCE_NUM_THREADS": str(args.threads),
        # The CPU plugin may otherwise lower eligible FP32 operations to BF16.
        # Parity must measure the converted graph before reduced-precision execution.
        "INFERENCE_PRECISION_HINT": "f32",
    }
    core = ov.Core()
    fp32 = core.compile_model(args.model_dir / "vocoder_decoder.xml", "CPU", ov_config)
    int8 = core.compile_model(args.model_dir / args.int8_model, "CPU", ov_config)

    results = []
    failures = []
    for length in args.sequence_lengths:
        generator = torch.Generator(device="cpu").manual_seed(args.seed + length)
        codes = torch.randint(
            0,
            decoder.config.codebook_size,
            (1, decoder.config.num_quantizers, length),
            generator=generator,
            dtype=torch.long,
        )
        with torch.inference_mode():
            torch_output, torch_seconds = _timed(lambda: decoder(codes))
            padded_codes = torch.nn.functional.pad(
                codes, (0, fixed_input_frames - length), value=0
            )
            wrapper_output, wrapper_seconds = _timed(lambda: export_wrapper(padded_codes))
        reference = torch_output.detach().cpu().numpy()
        expected_samples = length * metadata["vocoder_dims"]["total_upsample"]
        wrapper_array = wrapper_output[..., :expected_samples].detach().cpu().numpy()

        row = {
            "sequence_length": length,
            "expected_output_samples": expected_samples,
            "torch_seconds": torch_seconds,
            "wrapper_seconds": wrapper_seconds,
            "wrapper": _metrics(reference, wrapper_array),
        }
        try:
            fp32_full, fp32_seconds = _timed(lambda: _infer(fp32, padded_codes.numpy()))
            int8_full, int8_seconds = _timed(lambda: _infer(int8, padded_codes.numpy()))
            fp32_output = fp32_full[..., :expected_samples]
            int8_output = int8_full[..., :expected_samples]
            row.update(
                {
                    "ir_output_shape": list(fp32_full.shape),
                    "actual_output_shape": list(fp32_output.shape),
                    "fp32_seconds": fp32_seconds,
                    "int8_seconds": int8_seconds,
                    "fp32": _metrics(reference, fp32_output),
                    "int8": _metrics(fp32_output, int8_output),
                }
            )
            if fp32_output.shape != reference.shape:
                failures.append(
                    f"length {length}: FP32 shape {fp32_output.shape} != {reference.shape}"
                )
            if int8_output.shape != reference.shape:
                failures.append(
                    f"length {length}: INT8 shape {int8_output.shape} != {reference.shape}"
                )
            if row["wrapper"]["max_abs"] >= 1e-6:
                failures.append(f"length {length}: wrapper seam exceeded 1e-6")
            fp32_snr = row["fp32"].get("snr_db")
            if args.fp32_min_snr is not None and fp32_snr is not None:
                if fp32_snr < args.fp32_min_snr:
                    failures.append(
                        f"length {length}: FP32 SNR {fp32_snr:.1f} dB below {args.fp32_min_snr} dB"
                    )
            elif row["fp32"]["max_abs"] >= args.fp32_max_abs:
                failures.append(f"length {length}: FP32 exceeded {args.fp32_max_abs}")
            int8_snr = row["int8"].get("snr_db")
            if args.int8_min_snr is not None and int8_snr is not None:
                if int8_snr < args.int8_min_snr:
                    failures.append(
                        f"length {length}: INT8 SNR {int8_snr:.1f} dB below {args.int8_min_snr} dB"
                    )
            elif row["int8"]["max_abs"] >= args.int8_max_abs:
                failures.append(f"length {length}: INT8 exceeded {args.int8_max_abs}")
        except Exception as exc:
            row["inference_error"] = f"{type(exc).__name__}: {exc}"
            failures.append(f"length {length}: OpenVINO inference failed: {exc}")
        results.append(row)

    report = {
        "model_repo": metadata["model_repo"],
        "model_revision": metadata["model_revision"],
        "source_commit": metadata["source_commit"],
        "exporter_image_digest": metadata["exporter_image_digest"],
        "ir_metadata_sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
        "openvino_version": ov.__version__,
        "seed": args.seed,
        "threads": args.threads,
        "inference_precision_hint": "f32",
        "int8_model": args.int8_model,
        "fp32_max_abs_tolerance": args.fp32_max_abs,
        "fp32_min_snr_db": args.fp32_min_snr,
        "int8_max_abs_tolerance": args.int8_max_abs,
        "int8_min_snr_db": args.int8_min_snr,
        "results": results,
        "failures": failures,
    }
    output_path = args.output_json or args.model_dir / "vocoder_parity.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run())

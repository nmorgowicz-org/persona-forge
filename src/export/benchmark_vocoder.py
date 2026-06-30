"""Benchmark warm PyTorch, FP32 OpenVINO, and INT8 OpenVINO vocoder latency."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import statistics
import time
from pathlib import Path

import numpy as np

from export_openvino import _resolve_vocoder_decoder, _set_eager_attention
from qwen3_tts.model_config import configure_hf_token


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--sequence-length", type=int, default=325)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--warmup-iterations", type=int, default=1)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260628)
    parser.add_argument("--int8-model", default="vocoder_decoder_int8.xml")
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args()


def _measure(callable_, warmups: int, iterations: int) -> dict[str, object]:
    for _ in range(warmups):
        callable_()
    samples = []
    for _ in range(iterations):
        started = time.perf_counter()
        callable_()
        samples.append(time.perf_counter() - started)
    return {
        "samples_seconds": samples,
        "median_seconds": statistics.median(samples),
        "p95_seconds": float(np.percentile(samples, 95)),
    }


def run() -> int:
    args = parse_args()
    if args.sequence_length <= 0 or args.warmup_iterations < 0 or args.iterations <= 0:
        raise SystemExit("sequence length and iterations must be positive")

    metadata_path = args.model_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    fixed_frames = metadata["vocoder_input_frames"]
    if args.sequence_length != fixed_frames:
        raise SystemExit(f"benchmark sequence length must equal fixed input {fixed_frames}")

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
    generator = torch.Generator(device="cpu").manual_seed(args.seed)
    codes = torch.randint(
        0,
        decoder.config.codebook_size,
        (1, decoder.config.num_quantizers, fixed_frames),
        generator=generator,
        dtype=torch.long,
    )
    codes_np = codes.numpy()

    ov_config = {
        "PERFORMANCE_HINT": "LATENCY",
        "NUM_STREAMS": "1",
        "INFERENCE_NUM_THREADS": str(args.threads),
        "INFERENCE_PRECISION_HINT": "f32",
    }
    core = ov.Core()
    fp32 = core.compile_model(args.model_dir / "vocoder_decoder.xml", "CPU", ov_config)
    int8 = core.compile_model(args.model_dir / args.int8_model, "CPU", ov_config)

    with torch.inference_mode():
        pytorch = _measure(
            lambda: decoder(codes), args.warmup_iterations, args.iterations
        )
    fp32_result = _measure(
        lambda: fp32([codes_np])[0], args.warmup_iterations, args.iterations
    )
    int8_result = _measure(
        lambda: int8([codes_np])[0], args.warmup_iterations, args.iterations
    )
    pytorch_median = float(pytorch["median_seconds"])
    fp32_median = float(fp32_result["median_seconds"])
    int8_median = float(int8_result["median_seconds"])
    report = {
        "model_repo": metadata["model_repo"],
        "model_revision": metadata["model_revision"],
        "source_commit": metadata["source_commit"],
        "exporter_image_digest": metadata["exporter_image_digest"],
        "ir_metadata_sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
        "openvino_version": ov.__version__,
        "sequence_length": fixed_frames,
        "threads": args.threads,
        "warmup_iterations": args.warmup_iterations,
        "iterations": args.iterations,
        "inference_precision_hint": "f32",
        "int8_model": args.int8_model,
        "pytorch": pytorch,
        "fp32": fp32_result,
        "int8": int8_result,
        "fp32_speedup": pytorch_median / fp32_median,
        "int8_speedup": pytorch_median / int8_median,
        "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    output_path = args.output_json or args.model_dir / "vocoder_benchmark.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

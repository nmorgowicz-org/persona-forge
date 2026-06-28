"""Runtime tuning helpers for OpenVINO compilation.

Used by app_worker.py, parity tests, and benchmarks to produce a consistent
compilation config derived from environment variables.
"""

from __future__ import annotations
import os
from pathlib import Path


def get_ov_config() -> dict[str, object]:
    """Build an OpenVINO compile_model config from environment variables."""

    inference_threads = os.getenv(
        "OV_INFERENCE_THREADS",
        os.getenv("OMP_NUM_THREADS", "6"),
    ).strip()
    dynamic_quant_group = os.getenv("OV_DYNAMIC_QUANT_GROUP_SIZE", "32").strip()
    kv_cache_precision = os.getenv("OV_KV_CACHE_PRECISION", "f32").strip()

    cfg: dict[str, object] = {
        "PERFORMANCE_HINT": "LATENCY",
        "NUM_STREAMS": "1",
        "INFERENCE_NUM_THREADS": str(inference_threads),
        "INFERENCE_PRECISION_HINT": "f32",
        "DYNAMIC_QUANTIZATION_GROUP_SIZE": dynamic_quant_group,
        "KV_CACHE_PRECISION": kv_cache_precision,
    }

    # Vocoder runtime config.
    vocoder_enabled = os.getenv("OPENVINO_VOCODER_ENABLED", "0").strip() == "1"
    vocoder_dir = (os.getenv("OPENVINO_VOCODER_DIR") or "").strip() or None
    vocoder_device = (os.getenv("OPENVINO_VOCODER_DEVICE", "CPU") or "CPU").strip()
    vocoder_compression = (
        os.getenv("OPENVINO_VOCODER_COMPRESSION", "fp32").strip().lower() or "fp32"
    )

    cfg["vocoder"] = {
        "enabled": vocoder_enabled,
        "model_path": Path(vocoder_dir) if vocoder_dir else None,
        "device": vocoder_device,
        "compression": vocoder_compression,
        "config": {
            "PERFORMANCE_HINT": "LATENCY",
            "NUM_STREAMS": "1",
            "INFERENCE_NUM_THREADS": str(inference_threads),
        },
    }

    return cfg


def apply_thread_env():
    """Apply thread and runtime environment variables before importing Torch/OpenVINO.

    Call this as early as possible (before heavy library imports).
    """
    os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
    os.environ.setdefault("OMP_NUM_THREADS", "6")
    os.environ.setdefault("MKL_NUM_THREADS", "6")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

    # Keep ORT settings for the vocoder ONNX session if in use
    os.environ.setdefault("ORT_INTRA_OP_NUM_THREADS", "6")
    os.environ.setdefault("ORT_INTER_OP_NUM_THREADS", "2")


# Run at import time so callers don't have to remember.
apply_thread_env()

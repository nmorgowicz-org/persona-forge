"""Runtime tuning helpers for OpenVINO compilation.

Used by app_worker.py, parity tests, and benchmarks to produce a consistent
compilation config derived from environment variables.
"""

from __future__ import annotations
import os
from pathlib import Path


def resolve_inference_threads() -> int:
    """Choose inference thread count based on available cores.

    Priority:
    - OV_INFERENCE_THREADS (explicit override)
    - OMP_NUM_THREADS (legacy fallback)
    - Otherwise: logical_cores - 2, with a floor of 1.
    """
    # Allow explicit override
    explicit = (os.getenv("OV_INFERENCE_THREADS") or "").strip()
    if explicit:
        try:
            val = int(explicit)
            if val >= 1:
                return val
        except ValueError:
            pass

    # Legacy fallback
    legacy = (os.getenv("OMP_NUM_THREADS") or "").strip()
    if legacy:
        try:
            val = int(legacy)
            if val >= 1:
                return val
        except ValueError:
            pass

    # Auto: all cores minus 2, min 1
    cores = (os.cpu_count() or 4)
    threads = max(1, cores - 2)
    return threads


def get_ov_config() -> dict[str, object]:
    """Build an OpenVINO compile_model config from environment variables."""

    inference_threads = str(resolve_inference_threads())
    dynamic_quant_group = os.getenv("OV_DYNAMIC_QUANT_GROUP_SIZE", "32").strip()
    kv_cache_precision = os.getenv("OV_KV_CACHE_PRECISION", "f32").strip()

    # Compiled kernel cache — eliminates ~60–120s JIT on every restart/reload.
    # Defaults to /ov/cache, which is already on the persistent OV_DATA_PATH mount.
    # Set OV_CACHE_DIR="" to disable.
    cache_dir_raw = os.getenv("OV_CACHE_DIR", "/ov/cache").strip()
    cache_dir = cache_dir_raw or None
    if cache_dir:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

    cfg: dict[str, object] = {
        "PERFORMANCE_HINT": "LATENCY",
        "NUM_STREAMS": "1",
        "INFERENCE_NUM_THREADS": str(inference_threads),
        "INFERENCE_PRECISION_HINT": "f32",
        "DYNAMIC_QUANTIZATION_GROUP_SIZE": dynamic_quant_group,
        "KV_CACHE_PRECISION": kv_cache_precision,
    }
    if cache_dir:
        cfg["CACHE_DIR"] = cache_dir

    # OPENVINO_DEVICE (Phase A4, D9 axis a) — the talker/main/predictor cores' compile target.
    # CPU/GPU/AUTO; GPU targets an Intel iGPU. Separate from the vocoder's own device knob below.
    cfg["device"] = (os.getenv("OPENVINO_DEVICE", "AUTO") or "AUTO").strip().upper()

    # Vocoder runtime config (FP32-only; INT8 vocoder rejected).
    vocoder_enabled = os.getenv("OPENVINO_VOCODER_ENABLED", "0").strip() == "1"
    vocoder_dir = (os.getenv("OPENVINO_VOCODER_DIR") or "").strip() or None
    vocoder_device = (os.getenv("OPENVINO_VOCODER_DEVICE", "CPU") or "CPU").strip()
    # OPENVINO_VOCODER_COMPRESSION is kept for metadata; runtime only supports FP32.
    _ = os.getenv("OPENVINO_VOCODER_COMPRESSION", "fp32").strip().lower()

    vocoder_compile_cfg: dict[str, object] = {
        "PERFORMANCE_HINT": "LATENCY",
        "NUM_STREAMS": "1",
        "INFERENCE_NUM_THREADS": str(inference_threads),
    }
    if cache_dir:
        vocoder_compile_cfg["CACHE_DIR"] = cache_dir

    cfg["vocoder"] = {
        "enabled": vocoder_enabled,
        "model_path": Path(vocoder_dir) if vocoder_dir else None,
        "device": vocoder_device,
        "config": vocoder_compile_cfg,
    }

    return cfg


def apply_thread_env():
    """Apply thread and runtime environment variables before importing Torch/OpenVINO.

    Call this as early as possible (before heavy library imports).
    Uses resolve_inference_threads() for dynamic core-aware sizing.
    """
    threads = str(resolve_inference_threads())

    os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
    os.environ.setdefault("OMP_NUM_THREADS", threads)
    os.environ.setdefault("MKL_NUM_THREADS", threads)
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

    # Keep ORT settings for the vocoder ONNX session if in use
    os.environ.setdefault("ORT_INTRA_OP_NUM_THREADS", threads)
    os.environ.setdefault("ORT_INTER_OP_NUM_THREADS", "2")


# Run at import time so callers don't have to remember.
apply_thread_env()

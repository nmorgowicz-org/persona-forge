"""Shared helpers for the Milestone 0 benchmark and profile harnesses.

Importing this module sets single-process CPU thread limits *before* torch, ONNX
Runtime, or OpenVINO are imported, so every engine inherits the same budget. Import
it first in any benchmark entrypoint, ahead of torch/qwen_tts.
"""

from __future__ import annotations

import os

# Thread budget must be set before importing torch / onnxruntime / openvino.
# Mirrors app_worker.py so benchmark numbers reflect the deployed configuration.
for _key, _val in (
    ("OMP_WAIT_POLICY", "PASSIVE"),
    ("OMP_NUM_THREADS", "6"),
    ("MKL_NUM_THREADS", "6"),
    ("OPENBLAS_NUM_THREADS", "1"),
    ("ORT_INTRA_OP_NUM_THREADS", "6"),
    ("ORT_INTER_OP_NUM_THREADS", "2"),
):
    os.environ.setdefault(_key, _val)

import resource
import statistics
from dataclasses import dataclass
from pathlib import Path

from model_config import configure_hf_token, resolve_model_repo, resolve_torch_load_config


# Reference voice defaults mirror app_worker.py so a benchmark run reproduces the
# deployed voice-clone path. Override via REF_AUDIO / REF_TEXT.
DEFAULT_REF_AUDIO = "/voice/voice_A.wav"
DEFAULT_REF_TEXT = (
    "Welcome to Rosies. What can I get for you today? You know, Im a good girl. "
    "You want me, dont you? I am on the menu too."
)

# Short and paragraph prompts. The short prompt targets the 7-14 s utterance the plan
# flags for investigation; the paragraph prompt exercises a longer decode.
PROMPTS: dict[str, tuple[str, str]] = {
    "short": (
        "Thanks for stopping by. Your order will be ready in just a few minutes.",
        "English",
    ),
    "paragraph": (
        "Thanks for stopping by today. Our special this afternoon is a slow roasted "
        "tomato soup with fresh basil and a warm sourdough roll. If you are in the mood "
        "for something sweet, the lemon tart is just out of the oven. Let me know what "
        "you would like, and I will have it brought right out to your table.",
        "English",
    ),
}


def _proc_int(path: str, key: str) -> int | None:
    """Read an integer field keyed by name from a /proc file, or None if absent."""

    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] == key:
            return int(parts[1])
    return None


def read_swap_counters() -> tuple[int | None, int | None]:
    """Return cumulative (pages swapped in, pages swapped out) from /proc/vmstat."""

    return _proc_int("/proc/vmstat", "pswpin"), _proc_int("/proc/vmstat", "pswpout")


def swap_delta(before: tuple[int | None, int | None], after: tuple[int | None, int | None]) -> str:
    """Human-readable swap activity between two read_swap_counters() snapshots."""

    labels = ("pages_in", "pages_out")
    parts = []
    for label, b, a in zip(labels, before, after):
        parts.append(f"{label}={a - b if b is not None and a is not None else '?'}")
    return " ".join(parts)


def peak_rss_bytes() -> int:
    """Peak resident set size for this process. ru_maxrss is KiB on Linux, bytes on macOS."""

    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return maxrss * 1024 if os.uname().sysname == "Linux" else maxrss


def current_rss_bytes() -> int | None:
    """Current resident set size from /proc/self/status (Linux only)."""

    kib = _proc_int("/proc/self/status", "VmRSS:")
    return kib * 1024 if kib is not None else None


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile; falls back to max for tiny samples."""

    if not values:
        raise ValueError("percentile of empty sequence")
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(pct / 100 * len(ordered)) - 1))
    return ordered[rank]


@dataclass
class LoadedModel:
    model: object
    voice_clone_prompt: object


def load_model() -> LoadedModel:
    """Load the configured checkpoint at float32 and build the voice-clone prompt.

    WARNING: loads a full model (~4.7 GiB for 0.6B). On dockermisc1 stop the prod
    qwen3-tts container first so this does not contend for memory and swap-thrash.
    """

    configure_hf_token()

    import torch
    from qwen_tts import Qwen3TTSModel

    threads = int(os.environ["OMP_NUM_THREADS"])
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)

    model_repo = resolve_model_repo()
    revision = os.getenv("MODEL_REVISION") or None
    device = os.getenv("DEVICE", "cpu")

    # low_cpu_mem_usage is best-practice but does NOT move the 1.7B lifetime peak
    # (measured: device_map already implies it). The peak is the bf16->fp32 upcast:
    # the checkpoint is BF16, and forcing fp32 makes the mmap'd bf16 file (~3.9 GiB)
    # and the fp32 weights (~7.7 GiB) briefly coexist (~11.6 GiB), then the mmap
    # drops to ~8.5 GiB settled. OPENVINO_TORCH_DTYPE lets the *serving* path load in
    # native bf16 to skip that upcast; the exporter MUST stay fp32 for convert parity
    # (do not set the env in export). See docs/OPENVINO_RESULTS.md (M9).
    torch_dtype, dtype_name, low_cpu_mem_usage = resolve_torch_load_config(torch)
    print(
        f"[bench] loading {model_repo} (rev={revision}) on {device} at {dtype_name} "
        f"(low_cpu_mem_usage={low_cpu_mem_usage})...",
        flush=True,
    )
    model = Qwen3TTSModel.from_pretrained(
        model_repo,
        revision=revision,
        device_map=device,
        dtype=torch_dtype,
        low_cpu_mem_usage=low_cpu_mem_usage,
    )

    ref_audio = os.getenv("REF_AUDIO", DEFAULT_REF_AUDIO)
    ref_text = os.getenv("REF_TEXT", DEFAULT_REF_TEXT)
    prompt = model.create_voice_clone_prompt(
        ref_audio=ref_audio,
        ref_text=ref_text,
        x_vector_only_mode=False,
    )
    print("[bench] model and voice-clone prompt ready.", flush=True)
    return LoadedModel(model=model, voice_clone_prompt=prompt)


def export_bench_env():
    """Export environment variables for benchmarking with optimized settings.

    Called at the top of any benchmark or profile entrypoint. Enables buffer-backed
    K/V cache in the OpenVINO runtime to reduce per-frame glue overhead.
    """
    os.environ.setdefault("OPENVINO_BUFFER_KV", "1")


def fmt_mib(num_bytes: int | None) -> str:
    return f"{num_bytes / (1024 * 1024):.0f} MiB" if num_bytes is not None else "n/a"


def summarize(times_s: list[float], audio_s: list[float]) -> dict[str, float]:
    """Latency and real-time-factor summary for one prompt's measured iterations."""

    median_t = statistics.median(times_s)
    median_audio = statistics.median(audio_s)
    return {
        "iterations": len(times_s),
        "median_s": round(median_t, 3),
        "p95_s": round(percentile(times_s, 95), 3),
        "min_s": round(min(times_s), 3),
        "max_s": round(max(times_s), 3),
        "median_audio_s": round(median_audio, 3),
        # RTF < 1.0 means faster than real time.
        "rtf": round(median_t / median_audio, 3) if median_audio else float("nan"),
    }

"""Generate listenable WAVs for A/B comparison: PyTorch baseline vs OpenVINO.

Mirrors the test_ov_generation.py model-load + install path, but instead of
computing SNR it writes WAV files so a human can listen. Uses production
sampling (do_sample=True) with a fixed seed so each backend produces a full,
naturally-terminated utterance.

Usage (inside the exporter image, like the harness):
    python dump_audio.py --model-dir /ov_output/<ir-dir> --compression int8 \
        --out-dir /ov_output/<ir-dir>/audio

Writes:
    pytorch.wav        (PyTorch reference, same seed)
    ov_<compression>.wav
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import wave
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

import numpy as np

# Sets thread env before torch/openvino import (import side effect).
import ov_runtime_config  # noqa: F401
from bench_common import load_model


def _vmrss_mib() -> float:
    """Current resident set size in MiB from /proc, or -1 if unavailable."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024  # kB -> MiB
    except OSError:
        pass
    return -1.0


class _RssSampler:
    """Sample process RSS and label samples by generation phase."""

    def __init__(
        self,
        interval_ms: int,
        rss_reader: Callable[[], float] = _vmrss_mib,
    ) -> None:
        if interval_ms <= 0:
            raise ValueError("RSS sample interval must be positive")
        self.interval_seconds = interval_ms / 1000
        self._rss_reader = rss_reader
        self._phase = "generation_glue"
        self._phase_lock = threading.Lock()
        self._samples_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at = 0.0
        self.samples: list[dict[str, float | str]] = []

    def __enter__(self) -> "_RssSampler":
        self._started_at = time.monotonic()
        self._stop.clear()
        self.snapshot()
        self._thread = threading.Thread(target=self._run, name="rss-sampler", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.snapshot()
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 2))

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.snapshot()

    def snapshot(self) -> None:
        rss_mib = self._rss_reader()
        if rss_mib < 0:
            return
        with self._phase_lock:
            phase = self._phase
        sample: dict[str, float | str] = {
            "elapsed_seconds": round(time.monotonic() - self._started_at, 6),
            "rss_mib": round(rss_mib, 3),
            "phase": phase,
        }
        with self._samples_lock:
            self.samples.append(sample)

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        with self._phase_lock:
            previous = self._phase
            self._phase = name
        self.snapshot()
        try:
            yield
        finally:
            self.snapshot()
            with self._phase_lock:
                self._phase = previous

    def report(self) -> dict[str, object]:
        with self._samples_lock:
            samples = list(self.samples)
        phase_peaks: dict[str, float] = {}
        for sample in samples:
            phase = str(sample["phase"])
            rss_mib = float(sample["rss_mib"])
            phase_peaks[phase] = max(phase_peaks.get(phase, 0.0), rss_mib)
        peak = max((float(sample["rss_mib"]) for sample in samples), default=-1.0)
        return {
            "sample_interval_ms": int(self.interval_seconds * 1000),
            "sample_count": len(samples),
            "generation_peak_rss_mib": peak,
            "phase_peak_rss_mib": phase_peaks,
            "samples": samples,
        }


def _write_wav(path: Path, wav, sr: int) -> None:
    wav = np.asarray(wav, dtype=np.float32).ravel()
    peak = float(np.max(np.abs(wav))) if wav.size else 1.0
    if peak > 1.0:
        wav = wav / peak
    pcm = np.clip(wav, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(pcm.tobytes())
    print(f"  wrote {path}  ({len(pcm)/sr:.2f}s @ {sr} Hz)", flush=True)


def main() -> None:
    import torch

    p = argparse.ArgumentParser()
    p.add_argument("--model-dir", type=Path, required=True)
    p.add_argument("--compression", choices=["fp32", "int8"], default="int8")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--text", default="The quick brown fox jumps over the lazy dog.")
    p.add_argument("--language", default="English")
    p.add_argument("--threads", type=int, default=6)
    p.add_argument("--seed", type=int, default=20260628)
    p.add_argument(
        "--rss-profile",
        type=Path,
        help=(
            "write an M9 generation-only RSS timeline as JSON; samples are labeled "
            "transformer or vocoder"
        ),
    )
    p.add_argument(
        "--rss-sample-ms",
        type=int,
        default=50,
        help="RSS sampling interval used with --rss-profile (default: 50 ms)",
    )
    p.add_argument(
        "--ov-only",
        action="store_true",
        help=(
            "skip the PyTorch reference and generate only on OpenVINO. Required to validate "
            "OPENVINO_RELEASE_TORCH (Milestone 7): the released footprint is meaningful only "
            "when the PyTorch core forward is never invoked. Reports peak RSS at exit."
        ),
    )
    args = p.parse_args()

    torch.set_num_threads(args.threads)

    loaded = load_model()
    model, prompt = loaded.model, loaded.voice_clone_prompt
    talker = model.model.talker

    if not args.ov_only:
        # PyTorch baseline (only needs writing once; identical across compressions).
        pt_path = args.out_dir / "pytorch.wav"
        print("[dump] PyTorch reference ...", flush=True)
        torch.manual_seed(args.seed)
        pt_wavs, sr = model.generate_voice_clone(
            text=args.text, language=args.language, voice_clone_prompt=prompt, do_sample=True
        )
        _write_wav(pt_path, pt_wavs[0], sr)

    # OpenVINO candidate.
    from ov_talker_runtime import OVTalkerRuntime

    print(f"[dump] OpenVINO ({args.compression}) ...", flush=True)
    print(f"[dump] RSS after model load (before OV install): {_vmrss_mib():.0f} MiB", flush=True)
    runtime = OVTalkerRuntime(
        args.model_dir, talker, compression=args.compression,
        speech_tokenizer=model.model.speech_tokenizer,
    )
    runtime.install()
    _trim()
    print(f"[dump] RSS after OV install+release (idle): {_vmrss_mib():.0f} MiB", flush=True)
    sampler = _RssSampler(args.rss_sample_ms) if args.rss_profile else None
    speech_tokenizer = model.model.speech_tokenizer
    decode_before_profile = speech_tokenizer.decode
    core_runs_before_profile = []

    if sampler is not None:
        for core_name, core in (("main", runtime.main), ("predictor", runtime.pred)):
            run_before_profile = core.run

            def profiled_core_run(*, _core_name=core_name, _run=run_before_profile, **kwargs):
                past = kwargs.get("past_key_values")
                prior = past.get_seq_length() if past is not None else 0
                step = "prefill" if prior == 0 else "decode"
                with sampler.phase(f"{_core_name}_{step}"):
                    return _run(**kwargs)

            core_runs_before_profile.append((core, run_before_profile))
            core.run = profiled_core_run

        def profiled_decode(*decode_args, **decode_kwargs):
            with sampler.phase("vocoder"):
                return decode_before_profile(*decode_args, **decode_kwargs)

        speech_tokenizer.decode = profiled_decode

    try:
        torch.manual_seed(args.seed)
        if sampler is None:
            ov_wavs, ov_sr = model.generate_voice_clone(
                text=args.text, language=args.language, voice_clone_prompt=prompt, do_sample=True
            )
        else:
            with sampler:
                ov_wavs, ov_sr = model.generate_voice_clone(
                    text=args.text,
                    language=args.language,
                    voice_clone_prompt=prompt,
                    do_sample=True,
                )
    finally:
        if sampler is not None:
            speech_tokenizer.decode = decode_before_profile
            for core, run_before_profile in core_runs_before_profile:
                core.run = run_before_profile
        runtime.uninstall()
    _write_wav(args.out_dir / f"ov_{args.compression}.wav", ov_wavs[0], ov_sr)

    if sampler is not None:
        report = sampler.report()
        report["compression"] = args.compression
        report["threads"] = args.threads
        report["seed"] = args.seed
        report["text"] = args.text
        args.rss_profile.parent.mkdir(parents=True, exist_ok=True)
        args.rss_profile.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            f"[dump] wrote RSS profile {args.rss_profile} "
            f"(generation peak: {report['generation_peak_rss_mib']:.0f} MiB; "
            f"phase peaks: {report['phase_peak_rss_mib']})",
            flush=True,
        )

    # M7 memory signals at three checkpoints (see prints above): post-load, post-install+release
    # idle, and post-generation. ru_maxrss is the lifetime high-water mark — the per-request peak
    # the cgroup must hold. The trimmed idle figure below is the between-request steady state.
    import resource

    peak_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    post_gen = _vmrss_mib()
    _trim()
    idle_trimmed = _vmrss_mib()
    released = getattr(runtime, "_torch_cores_released", False)
    print(
        f"[dump] RSS lifetime peak (per-request): {peak_mib:.0f} MiB | "
        f"post-generation: {post_gen:.0f} MiB | trimmed idle: {idle_trimmed:.0f} MiB  "
        f"(torch cores released: {released}; ov-only: {args.ov_only})",
        flush=True,
    )

    print("[dump] done.", flush=True)


def _trim() -> None:
    """gc + glibc malloc_trim so RSS reflects retained, not cached-but-freed, memory."""
    import gc

    gc.collect()
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


if __name__ == "__main__":
    main()

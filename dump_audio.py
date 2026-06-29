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
import wave
from pathlib import Path

import numpy as np

# Sets thread env before torch/openvino import (import side effect).
import ov_runtime_config  # noqa: F401
from bench_common import load_model


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
    runtime = OVTalkerRuntime(
        args.model_dir, talker, compression=args.compression,
        speech_tokenizer=model.model.speech_tokenizer,
    )
    runtime.install()
    try:
        torch.manual_seed(args.seed)
        ov_wavs, ov_sr = model.generate_voice_clone(
            text=args.text, language=args.language, voice_clone_prompt=prompt, do_sample=True
        )
    finally:
        runtime.uninstall()
    _write_wav(args.out_dir / f"ov_{args.compression}.wav", ov_wavs[0], ov_sr)

    # M7 memory signals. ru_maxrss is the process high-water mark, so it captures the
    # PyTorch load transient (which precedes release) — the number that decides whether the
    # model fits the cgroup at startup. Current VmRSS after generation reflects the released
    # steady-state footprint the serving worker holds. Report both.
    import gc
    import resource

    gc.collect()
    peak_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    current_mib = None
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    current_mib = int(line.split()[1]) / 1024  # kB -> MiB
                    break
    except OSError:
        pass
    released = getattr(runtime, "_torch_cores_released", False)
    cur = f"{current_mib:.0f} MiB" if current_mib is not None else "n/a"
    print(
        f"[dump] RSS peak (incl. load transient): {peak_mib:.0f} MiB | "
        f"current (post-release steady state): {cur}  "
        f"(torch cores released: {released}; ov-only: {args.ov_only})",
        flush=True,
    )

    print("[dump] done.", flush=True)


if __name__ == "__main__":
    main()

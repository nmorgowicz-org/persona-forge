#!/usr/bin/env python
"""Diagnostic: report resident PyTorch bytes by component.

Confirms *why* 0.6B and 1.7B use nearly identical steady memory: the talker `.layers` (the only
big differentiator) are freed after the OpenVINO IR compiles, so what remains is dominated by the
PyTorch speech-tokenizer / codec, which is the same size in both models and is never released.

Run inside the runtime image on the box (needs torch + qwen_tts + the model + IR):

    docker compose run --rm --entrypoint python qwen3-tts scripts/codec_memory_report.py

Importing ``qwen3_tts.model`` loads the model and, on the OpenVINO backend, installs the OV runtime
and releases the talker ``.layers`` — so this reports the POST-release resident state, which is
exactly what dominates steady RSS. Use it to quantify the codec decoder vs encoder split before
implementing the decoder-only release (the encoder must stay for future per-request cloning /
VoiceDesign; see docs/plans/alexandria_ideas.md).
"""

from __future__ import annotations

import sys


def _bytes(module) -> int:
    total = 0
    for param in module.parameters(recurse=True):
        total += param.numel() * param.element_size()
    for buf in module.buffers(recurse=True):
        total += buf.numel() * buf.element_size()
    return total


def _gib(num_bytes: int) -> str:
    return f"{num_bytes / 2**30:.3f} GiB"


def _report(name: str, module) -> None:
    if module is None:
        print(f"  {name:<28} (absent)")
        return
    print(f"  {name:<28} {_gib(_bytes(module)):>12}")
    for child_name, child in module.named_children():
        print(f"      {child_name:<24} {_gib(_bytes(child)):>12}")


def main() -> int:
    from qwen3_tts import model as m  # triggers load + (openvino) OV install + release

    inner = getattr(m.model, "model", None)
    if inner is None:
        print("could not locate inner model (m.model.model)")
        return 1

    print(f"backend={m.TTS_BACKEND} model={m.MODEL_ID}")
    print("resident PyTorch bytes by component (post-OV-release):")
    _report("speech_tokenizer", getattr(inner, "speech_tokenizer", None))
    _report("talker", getattr(inner, "talker", None))
    _report("code_predictor", getattr(getattr(inner, "talker", None), "code_predictor", None))

    try:
        with open("/proc/self/status") as status:
            for line in status:
                if line.startswith(("VmRSS:", "VmHWM:")):
                    print("process", line.strip())
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

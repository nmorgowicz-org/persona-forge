#!/usr/bin/env python
"""Diagnostic: report resident PyTorch bytes by component.

Confirms *why* 0.6B and 1.7B use nearly identical steady memory: the talker `.layers` (the only
big differentiator) are freed after the OpenVINO IR compiles, so what remains is dominated by the
PyTorch speech-tokenizer / codec, which is the same size in both models and is never released.

Run inside the runtime image on the box (needs torch + qwen_tts + the model + IR):

    docker compose run --rm --entrypoint python qwen3-tts scripts/codec_memory_report.py

Importing ``qwen3_tts.model`` loads the model and, on the OpenVINO backend, installs the OV runtime
and releases the talker ``.layers`` — so this reports the POST-release resident state, which is
exactly what dominates steady RSS. ``speech_tokenizer`` is a wrapper object (not an ``nn.Module``),
so we introspect it for nested modules to quantify the codec decoder vs encoder split before
implementing the decoder-only release (the encoder must stay for future per-request cloning /
VoiceDesign; see docs/plans/alexandria_ideas.md).
"""

from __future__ import annotations

import sys


def main() -> int:
    import torch.nn as nn

    from qwen3_tts import model as m  # triggers load + (openvino) OV install + release

    inner = getattr(m.model, "model", None)
    if inner is None:
        print("could not locate inner model (m.model.model)")
        return 1

    def bytes_of(mod: "nn.Module") -> int:
        total = 0
        for param in mod.parameters(recurse=True):
            total += param.numel() * param.element_size()
        for buf in mod.buffers(recurse=True):
            total += buf.numel() * buf.element_size()
        return total

    def gib(num: int) -> str:
        return f"{num / 2**30:7.3f} GiB"

    def find_nested_modules(obj, prefix, depth, seen):
        """Yield (path, nn.Module) for module-valued attributes, descending into wrappers."""
        if id(obj) in seen:
            return
        seen.add(id(obj))
        if isinstance(obj, nn.Module):
            items = dict(obj.named_children())
        else:
            items = {k: v for k, v in vars(obj).items()} if hasattr(obj, "__dict__") else {}
        for key, val in items.items():
            path = f"{prefix}.{key}"
            if isinstance(val, nn.Module):
                yield path, val
            elif depth > 0 and hasattr(val, "__dict__") and not isinstance(val, (str, bytes)):
                yield from find_nested_modules(val, path, depth - 1, seen)

    print(f"backend={m.TTS_BACKEND} model={m.MODEL_ID}")
    print("resident PyTorch bytes by component (post-OV-release):")
    seen: set[int] = set()
    for name in ("talker", "speech_tokenizer"):
        obj = getattr(inner, name, None)
        if obj is None:
            print(f"  {name:<26} (absent)")
            continue
        if isinstance(obj, nn.Module):
            print(f"  {name:<26} {gib(bytes_of(obj))}  (total)")
            for child_name, child in obj.named_children():
                print(f"      {child_name:<22} {gib(bytes_of(child))}")
        else:
            print(f"  {name:<26} (wrapper: {type(obj).__name__}) — nested modules:")
            for path, mod in find_nested_modules(obj, name, 2, seen):
                print(f"      {path:<34} {gib(bytes_of(mod))}")

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

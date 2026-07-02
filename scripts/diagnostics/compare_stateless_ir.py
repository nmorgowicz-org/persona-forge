#!/usr/bin/env python3
"""Compare two static OpenVINO IRs with identical deterministic inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import openvino as ov


def _name(port, fallback: str) -> str:
    names = port.get_names()
    return sorted(names)[0] if names else fallback


def _shape(port, index: int, seq: int, hidden: int) -> tuple[int, ...]:
    defaults = ((1, seq, hidden), (1, seq), (1, seq), (seq,))
    result = []
    for axis, dim in enumerate(port.partial_shape):
        if dim.is_dynamic:
            if index >= len(defaults) or axis >= len(defaults[index]):
                raise RuntimeError(f"cannot resolve dynamic input: {_name(port, str(index))} {port.partial_shape}")
            result.append(defaults[index][axis])
        else:
            result.append(dim.get_length())
    return tuple(result)


def _make_input(port, index: int, rng: np.random.Generator, seq: int, hidden: int) -> np.ndarray:
    name, shape, kind = _name(port, str(index)), _shape(port, index, seq, hidden), port.element_type
    if kind in (ov.Type.i32, ov.Type.i64):
        dtype = np.int32 if kind == ov.Type.i32 else np.int64
        if index == 1 or "attention_mask" in name:
            return np.ones(shape, dtype=dtype)
        if index in (2, 3) or "position" in name:
            return np.arange(shape[-1], dtype=dtype).reshape(shape)
        return np.zeros(shape, dtype=dtype)
    if kind in (ov.Type.f16, ov.Type.f32, ov.Type.f64):
        dtype = {ov.Type.f16: np.float16, ov.Type.f32: np.float32, ov.Type.f64: np.float64}[kind]
        return rng.standard_normal(shape).astype(dtype)
    raise RuntimeError(f"unsupported input type: {name} {kind}")


def _run(core: ov.Core, path: str, inputs: list[np.ndarray], max_outputs: int | None) -> dict:
    compiled = core.compile_model(core.read_model(path), "CPU")
    values = compiled(inputs)
    outputs = []
    for index, port in enumerate(compiled.outputs):
        if max_outputs is not None and index >= max_outputs:
            break
        value = np.asarray(values[port])
        finite = np.isfinite(value)
        outputs.append({
            "index": index,
            "name": _name(port, str(index)),
            "shape": list(value.shape),
            "nonfinite": int(value.size - finite.sum()),
            "min": float(value[finite].min()) if finite.any() else None,
            "max": float(value[finite].max()) if finite.any() else None,
            "mean": float(value[finite].mean()) if finite.any() else None,
            "std": float(value[finite].std()) if finite.any() else None,
        })
    return {"path": path, "outputs": outputs}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference")
    parser.add_argument("candidate")
    parser.add_argument("--seed", type=int, default=20260702)
    parser.add_argument("--seq", type=int, default=8)
    parser.add_argument("--hidden", type=int, default=2048)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-outputs", type=int)
    args = parser.parse_args()
    core = ov.Core()
    reference = core.read_model(args.reference)
    candidate = core.read_model(args.candidate)
    ref_contract = [(str(p.element_type), str(p.partial_shape)) for p in reference.inputs]
    cand_contract = [(str(p.element_type), str(p.partial_shape)) for p in candidate.inputs]
    if ref_contract != cand_contract:
        raise RuntimeError(f"input contracts differ:\nreference={ref_contract}\ncandidate={cand_contract}")
    rng = np.random.default_rng(args.seed)
    inputs = [
        _make_input(port, index, rng, args.seq, args.hidden)
        for index, port in enumerate(reference.inputs)
    ]
    report = {
        "seed": args.seed,
        "inputs": [
            {"name": _name(p, str(index)), "shape": list(v.shape)}
            for index, (p, v) in enumerate(zip(reference.inputs, inputs, strict=True))
        ],
        "reference": _run(core, args.reference, inputs, args.max_outputs),
        "candidate": _run(core, args.candidate, inputs, args.max_outputs),
    }
    rendered = json.dumps(report, indent=2)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 1 if any(row["nonfinite"] for row in report["candidate"]["outputs"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())

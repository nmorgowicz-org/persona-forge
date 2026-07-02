#!/usr/bin/env python3
"""Diagnostic-only: replace one RoPE Constant, then INT4-compress the repaired IR."""

from __future__ import annotations

import argparse

import nncf
import numpy as np
import openvino as ov

TARGET = "__module.core.rotary_emb/aten::to/Convert_compressed"


def _constant(model, name):
    matches = [node for node in model.get_ordered_ops() if node.get_friendly_name() == name]
    if len(matches) != 1 or matches[0].get_type_name() != "Constant":
        raise RuntimeError(f"expected one Constant named {name!r}, found {matches}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("known_good_fp32")
    parser.add_argument("broken_fp32")
    parser.add_argument("output_int4")
    args = parser.parse_args()
    core = ov.Core()
    known_good = core.read_model(args.known_good_fp32)
    repaired = core.read_model(args.broken_fp32)
    source = np.asarray(_constant(known_good, TARGET).get_data()).copy()
    target = _constant(repaired, TARGET)
    print(f"old bad range: {np.asarray(target.get_data()).min()} .. {np.asarray(target.get_data()).max()}")
    print(f"replacement range: {source.min()} .. {source.max()}")
    replacement = ov.opset13.constant(source)
    replacement.set_friendly_name(TARGET)
    target.output(0).replace(replacement.output(0))
    repaired.validate_nodes_and_infer_types()
    compressed = nncf.compress_weights(
        repaired,
        mode=nncf.CompressWeightsMode.INT4_ASYM,
        group_size=32,
        ratio=1.0,
    )
    ov.save_model(compressed, args.output_int4)
    print(f"saved repaired INT4 diagnostic graph: {args.output_int4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

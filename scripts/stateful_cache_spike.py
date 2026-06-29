#!/usr/bin/env python3
"""Model-free M9 spike for a static-capacity OpenVINO K/V state buffer.

OpenVINO MakeStateful rejects dynamic state shapes. This spike validates the
replacement design used by M9.3b: keep a static-capacity Variable inside the IR,
update only cache_position indices with ScatterUpdate, and reset it between
requests through the State API.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def build_model(max_seq: int):
    import openvino as ov
    from openvino import opset13 as ops
    from openvino.op.util import Variable, VariableInfo

    updates = ops.parameter(
        ov.PartialShape([1, 2, -1, 4]),
        dtype=np.float32,
        name="updates",
    )
    cache_position = ops.parameter(
        ov.PartialShape([-1]),
        dtype=np.int64,
        name="cache_position",
    )

    info = VariableInfo()
    info.data_shape = ov.PartialShape([1, 2, max_seq, 4])
    info.data_type = ov.Type.f32
    info.variable_id = "kv_cache"
    variable = Variable(info)

    state = ops.read_value(variable)
    updated_state = ops.scatter_update(
        state,
        cache_position,
        updates,
        ops.constant(2, dtype=np.int64),
    )
    assign = ops.assign(updated_state, variable)
    result = ops.result(updates)

    # The production graph returns hidden state only. Returning updates here keeps
    # this spike focused on State API behavior; query_state verifies cache contents.
    return ov.Model(
        results=[result],
        sinks=[assign],
        parameters=[updates, cache_position],
        name="static_kv_state_spike",
    )


def run(max_seq: int, save_dir: Path | None) -> dict[str, object]:
    import openvino as ov

    model = build_model(max_seq)
    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)
        ov.save_model(model, save_dir / "static_kv_state_spike.xml", compress_to_fp16=False)
        model = ov.Core().read_model(save_dir / "static_kv_state_spike.xml")

    compiled = ov.Core().compile_model(model, "CPU")
    request = compiled.create_infer_request()
    states = request.query_state()
    if len(states) != 1:
        raise RuntimeError(f"expected one state, found {len(states)}")

    request.reset_state()
    first = np.ones((1, 2, 2, 4), dtype=np.float32)
    request.infer({"updates": first, "cache_position": np.array([0, 1], dtype=np.int64)})
    after_prefill = np.array(states[0].state.data, copy=True)

    decode = np.full((1, 2, 1, 4), 2.0, dtype=np.float32)
    request.infer({"updates": decode, "cache_position": np.array([2], dtype=np.int64)})
    after_decode = np.array(states[0].state.data, copy=True)

    if not np.all(after_prefill[:, :, :2, :] == 1.0):
        raise RuntimeError("prefill values were not persisted in state")
    if not np.all(after_decode[:, :, :2, :] == 1.0):
        raise RuntimeError("decode overwrote the prior cache")
    if not np.all(after_decode[:, :, 2:3, :] == 2.0):
        raise RuntimeError("decode value was not written at cache_position")

    request.reset_state()
    after_reset = np.array(states[0].state.data, copy=True)
    if np.any(after_reset):
        raise RuntimeError("reset_state did not clear the static cache")

    return {
        "openvino_version": ov.__version__,
        "state_name": states[0].name,
        "state_shape": list(after_decode.shape),
        "max_seq": max_seq,
        "prefill_persisted": True,
        "decode_appended": True,
        "reset_cleared": True,
        "serialized_round_trip": save_dir is not None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-seq", type=int, default=8)
    parser.add_argument("--save-dir", type=Path)
    args = parser.parse_args()
    if args.max_seq < 3:
        parser.error("--max-seq must be at least 3")
    print(json.dumps(run(args.max_seq, args.save_dir), indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Convert one explicit-cache OpenVINO core IR to static-capacity state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import openvino as ov

from ov_stateful_cache import make_static_kv_stateful


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--num-layers", type=int, required=True)
    parser.add_argument("--base-input-count", type=int, required=True)
    parser.add_argument("--cache-position-index", type=int, default=3)
    parser.add_argument("--max-seq", type=int, required=True)
    parser.add_argument("--state-prefix", required=True)
    parser.add_argument("--compile-smoke", action="store_true")
    args = parser.parse_args()

    core = ov.Core()
    model = core.read_model(args.input)
    make_static_kv_stateful(
        model,
        num_layers=args.num_layers,
        base_input_count=args.base_input_count,
        cache_position_index=args.cache_position_index,
        max_seq=args.max_seq,
        state_prefix=args.state_prefix,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ov.save_model(model, args.output, compress_to_fp16=False)

    report: dict[str, object] = {
        "openvino_version": ov.__version__,
        "input": str(args.input),
        "output": str(args.output),
        "parameters": len(model.get_parameters()),
        "results": len(model.get_results()),
        "variables": len(model.get_variables()),
        "max_seq": args.max_seq,
    }
    if args.compile_smoke:
        compiled = core.compile_model(model, "CPU")
        request = compiled.create_infer_request()
        states = request.query_state()
        report["compiled"] = True
        report["query_state_count"] = len(states)
        report["state_shapes"] = sorted({str(state.state.shape) for state in states})
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

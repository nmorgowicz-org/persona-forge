#!/usr/bin/env python3
"""Convert one explicit-cache OpenVINO core IR to static-capacity state."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import openvino as ov

from ov_stateful_cache import make_static_kv_stateful


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--num-layers", type=int,
        help="K/V layer count; inferred from graph outputs when omitted",
    )
    parser.add_argument(
        "--base-input-count", type=int,
        help="non-cache input count; inferred from graph inputs/outputs when omitted",
    )
    parser.add_argument(
        "--cache-position-index", type=int,
        help="cache_position input index; inferred from tensor names when omitted",
    )
    parser.add_argument("--max-seq", type=int, required=True)
    parser.add_argument("--state-prefix", required=True)
    parser.add_argument("--compile-smoke", action="store_true")
    parser.add_argument(
        "--report-json", type=Path,
        help="write transformation provenance and compile-smoke results",
    )
    args = parser.parse_args()

    core = ov.Core()
    model = core.read_model(args.input)
    kv_count = len(model.get_results()) - 1
    if kv_count <= 0 or kv_count % 2:
        raise ValueError(
            f"cannot infer K/V layout from {len(model.get_results())} graph outputs"
        )
    num_layers = args.num_layers if args.num_layers is not None else kv_count // 2
    base_input_count = (
        args.base_input_count
        if args.base_input_count is not None
        else len(model.get_parameters()) - kv_count
    )
    if args.cache_position_index is not None:
        cache_position_index = args.cache_position_index
    else:
        cache_matches = [
            index
            for index, input_port in enumerate(model.inputs[:base_input_count])
            if "cache_position" in input_port.names
        ]
        if len(cache_matches) != 1:
            raise ValueError(
                "could not identify exactly one cache_position input; "
                "pass --cache-position-index explicitly"
            )
        cache_position_index = cache_matches[0]
    make_static_kv_stateful(
        model,
        num_layers=num_layers,
        base_input_count=base_input_count,
        cache_position_index=cache_position_index,
        max_seq=args.max_seq,
        state_prefix=args.state_prefix,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ov.save_model(model, args.output, compress_to_fp16=False)
    output_bin = args.output.with_suffix(".bin")

    report: dict[str, object] = {
        "openvino_version": ov.__version__,
        "input": str(args.input),
        "output": str(args.output),
        "parameters": len(model.get_parameters()),
        "results": len(model.get_results()),
        "variables": len(model.get_variables()),
        "num_layers": num_layers,
        "base_input_count": base_input_count,
        "cache_position_index": cache_position_index,
        "max_seq": args.max_seq,
        "source_ir_sha256": _sha256(args.input),
        "output_xml_sha256": _sha256(args.output),
        "output_bin_sha256": _sha256(output_bin),
    }
    if args.compile_smoke:
        compiled = core.compile_model(model, "CPU")
        request = compiled.create_infer_request()
        states = request.query_state()
        report["compiled"] = True
        report["query_state_count"] = len(states)
        report["state_shapes"] = sorted({str(state.state.shape) for state in states})
    text = json.dumps(report, indent=2)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Compare a rewritten stateful main-core IR with its explicit-cache source IR."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def _metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    error = reference - candidate
    absolute = np.abs(error)
    error_rms = float(np.sqrt(np.mean(np.square(error))))
    signal_rms = float(np.sqrt(np.mean(np.square(reference))))
    return {
        "max_abs": float(absolute.max(initial=0.0)),
        "mean_abs": float(absolute.mean()),
        "snr_db": float(
            20.0 * np.log10(max(signal_rms, 1e-12) / max(error_rms, 1e-12))
        ),
    }


def _infer(request, inputs: list[np.ndarray], output_count: int) -> list[np.ndarray]:
    request.infer(inputs)
    return [
        np.array(request.get_output_tensor(i).data, copy=True)
        for i in range(output_count)
    ]


def _state_name(index: int, prefix: str) -> str:
    layer = index // 2
    kind = "key" if index % 2 == 0 else "value"
    return f"{prefix}.layer{layer}.{kind}"


def run(args: argparse.Namespace) -> dict[str, object]:
    import openvino as ov

    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    dims = metadata["main_dims"]
    hidden = int(dims["hidden_size"])
    kv_heads = int(dims["num_kv_heads"])
    head_dim = int(dims["head_dim"])
    layers = int(dims["num_layers"])

    config = {
        "PERFORMANCE_HINT": "LATENCY",
        "NUM_STREAMS": "1",
        "INFERENCE_NUM_THREADS": str(args.threads),
        "INFERENCE_PRECISION_HINT": "f32",
        "DYNAMIC_QUANTIZATION_GROUP_SIZE": "32",
    }
    core = ov.Core()
    explicit = core.compile_model(args.explicit, "CPU", config)
    stateful = core.compile_model(args.stateful, "CPU", config)
    explicit_request = explicit.create_infer_request()
    stateful_request = stateful.create_infer_request()
    stateful_request.reset_state()

    states = {state.name: state for state in stateful_request.query_state()}
    expected_state_names = {
        _state_name(index, args.state_prefix) for index in range(2 * layers)
    }
    if set(states) != expected_state_names:
        raise RuntimeError(
            f"state names differ: missing={sorted(expected_state_names - set(states))}, "
            f"extra={sorted(set(states) - expected_state_names)}"
        )

    rng = np.random.default_rng(args.seed)
    rows = []
    failures = []
    explicit_cache = [
        np.empty((1, kv_heads, 0, head_dim), dtype=np.float32)
        for _ in range(2 * layers)
    ]

    for step in range(args.decode_steps + 1):
        is_prefill = step == 0
        seq = args.prefill_seq if is_prefill else 1
        prior = 0 if is_prefill else args.prefill_seq + step - 1
        inputs_embeds = rng.standard_normal((1, seq, hidden), dtype=np.float32)
        attention_mask = np.ones((1, prior + seq), dtype=np.int64)
        position_ids = np.arange(prior, prior + seq, dtype=np.int64)[None, :]
        cache_position = np.arange(prior, prior + seq, dtype=np.int64)
        base_inputs = [inputs_embeds, attention_mask, position_ids, cache_position]

        explicit_outputs = _infer(
            explicit_request,
            [*base_inputs, *explicit_cache],
            1 + 2 * layers,
        )
        stateful_outputs = _infer(stateful_request, base_inputs, 1)
        metrics = _metrics(explicit_outputs[0], stateful_outputs[0])
        row = {
            "scope": "prefill" if is_prefill else "decode",
            "step": step,
            "prior": prior,
            "seq": seq,
            **metrics,
        }
        rows.append(row)
        if metrics["max_abs"] > args.max_abs:
            failures.append(
                f"step {step}: max_abs {metrics['max_abs']:.3e} > {args.max_abs:.3e}"
            )

        explicit_cache = explicit_outputs[1:]
        used_len = prior + seq
        for index, expected in enumerate(explicit_cache):
            actual = np.asarray(states[_state_name(index, args.state_prefix)].state.data)
            cache_metrics = _metrics(expected, actual[:, :, :used_len, :])
            if cache_metrics["max_abs"] > args.max_abs:
                failures.append(
                    f"step {step} state {index}: max_abs "
                    f"{cache_metrics['max_abs']:.3e} > {args.max_abs:.3e}"
                )

    stateful_request.reset_state()
    if any(np.any(np.asarray(state.state.data)) for state in states.values()):
        failures.append("reset_state did not clear every K/V state")

    return {
        "openvino_version": ov.__version__,
        "explicit_ir": str(args.explicit),
        "stateful_ir": str(args.stateful),
        "model_revision": metadata["model_revision"],
        "seed": args.seed,
        "threads": args.threads,
        "prefill_seq": args.prefill_seq,
        "decode_steps": args.decode_steps,
        "state_count": len(states),
        "max_abs_tolerance": args.max_abs,
        "results": rows,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--explicit", type=Path, required=True)
    parser.add_argument("--stateful", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--state-prefix", default="main")
    parser.add_argument("--prefill-seq", type=int, default=8)
    parser.add_argument("--decode-steps", type=int, default=3)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--seed", type=int, default=20260629)
    parser.add_argument("--max-abs", type=float, default=1e-5)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    report = run(args)
    text = json.dumps(report, indent=2)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text + "\n", encoding="utf-8")
    print(text)
    raise SystemExit(1 if report["failures"] else 0)


if __name__ == "__main__":
    main()

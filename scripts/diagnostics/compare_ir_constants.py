#!/usr/bin/env python3
"""Compare Constant tensors in two structurally equivalent OpenVINO IRs."""

from __future__ import annotations

import argparse

import numpy as np
import openvino as ov


def _constants(model) -> dict[str, np.ndarray]:
    result = {}
    for node in model.get_ordered_ops():
        if node.get_type_name() != "Constant":
            continue
        result[node.get_friendly_name()] = np.asarray(node.get_data())
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference")
    parser.add_argument("candidate")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()
    core = ov.Core()
    reference = _constants(core.read_model(args.reference))
    candidate = _constants(core.read_model(args.candidate))
    print(f"reference_constants={len(reference)} candidate_constants={len(candidate)}")
    print(f"only_reference={sorted(reference.keys() - candidate.keys())[:20]}")
    print(f"only_candidate={sorted(candidate.keys() - reference.keys())[:20]}")
    differences = []
    exact = 0
    for name in reference.keys() & candidate.keys():
        left, right = reference[name], candidate[name]
        if left.shape != right.shape or left.dtype != right.dtype:
            differences.append((float("inf"), name, left.shape, right.shape, str(left.dtype), str(right.dtype)))
            continue
        if np.array_equal(left, right, equal_nan=True):
            exact += 1
            continue
        if np.issubdtype(left.dtype, np.number):
            delta = np.abs(left.astype(np.float64) - right.astype(np.float64))
            differences.append((float(delta.max(initial=0)), name, left.shape,
                                float(np.nanmin(left)), float(np.nanmax(left)),
                                float(np.nanmin(right)), float(np.nanmax(right))))
        else:
            differences.append((float("inf"), name, left.shape, "non-numeric"))
    differences.sort(key=lambda row: row[0], reverse=True)
    print(f"exact={exact} different={len(differences)}")
    print("max_abs_diff name shape reference_min reference_max candidate_min candidate_max")
    for row in differences[: args.limit]:
        print(*row)
    return 1 if differences or reference.keys() != candidate.keys() else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate FP32 and INT8 OpenVINO transformer core outputs against PyTorch.

Covers three comparison scopes for both the main talker and the code predictor:

  1. Prefill hidden state: compare PyTorch core vs FP32 IR on the first prefill call.
  2. Decode hidden state: compare bounded multi-step decode while carrying each backend's
     own K/V cache so accumulated divergence is visible.
  3. Top-1 token agreement: project the generation-relevant final hidden state through
     talker.codec_head or the corresponding predictor lm_head for every tested step.

These tests use synthetic inputs with realistic shape and dtype and require both the IR
artifacts and the loaded model weights. They characterize the exported cores; they do not
replace generation-path, listening, or warm performance validation.

The position_ids / cache_position contract used here (simple arange) is the scaffold for
the full M2 parity gate.  The mRoPE 3-axis expansion and the exact values the eager
generation path supplies are NOT yet confirmed; a generation-level code-sequence comparison
(feeding an actual prompt through PyTorch generation vs a hooked IR version) is required
before the M2 milestone is declared complete.

Run in the exporter container against a full five-graph export directory:

    python test_transformer_parity.py --model-dir /ov_output/<versioned-dir> --threads 6

Writes a transformer_parity.json beside the IR files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from parity_contract import require_output_head


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--prefill-seq", type=int, default=8)
    parser.add_argument("--decode-steps", type=int, default=3)
    parser.add_argument(
        "--predictor-decode-steps",
        type=int,
        default=14,
        help="predictor decode calls after prefill; 14 covers all 15 predictor output heads",
    )
    parser.add_argument("--seed", type=int, default=20260628)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--fp32-max-abs", type=float, default=1e-2,
                        help="max absolute error threshold for FP32 hidden-state parity")
    parser.add_argument("--fp32-min-snr", type=float, default=60.0,
                        help="SNR gate (dB) for FP32; overrides --fp32-max-abs when set")
    parser.add_argument("--int8-max-abs", type=float, default=5e-2,
                        help="max absolute error threshold for INT8 hidden-state parity")
    parser.add_argument("--int8-min-snr", type=float, default=30.0,
                        help="SNR gate (dB) for INT8; overrides --int8-max-abs when set")
    parser.add_argument("--int8-min-token-agreement", type=float, default=0.90,
                        help="minimum top-1 token agreement fraction for INT8 vs PyTorch")
    parser.add_argument("--fp32-min-token-agreement", type=float, default=0.95,
                        help="minimum top-1 token agreement fraction for FP32 vs PyTorch")
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args()


def _metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    absolute = np.abs(reference - candidate)
    relative = absolute / np.maximum(np.abs(reference), 1e-6)
    error_rms = float(np.sqrt(np.mean(np.square(reference - candidate))))
    signal_rms = float(np.sqrt(np.mean(np.square(reference))))
    snr_db = float(20.0 * np.log10(max(signal_rms, 1e-12) / max(error_rms, 1e-12)))
    return {
        "max_abs": float(absolute.max(initial=0.0)),
        "mean_abs": float(absolute.mean()),
        "p99_abs": float(np.percentile(absolute, 99)),
        "error_rms": error_rms,
        "signal_rms": signal_rms,
        "snr_db": snr_db,
        "max_rel": float(relative.max(initial=0.0)),
        "mean_rel": float(relative.mean()),
    }


def _top1_agreement(a: np.ndarray, b: np.ndarray) -> float:
    """Fraction of positions where argmax agrees along the last axis."""
    return float(np.mean(np.argmax(a, axis=-1) == np.argmax(b, axis=-1)))


def _project_last_hidden(output_heads, hidden: np.ndarray, head_index: int) -> np.ndarray:
    """Project the generation-relevant final position through the required codebook head."""
    output_head = require_output_head(output_heads, head_index)
    import torch

    return output_head(torch.from_numpy(hidden[:, -1:, :])).detach().numpy()


def _timed(callable_):
    started = time.perf_counter()
    value = callable_()
    return value, time.perf_counter() - started


def _build_cache(past_kv_flat: list[np.ndarray], num_layers: int):
    """Reconstruct DynamicCache from flat k0,v0,k1,v1,... numpy array list."""
    import torch
    from transformers.cache_utils import DynamicCache

    legacy = tuple(
        (torch.from_numpy(past_kv_flat[2 * i]), torch.from_numpy(past_kv_flat[2 * i + 1]))
        for i in range(num_layers)
    )
    return DynamicCache.from_legacy_cache(legacy)


def _run_core(core_module, inputs_embeds, attention_mask, position_ids, cache_position, cache,
              *, generation_steps=None):
    """Single forward through a PyTorch transformer core."""
    import torch

    kwargs = dict(
        inputs_embeds=inputs_embeds,
        attention_mask=attention_mask,
        position_ids=position_ids,
        cache_position=cache_position,
        past_key_values=cache,
        use_cache=True,
    )
    if generation_steps is not None:
        kwargs["generation_steps"] = generation_steps
    with torch.inference_mode():
        return core_module(**kwargs)


def _ov_infer(compiled_model, *inputs: np.ndarray) -> list[np.ndarray]:
    result = compiled_model(list(inputs))
    return [np.asarray(result[i]) for i in range(len(result))]


def _compare_core(
    core_name: str,
    pt_core,
    ov_prefill,
    ov_decode,
    dims: dict[str, int],
    prefill_seq: int,
    decode_steps: int,
    seed: int,
    output_heads,
    fp32_max_abs: float,
    fp32_min_snr: float | None,
    fp32_min_token_agreement: float,
    predictor: bool,
    *,
    int8_prefill=None,
    int8_decode=None,
    int8_max_abs: float,
    int8_min_snr: float | None,
    int8_min_token_agreement: float,
) -> tuple[list[dict], list[str]]:
    import torch

    rng = torch.Generator(device="cpu").manual_seed(seed)
    hidden = dims["hidden_size"]
    kv_heads = dims["num_kv_heads"]
    head_dim = dims["head_dim"]
    num_layers = dims["num_layers"]

    def _rand(*shape):
        return torch.randn(*shape, generator=rng)

    results = []
    failures = []
    has_int8 = int8_prefill is not None and int8_decode is not None

    # ── Prefill ───────────────────────────────────────────────────────────────
    inputs_embeds = _rand(1, prefill_seq, hidden)
    attention_mask = torch.ones(1, prefill_seq, dtype=torch.long)
    position_ids = torch.arange(prefill_seq).unsqueeze(0)
    cache_position = torch.arange(prefill_seq)

    from transformers.cache_utils import DynamicCache
    gen_steps = torch.zeros(1, dtype=torch.long) if predictor else None

    pt_out, pt_seconds = _timed(lambda: _run_core(
        pt_core, inputs_embeds, attention_mask, position_ids, cache_position,
        DynamicCache(), generation_steps=gen_steps,
    ))
    pt_hidden_prefill = pt_out.last_hidden_state.detach().numpy()
    pt_kv_legacy = pt_out.past_key_values.to_legacy_cache()
    pt_kv_flat = []
    for k, v in pt_kv_legacy:
        pt_kv_flat.extend([k.detach().numpy(), v.detach().numpy()])

    # Build OV prefill inputs
    ov_prefill_inputs = [
        inputs_embeds.numpy(),
        attention_mask.numpy(),
        position_ids.numpy(),
        cache_position.numpy(),
    ]
    if predictor:
        ov_prefill_inputs.append(gen_steps.numpy())

    ov_out_prefill, ov_prefill_seconds = _timed(lambda: _ov_infer(ov_prefill, *ov_prefill_inputs))
    ov_hidden_prefill = ov_out_prefill[0]
    ov_kv_flat = ov_out_prefill[1:]

    # Verify K/V cache shapes from OV match expectation
    expected_kv_shape = (1, kv_heads, prefill_seq, head_dim)
    kv_shape_ok = all(t.shape == expected_kv_shape for t in ov_kv_flat)

    prefill_metrics = _metrics(pt_hidden_prefill, ov_hidden_prefill)
    prefill_row = {
        "scope": f"{core_name}/prefill",
        "prefill_seq": prefill_seq,
        "pt_seconds": pt_seconds,
        "ov_seconds": ov_prefill_seconds,
        "kv_cache_shape_ok": kv_shape_ok,
        "expected_kv_shape": list(expected_kv_shape),
        "fp32": prefill_metrics,
    }

    pt_logits_prefill = _project_last_hidden(output_heads, pt_hidden_prefill, 0)
    ov_logits = _project_last_hidden(output_heads, ov_hidden_prefill, 0)
    prefill_row["top1_agreement"] = _top1_agreement(pt_logits_prefill, ov_logits)

    # INT8 prefill comparison (if available)
    if has_int8:
        int8_out, int8_seconds = _timed(lambda: _ov_infer(int8_prefill, *ov_prefill_inputs))
        int8_hidden = int8_out[0]
        int8_kv_flat = int8_out[1:]
        int8_metrics = _metrics(pt_hidden_prefill, int8_hidden)
        prefill_row["int8"] = int8_metrics
        prefill_row["int8_seconds"] = int8_seconds

        int8_logits = _project_last_hidden(output_heads, int8_hidden, 0)
        prefill_row["int8_top1_agreement"] = _top1_agreement(pt_logits_prefill, int8_logits)

    results.append(prefill_row)

    _check_failures(failures, f"{core_name}/prefill", prefill_metrics, fp32_max_abs, fp32_min_snr)
    if not kv_shape_ok:
        failures.append(f"{core_name}/prefill: K/V cache shape mismatch")
    if prefill_row["top1_agreement"] < fp32_min_token_agreement:
        failures.append(
            f"{core_name}/prefill: top-1 agreement {prefill_row['top1_agreement']:.3f}"
            f" below {fp32_min_token_agreement}"
        )

    if has_int8 and "int8" in prefill_row:
        _check_int8_failures(
            failures, f"{core_name}/prefill",
            prefill_row["int8"], int8_max_abs, int8_min_snr,
            prefill_row.get("int8_top1_agreement"), int8_min_token_agreement,
        )

    # ── Decode steps ──────────────────────────────────────────────────────────
    # Feed the PyTorch prefill K/V cache to both backends so the decode test is
    # independent of any prefill-stage discrepancy.
    for step in range(decode_steps):
        prior = prefill_seq + step
        decode_embed = _rand(1, 1, hidden)
        decode_mask = torch.ones(1, prior + 1, dtype=torch.long)
        decode_pos = torch.tensor([[prior]])
        decode_cache_pos = torch.tensor([prior])
        gen_steps_decode = torch.tensor([step + 1], dtype=torch.long) if predictor else None

        pt_cache = _build_cache(pt_kv_flat, num_layers)
        pt_dec_out, pt_dec_seconds = _timed(lambda: _run_core(
            pt_core, decode_embed, decode_mask, decode_pos, decode_cache_pos,
            pt_cache, generation_steps=gen_steps_decode,
        ))
        pt_hidden_decode = pt_dec_out.last_hidden_state.detach().numpy()
        pt_kv_flat_updated = []
        for k, v in pt_dec_out.past_key_values.to_legacy_cache():
            pt_kv_flat_updated.extend([k.detach().numpy(), v.detach().numpy()])

        ov_decode_inputs = [
            decode_embed.numpy(),
            decode_mask.numpy(),
            decode_pos.numpy(),
            decode_cache_pos.numpy(),
        ]
        if predictor:
            ov_decode_inputs.append(gen_steps_decode.numpy())
        ov_decode_inputs.extend(ov_kv_flat)

        ov_out_decode, ov_dec_seconds = _timed(lambda: _ov_infer(ov_decode, *ov_decode_inputs))
        ov_hidden_decode = ov_out_decode[0]
        ov_kv_flat_updated = ov_out_decode[1:]

        decode_metrics = _metrics(pt_hidden_decode, ov_hidden_decode)
        decode_row = {
            "scope": f"{core_name}/decode",
            "step": step,
            "prior_seq": prior,
            "pt_seconds": pt_dec_seconds,
            "ov_seconds": ov_dec_seconds,
            "fp32": decode_metrics,
        }

        head_index = step + 1 if predictor else 0
        pt_logits_decode = _project_last_hidden(output_heads, pt_hidden_decode, head_index)
        ov_logits = _project_last_hidden(output_heads, ov_hidden_decode, head_index)
        decode_row["top1_agreement"] = _top1_agreement(pt_logits_decode, ov_logits)

        # INT8 decode comparison (if available)
        if has_int8:
            int8_decode_inputs = [*ov_decode_inputs[: 5 if predictor else 4], *int8_kv_flat]
            int8_out, int8_seconds = _timed(
                lambda: _ov_infer(int8_decode, *int8_decode_inputs)
            )
            int8_hidden = int8_out[0]
            int8_kv_flat_updated = int8_out[1:]
            int8_metrics = _metrics(pt_hidden_decode, int8_hidden)
            decode_row["int8"] = int8_metrics
            decode_row["int8_seconds"] = int8_seconds

            int8_logits = _project_last_hidden(output_heads, int8_hidden, head_index)
            decode_row["int8_top1_agreement"] = _top1_agreement(pt_logits_decode, int8_logits)

        results.append(decode_row)

        _check_failures(failures, f"{core_name}/decode/step{step}", decode_metrics, fp32_max_abs, fp32_min_snr)
        if decode_row["top1_agreement"] < fp32_min_token_agreement:
            failures.append(
                f"{core_name}/decode/step{step}: top-1 agreement {decode_row['top1_agreement']:.3f}"
                f" below {fp32_min_token_agreement}"
            )

        if has_int8 and "int8" in decode_row:
            _check_int8_failures(
                failures, f"{core_name}/decode/step{step}",
                decode_row["int8"], int8_max_abs, int8_min_snr,
                decode_row.get("int8_top1_agreement"), int8_min_token_agreement,
            )

        # Carry each backend's own updated cache forward so accumulated divergence is visible.
        pt_kv_flat = pt_kv_flat_updated
        ov_kv_flat = ov_kv_flat_updated
        if has_int8:
            int8_kv_flat = int8_kv_flat_updated

    return results, failures


def _check_failures(failures, label, metrics, fp32_max_abs, fp32_min_snr):
    snr = metrics.get("snr_db")
    if fp32_min_snr is not None and snr is not None:
        if snr < fp32_min_snr:
            failures.append(f"{label}: FP32 SNR {snr:.1f} dB below {fp32_min_snr} dB")
    elif metrics["max_abs"] >= fp32_max_abs:
        failures.append(
            f"{label}: FP32 max_abs {metrics['max_abs']:.3e} >= {fp32_max_abs:.3e}"
        )


def _check_int8_failures(
    failures, label, metrics, int8_max_abs, int8_min_snr,
    top1_agreement, int8_min_token_agreement,
):
    snr = metrics.get("snr_db")
    if int8_min_snr is not None and snr is not None:
        if snr < int8_min_snr:
            failures.append(
                f"{label}: INT8 SNR {snr:.1f} dB below {int8_min_snr} dB"
            )
    elif metrics["max_abs"] >= int8_max_abs:
        failures.append(
            f"{label}: INT8 max_abs {metrics['max_abs']:.3e} >= {int8_max_abs:.3e}"
        )
    if (
        top1_agreement is not None
        and top1_agreement < int8_min_token_agreement
    ):
        failures.append(
            f"{label}: INT8 top-1 agreement {top1_agreement:.3f}"
            f" below {int8_min_token_agreement}"
        )


def run() -> int:
    args = parse_args()
    metadata_path = args.model_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    required = {
        "main_prefill.xml", "main_decode.xml",
        "predictor_prefill.xml", "predictor_decode.xml",
    }
    missing = sorted(name for name in required if not (args.model_dir / name).is_file())
    if missing:
        raise SystemExit(f"missing IR files: {missing}")

    int8_files = {
        "main_prefill": "main_prefill_int8.xml",
        "main_decode": "main_decode_int8.xml",
        "predictor_prefill": "predictor_prefill_int8.xml",
        "predictor_decode": "predictor_decode_int8.xml",
    }
    present_int8 = {
        name: (args.model_dir / filename).is_file()
        for name, filename in int8_files.items()
    }
    has_all_int8 = all(present_int8.values())
    if any(present_int8.values()) and not has_all_int8:
        missing_int8 = sorted(name for name, present in present_int8.items() if not present)
        raise SystemExit(f"incomplete INT8 artifact set; missing: {missing_int8}")
    if metadata.get("compression") in {"int8", "both"} and not has_all_int8:
        raise SystemExit("metadata requires INT8 parity but no complete INT8 artifact set exists")

    from export_openvino import _resolve_vocoder_decoder, _set_eager_attention
    from model_config import configure_hf_token
    configure_hf_token()

    import openvino as ov
    import torch
    from qwen_tts import Qwen3TTSModel

    torch.set_num_threads(args.threads)
    print(f"[parity] loading model {metadata['model_repo']} ...", flush=True)
    wrapped = Qwen3TTSModel.from_pretrained(
        metadata["model_repo"],
        revision=metadata["model_revision"],
        device_map="cpu",
        dtype=torch.float32,
        attn_implementation="eager",
    )
    talker = wrapped.model.talker
    _set_eager_attention(talker.model)
    _set_eager_attention(talker.code_predictor.model)

    import ov_export_wrappers as wrappers
    main_dims = wrappers.core_dims(talker.model.config)
    pred_dims = wrappers.core_dims(talker.code_predictor.model.config)

    ov_config = {
        "PERFORMANCE_HINT": "LATENCY",
        "NUM_STREAMS": "1",
        "INFERENCE_NUM_THREADS": str(args.threads),
        "INFERENCE_PRECISION_HINT": "f32",
    }
    core = ov.Core()
    main_prefill = core.compile_model(args.model_dir / "main_prefill.xml", "CPU", ov_config)
    main_decode = core.compile_model(args.model_dir / "main_decode.xml", "CPU", ov_config)
    pred_prefill = core.compile_model(args.model_dir / "predictor_prefill.xml", "CPU", ov_config)
    pred_decode = core.compile_model(args.model_dir / "predictor_decode.xml", "CPU", ov_config)

    # Optionally compile INT8 models if present
    int8_config = {
        "PERFORMANCE_HINT": "LATENCY",
        "NUM_STREAMS": "1",
        "INFERENCE_NUM_THREADS": str(args.threads),
        "INFERENCE_PRECISION_HINT": "f32",
        "DYNAMIC_QUANTIZATION_GROUP_SIZE": "32",
    }
    int8_main_prefill = None
    int8_main_decode = None
    int8_pred_prefill = None
    int8_pred_decode = None
    if has_all_int8:
        print("[parity] INT8 IR files detected — compiling INT8 models", flush=True)
        int8_main_prefill = core.compile_model(
            args.model_dir / int8_files["main_prefill"], "CPU", int8_config
        )
        int8_main_decode = core.compile_model(
            args.model_dir / int8_files["main_decode"], "CPU", int8_config
        )
        int8_pred_prefill = core.compile_model(
            args.model_dir / int8_files["predictor_prefill"], "CPU", int8_config
        )
        int8_pred_decode = core.compile_model(
            args.model_dir / int8_files["predictor_decode"], "CPU", int8_config
        )
    else:
        print("[parity] INT8 IR not found — running FP32-only", flush=True)

    main_output_heads = [talker.codec_head]
    predictor_output_heads = list(talker.code_predictor.lm_head)
    required_predictor_heads = args.predictor_decode_steps + 1
    if len(predictor_output_heads) < required_predictor_heads:
        raise RuntimeError(
            f"predictor token parity requires {required_predictor_heads} output heads, "
            f"found {len(predictor_output_heads)}"
        )

    all_results = []
    all_failures = []

    print("[parity] comparing main core ...", flush=True)
    r, f = _compare_core(
        "main", talker.model, main_prefill, main_decode, main_dims,
        args.prefill_seq, args.decode_steps, args.seed,
        main_output_heads,
        args.fp32_max_abs, args.fp32_min_snr, args.fp32_min_token_agreement,
        predictor=False,
        int8_prefill=int8_main_prefill,
        int8_decode=int8_main_decode,
        int8_max_abs=args.int8_max_abs,
        int8_min_snr=args.int8_min_snr,
        int8_min_token_agreement=args.int8_min_token_agreement,
    )
    all_results.extend(r)
    all_failures.extend(f)

    print("[parity] comparing predictor core ...", flush=True)
    r, f = _compare_core(
        "predictor", talker.code_predictor.model, pred_prefill, pred_decode, pred_dims,
        2, args.predictor_decode_steps, args.seed + 1,
        predictor_output_heads,
        args.fp32_max_abs, args.fp32_min_snr, args.fp32_min_token_agreement,
        predictor=True,
        int8_prefill=int8_pred_prefill,
        int8_decode=int8_pred_decode,
        int8_max_abs=args.int8_max_abs,
        int8_min_snr=args.int8_min_snr,
        int8_min_token_agreement=args.int8_min_token_agreement,
    )
    all_results.extend(r)
    all_failures.extend(f)

    report = {
        "model_repo": metadata["model_repo"],
        "model_revision": metadata["model_revision"],
        "source_commit": metadata["source_commit"],
        "exporter_image_digest": metadata["exporter_image_digest"],
        "ir_metadata_sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
        "openvino_version": ov.__version__,
        "seed": args.seed,
        "threads": args.threads,
        "prefill_seq": args.prefill_seq,
        "decode_steps": args.decode_steps,
        "predictor_decode_steps": args.predictor_decode_steps,
        "inference_precision_hint": "f32",
        "fp32_max_abs_tolerance": args.fp32_max_abs,
        "fp32_min_snr_db": args.fp32_min_snr,
        "fp32_min_token_agreement": args.fp32_min_token_agreement,
        "int8_available": has_all_int8,
        "int8_max_abs_tolerance": args.int8_max_abs,
        "int8_min_snr_db": args.int8_min_snr,
        "int8_min_token_agreement": args.int8_min_token_agreement,
        "NOTE": (
            "Synthetic core-level characterization only. Position IDs/cache positions use "
            "simple arange; actual generation embeddings, 3-axis mRoPE values, sampled code "
            "sequences, listening quality, and warm end-to-end performance require the M4 runtime."
        ),
        "results": all_results,
        "failures": all_failures,
    }
    output_path = args.output_json or args.model_dir / "transformer_parity.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if all_failures else 0


if __name__ == "__main__":
    raise SystemExit(run())

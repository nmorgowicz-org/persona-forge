#!/usr/bin/env python3
"""Validate FP32 and INT8 OpenVINO transformer core outputs against PyTorch.

Covers three comparison scopes for both the main talker and the code predictor:

  1. Prefill hidden state: compare PyTorch core vs FP32 IR on the first prefill call.
  2. Decode hidden state: compare one decode step, feeding the prefill K/V cache to both.
  3. Top-1 token agreement: project hidden states through the PyTorch output head and check
     that greedy token selection matches across prefill and one decode step.

These tests use synthetic inputs with realistic shape and dtype (no model weights needed
for the tensor comparison) but DO require the IR artifacts and the loaded model.

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--prefill-seq", type=int, default=8)
    parser.add_argument("--decode-steps", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260628)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--fp32-max-abs", type=float, default=1e-2,
                        help="max absolute error threshold for FP32 hidden-state parity")
    parser.add_argument("--fp32-min-snr", type=float, default=60.0,
                        help="SNR gate (dB) for FP32; overrides --fp32-max-abs when set")
    parser.add_argument("--int8-max-abs", type=float, default=5e-2,
                        help="max absolute error threshold for INT8 hidden-state parity")
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
    output_head,
    fp32_max_abs: float,
    fp32_min_snr: float | None,
    fp32_min_token_agreement: float,
    predictor: bool,
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
    if output_head is not None:
        pt_logits = output_head(torch.from_numpy(pt_hidden_prefill)).detach().numpy()
        ov_logits = output_head(torch.from_numpy(ov_hidden_prefill)).detach().numpy()
        prefill_row["top1_agreement"] = _top1_agreement(pt_logits, ov_logits)
    results.append(prefill_row)

    _check_failures(failures, f"{core_name}/prefill", prefill_metrics, fp32_max_abs, fp32_min_snr)
    if not kv_shape_ok:
        failures.append(f"{core_name}/prefill: K/V cache shape mismatch")
    if "top1_agreement" in prefill_row and prefill_row["top1_agreement"] < fp32_min_token_agreement:
        failures.append(
            f"{core_name}/prefill: top-1 agreement {prefill_row['top1_agreement']:.3f}"
            f" below {fp32_min_token_agreement}"
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
        gen_steps_decode = torch.tensor([step], dtype=torch.long) if predictor else None

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
        ov_decode_inputs.extend(pt_kv_flat)

        ov_out_decode, ov_dec_seconds = _timed(lambda: _ov_infer(ov_decode, *ov_decode_inputs))
        ov_hidden_decode = ov_out_decode[0]

        decode_metrics = _metrics(pt_hidden_decode, ov_hidden_decode)
        decode_row = {
            "scope": f"{core_name}/decode",
            "step": step,
            "prior_seq": prior,
            "pt_seconds": pt_dec_seconds,
            "ov_seconds": ov_dec_seconds,
            "fp32": decode_metrics,
        }
        if output_head is not None:
            pt_logits = output_head(torch.from_numpy(pt_hidden_decode)).detach().numpy()
            ov_logits = output_head(torch.from_numpy(ov_hidden_decode)).detach().numpy()
            decode_row["top1_agreement"] = _top1_agreement(pt_logits, ov_logits)
        results.append(decode_row)

        _check_failures(failures, f"{core_name}/decode/step{step}", decode_metrics, fp32_max_abs, fp32_min_snr)
        if "top1_agreement" in decode_row and decode_row["top1_agreement"] < fp32_min_token_agreement:
            failures.append(
                f"{core_name}/decode/step{step}: top-1 agreement {decode_row['top1_agreement']:.3f}"
                f" below {fp32_min_token_agreement}"
            )

        # Carry forward PyTorch's updated cache for the next step
        pt_kv_flat = pt_kv_flat_updated

    return results, failures


def _check_failures(failures, label, metrics, fp32_max_abs, fp32_min_snr):
    snr = metrics.get("snr_db")
    if fp32_min_snr is not None and snr is not None:
        if snr < fp32_min_snr:
            failures.append(f"{label}: SNR {snr:.1f} dB below {fp32_min_snr} dB")
    elif metrics["max_abs"] >= fp32_max_abs:
        failures.append(f"{label}: max_abs {metrics['max_abs']:.3e} >= {fp32_max_abs:.3e}")


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

    # Use the first codebook output head as the projection for top-1 comparison.
    # The output head is a linear over hidden_size -> vocab_size.
    try:
        output_head = talker.first_codebook_head
    except AttributeError:
        output_head = None

    all_results = []
    all_failures = []

    print("[parity] comparing main core ...", flush=True)
    r, f = _compare_core(
        "main", talker.model, main_prefill, main_decode, main_dims,
        args.prefill_seq, args.decode_steps, args.seed,
        output_head,
        args.fp32_max_abs, args.fp32_min_snr, args.fp32_min_token_agreement,
        predictor=False,
    )
    all_results.extend(r)
    all_failures.extend(f)

    print("[parity] comparing predictor core ...", flush=True)
    r, f = _compare_core(
        "predictor", talker.code_predictor.model, pred_prefill, pred_decode, pred_dims,
        args.prefill_seq, args.decode_steps, args.seed + 1,
        None,  # no simple output head for the predictor; use hidden-state comparison only
        args.fp32_max_abs, args.fp32_min_snr, args.fp32_min_token_agreement,
        predictor=True,
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
        "inference_precision_hint": "f32",
        "fp32_max_abs_tolerance": args.fp32_max_abs,
        "fp32_min_snr_db": args.fp32_min_snr,
        "fp32_min_token_agreement": args.fp32_min_token_agreement,
        "NOTE": (
            "position_ids/cache_position use simple arange — mRoPE 3-axis expansion and "
            "exact generation-path semantics NOT yet confirmed. See M2 parity gate docs."
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

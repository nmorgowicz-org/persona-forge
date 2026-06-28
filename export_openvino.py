#!/usr/bin/env python3
"""Milestone 2/3 exporter: Qwen3-TTS transformer cores -> OpenVINO IR (+ optional INT8).

One-shot disposable CLI for the exporter image. Resolves the configured checkpoint,
wraps the two transformer cores (see ov_export_wrappers.py), converts each to a prefill
and a decode IR graph with openvino.convert_model, optionally compresses weights with
NNCF, and publishes a versioned, checkpoint-specific output directory atomically.

    python export_openvino.py --output-dir /ov_output --compression both --validate

Model selection / auth come from MODEL_SIZE | MODEL_REPO, MODEL_REVISION, and optional
HF_TOKEN | HF_TOKEN_FILE (handled by model_config). Reuses the standard Hugging Face
cache; writes only under --output-dir.

STATUS: first-draft scaffold. The graph-level details below (dynamic axes, the exact
position_ids/cache_position values, predictor generation_steps, and the parity gate) must
be iterated and confirmed on dockermisc1 before any IR is trusted. The script exits
nonzero and leaves no final directory on any failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from model_config import configure_hf_token, resolve_model_repo

COMPRESSION_CHOICES = ("fp32", "int8", "both")

# Graph names match the plan's output layout.
GRAPHS = ("main_prefill", "main_decode", "predictor_prefill", "predictor_decode", "vocoder_decoder")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, help="parent dir for the versioned IR directory")
    parser.add_argument("--compression", choices=COMPRESSION_CHOICES, default="both")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="run the FP32 parity gate before publishing",
    )
    parser.add_argument(
        "--int8-mode",
        choices=("sym", "asym", "int8_asym", "int8_sym"),
        default="int8_asym",
        help="NNCF INT8 quantization mode (default: int8_asym)",
    )
    parser.add_argument(
        "--int8-group-size",
        type=int,
        default=32,
        help="NNCF weight compression group size: 0=per-channel, 32/64=per-group (default: 32)",
    )
    parser.add_argument(
        "--int8-ratio",
        type=float,
        default=1.0,
        help="fraction of weights to quantize (0.0-1.0; default 1.0 = all)",
    )
    parser.add_argument("--prefill-seq", type=int, default=8, help="example prefill length for tracing")
    parser.add_argument("--decode-prior", type=int, default=4, help="example prior cache length for the decode graph")
    parser.add_argument(
        "--vocoder-chunk",
        type=int,
        default=325,
        help="fixed vocoder input frames (300-frame chunk plus 25-frame left context)",
    )
    graph_scope = parser.add_mutually_exclusive_group()
    graph_scope.add_argument(
        "--skip-vocoder",
        action="store_true",
        help="skip vocoder decoder export (transformer cores only)",
    )
    graph_scope.add_argument(
        "--vocoder-only",
        action="store_true",
        help="export only the vocoder decoder into an isolated milestone directory",
    )
    return parser.parse_args()


def _versioned_dirname(qwen_version: str, model_repo: str, revision: str, ov_version: str) -> str:
    size = "1.7b" if "1.7B" in model_repo else "0.6b"
    rev = (revision or "main")[:12]
    return f"qwen-tts-{qwen_version}_{size}_{rev}_ov-{ov_version}"


def _example_inputs(dims: dict[str, int], *, torch, vocoder_chunk: int = 0, seq: int = 0, prior: int = 0, predictor: bool = False):
    """Build a positional example-input tuple matching the wrapper forward signature.

    Pass vocoder_chunk>0 for the vocoder decoder (codes-only forward).
    Pass seq/prior/predictor for the transformer cores.
    prior=0 produces the prefill example (no past K/V); prior>0 produces the decode example.
    """
    if vocoder_chunk:
        # codes: [batch=1, num_quantizers, seq_len]  int64
        return (torch.randint(0, dims["codebook_size"], (1, dims["num_quantizers"], vocoder_chunk)),)

    b, h = 1, dims["hidden_size"]
    kv, hd, layers = dims["num_kv_heads"], dims["head_dim"], dims["num_layers"]
    total = prior + seq

    inputs_embeds = torch.randn(b, seq, h)
    attention_mask = torch.ones(b, total, dtype=torch.long)
    position_ids = torch.arange(prior, prior + seq).unsqueeze(0)
    cache_position = torch.arange(prior, prior + seq)

    example = [inputs_embeds, attention_mask, position_ids, cache_position]
    if predictor:
        # generation_steps: exposed explicitly; value semantics confirmed by the parity gate.
        example.append(torch.zeros(1, dtype=torch.long))
    if prior > 0:
        for _ in range(layers):
            example.append(torch.randn(b, kv, prior, hd))  # key
            example.append(torch.randn(b, kv, prior, hd))  # value
    return tuple(example)


def _convert(wrapper, example, ov):
    wrapper.eval()
    return ov.convert_model(wrapper, example_input=example)


def _compress(ov_model, nncf, *, mode: str = "int8_asym", group_size: int = 32, ratio: float = 1.0):
    """Compress weights with NNCF.

    mode: NNCF CompressWeightsMode enum name prefix.
    group_size: 0=per-channel, >0=per-group (32/64).
    ratio: fraction of weights to quantize.
    """
    if mode.lower().startswith("sym"):
        ov_mode = nncf.CompressWeightsMode.INT8_SYM
    else:
        ov_mode = nncf.CompressWeightsMode.INT8_ASYM

    kwargs = {
        "mode": ov_mode,
        "group_size": group_size,
        "ratio": ratio,
    }
    return nncf.compress_weights(ov_model, **kwargs)


def _source_hash() -> str:
    h = hashlib.sha256()
    for name in ("ov_export_wrappers.py", "export_openvino.py", "model_config.py"):
        path = Path(__file__).resolve().parent / name
        h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _resolve_vocoder_decoder(speech_tokenizer):
    """Return the loaded 12 Hz decoder from qwen-tts's inference wrapper."""
    tokenizer_model = getattr(speech_tokenizer, "model", None)
    decoder = getattr(tokenizer_model, "decoder", None)
    if decoder is None:
        raise RuntimeError(
            "qwen-tts tokenizer contract mismatch: expected speech_tokenizer.model.decoder"
        )
    return decoder


def _set_eager_attention(module) -> int:
    """Force eager attention on every distinct Transformers config below a module."""
    configs = {}
    candidates = module.modules() if callable(getattr(module, "modules", None)) else (module,)
    for candidate in candidates:
        config = getattr(candidate, "config", None)
        if config is not None and hasattr(config, "_attn_implementation"):
            configs[id(config)] = config
    for config in configs.values():
        config._attn_implementation = "eager"
    return len(configs)


def _export_provenance(environ=os.environ) -> tuple[str, str]:
    source_commit = environ.get("SOURCE_COMMIT", "")
    image_digest = environ.get("EXPORTER_IMAGE_DIGEST", "")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise SystemExit("SOURCE_COMMIT must be the full 40-character Git commit SHA")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest):
        raise SystemExit("EXPORTER_IMAGE_DIGEST must be a sha256 registry digest")
    return source_commit, image_digest


def run() -> int:
    args = parse_args()
    source_commit, exporter_image_digest = _export_provenance()
    configure_hf_token()

    import openvino as ov
    import torch
    from qwen_tts import Qwen3TTSModel

    import ov_export_wrappers as wrappers

    model_repo = resolve_model_repo()
    revision = os.getenv("MODEL_REVISION") or None
    ov_version = ov.__version__.split("-")[0]

    import qwen_tts
    qwen_version = getattr(qwen_tts, "__version__", "0.1.1")

    print(f"[export] loading {model_repo} (rev={revision}) at float32...", flush=True)
    wrapped = Qwen3TTSModel.from_pretrained(
        model_repo,
        revision=revision,
        device_map="cpu",
        dtype=torch.float32,
        attn_implementation="eager",
    )
    talker = wrapped.model.talker
    vocoder_decoder = _resolve_vocoder_decoder(wrapped.model.speech_tokenizer)
    eager_config_count = _set_eager_attention(vocoder_decoder)
    eager_config_count += _set_eager_attention(talker.model)
    eager_config_count += _set_eager_attention(talker.code_predictor.model)
    print(f"[export] forced eager attention on {eager_config_count} nested configs", flush=True)

    voc_dims = wrappers.vocoder_dims(vocoder_decoder.config)

    vocoder = wrappers.VocoderDecoderWrapper(vocoder_decoder)

    plan: dict[str, tuple] = {}
    if not args.skip_vocoder:
        plan["vocoder_decoder"] = (vocoder, voc_dims, dict(vocoder_chunk=args.vocoder_chunk))
    main_dims = None
    pred_dims = None
    if not args.vocoder_only:
        main_dims = wrappers.core_dims(talker.model.config)
        pred_dims = wrappers.core_dims(talker.code_predictor.model.config)
        main = wrappers.MainCoreWrapper(talker.model, main_dims["num_layers"])
        predictor = wrappers.PredictorCoreWrapper(
            talker.code_predictor.model, pred_dims["num_layers"]
        )
        plan.update(
            {
                "main_prefill": (
                    main,
                    main_dims,
                    dict(seq=args.prefill_seq, prior=0, predictor=False),
                ),
                "main_decode": (
                    main,
                    main_dims,
                    dict(seq=1, prior=args.decode_prior, predictor=False),
                ),
                "predictor_prefill": (
                    predictor,
                    pred_dims,
                    dict(seq=args.prefill_seq, prior=0, predictor=True),
                ),
                "predictor_decode": (
                    predictor,
                    pred_dims,
                    dict(seq=1, prior=args.decode_prior, predictor=True),
                ),
            }
        )

    out_parent = Path(args.output_dir)
    out_parent.mkdir(parents=True, exist_ok=True)
    final_name = _versioned_dirname(qwen_version, model_repo, revision or "main", ov_version)
    if args.vocoder_only:
        final_name = f"{final_name}_vocoder"
    final_dir = out_parent / final_name
    if final_dir.exists():
        raise SystemExit(f"refusing to overwrite existing IR dir: {final_dir}")

    want_int8 = args.compression in ("int8", "both")
    want_fp32 = args.compression in ("fp32", "both")
    nncf = None
    if want_int8:
        import nncf as _nncf
        nncf = _nncf

    tmp_dir = Path(tempfile.mkdtemp(prefix=".export-", dir=out_parent))
    try:
        with torch.no_grad():
            for name, (wrapper, dims, kw) in plan.items():
                print(f"[export] converting {name} ...", flush=True)
                example = _example_inputs(dims, torch=torch, **kw)
                ov_model = _convert(wrapper, example, ov)
                # TODO(parity): mark dynamic seq / prior axes for transformer cores via
                # ov_model.reshape once the eager position_ids/cache_position contract is
                # confirmed on dockermisc1.
                if want_fp32:
                    ov.save_model(ov_model, tmp_dir / f"{name}.xml")
                if want_int8:
                    print(
                        f"[export] compressing {name} to INT8 "
                        f"(mode={args.int8_mode}, group_size={args.int8_group_size}) ...",
                        flush=True,
                    )
                    ov.save_model(
                        _compress(
                            ov_model,
                            nncf,
                            mode=args.int8_mode,
                            group_size=args.int8_group_size,
                            ratio=args.int8_ratio,
                        ),
                        tmp_dir / f"{name}_int8.xml",
                    )

        if args.validate:
            # The FP32 parity gate belongs here: compare PyTorch core vs compiled IR on
            # prefill and several decode steps (max/mean abs+rel error, top-1 token agreement)
            # before publishing. Implemented as a separate step in the parity-test milestone.
            raise SystemExit("[export] --validate is not implemented yet; parity gate is pending (Milestone 2)")

        metadata = {
            "qwen_tts_version": qwen_version,
            "model_repo": model_repo,
            "model_revision": revision or "main",
            "openvino_version": ov.__version__,
            "attention_implementation": "eager",
            "source_commit": source_commit,
            "exporter_image_digest": exporter_image_digest,
            "compression": args.compression,
            "int8_config": (
                {
                    "mode": args.int8_mode,
                    "group_size": args.int8_group_size,
                    "ratio": args.int8_ratio,
                }
                if want_int8
                else None
            ),
            "main_dims": main_dims,
            "predictor_dims": pred_dims,
            "vocoder_dims": voc_dims,
            "vocoder_input_frames": args.vocoder_chunk if not args.skip_vocoder else None,
            "num_code_groups": getattr(talker.model.config, "num_code_groups", None)
            or getattr(wrapped.model.config.talker_config, "num_code_groups", None),
            "source_hash": _source_hash(),
            "graphs": list(plan.keys()),
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        (tmp_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        os.replace(tmp_dir, final_dir)
        final_dir.chmod(0o755)
        print(f"[export] published {final_dir}")
        return 0
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(run())

"""Capture real per-core calibration inputs for data-aware INT8 weight compression.

Milestone 6. Weight-only INT8 (`compress_weights` with no dataset) quantizes each weight to
minimize its own round-trip error, ignoring activation propagation — which is what makes the
talker emit a divergent duration token (the "slight pause"). NNCF's `scale_estimation` fixes this
but needs representative inputs. For the OpenVINO backend, `scale_estimation` IS supported for
INT8_ASYM (unlike the torch backend, which forces dataset=None for INT8).

This module runs the FP32 PyTorch model, monkeypatches the two inner transformer core forwards
(`talker.model`, `talker.code_predictor.model`) to record exactly the positional input list the
exported IR consumes — mirroring ov_talker_runtime._OVCore._run_non_buffered — and buckets each
call into one of the four graphs by phase (prior==0 prefill, prior>0 decode). The records are
pickled per graph for sensitivity and quantization diagnostics. Pinned NNCF 3.2.0 rejects
calibration datasets for INT8 `compress_weights`; see Milestone 6 in the implementation plan.

Record layout (matches the wrapper forward contract / IR input order):
    [inputs_embeds, attention_mask, position_ids, cache_position,
     (generation_steps if predictor), k0, v0, k1, v1, ...]   all numpy.

Usage (inside the exporter image):
    python calibration_capture.py --out-dir /ov_output/<ir>_calib \
        --max-prefill 48 --max-decode 48 --decode-stride 6
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np

# Sets thread env before torch/openvino import (import side effect).
import qwen3_tts.openvino.runtime_config as ov_runtime_config  # noqa: F401
from bench_common import load_model
from qwen3_tts.openvino.talker import _to_numpy

GRAPHS = ("main_prefill", "main_decode", "predictor_prefill", "predictor_decode")

# A spread of texts so main_prefill (one record per utterance) sees varied lengths/content.
DEFAULT_TEXTS = [
    "The quick brown fox jumps over the lazy dog.",
    "Hello there, how are you doing today?",
    "Artificial intelligence is transforming the world around us.",
    "Please remember to bring your umbrella, it might rain later.",
    "She sells seashells by the seashore on a sunny afternoon.",
    "Our quarterly results exceeded every expectation this year.",
    "Can you tell me the way to the nearest train station?",
    "Once upon a time, in a village far away, lived a curious child.",
    "The recipe calls for two cups of flour and a pinch of salt.",
    "Thank you for calling; your feedback is very important to us.",
    "A journey of a thousand miles begins with a single step.",
    "The weather forecast predicts clear skies through the weekend.",
    "He carefully placed the last piece into the wooden puzzle.",
    "Welcome aboard! Please fasten your seatbelt for departure.",
    "Mathematics is the language in which the universe is written.",
    "I would love a cup of coffee and a slice of warm toast.",
    "The orchestra tuned their instruments before the performance.",
    "Remember that every expert was once a complete beginner.",
    "The garden bloomed with tulips, roses, and bright daffodils.",
    "Could you please repeat the question a little more slowly?",
    "Innovation distinguishes between a leader and a follower.",
    "The lighthouse stood firm against the crashing evening waves.",
    "Let us meet at noon to review the final project proposal.",
    "Curiosity is the engine that drives all scientific discovery.",
]


def _resolve_position_ids(position_ids, cache_position, torch):
    """Mirror _OVCore._resolve_position_ids: collapse 3-axis mRoPE, fill from cache_position."""
    if position_ids is None:
        return cache_position.unsqueeze(0)
    if position_ids.ndim == 3:
        return position_ids[0]
    return position_ids


def _build_record(inputs_embeds, attention_mask, position_ids, cache_position,
                  past_key_values, generation_steps, *, predictor, torch):
    """Build the IR positional input list from real core-forward kwargs (numpy)."""
    seq = inputs_embeds.shape[1]
    prior = past_key_values.get_seq_length() if past_key_values is not None else 0

    position_ids = _resolve_position_ids(position_ids, cache_position, torch)
    if attention_mask is None:
        attention_mask = torch.ones(
            inputs_embeds.shape[0], prior + seq, dtype=torch.long, device=inputs_embeds.device
        )

    rec = [
        _to_numpy(inputs_embeds, np.float32),
        _to_numpy(attention_mask, np.int64),
        _to_numpy(position_ids, np.int64),
        _to_numpy(cache_position, np.int64),
    ]
    if predictor:
        if generation_steps is None:
            generation_steps = torch.zeros(1, dtype=torch.long)
        rec.append(_to_numpy(generation_steps, np.int64))

    if prior > 0:
        for k_t, v_t in past_key_values.to_legacy_cache():
            rec.append(_to_numpy(k_t, np.float32))
            rec.append(_to_numpy(v_t, np.float32))
    return rec, prior


def main() -> None:
    import torch

    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--threads", type=int, default=6)
    p.add_argument("--seed", type=int, default=20260628)
    p.add_argument("--language", default="English")
    p.add_argument("--max-prefill", type=int, default=48, help="cap records per *_prefill graph")
    p.add_argument("--max-decode", type=int, default=48, help="cap records per *_decode graph")
    p.add_argument("--decode-stride", type=int, default=6,
                   help="record every Nth decode call so prior lengths spread across the utterance")
    p.add_argument("--max-texts", type=int, default=0, help="0 = use all default texts")
    args = p.parse_args()

    torch.set_num_threads(args.threads)

    loaded = load_model()
    model, prompt = loaded.model, loaded.voice_clone_prompt
    talker = model.model.talker
    main_core = talker.model
    pred_core = talker.code_predictor.model

    buckets: dict[str, list] = {g: [] for g in GRAPHS}
    caps = {
        "main_prefill": args.max_prefill, "predictor_prefill": args.max_prefill,
        "main_decode": args.max_decode, "predictor_decode": args.max_decode,
    }
    decode_seen = {"main_decode": 0, "predictor_decode": 0}

    orig_main = main_core.forward
    orig_pred = pred_core.forward

    def record(predictor, attention_mask, position_ids, past_key_values, cache_position,
               inputs_embeds, generation_steps):
        if inputs_embeds is None:
            return  # M4 contract feeds inputs_embeds; skip anything else defensively.
        rec, prior = _build_record(
            inputs_embeds, attention_mask, position_ids, cache_position,
            past_key_values, generation_steps, predictor=predictor, torch=torch,
        )
        phase = "prefill" if prior == 0 else "decode"
        name = ("predictor" if predictor else "main") + "_" + phase
        if len(buckets[name]) >= caps[name]:
            return
        if phase == "decode":
            n = decode_seen[name]
            decode_seen[name] = n + 1
            if n % args.decode_stride != 0:
                return
        buckets[name].append(rec)

    def main_hook(input_ids=None, attention_mask=None, position_ids=None, past_key_values=None,
                  inputs_embeds=None, use_cache=None, output_attentions=None,
                  output_hidden_states=None, cache_position=None, **kwargs):
        record(False, attention_mask, position_ids, past_key_values, cache_position,
               inputs_embeds, None)
        return orig_main(
            input_ids=input_ids, attention_mask=attention_mask, position_ids=position_ids,
            past_key_values=past_key_values, inputs_embeds=inputs_embeds, use_cache=use_cache,
            output_attentions=output_attentions, output_hidden_states=output_hidden_states,
            cache_position=cache_position, **kwargs,
        )

    def pred_hook(input_ids=None, attention_mask=None, position_ids=None, past_key_values=None,
                  inputs_embeds=None, use_cache=None, output_attentions=None,
                  output_hidden_states=None, cache_position=None, generation_steps=None, **kwargs):
        record(True, attention_mask, position_ids, past_key_values, cache_position,
               inputs_embeds, generation_steps)
        return orig_pred(
            input_ids=input_ids, attention_mask=attention_mask, position_ids=position_ids,
            past_key_values=past_key_values, inputs_embeds=inputs_embeds, use_cache=use_cache,
            output_attentions=output_attentions, output_hidden_states=output_hidden_states,
            cache_position=cache_position, generation_steps=generation_steps, **kwargs,
        )

    texts = DEFAULT_TEXTS if args.max_texts <= 0 else DEFAULT_TEXTS[: args.max_texts]

    main_core.forward = main_hook
    pred_core.forward = pred_hook
    try:
        for i, text in enumerate(texts):
            torch.manual_seed(args.seed + i)
            model.generate_voice_clone(
                text=text, language=args.language, voice_clone_prompt=prompt, do_sample=True
            )
            counts = {g: len(buckets[g]) for g in GRAPHS}
            print(f"[calib] {i+1}/{len(texts)} done; counts={counts}", flush=True)
            if all(len(buckets[g]) >= caps[g] for g in GRAPHS):
                print("[calib] all buckets full; stopping early.", flush=True)
                break
    finally:
        main_core.forward = orig_main
        pred_core.forward = orig_pred

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for g in GRAPHS:
        path = args.out_dir / f"{g}.pkl"
        with open(path, "wb") as f:
            pickle.dump(buckets[g], f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"[calib] wrote {path}  ({len(buckets[g])} records)", flush=True)
    print("[calib] done.", flush=True)


if __name__ == "__main__":
    main()

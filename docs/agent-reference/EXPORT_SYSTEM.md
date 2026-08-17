# Export System — Agent Reference

> This is memory-intensive and brittle. The export pipeline must be treated as a whole:
> changing one part without understanding the others will break runtime.

## How it works

- `scripts/export.py` orchestrates the process using `src/export/export_openvino.py`.
- Loads `Qwen3TTSModel` via `from_pretrained` at FP32.
- Wraps:
  - `talker.model` (main transformer)
  - `talker.code_predictor.model` (predictor transformer)
  - `vocoder decoder` (Qwen3TTSTokenizerV2Decoder)
- Converts to OpenVINO via `openvino.convert_model` with explicit tensor-only wrappers.
- Applies NNCF `compress_weights`:
  - INT8: all weights, per-channel; no extra knobs.
  - INT4: accepts `group_size` and `ratio`.
- Outputs a versioned directory (`qwen-tts-{ver}_{size}_{rev}_ov-{ov_ver}`) with IR files + `metadata.json`.
- Stateful graphs are built separately by `scripts/transform_stateful_ir.py`.

## Fragile parts

- Wrapper inputs must match the IR exactly (`export_openvino._example_inputs`, `ov_export_wrappers`, `talker.py` I/O order).
- Must load with `attn_implementation="eager"` and explicitly set `_attn_implementation` on nested configs; otherwise TorchScript/OpenVINO tracing fails on vmap masks.
- The export expects `inputs_embeds`, not just `input_ids`.
- INT8 vs INT4:
  - INT8: all weights, per-channel; nothing else.
  - INT4: only for 1.7B; 0.6B cannot handle INT4 quality.
  - Do NOT use W8A8 (`nncf.quantize`) — previously caused ~23 dB SNR regression.
- NNCF 3.2.0:
  - Do not pass datasets, AWQ, GPTQ, LoRA correction, or sensitivity selection to `compress_weights`; the API rejects them.

## Memory considerations

- Export uses up to 13 GiB.
- Must not run concurrently with serving on limited boxes.

## Agent rule

- Never change export code without re-running parity tests on `docker-agent`.
- IR paths in `presets.py` must match what export produces.

"""OpenVINO-backed talker runtime (Milestone 4).

Routes the two Qwen3-TTS transformer cores through exported OpenVINO IR while leaving the
entire stock generation path in PyTorch. Instead of reimplementing the nested
main-talker / code-predictor schedule, this adapter swaps only the two *inner* core
`forward` methods — the same modules the export wrappers wrapped — so sampling, EOS,
mRoPE position math, `generation_steps`, `small_to_mtp_projection`, the output heads, and
the `(outputs.hidden_states, codec_ids)` result packing all stay as the original PyTorch
code. That is correct-by-construction for generation-level parity.

Seam (verified qwen-tts==0.1.1, transformers 4.57.3):

  - Patched modules: `talker.model` (Qwen3TTSTalkerModel) and
    `talker.code_predictor.model` (Qwen3TTSTalkerCodePredictorModel).
  - Inputs arriving at this seam are flat tensors matching the IR trace:
    `inputs_embeds` (already projected for the predictor), 2-D `attention_mask`,
    `position_ids`, `cache_position`, and (predictor only) `generation_steps`.
  - `position_ids` arrives 3-axis `[3, batch, seq]` for the main core; all three mRoPE
    axes are identical in the TTS audio path, so axis 0 is fed to the 2-D-position IR.
  - The inner predictor core ignores `generation_steps`; the head/embedding selection that
    uses it lives in the FCG glue, which is untouched.

Each patched forward returns `BaseModelOutputWithPast(last_hidden_state=H,
hidden_states=(H,), past_key_values=<DynamicCache from present K/V>)`. The outer extractor
reads `hid[0][-1]` (final hidden) and `hid[-1]` (codec_ids from the glue), so the length-1
`hidden_states` tuple is sufficient; intermediate per-layer states (unused) are not
reproduced.

IR I/O order mirrors `ov_export_wrappers` / `export_openvino._example_inputs`:

  inputs : inputs_embeds, attention_mask, position_ids, cache_position,
           [generation_steps if predictor], k0, v0, k1, v1, ...   (K/V on decode only)
  outputs: last_hidden_state, k0, v0, k1, v1, ...

This module deliberately does not import `ov_export_wrappers` (that module installs a
global export-only `DynamicLayer.lazy_initialization` patch). Cache objects here are built
from real tensors via `DynamicCache.from_legacy_cache`, so lazy init never runs.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

# IR filenames produced by export_openvino.py.
_GRAPH_FILES = {
    "main_prefill": "main_prefill.xml",
    "main_decode": "main_decode.xml",
    "predictor_prefill": "predictor_prefill.xml",
    "predictor_decode": "predictor_decode.xml",
}
# INT8 variants, when a compressed export is present.
_INT8_GRAPH_FILES = {key: name.replace(".xml", "_int8.xml") for key, name in _GRAPH_FILES.items()}


def _to_numpy(tensor, dtype) -> np.ndarray:
    """Detach a torch tensor to a contiguous numpy array of the IR's expected dtype."""
    array = tensor.detach().cpu().numpy()
    if array.dtype != dtype:
        array = array.astype(dtype)
    return np.ascontiguousarray(array)


class _OVCore:
    """Persistent prefill/decode InferRequests for one transformer core."""

    def __init__(self, compiled_prefill, compiled_decode, num_layers: int, predictor: bool):
        # One persistent request per graph: never create an InferRequest per token
        # (Design Constraint #5). The predictor pair is reused across all 15 codebook
        # steps and reset implicitly each frame because the FCG glue starts a fresh
        # DynamicCache via predictor.generate().
        self._prefill_req = compiled_prefill.create_infer_request()
        self._decode_req = compiled_decode.create_infer_request()
        self.num_layers = num_layers
        self.predictor = predictor
        self._n_outputs = 1 + 2 * num_layers
        self._axis_checked = False

    def _resolve_position_ids(self, position_ids, cache_position):
        import torch

        if position_ids is None:
            return cache_position.unsqueeze(0)
        if position_ids.ndim == 3:
            # mRoPE [3, batch, seq]; all axes identical in the TTS audio path.
            if not self._axis_checked:
                if not torch.equal(position_ids[0], position_ids[1]) or not torch.equal(
                    position_ids[0], position_ids[2]
                ):
                    raise RuntimeError(
                        "mRoPE contract violated: the three position_ids axes differ; the "
                        "2-D-position IR cannot represent this. Re-export or update the adapter."
                    )
                self._axis_checked = True
            return position_ids[0]
        return position_ids

    def run(self, *, inputs_embeds, attention_mask, position_ids, cache_position,
            past_key_values, generation_steps=None):
        import torch
        from transformers.cache_utils import DynamicCache
        from transformers.modeling_outputs import BaseModelOutputWithPast

        seq = inputs_embeds.shape[1]
        prior = past_key_values.get_seq_length() if past_key_values is not None else 0
        is_prefill = prior == 0

        position_ids = self._resolve_position_ids(position_ids, cache_position)
        if attention_mask is None:
            attention_mask = torch.ones(
                inputs_embeds.shape[0], prior + seq, dtype=torch.long, device=inputs_embeds.device
            )

        ir_inputs = [
            _to_numpy(inputs_embeds, np.float32),
            _to_numpy(attention_mask, np.int64),
            _to_numpy(position_ids, np.int64),
            _to_numpy(cache_position, np.int64),
        ]
        if self.predictor:
            if generation_steps is None:
                generation_steps = torch.zeros(1, dtype=torch.long)
            ir_inputs.append(_to_numpy(generation_steps, np.int64))
        if not is_prefill:
            for key, value in past_key_values.to_legacy_cache():
                ir_inputs.append(_to_numpy(key, np.float32))
                ir_inputs.append(_to_numpy(value, np.float32))

        request = self._prefill_req if is_prefill else self._decode_req
        request.infer(ir_inputs)
        outs = [np.array(request.get_output_tensor(i).data, copy=True) for i in range(self._n_outputs)]

        last_hidden = torch.from_numpy(outs[0])
        legacy_present = tuple(
            (torch.from_numpy(outs[1 + 2 * i]), torch.from_numpy(outs[2 + 2 * i]))
            for i in range(self.num_layers)
        )
        present = DynamicCache.from_legacy_cache(legacy_present)

        # hidden_states=(H,) so the outer extractor's hid[0][-1] yields the final hidden.
        return BaseModelOutputWithPast(
            last_hidden_state=last_hidden,
            past_key_values=present,
            hidden_states=(last_hidden,),
            attentions=None,
        )


class OVTalkerRuntime:
    """Compile the four transformer IR graphs and patch the talker's two inner cores.

    Usage:

        runtime = OVTalkerRuntime(model_dir, talker, ov_config)
        runtime.install()
        ...  # model.generate_voice_clone(...) now runs the cores on OpenVINO
        runtime.uninstall()  # or use as a context manager

    `compression` selects which IR set to load: "fp32" (default) loads `*_prefill.xml` /
    `*_decode.xml`; "int8" loads the `*_int8.xml` variants. Defaults to the metadata's
    declared compression when available.
    """

    def __init__(self, model_dir, talker, ov_config=None, *, compression: str | None = None, core=None):
        import openvino as ov

        from ov_runtime_config import get_ov_config

        self.model_dir = Path(model_dir)
        self._talker = talker
        self._ov_config = dict(ov_config) if ov_config is not None else get_ov_config()
        self.core = core or ov.Core()
        self.compression = (compression or self._default_compression()).lower()

        graph_files = _INT8_GRAPH_FILES if self.compression == "int8" else _GRAPH_FILES
        compiled = {}
        for key, filename in graph_files.items():
            path = self.model_dir / filename
            if not path.is_file():
                raise FileNotFoundError(f"missing IR graph for {key}: {path}")
            compiled[key] = self.core.compile_model(str(path), "CPU", self._ov_config)

        main_layers = talker.model.config.num_hidden_layers
        pred_layers = talker.code_predictor.model.config.num_hidden_layers
        self.main = _OVCore(compiled["main_prefill"], compiled["main_decode"], main_layers, predictor=False)
        self.pred = _OVCore(
            compiled["predictor_prefill"], compiled["predictor_decode"], pred_layers, predictor=True
        )

        self._orig_main_forward = None
        self._orig_pred_forward = None

    def _default_compression(self) -> str:
        meta_path = self.model_dir / "metadata.json"
        if meta_path.is_file():
            import json

            compression = json.loads(meta_path.read_text(encoding="utf-8")).get("compression")
            # "both" exports ship FP32 + INT8; default to FP32 unless overridden.
            if compression == "int8":
                return "int8"
        return "fp32"

    def install(self) -> "OVTalkerRuntime":
        if self._orig_main_forward is not None:
            raise RuntimeError("OVTalkerRuntime already installed")

        main_module = self._talker.model
        pred_module = self._talker.code_predictor.model
        main_runner, pred_runner = self.main, self.pred

        self._orig_main_forward = main_module.forward
        self._orig_pred_forward = pred_module.forward

        def main_forward(
            input_ids=None, attention_mask=None, position_ids=None, past_key_values=None,
            inputs_embeds=None, use_cache=None, output_attentions=None,
            output_hidden_states=None, cache_position=None, **kwargs,
        ):
            return main_runner.run(
                inputs_embeds=inputs_embeds, attention_mask=attention_mask,
                position_ids=position_ids, cache_position=cache_position,
                past_key_values=past_key_values,
            )

        def predictor_forward(
            input_ids=None, attention_mask=None, position_ids=None, past_key_values=None,
            inputs_embeds=None, use_cache=None, output_attentions=None,
            output_hidden_states=None, cache_position=None, generation_steps=None, **kwargs,
        ):
            return pred_runner.run(
                inputs_embeds=inputs_embeds, attention_mask=attention_mask,
                position_ids=position_ids, cache_position=cache_position,
                past_key_values=past_key_values, generation_steps=generation_steps,
            )

        main_module.forward = main_forward
        pred_module.forward = predictor_forward
        return self

    def uninstall(self) -> None:
        if self._orig_main_forward is not None:
            self._talker.model.forward = self._orig_main_forward
            self._orig_main_forward = None
        if self._orig_pred_forward is not None:
            self._talker.code_predictor.model.forward = self._orig_pred_forward
            self._orig_pred_forward = None

    def __enter__(self) -> "OVTalkerRuntime":
        return self.install()

    def __exit__(self, *exc) -> None:
        self.uninstall()


def build_runtime(model_dir, talker, *, ov_config=None, compression=None, install=True) -> OVTalkerRuntime:
    """Construct an OVTalkerRuntime and (by default) install it on the talker."""
    runtime = OVTalkerRuntime(model_dir, talker, ov_config=ov_config, compression=compression)
    if install:
        runtime.install()
    return runtime

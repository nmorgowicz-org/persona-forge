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

# Max sequence length for K/V buffers. 4096 is safe for typical TTS generation.
_MAX_SEQ = 4096


def _to_numpy(tensor, dtype) -> np.ndarray:
    """Detach a torch tensor to a contiguous numpy array of the IR's expected dtype.

    Avoids extra ascontiguousarray when the array is already C-contiguous (avoids one
    unnecessary alloc + scan for small inputs like position_ids, cache_position).
    """
    array = tensor.detach().cpu().numpy()
    if array.dtype != dtype:
        array = array.astype(dtype, copy=False)
    if not array.flags["C_CONTIGUOUS"]:
        array = np.ascontiguousarray(array)
    return array


class _OVCore:
    """Persistent prefill/decode InferRequests with zero-alloc K/V buffers."""

    def __init__(self, compiled_prefill, compiled_decode, num_layers: int, predictor: bool):
        # One persistent request per graph (Design Constraint #5).
        self._prefill_req = compiled_prefill.create_infer_request()
        self._decode_req = compiled_decode.create_infer_request()
        self.num_layers = num_layers
        self.predictor = predictor
        self._n_outputs = 1 + 2 * num_layers
        self._axis_checked = False

        # Persistent K/V and output buffers (allocated lazily from IR shapes).
        self._kv_buf = None          # [L][2][1, kv_heads, max_seq, head_dim]
        self._out_decode = None      # [1, 1, hidden] reused every decode step
        self._cache_len = 0
        self._dims_set = False

    def _ensure_buffers(self):
        """Derive head / hidden dims from IR and allocate persistent buffers (once)."""
        if self._dims_set:
            return

        # Output 0: last_hidden_state [batch, seq, hidden]
        # Output 1: k0             [batch, kv_heads, seq, head_dim]
        o0 = self._prefill_req.get_output_tensor(0)
        o1 = self._prefill_req.get_output_tensor(1)
        hidden_size = o0.shape[2]
        kv_heads = o1.shape[1]
        head_dim = o1.shape[3]

        L = self.num_layers

        # K/V: [L][2] where 0=K, 1=V
        self._kv_buf = [
            [
                np.empty((1, kv_heads, _MAX_SEQ, head_dim), dtype=np.float32, order="C")
                for _ in range(2)
            ]
            for _ in range(L)
        ]
        # Decode output buffer reused every step.
        self._out_decode = np.empty((1, 1, hidden_size), dtype=np.float32, order="C")

        self._dims_set = True

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

        # Ensure persistent buffers are allocated (from IR output shapes).
        self._ensure_buffers()

        # --- Prefill reset ------------------------------------------------
        if is_prefill:
            self._cache_len = 0

        # --- Build IR inputs (no per-step K/V allocs) ---------------------
        base_inputs = [
            _to_numpy(inputs_embeds, np.float32),
            _to_numpy(attention_mask, np.int64),
            _to_numpy(position_ids, np.int64),
            _to_numpy(cache_position, np.int64),
        ]
        if self.predictor:
            if generation_steps is None:
                generation_steps = torch.zeros(1, dtype=torch.long)
            base_inputs.append(_to_numpy(generation_steps, np.int64))

        ir_inputs = base_inputs
        if not is_prefill:
            # Feed K/V as views into persistent buffer (zero extra allocs).
            L = self.num_layers
            clen = self._cache_len
            # Pre-extend once; avoid repeated list append overhead.
            capacity = len(base_inputs) + 2 * L
            ir_inputs = base_inputs + [None] * (2 * L)
            idx = len(base_inputs)
            for i in range(L):
                k = self._kv_buf[i][0][:, :, :clen, :]
                v = self._kv_buf[i][1][:, :, :clen, :]
                ir_inputs[idx] = k
                ir_inputs[idx + 1] = v
                idx += 2

        # --- Infer --------------------------------------------------------
        request = self._prefill_req if is_prefill else self._decode_req
        request.infer(ir_inputs)

        # --- Prefill path: write all K/V into buffers ---------------------
        if is_prefill:
            new_len = int(self._cache_len + seq)
            self._cache_len = new_len

            # Hidden output: allocate per prefill (rare; OK).
            hidden_out = request.get_output_tensor(0)
            last_hidden = torch.from_numpy(
                np.array(hidden_out.data, dtype=np.float32, copy=True)
            )

            # K/V: in-place copyto into persistent buffer slices.
            L = self.num_layers
            out = 1  # start after hidden
            for i in range(L):
                kt = request.get_output_tensor(out)
                vt = request.get_output_tensor(out + 1)
                np.copyto(
                    self._kv_buf[i][0][:, :, :new_len, :],
                    kt.data,
                )
                np.copyto(
                    self._kv_buf[i][1][:, :, :new_len, :],
                    vt.data,
                )
                out += 2

        # --- Decode path: write new K/V into buffers in place -------------
        else:
            next_len = self._cache_len + 1
            self._cache_len = next_len

            # Hidden output: copyto into persistent decode buffer.
            hidden_out = request.get_output_tensor(0)
            np.copyto(self._out_decode, hidden_out.data)
            last_hidden = torch.from_numpy(self._out_decode)

            # K/V: in-place copyto.
            L = self.num_layers
            out = 1
            for i in range(L):
                kt = request.get_output_tensor(out)
                vt = request.get_output_tensor(out + 1)
                np.copyto(
                    self._kv_buf[i][0][:, :, :next_len, :],
                    kt.data,
                )
                np.copyto(
                    self._kv_buf[i][1][:, :, :next_len, :],
                    vt.data,
                )
                out += 2

        # --- Build DynamicCache from buffer views -------------------------
        # Minimal torch involvement: from_numpy views over existing buffers.
        L = self.num_layers
        clen = self._cache_len
        legacy_present = []
        for i in range(L):
            k = torch.from_numpy(self._kv_buf[i][0][:, :, :clen, :])
            v = torch.from_numpy(self._kv_buf[i][1][:, :, :clen, :])
            legacy_present.append((k, v))
        present = DynamicCache.from_legacy_cache(tuple(legacy_present))

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

        # Vocoder runtime: loads vocoder IR and patches speech_tokenizer.decode.
        self.vocoder_runtime = None
        vocoder_cfg = (self._ov_config or {}).get("vocoder")
        if vocoder_cfg:
            from ov_vocoder_runtime import OpenVinoVocoderRuntime
            speech_tokenizer = getattr(self._talker, "speech_tokenizer", None)
            if speech_tokenizer is not None:
                self.vocoder_runtime = OpenVinoVocoderRuntime(speech_tokenizer, vocoder_cfg)

        self._orig_main_forward = None
        self._orig_pred_forward = None
        self._orig_st_decode = None

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

        # Patch speech_tokenizer.decode to use vocoder_runtime (if enabled).
        if self.vocoder_runtime and self.vocoder_runtime.enabled:
            st = getattr(self._talker, "speech_tokenizer", None)
            if st is not None:
                self._orig_st_decode = st.decode

                def _ov_decode(inputs, *args, **kwargs):
                    try:
                        return self.vocoder_runtime.decode(inputs, *args, **kwargs)
                    except Exception:
                        return self._orig_st_decode(inputs, *args, **kwargs)

                st.decode = _ov_decode

        return self

    def uninstall(self) -> None:
        if self._orig_main_forward is not None:
            self._talker.model.forward = self._orig_main_forward
            self._orig_main_forward = None
        if self._orig_pred_forward is not None:
            self._talker.code_predictor.model.forward = self._orig_pred_forward
            self._orig_pred_forward = None
        if self._orig_st_decode is not None:
            st = getattr(self._talker, "speech_tokenizer", None)
            if st is not None:
                st.decode = self._orig_st_decode
            self._orig_st_decode = None

    @property
    def talker(self):
        """Expose the talker for external callers (e.g., parity tests)."""
        return self._talker

    def generate_waveform_from_codes(self, codes):
        """Generate waveform from audio codes using vocoder_runtime or PyTorch fallback.

        Args:
            codes: tensor or numpy [frames, num_quantizers] of audio codes.

        Returns:
            1-D float32 waveform (same convention as speech_tokenizer.decode).
        """
        if self.vocoder_runtime and self.vocoder_runtime.enabled:
            try:
                return self.vocoder_runtime.decode(codes)
            except Exception:
                # Fallback to PyTorch vocoder on any error.
                pass
        # PyTorch fallback.
        st = getattr(self._talker, "speech_tokenizer", None)
        if st is not None:
            return st.decode(codes)
        raise RuntimeError("No vocoder available (no speech_tokenizer).")

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

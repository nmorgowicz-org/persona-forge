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

import os
from pathlib import Path

import numpy as np

from qwen3_tts.presets import seconds_for_capacity

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

    - If already the correct dtype and C-contiguous, returns the array directly.
    - Otherwise applies minimal conversions (astype, ascontiguousarray) as needed.

    bfloat16 has no numpy equivalent, so ``.numpy()`` raises ``Got unsupported
    ScalarType BFloat16``. When the serving model is loaded in bf16
    (``OPENVINO_TORCH_DTYPE=bfloat16``) the PyTorch glue emits bf16 tensors at the
    OV seam; upcast them to fp32 on the torch side first (the IR's float inputs are
    fp32 regardless). ``.float()`` avoids importing torch in this module.
    """
    if isinstance(tensor, np.ndarray):
        array = tensor
    else:
        if "bfloat16" in str(getattr(tensor, "dtype", "")):
            tensor = tensor.float()
        array = tensor.detach().cpu().numpy()
    if array.dtype == dtype and array.flags["C_CONTIGUOUS"]:
        return array
    if array.dtype != dtype:
        array = array.astype(dtype, copy=False)
    if not array.flags["C_CONTIGUOUS"]:
        array = np.ascontiguousarray(array)
    return array


def _cache_position_or_default(cache_position, *, prior: int, seq: int, device):
    """Provide positions when Transformers 5 omits them for this custom model."""
    if cache_position is not None:
        return cache_position

    import torch

    return torch.arange(prior, prior + seq, dtype=torch.long, device=device)


def _dynamic_cache_from_kv(pairs):
    """Build a DynamicCache with the Transformers 4 or 5 cache API."""
    from transformers.cache_utils import DynamicCache

    factory = getattr(DynamicCache, "from_legacy_cache", None)
    if factory is not None:
        return factory(tuple(pairs))
    return DynamicCache(pairs)


def _dynamic_cache_kv(cache):
    """Return K/V pairs from a Transformers 4 or 5 DynamicCache."""
    converter = getattr(cache, "to_legacy_cache", None)
    if converter is not None:
        return converter()
    return tuple((layer[0], layer[1]) for layer in cache)


def _stateful_generation_steps(generation_steps, expects_generation_steps: bool):
    """Mirror the explicit predictor's optional generation_steps contract."""
    if not expects_generation_steps:
        return None
    if generation_steps is None:
        return np.zeros(1, dtype=np.int64)
    return generation_steps


class _OVCore:
    """Persistent prefill/decode InferRequests with optional zero-alloc K/V buffers.

    Buffer-backed mode (OPENVINO_BUFFER_KV=1):
      - Allocates K/V and output buffers once from IR shapes.
      - Zero per-step numpy allocations for K/V inputs/outputs.
      - Uses np.copyto and torch.from_numpy views for cache reconstruction.

    Non-buffered fallback:
      - Uses DynamicCache round-trip (to_legacy_cache → _to_numpy → from_legacy_cache).
      - Preserved for parity and as a safe default.
    """

    def __init__(self, compiled_prefill, compiled_decode, num_layers: int, predictor: bool):
        import os

        # One persistent request per graph (Design Constraint #5).
        self._prefill_req = compiled_prefill.create_infer_request()
        self._decode_req = compiled_decode.create_infer_request()
        self.num_layers = num_layers
        self.predictor = predictor
        self._n_outputs = 1 + 2 * num_layers
        self._axis_checked = False

        # Buffer-backed K/V cache mode controlled by environment.
        self._buffer_kv = os.getenv("OPENVINO_BUFFER_KV", "0") == "1"

        # Persistent K/V and output buffers (only when buffer mode is enabled).
        self._kv_buf = None          # [L][2][1, kv_heads, max_seq, head_dim]
        self._out_decode = None      # [1, 1, hidden] reused every decode step
        self._cache_len = 0
        self._dims_set = False

    def _ensure_buffers(self):
        """Derive head / hidden dims from IR and allocate persistent buffers (once)."""
        if not self._buffer_kv or self._dims_set:
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

    @staticmethod
    def _resolve_position_ids(position_ids, cache_position, axis_checked):
        import torch

        if position_ids is None:
            return cache_position.unsqueeze(0), axis_checked
        if position_ids.ndim == 3:
            # mRoPE [3, batch, seq]; all axes identical in the TTS audio path.
            if not axis_checked:
                if not torch.equal(position_ids[0], position_ids[1]) or not torch.equal(
                    position_ids[0], position_ids[2]
                ):
                    raise RuntimeError(
                        "mRoPE contract violated: the three position_ids axes differ; the "
                        "2-D-position IR cannot represent this. Re-export or update the adapter."
                    )
                axis_checked = True
            return position_ids[0], axis_checked
        return position_ids, axis_checked

    # ---------------------------------------------------------------------
    # Buffer-backed run (OPENVINO_BUFFER_KV=1)
    # ---------------------------------------------------------------------
    def _run_buffered(self, *, inputs_embeds, attention_mask, position_ids,
                      cache_position, past_key_values, generation_steps=None):
        import torch
        from transformers.modeling_outputs import BaseModelOutputWithPast

        seq = inputs_embeds.shape[1]
        prior = past_key_values.get_seq_length() if past_key_values is not None else 0
        is_prefill = prior == 0
        cache_position = _cache_position_or_default(
            cache_position, prior=prior, seq=seq, device=inputs_embeds.device
        )

        if is_prefill:
            position_ids, self._axis_checked = self._resolve_position_ids(
                position_ids, cache_position, self._axis_checked
            )
        else:
            position_ids = cache_position.unsqueeze(0)
        if attention_mask is None:
            attention_mask = torch.ones(
                inputs_embeds.shape[0], prior + seq, dtype=torch.long, device=inputs_embeds.device
            )

        self._ensure_buffers()

        if is_prefill:
            self._cache_len = 0

        # Build base inputs.
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

        # Build K/V inputs from buffer views (zero extra allocs).
        ir_inputs = base_inputs
        if not is_prefill:
            L = self.num_layers
            clen = self._cache_len
            ir_inputs = base_inputs + [None] * (2 * L)
            idx = len(base_inputs)
            for i in range(L):
                k = self._kv_buf[i][0][:, :, :clen, :]
                v = self._kv_buf[i][1][:, :, :clen, :]
                ir_inputs[idx] = k
                ir_inputs[idx + 1] = v
                idx += 2

        request = self._prefill_req if is_prefill else self._decode_req
        request.infer(ir_inputs)

        if is_prefill:
            new_len = int(self._cache_len + seq)
            self._cache_len = new_len

            hidden_out = request.get_output_tensor(0)
            last_hidden = torch.from_numpy(
                np.array(hidden_out.data, dtype=np.float32, copy=True)
            )

            # K/V: copyto into persistent buffers.
            L = self.num_layers
            out = 1
            for i in range(L):
                kt = request.get_output_tensor(out)
                vt = request.get_output_tensor(out + 1)
                np.copyto(self._kv_buf[i][0][:, :, :new_len, :], kt.data)
                np.copyto(self._kv_buf[i][1][:, :, :new_len, :], vt.data)
                out += 2

        else:
            next_len = self._cache_len + 1
            self._cache_len = next_len

            hidden_out = request.get_output_tensor(0)
            np.copyto(self._out_decode, hidden_out.data)
            last_hidden = torch.from_numpy(self._out_decode)

            # K/V: copyto into persistent buffers.
            L = self.num_layers
            out = 1
            for i in range(L):
                kt = request.get_output_tensor(out)
                vt = request.get_output_tensor(out + 1)
                np.copyto(self._kv_buf[i][0][:, :, :next_len, :], kt.data)
                np.copyto(self._kv_buf[i][1][:, :, :next_len, :], vt.data)
                out += 2

        # Build DynamicCache from buffer views.
        L = self.num_layers
        clen = self._cache_len
        legacy_present = []
        for i in range(L):
            k = torch.from_numpy(self._kv_buf[i][0][:, :, :clen, :])
            v = torch.from_numpy(self._kv_buf[i][1][:, :, :clen, :])
            legacy_present.append((k, v))
        present = _dynamic_cache_from_kv(legacy_present)

        return BaseModelOutputWithPast(
            last_hidden_state=last_hidden,
            past_key_values=present,
            hidden_states=(last_hidden,),
            attentions=None,
        )

    # ---------------------------------------------------------------------
    # Non-buffered run (OPENVINO_BUFFER_KV not set)
    # ---------------------------------------------------------------------
    def _run_non_buffered(self, *, inputs_embeds, attention_mask, position_ids,
                          cache_position, past_key_values, generation_steps=None):
        import torch
        from transformers.modeling_outputs import BaseModelOutputWithPast

        seq = inputs_embeds.shape[1]
        prior = past_key_values.get_seq_length() if past_key_values is not None else 0
        is_prefill = prior == 0
        cache_position = _cache_position_or_default(
            cache_position, prior=prior, seq=seq, device=inputs_embeds.device
        )

        if is_prefill:
            position_ids, self._axis_checked = self._resolve_position_ids(
                position_ids, cache_position, self._axis_checked
            )
        else:
            position_ids = cache_position.unsqueeze(0)
        if attention_mask is None:
            attention_mask = torch.ones(
                inputs_embeds.shape[0], prior + seq, dtype=torch.long, device=inputs_embeds.device
            )

        # Build base inputs.
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

        # Build K/V inputs from DynamicCache via to_legacy_cache.
        ir_inputs = base_inputs
        if not is_prefill:
            legacy = _dynamic_cache_kv(past_key_values)
            L = self.num_layers
            for i in range(L):
                k_t, v_t = legacy[i]
                ir_inputs.append(_to_numpy(k_t, np.float32))
                ir_inputs.append(_to_numpy(v_t, np.float32))

        # Infer.
        request = self._prefill_req if is_prefill else self._decode_req
        request.infer(ir_inputs)

        # Read outputs: [0]=last_hidden, [1..]=K/V per layer.
        hidden_out = request.get_output_tensor(0)
        last_hidden = torch.from_numpy(
            np.array(hidden_out.data, dtype=np.float32, copy=True)
        )

        L = self.num_layers
        out = 1
        legacy_present = []
        for i in range(L):
            kt = request.get_output_tensor(out)
            vt = request.get_output_tensor(out + 1)
            k = torch.from_numpy(np.array(kt.data, dtype=np.float32, copy=True))
            v = torch.from_numpy(np.array(vt.data, dtype=np.float32, copy=True))
            legacy_present.append((k, v))
            out += 2

        present = _dynamic_cache_from_kv(legacy_present)

        return BaseModelOutputWithPast(
            last_hidden_state=last_hidden,
            past_key_values=present,
            hidden_states=(last_hidden,),
            attentions=None,
        )

    def run(self, *, inputs_embeds, attention_mask, position_ids, cache_position,
            past_key_values, generation_steps=None):
        if self._buffer_kv:
            return self._run_buffered(
                inputs_embeds=inputs_embeds,
                attention_mask=attention_mask,
                position_ids=position_ids,
                cache_position=cache_position,
                past_key_values=past_key_values,
                generation_steps=generation_steps,
            )
        return self._run_non_buffered(
            inputs_embeds=inputs_embeds,
            attention_mask=attention_mask,
            position_ids=position_ids,
            cache_position=cache_position,
            past_key_values=past_key_values,
            generation_steps=generation_steps,
        )


def _length_only_cache(seq_length: int, num_layers: int):
    """Return a Transformers Cache that carries length but no K/V tensors."""
    from transformers.cache_utils import Cache

    class _LengthOnlyCache(Cache):
        def __init__(self) -> None:
            super().__init__(layers=[])
            self._seq_length = seq_length

        def get_seq_length(self, layer_idx: int = 0) -> int:
            return self._seq_length

        def get_mask_sizes(self, cache_position, layer_idx: int) -> tuple[int, int]:
            return self._seq_length + cache_position.shape[0], 0

        def get_max_cache_shape(self, layer_idx: int = 0) -> int:
            return -1

        def reorder_cache(self, beam_idx) -> None:
            if len(beam_idx) != 1 or int(beam_idx[0]) != 0:
                raise RuntimeError("stateful OpenVINO cache supports batch size 1 only")

        def __len__(self) -> int:
            return num_layers

    return _LengthOnlyCache()


class _OVStatefulCore:
    """One InferRequest whose static-capacity K/V buffers live inside OpenVINO."""

    def __init__(self, compiled_model, num_layers: int):
        self._request = compiled_model.create_infer_request()
        self.num_layers = num_layers
        input_count = len(compiled_model.inputs)
        if input_count not in (4, 5):
            raise RuntimeError(
                "stateful core expected four main inputs or five predictor inputs, "
                f"found {input_count}"
            )
        self._expects_generation_steps = input_count == 5
        states = self._request.query_state()
        if len(states) != 2 * num_layers:
            raise RuntimeError(
                f"stateful core expected {2 * num_layers} K/V states, found {len(states)}"
            )
        capacities = {int(state.state.shape[2]) for state in states}
        if len(capacities) != 1:
            raise RuntimeError(f"stateful core K/V capacities differ: {sorted(capacities)}")
        self.capacity = capacities.pop()
        self._cache_len = 0
        self._axis_checked = False
        self._decode_step = 0
        self._decode_t0 = 0.0

    def run(self, *, inputs_embeds, attention_mask, position_ids, cache_position,
            past_key_values, generation_steps=None):
        import torch
        from transformers.modeling_outputs import BaseModelOutputWithPast

        # The predictor IR retains generation_steps as its fifth base input. The
        # main IR has only the first four inputs.
        seq = int(inputs_embeds.shape[1])
        prior = past_key_values.get_seq_length() if past_key_values is not None else 0
        is_prefill = prior == 0
        cache_position = _cache_position_or_default(
            cache_position, prior=prior, seq=seq, device=inputs_embeds.device
        )
        if is_prefill:
            self._request.reset_state()
            self._cache_len = 0
            self._decode_step = 0
            self._decode_t0 = 0.0
            print(
                f"[ov_stateful] prefill  seq={seq}  capacity={self.capacity}"
                f"  budget={self.capacity - seq}",
                flush=True,
            )
        elif prior != self._cache_len:
            raise RuntimeError(
                f"stateful cache length mismatch: outer cache={prior}, internal={self._cache_len}"
            )
        if prior + seq > self.capacity:
            raise RuntimeError(
                f"stateful cache capacity exceeded: need {prior + seq} frames "
                f"(~{seconds_for_capacity(prior + seq):.1f}s), max {self.capacity} frames "
                f"(~{seconds_for_capacity(self.capacity):.1f}s). This deployment was exported "
                f"with TTS_MAX_SPEECH_SECONDS={seconds_for_capacity(self.capacity):.0f} (or the "
                "64s default) — re-export with a larger value if you need longer requests."
            )

        if is_prefill:
            position_ids, self._axis_checked = _OVCore._resolve_position_ids(
                position_ids, cache_position, self._axis_checked
            )
        else:
            # Decode: authoritative position from cache_position, not caller.
            # Under transformers 5.x, the outer path can emit position_ids = arange(N)
            # from the full input_ids shape instead of [current_pos], breaking mRoPE
            # and making EOS probability ≈ 0 every step.
            position_ids = cache_position.unsqueeze(0)
        if attention_mask is None:
            attention_mask = torch.ones(
                inputs_embeds.shape[0], prior + seq, dtype=torch.long,
                device=inputs_embeds.device,
            )
        infer_inputs = [
            _to_numpy(inputs_embeds, np.float32),
            _to_numpy(attention_mask, np.int64),
            _to_numpy(position_ids, np.int64),
            _to_numpy(cache_position, np.int64),
        ]
        generation_steps = _stateful_generation_steps(
            generation_steps, self._expects_generation_steps
        )
        if generation_steps is not None:
            # Match _OVCore: the live nested GenerationMixin path does not
            # always forward this optional argument to the predictor core.
            infer_inputs.append(_to_numpy(generation_steps, np.int64))
        import time as _time

        if not is_prefill and self._decode_step < 5:
            mask_shape = tuple(attention_mask.shape) if attention_mask is not None else None
            pid_val = position_ids[0].tolist() if position_ids is not None else None
            cp_val = cache_position.tolist() if cache_position is not None else None
            print(
                f"[ov_stateful] decode_step={self._decode_step}"
                f"  prior={prior}  mask={mask_shape}"
                f"  pos={pid_val}  cache_pos={cp_val}",
                flush=True,
            )
        self._request.infer(infer_inputs)
        hidden = torch.from_numpy(
            np.array(self._request.get_output_tensor(0).data, dtype=np.float32, copy=True)
        )
        self._cache_len = prior + seq
        if not is_prefill:
            self._decode_step += 1
            if self._decode_step == 1:
                self._decode_t0 = _time.monotonic()
            elif self._decode_step % 50 == 0:
                elapsed = _time.monotonic() - self._decode_t0
                rate = (self._decode_step - 1) / elapsed if elapsed > 0 else 0
                print(
                    f"[ov_talker] decode step {self._decode_step}"
                    f"  cache={self._cache_len}/{self.capacity}"
                    f"  {rate:.1f} tok/s",
                    flush=True,
                )
        cache = _length_only_cache(self._cache_len, self.num_layers)
        return BaseModelOutputWithPast(
            last_hidden_state=hidden,
            past_key_values=cache,
            hidden_states=(hidden,),
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

    def __init__(self, model_dir, talker, ov_config=None, *, compression: str | None = None,
                 core=None, speech_tokenizer=None):
        import openvino as ov

        from qwen3_tts.openvino.runtime_config import get_ov_config

        self.model_dir = Path(model_dir)
        self._talker = talker
        self._ov_config = dict(ov_config) if ov_config is not None else get_ov_config()
        self.core = core or ov.Core()
        self.compression = (compression or self._default_compression()).lower()

        # "vocoder" is internal config; OpenVINO CPU plugin doesn't understand it.
        core_config = {k: v for k, v in self._ov_config.items() if k != "vocoder"}

        # Per-core precision override (diagnostic): localize INT8 quality loss by
        # running one core INT8 and the other FP32. Defaults to the global compression
        # so normal runs are unaffected.
        main_comp = os.getenv("OV_MAIN_COMPRESSION", self.compression).lower()
        pred_comp = os.getenv("OV_PREDICTOR_COMPRESSION", self.compression).lower()
        self.main_comp = main_comp
        self.pred_comp = pred_comp

        def _files_for(comp: str) -> dict:
            # INT4 and INT8 artifacts share the compressed graph filenames; the
            # metadata records the actual per-core weight format.
            return _INT8_GRAPH_FILES if comp in {"int4", "int8"} else _GRAPH_FILES

        main_stateful_raw = os.getenv("OPENVINO_MAIN_STATEFUL_MODEL", "").strip()
        main_stateful_path = None
        if main_stateful_raw:
            main_stateful_path = Path(main_stateful_raw)
            if not main_stateful_path.is_absolute():
                main_stateful_path = self.model_dir / main_stateful_path

        predictor_stateful_raw = os.getenv("OPENVINO_PREDICTOR_STATEFUL_MODEL", "").strip()
        predictor_stateful_path = None
        if predictor_stateful_raw:
            predictor_stateful_path = Path(predictor_stateful_raw)
            if not predictor_stateful_path.is_absolute():
                predictor_stateful_path = self.model_dir / predictor_stateful_path

        # Milestone 7 / M9: OPENVINO_RELEASE_TORCH controls when PyTorch core weights are freed.
        # When enabled, we use a phased compilation:
        #   1) Compile predictor (small, safe while PyTorch loaded).
        #   2) Release PyTorch .layers early (they are dead once OV replaces them).
        #   3) Compile main/stateful (heaviest phase; now without PyTorch weights).
        # This avoids the startup overlap peak (~12 GiB) where both PyTorch and OV
        # compiled-model working buffers reside simultaneously.
        self._release_torch = os.getenv("OPENVINO_RELEASE_TORCH", "0").strip() == "1"
        self._torch_cores_released = False

        # Codec (speech_tokenizer) weight release after startup. The codec ENCODER is only
        # used to build a voice_clone_prompt (at load time for the startup default voice,
        # and on demand for any other voice_id via get_voice_clone_prompt/model.py), and
        # the codec DECODER is fully replaced by the OpenVINO vocoder IR (speech_tokenizer.decode
        # is patched below). release_codec() frees the ~0.3 GiB PyTorch codec once it is no
        # longer needed. One-way and fail-closed: once freed, the PyTorch speech_tokenizer.decode
        # fallback can no longer run (an OV vocoder failure errors the request instead of
        # silently switching to PyTorch), and no further voice_clone_prompt can be built for a
        # new voice_id (Persona Forge / Voice Library / Speak-tab voice switching needs this).
        # Defaults to keeping the encoder resident so per-request voice cloning always works;
        # set OPENVINO_KEEP_CODEC_ENCODER=0 to free it and shave ~0.3 GiB when only ever the one
        # startup reference voice is served (e.g. a single-voice Hermes-style deployment).
        self._release_codec = os.getenv("OPENVINO_KEEP_CODEC_ENCODER", "1").strip() != "1"
        self._codec_released = False

        graph_files = {}
        if predictor_stateful_path is None:
            graph_files["predictor_prefill"] = _files_for(pred_comp)["predictor_prefill"]
            graph_files["predictor_decode"] = _files_for(pred_comp)["predictor_decode"]
        if main_stateful_path is None:
            graph_files["main_prefill"] = _files_for(main_comp)["main_prefill"]
            graph_files["main_decode"] = _files_for(main_comp)["main_decode"]
        if main_comp != pred_comp:
            print(
                f"[ov_talker] per-core precision: main={main_comp} predictor={pred_comp}",
                flush=True,
            )

        if self._release_torch:
            # ---- Phased compilation: predictor -> release -> main ----
            self._log_rss("before_all_compile")

            # Phase 1: compile predictor (small; safe with PyTorch loaded)
            compiled = {}
            if predictor_stateful_path is not None:
                if not predictor_stateful_path.is_file():
                    raise FileNotFoundError(f"missing stateful predictor IR: {predictor_stateful_path}")
                compiled["predictor_stateful"] = self.core.compile_model(
                    str(predictor_stateful_path), "CPU", core_config
                )
            else:
                for key, filename in graph_files.items():
                    if key not in ("predictor_prefill", "predictor_decode"):
                        continue
                    path = self.model_dir / filename
                    if not path.is_file():
                        raise FileNotFoundError(f"missing IR graph for {key}: {path}")
                    compiled[key] = self.core.compile_model(str(path), "CPU", core_config)
            self._log_rss("after_predictor_compile")

            # Phase 2: release PyTorch weights before main compile
            self._release_torch_core_weights()
            self._log_rss("after_release_before_main_compile")

            # Phase 3: compile main/stateful (heaviest phase; now without PyTorch weights).
            # After _release_torch_core_weights above, the PyTorch core forward cannot run;
            # if compilation fails here, startup must abort (no in-process fallback).
            try:
                for key, filename in graph_files.items():
                    if key in ("predictor_prefill", "predictor_decode"):
                        continue
                    path = self.model_dir / filename
                    if not path.is_file():
                        raise FileNotFoundError(f"missing IR graph for {key}: {path}")
                    compiled[key] = self.core.compile_model(str(path), "CPU", core_config)

                main_layers = talker.model.config.num_hidden_layers
                if main_stateful_path is not None:
                    if not main_stateful_path.is_file():
                        raise FileNotFoundError(f"missing stateful main IR: {main_stateful_path}")
                    main_stateful_compiled = self.core.compile_model(
                        str(main_stateful_path), "CPU", core_config
                    )
                    self.main = _OVStatefulCore(main_stateful_compiled, main_layers)
                    self.main_comp = f"stateful-{main_comp}"
                else:
                    self.main = _OVCore(
                        compiled["main_prefill"], compiled["main_decode"],
                        main_layers, predictor=False,
                    )
                self._log_rss("after_main_compile")
            except Exception:
                print(
                    "[ov_talker] OPENVINO_RELEASE_TORCH=1: main-graph compile failed "
                    "after PyTorch weights were released. No in-process PyTorch fallback "
                    "is possible; container must restart with TTS_BACKEND=pytorch.",
                    flush=True,
                )
                raise

        else:
            # ---- Single-phase compilation (original behavior) ----
            compiled = {}
            for key, filename in graph_files.items():
                path = self.model_dir / filename
                if not path.is_file():
                    raise FileNotFoundError(f"missing IR graph for {key}: {path}")
                compiled[key] = self.core.compile_model(str(path), "CPU", core_config)

            main_layers = talker.model.config.num_hidden_layers
            if main_stateful_path is not None:
                if not main_stateful_path.is_file():
                    raise FileNotFoundError(f"missing stateful main IR: {main_stateful_path}")
                main_stateful_compiled = self.core.compile_model(
                    str(main_stateful_path), "CPU", core_config
                )
                self.main = _OVStatefulCore(main_stateful_compiled, main_layers)
                self.main_comp = f"stateful-{main_comp}"
            else:
                self.main = _OVCore(
                    compiled["main_prefill"], compiled["main_decode"],
                    main_layers, predictor=False,
                )

        pred_layers = talker.code_predictor.model.config.num_hidden_layers
        if predictor_stateful_path is not None:
            self.pred = _OVStatefulCore(compiled["predictor_stateful"], pred_layers)
            self.pred_comp = f"stateful-{self.pred_comp}"
        else:
            self.pred = _OVCore(
                compiled["predictor_prefill"], compiled["predictor_decode"], pred_layers, predictor=True
            )

        # Resolve speech_tokenizer. In qwen-tts it is a SIBLING of `talker` on the parent
        # model (model.model.speech_tokenizer), not an attribute of `talker`, so the old
        # getattr(talker, ...) always returned None and silently disabled the OV vocoder.
        # Prefer the explicitly passed handle; fall back to the legacy lookup.
        self._speech_tokenizer = speech_tokenizer or getattr(self._talker, "speech_tokenizer", None)

        # Vocoder runtime: loads vocoder IR and patches speech_tokenizer.decode.
        self.vocoder_runtime = None
        vocoder_cfg = (self._ov_config or {}).get("vocoder")
        if vocoder_cfg and self._speech_tokenizer is not None:
            from qwen3_tts.openvino.vocoder import OpenVinoVocoderRuntime
            self.vocoder_runtime = OpenVinoVocoderRuntime(self._speech_tokenizer, vocoder_cfg)
        elif vocoder_cfg and vocoder_cfg.get("enabled"):
            print(
                "[ov_talker] vocoder enabled but speech_tokenizer not found; "
                "using PyTorch vocoder.",
                flush=True,
            )

        self._orig_main_forward = None
        self._orig_pred_forward = None
        self._orig_st_decode = None
        self._logits_diag_step = 0

        # Diagnostic: wrap codec_head.forward to log top-5 logits at selected decode steps.
        # This tells us whether EOS is ever assigned high probability.
        # Gated by TTS_LOGITS_DIAG env var so it can be turned off in production.
        if os.getenv("TTS_LOGITS_DIAG", "0").strip() == "1":
            _orig_codec_forward = talker.codec_head.forward
            _diag_at = {1, 2, 3, 5, 10, 20, 50, 100, 200, 400}
            eos_id = 2150

            def _diag_codec_forward(hidden):
                self._logits_diag_step += 1
                logits = _orig_codec_forward(hidden)
                if self._logits_diag_step in _diag_at:
                    import torch
                    step = self._logits_diag_step
                    last_step_logits = logits[0, -1]
                    probs = torch.softmax(last_step_logits.float(), dim=-1)
                    eos_p = float(probs[eos_id])
                    top5 = probs.topk(5)
                    tok_str = ", ".join(
                        f"{int(i)}({float(p):.4f})"
                        for i, p in zip(top5.indices, top5.values)
                    )
                    argmax = int(probs.argmax())
                    print(
                        f"[logits_diag] step={step:4d}  eos({eos_id})={eos_p:.6f}  "
                        f"top5=[{tok_str}]  argmax={argmax}",
                        flush=True,
                    )
                return logits

            talker.codec_head.forward = _diag_codec_forward
            print(f"[ov_talker] codec_head diag enabled  eos={eos_id}", flush=True)
        else:
            self._logits_diag_step = 0

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

        def _match_dtype(out, inputs_embeds):
            # OV rebuilds hidden states as fp32. When the serving model is loaded in
            # bf16 (OPENVINO_TORCH_DTYPE=bfloat16) the downstream PyTorch heads hold
            # bf16 weights, so the fp32 hidden must be cast back to the model dtype to
            # avoid a matmul dtype mismatch. No-op under fp32 serving.
            if (
                inputs_embeds is not None
                and out.last_hidden_state is not None
                and out.last_hidden_state.dtype != inputs_embeds.dtype
            ):
                out.last_hidden_state = out.last_hidden_state.to(inputs_embeds.dtype)
            return out

        _main_diag = {"n": 0, "prev_in": None, "prev_out": None}

        def main_forward(
            input_ids=None, attention_mask=None, position_ids=None, past_key_values=None,
            inputs_embeds=None, use_cache=None, output_attentions=None,
            output_hidden_states=None, cache_position=None, **kwargs,
        ):
            out = _match_dtype(main_runner.run(
                inputs_embeds=inputs_embeds, attention_mask=attention_mask,
                position_ids=position_ids, cache_position=cache_position,
                past_key_values=past_key_values,
            ), inputs_embeds)
            try:
                import os as _os2, numpy as _np2
                if _os2.path.exists("/tmp/tts_dump") and inputs_embeds is not None and inputs_embeds.shape[1] > 1:
                    _np2.save("/tmp/dump_ie_prefill.npy", inputs_embeds.detach().float().cpu().numpy())
                    _np2.save("/tmp/dump_out_prefill.npy", out.last_hidden_state.detach().float().cpu().numpy())
                    _np2.save("/tmp/dump_pos_prefill.npy",
                              position_ids.detach().cpu().numpy() if position_ids is not None else _np2.array([]))
                    _np2.save("/tmp/dump_cp_prefill.npy",
                              cache_position.detach().cpu().numpy() if cache_position is not None else _np2.array([]))
                    _np2.save("/tmp/dump_am_prefill.npy",
                              attention_mask.detach().cpu().numpy() if attention_mask is not None else _np2.array([]))
                    print(f"[dump] prefill ie={tuple(inputs_embeds.shape)} out={tuple(out.last_hidden_state.shape)} saved", flush=True)
            except Exception as _e2:
                print(f"[dump] err {_e2!r}", flush=True)
            try:
                if (
                    os.path.exists("/tmp/tts_step_diag")
                    and inputs_embeds is not None
                    and inputs_embeds.shape[1] == 1  # decode only
                    and _main_diag["n"] < 12
                ):
                    import torch as _t
                    iv = inputs_embeds.float().reshape(-1)
                    ov = out.last_hidden_state.float().reshape(-1)
                    din = (
                        (iv - _main_diag["prev_in"]).norm().item()
                        if _main_diag["prev_in"] is not None else float("nan")
                    )
                    dout = (
                        (ov - _main_diag["prev_out"]).norm().item()
                        if _main_diag["prev_out"] is not None else float("nan")
                    )
                    print(
                        f"[main_diag] dstep={_main_diag['n']} "
                        f"in_norm={iv.norm().item():.3f} out_norm={ov.norm().item():.3f} "
                        f"d_in_vs_prev={din:.4f} d_out_vs_prev={dout:.4f}",
                        flush=True,
                    )
                    _main_diag["prev_in"] = iv.clone()
                    _main_diag["prev_out"] = ov.clone()
                    _main_diag["n"] += 1
            except Exception as _e:
                print(f"[main_diag] error: {_e!r}", flush=True)
            return out

        _pred_diag = {"n": 0}

        def predictor_forward(
            input_ids=None, attention_mask=None, position_ids=None, past_key_values=None,
            inputs_embeds=None, use_cache=None, output_attentions=None,
            output_hidden_states=None, cache_position=None, generation_steps=None, **kwargs,
        ):
            if os.path.exists("/tmp/tts_step_diag") and _pred_diag["n"] < 40:
                prior_p = (
                    past_key_values.get_seq_length()
                    if past_key_values is not None else 0
                )
                print(
                    f"[pred_diag] call={_pred_diag['n']} gsteps={generation_steps} "
                    f"prior={prior_p} "
                    f"ie={tuple(inputs_embeds.shape) if inputs_embeds is not None else None} "
                    f"ii={tuple(input_ids.shape) if input_ids is not None else None} "
                    f"cp={cache_position.tolist() if cache_position is not None else None}",
                    flush=True,
                )
                _pred_diag["n"] += 1
            return _match_dtype(pred_runner.run(
                inputs_embeds=inputs_embeds, attention_mask=attention_mask,
                position_ids=position_ids, cache_position=cache_position,
                past_key_values=past_key_values, generation_steps=generation_steps,
            ), inputs_embeds)

        main_module.forward = main_forward
        pred_module.forward = predictor_forward

        # Step-level EOS diagnostic on the OUTER talker forward. Transparent unless
        # /tmp/tts_step_diag exists (toggle live, no restart). Logs the trailing-text
        # advance state that drives codec-EOS: if generation_step never advances past
        # trailing_text_hidden length, the talker never reaches the pad->EOS phase.
        _orig_outer_forward = self._talker.forward
        _step_diag = {"n": 0}

        import functools as _functools

        @_functools.wraps(_orig_outer_forward)
        def _outer_forward_diag(*a, **kw):
            out = _orig_outer_forward(*a, **kw)
            try:
                if os.path.exists("/tmp/tts_step_diag"):
                    n = _step_diag["n"]
                    ie0 = kw.get("inputs_embeds")
                    if ie0 is not None and ie0.shape[1] > 1:
                        import torch as _t
                        f = ie0.float()
                        # per-position norms reveal whether rows are distinct
                        pnorm = f.norm(dim=-1)[0]
                        print(
                            f"[embed_diag] PREFILL ie={tuple(ie0.shape)} "
                            f"mean={f.mean().item():.4f} std={f.std().item():.4f} "
                            f"min={f.min().item():.3f} max={f.max().item():.3f} "
                            f"nan={bool(_t.isnan(f).any())} "
                            f"pnorm[min/mean/max]={pnorm.min().item():.2f}/"
                            f"{pnorm.mean().item():.2f}/{pnorm.max().item():.2f} "
                            f"n_distinct_rows≈{int((pnorm.round(decimals=2).unique().numel()))}",
                            flush=True,
                        )
                    if n < 25 or n % 50 == 0:
                        gs_in = kw.get("generation_step")
                        tth = kw.get("trailing_text_hidden")
                        ie = kw.get("inputs_embeds")
                        ii = kw.get("input_ids")
                        cp = kw.get("cache_position")
                        tth_len = int(tth.shape[1]) if tth is not None else None
                        pad_phase = (
                            gs_in is not None and tth_len is not None and gs_in >= tth_len
                        )
                        print(
                            f"[step_diag] call={n} gs_in={gs_in} tth_len={tth_len} "
                            f"pad_phase={pad_phase} "
                            f"ie={tuple(ie.shape) if ie is not None else None} "
                            f"ii={tuple(ii.shape) if ii is not None else None} "
                            f"cp={cp.tolist() if cp is not None else None} "
                            f"gs_out={getattr(out, 'generation_step', None)}",
                            flush=True,
                        )
            except Exception as _e:  # never let diagnostics break generation
                print(f"[step_diag] error: {_e!r}", flush=True)
            _step_diag["n"] += 1
            return out

        self._talker.forward = _outer_forward_diag

        # Patch speech_tokenizer.decode to use vocoder_runtime (if enabled).
        if self.vocoder_runtime and self.vocoder_runtime.enabled:
            st = self._speech_tokenizer
            if st is not None:
                self._orig_st_decode = st.decode

                # One-time warning on first fallback to avoid silent PyTorch takeover.
                first_decode_failure = [True]

                def _ov_decode(inputs, *args, **kwargs):
                    try:
                        return self.vocoder_runtime.decode(inputs, *args, **kwargs)
                    except Exception:
                        if self._codec_released:
                            # Fail-closed: the PyTorch codec was freed after startup, so
                            # there is no decode fallback. Surface the OV failure loudly.
                            raise RuntimeError(
                                "OpenVINO vocoder decode failed and the PyTorch codec was "
                                "released (OPENVINO_KEEP_CODEC_ENCODER=0); no fallback available. "
                                "Restart with OPENVINO_KEEP_CODEC_ENCODER=1 (the default) to keep "
                                "the PyTorch fallback live."
                            )
                        if first_decode_failure[0]:
                            first_decode_failure[0] = False
                            print(
                                "[ov_talker_runtime] vocoder IR failed; "
                                "falling back to PyTorch speech_tokenizer.decode. "
                                "Subsequent calls will keep using PyTorch without logging.",
                                flush=True,
                            )
                        return self._orig_st_decode(inputs, *args, **kwargs)

                st.decode = _ov_decode

        # Loud backend provenance so a run self-documents what actually executed
        # (silent PyTorch fallbacks previously hid that the vocoder never ran).
        voc = "OV" if (self.vocoder_runtime and self.vocoder_runtime.enabled) else "PyTorch"
        print(
            f"[ov_talker] backends: main={self.main_comp} "
            f"predictor={self.pred_comp} vocoder={voc}",
            flush=True,
        )

        return self

    @staticmethod
    def _log_rss(label: str) -> None:
        """Log current RSS from /proc/self/status (Linux only)."""
        try:
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        mib = int(line.split()[1]) / 1024  # /proc reports kB
                        print(f"[ov_talker] RSS({label}): {mib:.0f} MiB", flush=True)
                        return
        except Exception:
            pass

    def _release_torch_core_weights(self) -> None:
        """Free the PyTorch transformer-block weights of the two inner cores (Milestone 7).

        Scoped to each core's ``.layers`` (the decoder blocks), which the OpenVINO graphs fully
        replace and which hold ~all of the parameters. The inner ``embed_tokens`` and ``norm``
        are deliberately kept: the outer generation glue calls ``talker.get_text_embeddings()``
        (== ``talker.model.embed_tokens``) to build the ``inputs_embeds`` it feeds to OV, so
        freeing the embedding table breaks generation. Block tensors are replaced with empty
        storage, then the allocator is asked to return pages to the OS (glibc malloc_trim).
        One-way: the eager PyTorch core forward cannot run after this, so uninstall() will not
        restore it.
        """
        import gc

        import torch

        freed_bytes = 0
        cores = (self._talker.model, self._talker.code_predictor.model)
        with torch.no_grad():
            for core in cores:
                layers = getattr(core, "layers", None)
                if layers is None:
                    continue
                for param in layers.parameters(recurse=True):
                    freed_bytes += param.numel() * param.element_size()
                    param.data = torch.empty(0, dtype=param.dtype, device=param.device)
                for buf in layers.buffers(recurse=True):
                    freed_bytes += buf.numel() * buf.element_size()
                    buf.data = torch.empty(0, dtype=buf.dtype, device=buf.device)
        self._torch_cores_released = True
        gc.collect()
        # Return freed arena pages to the OS where the allocator supports it (glibc only).
        try:
            import ctypes

            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass
        print(
            f"[ov_talker] released ~{freed_bytes / 2**30:.2f} GiB of PyTorch transformer "
            "core weights (OPENVINO_RELEASE_TORCH=1); eager PyTorch core forward is now "
            "unavailable for this process.",
            flush=True,
        )

    def release_codec(self) -> None:
        """Free the PyTorch speech-tokenizer (codec) weights after startup (memory).

        Self-gates on OPENVINO_KEEP_CODEC_ENCODER (see __init__). Must be called only after the
        server-side voice_clone_prompt has been built (the encoder's one job) and the OV
        vocoder is installed (replacing the decoder). The OV vocoder resolves num_quantizers,
        total_upsample, and sample_rate from the codec config at construction time and caches
        them as plain ints, so it does not touch the codec after that. Freeing is one-way and
        fail-closed: _ov_decode / generate_waveform_from_codes stop offering a PyTorch
        fallback once _codec_released is set.
        """
        if not self._release_codec or self._codec_released:
            return
        st = self._speech_tokenizer
        codec = getattr(st, "model", None) if st is not None else None
        if codec is None or not hasattr(codec, "parameters"):
            print(
                "[ov_talker] release_codec(): no speech_tokenizer.model nn.Module to free; "
                "skipping (codec already absent or non-standard).",
                flush=True,
            )
            return

        import gc

        import torch

        freed_bytes = 0
        with torch.no_grad():
            for param in codec.parameters(recurse=True):
                freed_bytes += param.numel() * param.element_size()
                param.data = torch.empty(0, dtype=param.dtype, device=param.device)
            for buf in codec.buffers(recurse=True):
                freed_bytes += buf.numel() * buf.element_size()
                buf.data = torch.empty(0, dtype=buf.dtype, device=buf.device)
        self._codec_released = True
        # The dead PyTorch decode fallback must never be restored on uninstall().
        self._orig_st_decode = None
        gc.collect()
        try:
            import ctypes

            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass
        print(
            f"[ov_talker] released ~{freed_bytes / 2**30:.2f} GiB of PyTorch codec "
            "(speech_tokenizer) weights (OPENVINO_KEEP_CODEC_ENCODER=0); the PyTorch decode "
            "fallback is now unavailable — the OV vocoder is the only decode path.",
            flush=True,
        )

    @property
    def codec_released(self) -> bool:
        """Whether release_codec() has freed the PyTorch codec weights (one-way, fail-closed).

        Callers that need to *encode* new reference audio (e.g. building a fresh
        voice_clone_prompt for a not-yet-cached voice_id) must check this first — encoding
        against freed weights doesn't raise, it silently runs on empty tensors and produces a
        confusing downstream shape/AttributeError instead of a clear "restart with
        OPENVINO_KEEP_CODEC_ENCODER=1" message.
        """
        return self._codec_released

    def uninstall(self) -> None:
        if self._torch_cores_released:
            # Weights were freed for memory; restoring the eager forwards would only expose
            # empty tensors. Leave the OV-backed forwards in place and skip restoration.
            print(
                "[ov_talker] uninstall(): PyTorch core weights were released "
                "(OPENVINO_RELEASE_TORCH); leaving OpenVINO forwards installed.",
                flush=True,
            )
            return
        if self._orig_main_forward is not None:
            self._talker.model.forward = self._orig_main_forward
            self._orig_main_forward = None
        if self._orig_pred_forward is not None:
            self._talker.code_predictor.model.forward = self._orig_pred_forward
            self._orig_pred_forward = None
        if self._orig_st_decode is not None:
            # Use the resolved sibling handle, not getattr(talker, ...) which is always None.
            st = self._speech_tokenizer
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
                if self._codec_released:
                    raise RuntimeError(
                        "OpenVINO vocoder decode failed and the PyTorch codec was released "
                        "(OPENVINO_KEEP_CODEC_ENCODER=0); no fallback available."
                    )
                # One-time warning on first fallback.
                if getattr(self, "_wvf_first_warn", True):
                    self._wvf_first_warn = False
                    print(
                        "[ov_talker_runtime] generate_waveform_from_codes: "
                        "vocoder IR failed; falling back to PyTorch. "
                        "Subsequent calls will keep using PyTorch without logging.",
                        flush=True,
                    )
        # PyTorch fallback.
        st = self._speech_tokenizer
        if st is not None:
            return st.decode(codes)
        raise RuntimeError("No vocoder available (no speech_tokenizer).")

    def __enter__(self) -> "OVTalkerRuntime":
        return self.install()

    def __exit__(self, *exc) -> None:
        self.uninstall()


def build_runtime(model_dir, talker, *, ov_config=None, compression=None, install=True,
                  speech_tokenizer=None) -> OVTalkerRuntime:
    """Construct an OVTalkerRuntime and (by default) install it on the talker."""
    runtime = OVTalkerRuntime(model_dir, talker, ov_config=ov_config, compression=compression,
                              speech_tokenizer=speech_tokenizer)
    if install:
        runtime.install()
    return runtime

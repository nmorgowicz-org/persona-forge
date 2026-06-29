"""OpenVINO vocoder runtime (Step 2 of M4).

Replaces the PyTorch vocoder decoder body in speech_tokenizer.decode with the
FP32 OpenVINO IR (vocoder.xml) while preserving the exact chunking, left-context,
padding, and return shape expected by the Qwen3-TTS generation path.

Only the per-chunk decoder forward (12 Hz decoder) runs on OpenVINO; chunking,
quantizer decode, pre-conv, and concatenation stay in Python. INT8 vocoder was
rejected; only FP32 IR is supported.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


class OpenVinoVocoderRuntime:
    """Load and run the vocoder decoder IR for speech_tokenizer.decode.

    Args:
        speech_tokenizer: the talker's speech_tokenizer (used to access model config
                          for num_quantizers and upsample factors).
        cfg: vocoder config dict from ov_runtime_config with keys:
              enabled, model_path, device, config.
    """

    def __init__(self, speech_tokenizer: Any, cfg: dict[str, Any]) -> None:
        if not cfg or not cfg.get("enabled"):
            self.enabled = False
            return

        model_path = cfg.get("model_path")
        if model_path is None:
            self.enabled = False
            return

        # The exporter writes "vocoder_decoder.xml"; older docs/tooling referred to
        # "vocoder.xml". Accept either so a name skew can't silently disable the IR.
        xml_path = None
        for candidate in ("vocoder.xml", "vocoder_decoder.xml"):
            p = Path(model_path) / candidate
            if p.is_file():
                xml_path = p
                break
        if xml_path is None:
            print(
                f"[ov_vocoder] no vocoder IR (vocoder.xml / vocoder_decoder.xml) in "
                f"{model_path}; falling back to PyTorch vocoder.",
                flush=True,
            )
            self.enabled = False
            return

        import openvino as ov

        core = ov.Core()
        device = cfg.get("device", "CPU")
        extra_cfg = cfg.get("config") or {}

        self.core = core
        self.compiled_model = core.compile_model(str(xml_path), device, extra_cfg)
        self.req = self.compiled_model.create_infer_request()

        # Resolve quantizers and expected IR layout from metadata.
        self._cfg = cfg
        self._speech_tokenizer = speech_tokenizer

        # Infer dimensions from metadata if present.
        meta_cfg = cfg.get("meta") or {}
        self._num_quantizers = meta_cfg.get("num_quantizers") or self._resolve_num_quantizers()
        self._total_upsample = meta_cfg.get("total_upsample") or self._resolve_total_upsample()

        # Validate input/output layers.
        self._validate_io()

        # Sanity check: small dummy inference.
        self._sanity_check()

        self.enabled = True

    # -- internal helpers ----------------------------------------------------------

    def _resolve_num_quantizers(self) -> int:
        """Extract num_quantizers from speech_tokenizer config."""
        m = getattr(self._speech_tokenizer, "model", None)
        if m is None:
            return 16  # known default
        dec = getattr(m, "decoder", None)
        cfg = getattr(dec, "config", None) if dec is not None else None
        return int(getattr(cfg, "num_quantizers", 16))

    def _resolve_total_upsample(self) -> int:
        """Extract total_upsample (samples per 12 Hz frame) from config."""
        m = getattr(self._speech_tokenizer, "model", None)
        if m is None:
            return 1920  # known default: 8*5*4*3*2*2
        dec = getattr(m, "decoder", None)
        cfg = getattr(dec, "config", None) if dec is not None else None
        if cfg is None:
            return 1920
        try:
            import numpy as np
            up = list(getattr(cfg, "upsample_rates", []))
            ur = list(getattr(cfg, "upsampling_ratios", []))
            return int(np.prod(up + ur))
        except Exception:
            return 1920

    def _validate_io(self) -> None:
        """Validate IR I/O shapes match expectations."""
        input_layer = self.compiled_model.input(0)
        output_layer = self.compiled_model.output(0)
        self.input_name = input_layer.any_name
        self.output_name = output_layer.any_name

        in_shape = input_layer.get_shape()       # e.g. [1, 16, 325] or [1, 16, -1]
        out_shape = output_layer.get_shape()     # e.g. [1, 1, -1]

        # Input name sanity check (heuristic, not strict).
        in_lower = self.input_name.lower()
        has_codes_hint = any(tok in in_lower for tok in ("codes", "code", "input"))
        if not has_codes_hint:
            # Warn but don't fail; some exports use generic names.
            print(
                f"[ov_vocoder] input name {self.input_name!r} does not contain 'codes' hint; "
                f"proceeding if shape is correct.",
                flush=True,
            )

        # Input must be rank 3: [batch, quantizers, frames].
        if in_shape.rank != 3:
            raise RuntimeError(
                f"vocoder IR input rank {in_shape.rank} != 3; cannot use: {in_shape}"
            )

        # Output must be rank 3: [batch, 1, samples].
        if out_shape.rank != 3:
            raise RuntimeError(
                f"vocoder IR output rank {out_shape.rank} != 3; cannot use: {out_shape}"
            )

        print(
            f"[ov_vocoder] IR OK: in={in_shape} out={out_shape} "
            f"q={self._num_quantizers} upsample={self._total_upsample}",
            flush=True,
        )

    def _sanity_check(self) -> None:
        """Quick smoke-test: run on tiny random codes to confirm it compiles/infers."""
        # Use the minimal valid shape the IR was traced with: [1, 16, 325] or similar.
        # If last dim is dynamic (-1), we pick 325 as reference.
        try:
            from openvino.runtime import PartialShape
            p = self.compiled_model.input(0).get_partial_shape()
            seq_dim = int(p[2]) if p[2].is_static else 325
        except Exception:
            seq_dim = 325

        codes = np.random.randint(0, 2048, (1, self._num_quantizers, seq_dim), dtype=np.int64)
        self.req.infer({self.input_name: codes})
        wav = self.req.get_tensor(self.output_name).data
        if wav.size == 0:
            raise RuntimeError("vocoder IR sanity check produced empty output")

    # -- public decode -------------------------------------------------------------

    def decode(self, inputs, *args, **kwargs):
        """Run vocoder inference on generated audio codes.

        Accepts either:
          - speech_tokenizer.decode-style: inputs is a list of dicts with
            "audio_codes" key holding a [frames, Q] tensor (batch > 1 supported).
          - raw codes: a [frames, Q] tensor or numpy array (for direct calls).

        Returns:
            For list-of-dict input: list of 1-D float32 waveforms as torch tensors (one per item).
            For raw input: single 1-D float32 waveform as torch tensor.
        Raises:
            RuntimeError on failure so caller can fall back.
        """
        import torch

        # Handle list-of-dict format used by speech_tokenizer.decode.
        if isinstance(inputs, (list, tuple)) and len(inputs) > 0:
            if isinstance(inputs[0], dict):
                # speech_tokenizer.decode style: [{"audio_codes": tensor}, ...]
                results = []
                for item in inputs:
                    c = item["audio_codes"]
                    wav = self._decode_codes_tensor(c)
                    results.append(
                        torch.from_numpy(wav) if isinstance(wav, np.ndarray) else wav
                    )
                return results

        # Fallback: treat inputs as raw codes tensor/array.
        wav = self._decode_codes_tensor(inputs)
        return torch.from_numpy(wav) if isinstance(wav, np.ndarray) else wav

    def _decode_codes_tensor(self, codes):
        """Core decode path for a single [frames, Q] codes tensor/array."""
        import torch

        # Normalize input to numpy [frames, Q].
        if isinstance(codes, torch.Tensor):
            codes = codes.detach().cpu().numpy()
        codes = np.asarray(codes, dtype=np.int64)


        if codes.ndim == 2:
            frames, q = codes.shape
        elif codes.ndim == 3 and codes.shape[0] == 1:
            # Already [1, frames, Q]; squeeze.
            codes = codes[0]
            frames, q = codes.shape
        else:
            raise RuntimeError(
                f"vocoder_runtime.decode: unexpected codes shape {codes.shape}; "
                f"expected [frames, {self._num_quantizers}]"
            )

        if frames == 0:
            return np.array([], dtype=np.float32)

        # Chunking parameters consistent with the export wrapper.
        chunk_size = 300        # frames per chunk
        left_context = 25       # previous frames for continuity
        ir_input_frames = chunk_size + left_context  # 325

        # If input fits in one chunk, pad and infer directly, using left-context
        # warmup to match multi-chunk behavior.
        if frames <= chunk_size:
            return self._single_chunk(codes, chunk_size, left_context)

        # Longer: chunk with left context overlap, concatenate waveforms.
        chunks = []
        pos = 0
        while pos < frames:
            end = min(pos + chunk_size, frames)
            chunk_len = end - pos

            # Left context from previous region (or zero-pad at start).
            ctx_start = max(0, pos - left_context)
            ctx = codes[ctx_start:pos]
            needed_ctx = left_context - (pos - ctx_start)
            if needed_ctx > 0:
                pad = np.zeros((int(needed_ctx), int(q)), dtype=np.int64)
                ctx = np.concatenate([pad, ctx], axis=0)

            combined = np.concatenate([ctx, codes[pos:end]], axis=0)  # [325, Q]

            # Run chunk via IR.
            wav_chunk = self._run_ir(combined)

            # Crop to just this chunk's samples, skipping left-context output.
            skip_ctx = int(left_context * self._total_upsample)
            chunk_samples = int(chunk_len * self._total_upsample)
            wav_chunk = wav_chunk[skip_ctx : skip_ctx + chunk_samples]
            chunks.append(wav_chunk)

            pos = end

        return np.concatenate(chunks, axis=0).astype(np.float32)

    def _single_chunk(self, codes, chunk_size, left_context):
        """Handle frames <= chunk_size with left-context warmup and right-padding.

        Mirrors the first chunk of the multi-chunk path:
          - prepend left_context=25 zero frames as warmup,
          - pad chunk to 300 frames,
          - infer,
          - skip the left_context output, keep only the real frames' output.
        """
        frames = codes.shape[0]
        q = codes.shape[1]

        # Prepend zero left-context to warm up the decoder (matches multi-chunk behavior).
        left_pad = np.zeros((int(left_context), int(q)), dtype=np.int64)
        ctx_and_codes = np.concatenate([left_pad, codes], axis=0)

        # Pad chunk to 300 frames (so total length is 325 including left_context).
        remaining = chunk_size - frames
        if remaining > 0:
            right_pad = np.zeros((int(remaining), int(q)), dtype=np.int64)
            combined = np.concatenate([ctx_and_codes, right_pad], axis=0)
        else:
            combined = ctx_and_codes

        wav = self._run_ir(combined)

        # Skip left-context output; keep only samples for the real frames.
        skip_ctx = int(left_context * self._total_upsample)
        chunk_samples = int(frames * self._total_upsample)
        wav = wav[skip_ctx : skip_ctx + chunk_samples]

        return wav.astype(np.float32)

    def _run_ir(self, codes_2d):
        """Run one IR inference on a [325, Q] codes array.

        Expects IR input: [1, Q, 325].
        Output: [1, 1, samples]; returns 1-D float32.
        """
        frames, q = codes_2d.shape
        codes_input = codes_2d.T.reshape(1, q, frames)

        self.req.infer({self.input_name: codes_input})
        out = self.req.get_tensor(self.output_name)
        wav = out.data
        # Squeeze batch and channel dims.
        wav = wav.reshape(-1)
        return wav.astype(np.float32, copy=True)

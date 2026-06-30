import gc
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional

# Apply thread and runtime envs before heavy imports
from ov_runtime_config import apply_thread_env

apply_thread_env()
os.environ.setdefault("ORT_INTRA_OP_NUM_THREADS", "6")
os.environ.setdefault("ORT_INTER_OP_NUM_THREADS", "2")
os.environ.setdefault("OMP_NUM_THREADS", "6")
os.environ.setdefault("MKL_NUM_THREADS", "6")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import soundfile as sf
import torch

from flask import Flask, Response, jsonify, request
from model_config import configure_hf_token, resolve_model_repo

configure_hf_token()

from qwen_tts import Qwen3TTSModel

app = Flask(__name__)

MODEL_ID = resolve_model_repo()
MODEL_REVISION = os.getenv("MODEL_REVISION") or None
DEVICE = os.getenv("DEVICE", "cpu")
REF_AUDIO = os.getenv("REF_AUDIO", "/voice/voice_A.wav")
REF_TEXT = os.getenv(
    "REF_TEXT",
    "Welcome to Rosies. What can I get for you today? You know, Im a good girl. "
    "You want me, dont you? I am on the menu too.",
)

TTS_BACKEND = (os.getenv("TTS_BACKEND", "pytorch") or "pytorch").strip().lower()
OV_MODEL_DIR = os.getenv("OV_MODEL_DIR")
OPENVINO_RELEASE_TORCH = os.getenv("OPENVINO_RELEASE_TORCH", "0").strip() == "1"
OPENVINO_MAIN_STATEFUL_MODEL = (os.getenv("OPENVINO_MAIN_STATEFUL_MODEL") or "").strip() or None
OPENVINO_PREDICTOR_STATEFUL_MODEL = (
    (os.getenv("OPENVINO_PREDICTOR_STATEFUL_MODEL") or "").strip() or None
)

torch.set_num_threads(6)

model = None
voice_clone_prompt = None

ov_metadata = None
ov_config = None
ov_runtime = None

# Streaming vocoder constants (must match ov_vocoder_runtime and the chunked_decode
# contract in the Qwen3-TTS tokenizer).
_STREAMING_CHUNK_SIZE = 300       # frames per vocoder chunk
_STREAMING_LEFT_CONTEXT = 25      # previous frames for continuity


class _StreamingVocoderContext:
    """Opt-in, non-breaking streaming context for incremental vocoder decode.

    Wrap model.generate_voice_clone(...) inside this context when you want audio
    chunks emitted as soon as each 300-frame vocoder block is ready.

    Behavior:
      - If on_audio_chunk is None: no-op wrapper; identical to normal batch mode.
      - If on_audio_chunk is set:
          - Patches talker.model.forward (the inner core, where OpenVINO is wired)
            instead of talker.forward to avoid colliding with Transformers'
            kwarg validation.
          - Each completed 16-codebook frame is captured from hidden_states[-1]
            and appended to an internal buffer.
          - When buffer reaches >= STREAMING_CHUNK_SIZE frames, it flushes a chunk
            through the vocoder runtime's iter_decode_chunks and yields PCM via
            on_audio_chunk(chunk: np.ndarray[float32]).
          - On __exit__, flushes any remaining frames (partial chunk) via iter_decode_chunks
            in exactly the same way, then restores the original forward.
      - Existing batch /generate path is unchanged: codes are still returned
        as a complete sequence; we only emit early PCM side-channel.
    """

    def __init__(
        self,
        model: Any,
        on_audio_chunk: Callable[[Any], None] | None,
    ) -> None:
        self.model = model
        self.on_audio_chunk = on_audio_chunk
        self._codes_buffer: Any = None  # [frames, 16], starts as list[tensor]
        self._decoded_frames: int = 0  # how many frames already emitted via streaming
        self._prev_wav: Any = None    # previous full decode output for diff streaming
        self._orig_forward: Any = None
        self._speech_tokenizer: Any = None
        self._vocoder_runtime: Any = None

    def _get_vocoder_runtime(self):
        """Resolve the vocoder_runtime that the current OV install is using."""
        if self._vocoder_runtime is not None:
            return self._vocoder_runtime

        # If OV runtime installed and vocoder enabled, use its iter_decode_chunks.
        if ov_runtime is not None:
            vr = getattr(ov_runtime, "vocoder_runtime", None)
            if vr is not None and getattr(vr, "enabled", False):
                self._vocoder_runtime = vr
                return vr

        # Fallback: use speech_tokenizer.decode's underlying runtime.
        st = getattr(getattr(self.model, "model", None), "speech_tokenizer", None)
        if st is not None:
            # When vocoder_runtime patches decode, use it directly.
            decode_fn = getattr(st, "decode", None)
            if callable(decode_fn):
                # We'll just use st.decode for flush: it already wraps iter_decode_chunks.
                self._speech_tokenizer = st
        return None

    def _to_numpy(self, x):
        """Normalize a codes tensor or list of tensors to [frames, Q] int64 numpy."""
        import numpy as np

        # x is a list of [16] tensors per step.
        if isinstance(x, list):
            # stack in-place: each is [16], result [frames, 16].
            import torch

            if len(x) == 0:
                return np.empty((0, 16), dtype=np.int64)
            stacked = torch.cat([t.unsqueeze(0) for t in x], dim=0)
            return stacked.detach().cpu().numpy().astype(np.int64, copy=False)
        # If already numpy [frames, 16]
        if isinstance(x, np.ndarray):
            if x.ndim == 2 and x.shape[1] == 16:
                return np.asarray(x, dtype=np.int64)
        # If torch
        if hasattr(x, "detach") and hasattr(x, "cpu"):
            x = x.detach().cpu().numpy()
        return np.asarray(x, dtype=np.int64)

    def _maybe_flush_chunk(self) -> None:
        """Flush new audio chunks incrementally.

        To ensure the streaming path is bit-identical to the batch path:
        - We always decode codes[0:N] as a prefix using iter_decode_chunks.
        - We emit only the new audio beyond what we previously streamed.
        - Left-context / overlap logic is fully handled by iter_decode_chunks.
        """
        if self.on_audio_chunk is None:
            return
        import numpy as np

        codes_arr = self._to_numpy(self._codes_buffer)
        frames, q = codes_arr.shape
        chunk_size = _STREAMING_CHUNK_SIZE

        if frames < chunk_size:
            return

        # Decode the full prefix [0:N].
        wav = self._decode_codes(codes_arr)
        if wav is None or wav.size == 0:
            return

        # Determine how many audio samples we already emitted.
        if self._prev_wav is not None:
            emitted_samples = len(self._prev_wav)
        else:
            emitted_samples = 0

        # Emit only the new tail.
        if len(wav) > emitted_samples:
            new_chunk = wav[emitted_samples:]
            self.on_audio_chunk(new_chunk)

        # Remember last full decode for diff streaming.
        self._prev_wav = wav
        self._decoded_frames = frames

    def _decode_codes(self, codes_2d: Any) -> Any | None:
        """Run iter_decode_chunks on the given [frames, 16] codes once.

        Uses:
          - ov_runtime.vocoder_runtime if enabled (preferred),
          - or speech_tokenizer.decode as a safe fallback.
        Returns a 1-D float32 PCM array or None on failure.
        """
        import numpy as np

        vr = self._get_vocoder_runtime()
        if vr is not None:
            try:
                # Use iter_decode_chunks: its output concatenated is the full waveform
                # for this chunk. We already ensured codes_2d is exactly one chunk's
                # worth (or less), so this will emit at most one or two IR calls
                # matching the existing _single_chunk / iter_decode_chunks behavior.
                chunks = list(vr.iter_decode_chunks(codes_2d))
                if chunks:
                    return np.concatenate(chunks, axis=0).astype(np.float32, copy=False)
                return None
            except Exception:
                pass

        st = self._speech_tokenizer
        if st is not None:
            try:
                result = st.decode([{"audio_codes": codes_2d}])
                # speech_tokenizer.decode returns (wavs, sample_rate) for list inputs.
                if isinstance(result, (list, tuple)) and len(result) >= 2:
                    wavs, sr = result[0], result[1]
                    if isinstance(wavs, list) and len(wavs) == 1:
                        return np.asarray(wavs[0], dtype=np.float32).ravel()
                return np.asarray(result, dtype=np.float32).ravel()
            except Exception:
                pass

        return None

    def __enter__(self) -> "_StreamingVocoderContext":
        # No streaming if no callback is set.
        if self.on_audio_chunk is None:
            return self

        # Patch the inner model forward (where OV is wired) to avoid colliding
        # with Transformers' outer model_kwargs validation.
        talker = getattr(getattr(self.model, "model", None), "talker", None)
        if talker is None:
            self.on_audio_chunk = None
            return self

        inner = getattr(talker, "model", None)
        if inner is None:
            self.on_audio_chunk = None
            return self

        # Store original inner forward.
        self._orig_forward = getattr(inner, "forward", None)
        if not callable(self._orig_forward):
            self.on_audio_chunk = None
            return self

        # Start buffer as a list of per-step code vectors.
        self._codes_buffer = []

        def _streaming_forward(*args, **kwargs):
            out = self._orig_forward(*args, **kwargs)
            # hidden_states[-1] is the codes tensor: [1, 1, 16] (batch=1, seq=1, Q=16)
            # for each autoregressive step, or [1, seq, 16] on prefill.
            if hasattr(out, "hidden_states") and isinstance(out.hidden_states, tuple):
                codes = out.hidden_states[-1]  # [1, 1, 16] per step
            else:
                # Fallback: nothing to capture.
                return out

            # Normalize: [1,1,16] -> [16] per step, or [1,N,16] -> N rows.
            import torch

            if hasattr(codes, "squeeze"):
                codes = codes.squeeze(0)
            if codes.ndim == 3 and codes.shape[0] == 1:
                codes = codes[0]
            if codes.ndim == 2 and codes.shape[1] == 16:
                # multi-row (prefill): append each row individually.
                for i in range(codes.shape[0]):
                    self._codes_buffer.append(codes[i])
            elif codes.ndim == 1 and codes.shape[0] == 16:
                # single step
                self._codes_buffer.append(codes)

            # Try to flush a complete chunk.
            self._maybe_flush_chunk()
            return out

        inner.forward = _streaming_forward
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Restore original inner forward.
        if self._orig_forward is not None:
            talker = getattr(getattr(self.model, "model", None), "talker", None)
            if talker is not None:
                inner = getattr(talker, "model", None)
                if inner is not None and hasattr(inner, "forward"):
                    inner.forward = self._orig_forward
            self._orig_forward = None

        # Flush any remaining codes as a final full decode.
        if self.on_audio_chunk is not None and self._codes_buffer:
            import numpy as np

            codes_arr = self._to_numpy(self._codes_buffer)
            wav = self._decode_codes(codes_arr)
            if wav is not None and wav.size > 0:
                # Emit only the part beyond what we already streamed.
                if self._prev_wav is not None:
                    emitted_samples = len(self._prev_wav)
                    if len(wav) > emitted_samples:
                        self.on_audio_chunk(wav[emitted_samples:])
                else:
                    self.on_audio_chunk(wav)

            self._codes_buffer = None
            self._prev_wav = None
            self._decoded_frames = 0

executor = ThreadPoolExecutor(max_workers=1)


def _validate_ov_metadata(model_dir: str):
    global ov_metadata, ov_config
    path = Path(model_dir)
    meta_path = path / "metadata.json"
    if not meta_path.is_file():
        raise RuntimeError(f"OV_MODEL_DIR missing metadata.json: {meta_path}")

    ov_metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    from ov_runtime_config import get_ov_config
    ov_config = get_ov_config()

    # Validate metadata matches loaded model
    if ov_metadata.get("model_repo") != MODEL_ID:
        raise RuntimeError(
            f"OV metadata model_repo {ov_metadata.get('model_repo')!r} "
            f"!= {MODEL_ID!r}"
        )

    # Revision check: only enforced when MODEL_REVISION is explicitly pinned. When it is
    # unset, accept whatever the export recorded (an auto-resolved commit SHA or "main"),
    # so easy/ad-hoc exports don't block worker startup.
    artifact_revision = ov_metadata.get("model_revision")
    if MODEL_REVISION and artifact_revision != MODEL_REVISION:
        raise RuntimeError(
            f"OV metadata model_revision {artifact_revision!r} != pinned {MODEL_REVISION!r}"
        )
    if not MODEL_REVISION:
        print(
            f"[app_worker] MODEL_REVISION unpinned; accepting artifact revision "
            f"{artifact_revision!r}.",
            flush=True,
        )

    qwen_version = ov_metadata.get("qwen_tts_version")
    if qwen_version:
        try:
            import qwen_tts
            runtime_version = getattr(qwen_tts, "__version__", None)
            if runtime_version and runtime_version != qwen_version:
                raise RuntimeError(
                    f"OV metadata qwen_tts_version {qwen_version!r} "
                    f"!= runtime {runtime_version!r}"
                )
        except ImportError:
            pass

    print(
        f"[app_worker] OpenVINO metadata OK: {path.name} "
        f"(openvino={ov_metadata.get('openvino_version')}, "
        f"compression={ov_metadata.get('compression')})",
        flush=True,
    )


def load_model():
    global model, voice_clone_prompt, ov_runtime

    if TTS_BACKEND not in ("pytorch", "openvino"):
        raise RuntimeError(f"Invalid TTS_BACKEND: {TTS_BACKEND!r}")

    if TTS_BACKEND == "openvino":
        if not OV_MODEL_DIR:
            raise RuntimeError(
                "TTS_BACKEND=openvino requires OV_MODEL_DIR"
            )
        _validate_ov_metadata(OV_MODEL_DIR)
    else:
        # PyTorch-only backend
        if OV_MODEL_DIR:
            print(
                "[app_worker] OV_MODEL_DIR set but TTS_BACKEND=pytorch; "
                "ignoring OpenVINO directory.",
                flush=True,
            )

    print(
        f"[app_worker] Backend={TTS_BACKEND}, loading model at float32...",
        flush=True,
    )
    wrapped = Qwen3TTSModel.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        device_map=DEVICE,
        dtype=torch.float32,
    )

    gc.collect()
    print("[app_worker] Model loaded. Creating voice clone prompt...", flush=True)

    model = wrapped
    voice_clone_prompt = model.create_voice_clone_prompt(
        ref_audio=REF_AUDIO,
        ref_text=REF_TEXT,
        x_vector_only_mode=False,
    )

    if TTS_BACKEND == "openvino":
        # Milestone 4: install the OpenVINO talker runtime by swapping the two inner
        # transformer core forwards. All other generation glue stays in PyTorch.
        from ov_talker_runtime import OVTalkerRuntime

        talker = model.model.talker
        # speech_tokenizer is a sibling of talker on the parent model, not a child of it;
        # pass it explicitly so the OV vocoder patch can find it.
        ov_runtime = OVTalkerRuntime(
            OV_MODEL_DIR, talker, ov_config=ov_config,
            speech_tokenizer=model.model.speech_tokenizer,
        )
        ov_runtime.install()

        # Startup policy logs
        if OPENVINO_RELEASE_TORCH:
            print(
                "[app_worker] OPENVINO_RELEASE_TORCH active: "
                "PyTorch core weights may be released during OpenVINO compilation.",
                flush=True,
            )
        if OPENVINO_MAIN_STATEFUL_MODEL:
            print(
                f"[app_worker] OPENVINO_MAIN_STATEFUL_MODEL active: "
                f"{OPENVINO_MAIN_STATEFUL_MODEL}",
                flush=True,
            )
        if OPENVINO_PREDICTOR_STATEFUL_MODEL:
            print(
                f"[app_worker] OPENVINO_PREDICTOR_STATEFUL_MODEL active: "
                f"{OPENVINO_PREDICTOR_STATEFUL_MODEL}",
                flush=True,
            )

        vocoder_status = (
            f"vocoder={'OV' if (ov_runtime.vocoder_runtime and ov_runtime.vocoder_runtime.enabled) else 'PyTorch'}"
        )
        print(
            f"[app_worker] OpenVINO talker runtime installed "
            f"(compression={ov_runtime.compression}, {vocoder_status}); "
            f"cores run on OpenVINO.",
            flush=True,
        )

    print("[app_worker] Model loaded and ready.")


load_model()


@app.route("/health")
def health():
    base = {
        "status": "ok",
        "backend": TTS_BACKEND,
        "model": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "device": DEVICE,
        "ref_audio": REF_AUDIO,
        "timestamp": time.time(),
    }

    if TTS_BACKEND == "openvino" and ov_metadata:
        vocoder_info = None
        if ov_runtime is not None:
            vr = ov_runtime.vocoder_runtime
            vocoder_info = {
                "enabled": bool(vr and vr.enabled),
                "device": "CPU",
            }

        base.update(
            {
                "openvino": {
                    "version": ov_metadata.get("openvino_version"),
                    "device": "CPU",
                    "ir_directory": Path(OV_MODEL_DIR or "").name,
                    "ir_metadata_hash": ov_metadata.get("source_hash"),
                    "compression": ov_metadata.get("compression"),
                    "int8_config": ov_metadata.get("int8_config"),
                    "config": ov_config,
                    "runtime_wired": ov_runtime is not None,
                    "active_compression": (
                        ov_runtime.compression if ov_runtime is not None else None
                    ),
                    "stateful_main": bool(OPENVINO_MAIN_STATEFUL_MODEL),
                    "stateful_predictor": bool(OPENVINO_PREDICTOR_STATEFUL_MODEL),
                    "stateful_capacity": {
                        "main": getattr(getattr(ov_runtime, "main", None), "capacity", None),
                        "predictor": getattr(getattr(ov_runtime, "pred", None), "capacity", None),
                    },
                    "release_torch": OPENVINO_RELEASE_TORCH,
                    "vocoder": vocoder_info,
                }
            }
        )

    def _json_safe(obj):
        if isinstance(obj, Path):
            return obj.as_posix()
        if isinstance(obj, dict):
            return {k: _json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_json_safe(v) for v in obj]
        return obj

    return jsonify(_json_safe(base))


def _trim_silence(wav, sr):
    """Strip the leading/trailing near-silence the model emits around speech.

    The talker naturally pads utterances with up to ~1 s of dead air at the head
    and tail (present identically in PyTorch and OpenVINO output — it is a
    generation behavior, not a backend artifact). This energy-gates relative to
    the clip's own peak and keeps a small pad so the onset/offset is never
    clipped. Gated by SILENCE_TRIM (default on); SILENCE_TRIM_THRESH (fraction of
    peak) and SILENCE_TRIM_PAD_MS tune it. No-op on an essentially silent clip.
    """
    if os.getenv("SILENCE_TRIM", "1").strip() == "0":
        return wav
    import numpy as np

    arr = np.asarray(wav, dtype=np.float32).ravel()
    peak = float(np.max(np.abs(arr))) if arr.size else 0.0
    if peak <= 0.0:
        return wav
    thresh = peak * float(os.getenv("SILENCE_TRIM_THRESH", "0.01"))
    above = np.nonzero(np.abs(arr) >= thresh)[0]
    if above.size == 0:
        return wav
    pad = int(sr * float(os.getenv("SILENCE_TRIM_PAD_MS", "30")) / 1000.0)
    start = max(0, int(above[0]) - pad)
    end = min(arr.size, int(above[-1]) + 1 + pad)
    return arr[start:end]


def _run_generate(text: str, language: str, **gen_kwargs):
    if model is None or voice_clone_prompt is None:
        raise RuntimeError("Model not loaded")
    import traceback as _tb
    try:
        wavs, sr = model.generate_voice_clone(
            text=text,
            language=language,
            voice_clone_prompt=voice_clone_prompt,
            **gen_kwargs,
        )
    except Exception:
        _tb.print_exc()
        raise
    return _trim_silence(wavs[0], sr), sr


def _run_generate_with_streaming(
    text: str,
    language: str,
    on_audio_chunk: Callable[[Any], None],
    **gen_kwargs,
):
    """Run generation and call on_audio_chunk(1-D float32 PCM) for each streaming chunk.

    - on_audio_chunk is called as soon as each 300-frame vocoder chunk is decoded.
    - Still returns the same (full wav, sr) as _run_generate so existing callers
      that ignore on_audio_chunk get unchanged batch behavior.
    - Opt-in: only used when on_audio_chunk is provided; if None, falls back to _run_generate.
    - Uses _StreamingVocoderContext to intercept talker.forward outputs incrementally
      and feeds them into iter_decode_chunks from ov_vocoder_runtime.
    - Extra gen_kwargs are forwarded to generate_voice_clone (e.g., do_sample=False).
    """
    if on_audio_chunk is None:
        if gen_kwargs:
            raise RuntimeError("_run_generate_with_streaming called with gen_kwargs but no streaming callback")
        return _run_generate(text, language)

    import numpy as np

    if model is None or voice_clone_prompt is None:
        raise RuntimeError("Model not loaded")

    chunks: List[np.ndarray] = []

    def chunk_callback(pcm: Any):
        chunks.append(np.asarray(pcm, dtype=np.float32).ravel())
        on_audio_chunk(pcm)

    ctx = _StreamingVocoderContext(model, chunk_callback)
    try:
        with ctx:
            import traceback as _tb
            try:
                wavs, sr = model.generate_voice_clone(
                    text=text,
                    language=language,
                    voice_clone_prompt=voice_clone_prompt,
                    **gen_kwargs,
                )
            except Exception:
                _tb.print_exc()
                raise
    finally:
        pass

    # Existing batch behavior: still return the complete trimmed wav.
    return _trim_silence(wavs[0], sr), sr


@app.route("/infer", methods=["POST"])
def infer():
    if model is None or voice_clone_prompt is None:
        return jsonify({"error": "Model not loaded"}), 503

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    language = (data.get("language") or "English").strip()

    def do_work():
        # Allow parity/greedy overrides in request (dev-only; not public API).
        gen_kwargs_raw = {
            "do_sample": data.get("do_sample"),
            "temperature": data.get("temperature"),
            "top_p": data.get("top_p"),
            "top_k": data.get("top_k"),
        }
        gen_kwargs = {k: v for k, v in gen_kwargs_raw.items() if v is not None}

        wav, sr = _run_generate(text, language, **gen_kwargs)

        fmt = (data.get("response_format") or "mp3").lower()
        buf = io.BytesIO()
        if fmt == "mp3":
            sf.write(buf, wav, sr, format="MP3")
            media_type = "audio/mpeg"
        else:
            sf.write(buf, wav, sr, format="WAV")
            media_type = "audio/wav"
        buf.seek(0)
        return buf.read(), media_type

    try:
        audio_bytes, media_type = executor.submit(do_work).result(timeout=300)
    except Exception as e:
        return jsonify({"error": f"Inference error: {str(e)}"}), 500

    return Response(audio_bytes, content_type=media_type)


@app.route("/stream_internal", methods=["POST"])
def stream_internal():
    """Dev-only streaming parity endpoint.

    - Uses _run_generate_with_streaming to exercise the streaming vocoder path.
    - Same JSON input as /infer.
    - Returns WAV of concatenated streaming chunks.
    - NOT part of the public API; may change or be removed.
    """
    if model is None or voice_clone_prompt is None:
        return jsonify({"error": "Model not loaded"}), 503

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    language = (data.get("language") or "English").strip()

    def do_work():
        import numpy as np

        # Forward generation kwargs for parity and tests (e.g., do_sample=False).
        gen_kwargs = {
            "do_sample": data.get("do_sample"),
            "temperature": data.get("temperature"),
            "top_p": data.get("top_p"),
            "top_k": data.get("top_k"),
        }
        gen_kwargs = {k: v for k, v in gen_kwargs.items() if v is not None}

        stream_chunks: List[np.ndarray] = []

        def on_chunk(pcm: Any):
            stream_chunks.append(np.asarray(pcm, dtype=np.float32).ravel())

        wav, sr = _run_generate_with_streaming(text, language, on_chunk, **gen_kwargs)

        # Build audio from the streaming chunks for parity comparison.
        if stream_chunks:
            wav_stream = np.concatenate(stream_chunks, axis=0)
        else:
            wav_stream = wav

        # Return streaming result as WAV.
        buf = io.BytesIO()
        sf.write(buf, wav_stream, sr, format="WAV")
        buf.seek(0)
        return buf.read(), "audio/wav", wav, sr

    try:
        audio_bytes, media_type, wav_batch, sr = executor.submit(do_work).result(timeout=300)
    except Exception as e:
        return jsonify({"error": f"Inference error: {str(e)}"}), 500

    return Response(audio_bytes, content_type=media_type)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8319)

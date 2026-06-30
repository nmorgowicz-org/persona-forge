import gc
import io
import json
import os
import queue
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

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
from model_config import configure_hf_token, resolve_model_repo, resolve_torch_load_config
from streaming_vocoder import StreamingVocoderSession

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
TORCH_DTYPE, TORCH_DTYPE_NAME, OPENVINO_LOW_CPU_MEM_USAGE = resolve_torch_load_config(torch)

torch.set_num_threads(6)

model = None
voice_clone_prompt = None

ov_metadata = None
ov_config = None
ov_runtime = None

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
        f"[app_worker] Backend={TTS_BACKEND}, loading model at {TORCH_DTYPE_NAME} "
        f"(low_cpu_mem_usage={OPENVINO_LOW_CPU_MEM_USAGE})...",
        flush=True,
    )
    wrapped = Qwen3TTSModel.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        device_map=DEVICE,
        dtype=TORCH_DTYPE,
        low_cpu_mem_usage=OPENVINO_LOW_CPU_MEM_USAGE,
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
        "torch_dtype": TORCH_DTYPE_NAME,
        "low_cpu_mem_usage": OPENVINO_LOW_CPU_MEM_USAGE,
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
                    "active_main_compression": (
                        ov_runtime.main_comp if ov_runtime is not None else None
                    ),
                    "active_predictor_compression": (
                        ov_runtime.pred_comp if ov_runtime is not None else None
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
    *,
    reuse_streamed_decode: bool = False,
    **gen_kwargs,
):
    """Run generation while emitting incremental untrimmed PCM chunks.

    The terminal return preserves the existing trimmed batch behavior. Internal
    parity tests may retain the stock decode; transport reuses the final prefix.
    """

    import numpy as np

    if model is None or voice_clone_prompt is None:
        raise RuntimeError("Model not loaded")

    vr = getattr(ov_runtime, "vocoder_runtime", None)
    if vr is None or not vr.enabled:
        raise RuntimeError("streaming parity requires the FP32 OpenVINO vocoder")

    reference_codes = None
    if isinstance(voice_clone_prompt, list) and voice_clone_prompt:
        reference_codes = getattr(voice_clone_prompt[0], "ref_code", None)
    elif isinstance(voice_clone_prompt, dict):
        ref_code_list = voice_clone_prompt.get("ref_code")
        if ref_code_list:
            reference_codes = ref_code_list[0]

    def decode_prefix(codes):
        chunks = list(vr.iter_decode_chunks(codes))
        if not chunks:
            return np.empty(0, dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32, copy=False)

    talker = model.model.talker
    eos_token_id = model.model.config.talker_config.codec_eos_token_id
    session = StreamingVocoderSession(
        talker,
        decode_prefix,
        on_audio_chunk,
        reference_codes=reference_codes,
        eos_token_id=eos_token_id,
    )
    speech_tokenizer = model.model.speech_tokenizer
    original_decode = speech_tokenizer.decode

    def reuse_decode(items):
        if not isinstance(items, list) or len(items) != 1:
            raise RuntimeError("streaming decode currently supports batch size 1")
        item = items[0]
        if not isinstance(item, dict) or not session.matches_codes(item.get("audio_codes")):
            raise RuntimeError("terminal decode codes differ from the captured streaming prefix")
        session.flush()
        return [session.full_waveform], vr.sample_rate

    started = time.monotonic()
    with session:
        if reuse_streamed_decode:
            speech_tokenizer.decode = reuse_decode
        try:
            wavs, sr = model.generate_voice_clone(
                text=text,
                language=language,
                voice_clone_prompt=voice_clone_prompt,
                **gen_kwargs,
            )
        finally:
            if reuse_streamed_decode:
                speech_tokenizer.decode = original_decode

    # Existing batch behavior: still return the complete trimmed wav. The raw
    # waveform is returned only to the internal parity harness so it can compare
    # the side-channel chunks against the stock decode from the same generation.
    wav_raw = np.asarray(wavs[0], dtype=np.float32).ravel()
    return _trim_silence(wav_raw, sr), sr, wav_raw, {
        "elapsed_seconds": time.monotonic() - started,
        "generated_frames": session.generated_frames,
        "reference_frames": session.reference_frames,
        "decode_boundaries": session.decode_boundaries,
    }


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
        wav, sr = _run_generate(text, language)
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


@app.route("/infer_stream", methods=["POST"])
def infer_stream():
    """Stream mono float32 little-endian PCM from the OpenVINO vocoder.

    The response contains no container header. A client must use the advertised
    sample rate/channel/format headers. If generation fails after bytes have
    been emitted, the connection closes and the partial PCM must be discarded
    or handled explicitly by the client.
    """
    if model is None or voice_clone_prompt is None:
        return jsonify({"error": "Model not loaded"}), 503
    vr = getattr(ov_runtime, "vocoder_runtime", None)
    if vr is None or not vr.enabled:
        return jsonify({"error": "Streaming requires the FP32 OpenVINO vocoder"}), 503

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400
    language = (data.get("language") or "English").strip()

    stream_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

    def on_chunk(pcm: Any) -> None:
        import numpy as np

        payload = np.asarray(pcm, dtype="<f4").reshape(-1).tobytes()
        if payload:
            stream_queue.put(("audio", payload))

    def produce() -> None:
        try:
            _run_generate_with_streaming(
                text,
                language,
                on_chunk,
                reuse_streamed_decode=True,
            )
        except BaseException as exc:
            stream_queue.put(("error", exc))
        finally:
            stream_queue.put(("done", None))

    future = executor.submit(produce)

    def body():
        while True:
            kind, payload = stream_queue.get()
            if kind == "audio":
                yield payload
            elif kind == "error":
                raise RuntimeError(f"streaming inference failed: {payload}") from payload
            elif kind == "done":
                future.result()
                return

    return Response(
        body(),
        content_type="application/octet-stream",
        headers={
            "X-Audio-Format": "f32le",
            "X-Audio-Sample-Rate": str(vr.sample_rate),
            "X-Audio-Channels": "1",
            "X-Stream-Error-Semantics": "connection-close",
        },
        direct_passthrough=True,
    )


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
            "max_new_tokens": data.get("max_new_tokens"),
        }
        gen_kwargs = {k: v for k, v in gen_kwargs.items() if v is not None}

        stream_chunks: list[np.ndarray] = []
        chunk_times: list[float] = []
        started = time.monotonic()

        def on_chunk(pcm: Any):
            stream_chunks.append(np.asarray(pcm, dtype=np.float32).ravel())
            chunk_times.append(time.monotonic() - started)

        reuse_streamed_decode = bool(data.get("reuse_streamed_decode", False))
        wav, sr, wav_raw, stream_info = _run_generate_with_streaming(
            text,
            language,
            on_chunk,
            reuse_streamed_decode=reuse_streamed_decode,
            **gen_kwargs,
        )

        # Build audio from the streaming chunks for parity comparison.
        if stream_chunks:
            wav_stream = np.concatenate(stream_chunks, axis=0)
        else:
            wav_stream = wav

        if wav_stream.shape != wav_raw.shape:
            raise RuntimeError(
                f"stream/batch length mismatch: {wav_stream.size} != {wav_raw.size}"
            )
        diff = wav_stream.astype(np.float64) - wav_raw.astype(np.float64)
        signal = float(np.sum(wav_raw.astype(np.float64) ** 2))
        noise = float(np.sum(diff ** 2))
        snr_db = float("inf") if noise == 0.0 else 10.0 * np.log10(signal / noise)

        # Return streaming result as WAV. Parity metrics are response headers so
        # the body remains directly inspectable/listenable by the target harness.
        buf = io.BytesIO()
        sf.write(buf, wav_stream, sr, format="WAV")
        buf.seek(0)
        return buf.read(), "audio/wav", {
            "X-Streaming-Frames": str(wav_stream.size // 1920),
            "X-Streaming-Reference-Frames": str(stream_info["reference_frames"]),
            "X-Streaming-Decode-Boundaries": ",".join(
                str(value) for value in stream_info["decode_boundaries"]
            ),
            "X-Streaming-Chunk-Count": str(len(stream_chunks)),
            "X-Streaming-Reused-Decode": str(reuse_streamed_decode).lower(),
            "X-Streaming-TTFB-Seconds": (
                f"{chunk_times[0]:.6f}" if chunk_times else "none"
            ),
            "X-Streaming-Total-Seconds": f"{stream_info['elapsed_seconds']:.6f}",
            "X-Streaming-Max-Abs": f"{float(np.max(np.abs(diff), initial=0.0)):.9g}",
            "X-Streaming-SNR-Db": "inf" if np.isinf(snr_db) else f"{snr_db:.6f}",
        }

    try:
        audio_bytes, media_type, parity_headers = executor.submit(do_work).result(timeout=300)
    except Exception as e:
        return jsonify({"error": f"Inference error: {str(e)}"}), 500

    return Response(audio_bytes, content_type=media_type, headers=parity_headers)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8319)

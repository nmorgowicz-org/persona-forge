import gc
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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


def _run_generate(text: str, language: str):
    if model is None or voice_clone_prompt is None:
        raise RuntimeError("Model not loaded")
    import traceback as _tb
    try:
        wavs, sr = model.generate_voice_clone(
            text=text,
            language=language,
            voice_clone_prompt=voice_clone_prompt,
        )
    except Exception:
        _tb.print_exc()
        raise
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8319)

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
        ov_runtime = OVTalkerRuntime(OV_MODEL_DIR, talker, ov_config=ov_config)
        ov_runtime.install()
        print(
            f"[app_worker] OpenVINO talker runtime installed "
            f"(compression={ov_runtime.compression}); cores run on OpenVINO.",
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
                }
            }
        )

    return jsonify(base)


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
    return wavs[0], sr


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

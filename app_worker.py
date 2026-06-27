import gc
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor

os.environ["ORT_INTRA_OP_NUM_THREADS"] = "6"
os.environ["ORT_INTER_OP_NUM_THREADS"] = "2"
os.environ["OMP_NUM_THREADS"] = "6"
os.environ["MKL_NUM_THREADS"] = "6"
os.environ["OPENBLAS_NUM_THREADS"] = "6"

import soundfile as sf
import torch
import torch.nn as nn

from flask import Flask, Response, jsonify, request
from qwen_tts import Qwen3TTSModel

app = Flask(__name__)

MODEL_ID = os.getenv("MODEL_REPO", "Qwen/Qwen3-TTS-12Hz-1.7B-Base")
DEVICE = os.getenv("DEVICE", "cpu")
REF_AUDIO = os.getenv("REF_AUDIO", "/voice/voice_A.wav")
REF_TEXT = os.getenv(
    "REF_TEXT",
    "Welcome to Rosies. What can I get for you today? You know, Im a good girl. "
    "You want me, dont you? I am on the menu too.",
)

torch.set_num_threads(6)

model = None
voice_clone_prompt = None

executor = ThreadPoolExecutor(max_workers=1)


def load_model():
    global model, voice_clone_prompt

    print("[app_worker] Loading model at float32...")
    wrapped = Qwen3TTSModel.from_pretrained(
        MODEL_ID,
        device_map=DEVICE,
        dtype=torch.float32,
    )

    gc.collect()
    print("[app_worker] Model loaded. Creating voice clone prompt...")

    model = wrapped
    voice_clone_prompt = model.create_voice_clone_prompt(
        ref_audio=REF_AUDIO,
        ref_text=REF_TEXT,
        x_vector_only_mode=False,
    )
    print("[app_worker] Model loaded and ready.")


load_model()


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "model": MODEL_ID,
            "device": DEVICE,
            "ref_audio": REF_AUDIO,
            "timestamp": time.time(),
        }
    )


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

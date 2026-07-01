"""Single-process HTTP service for Qwen3-TTS."""

from __future__ import annotations

import io
import queue
import time
from typing import Any

import soundfile as sf
from flask import Flask, Response, jsonify, request

from qwen3_tts import model

app = Flask(__name__)


def _openai_error(message: str, status: int, err_type: str = "invalid_request_error"):
    return jsonify({"error": {"message": message, "type": err_type, "code": None}}), status


# Encodings we can actually produce. Anything else is rejected with 400 rather than
# silently returned as mislabeled WAV. (opus/aac/flac are future work — see docs/plans.)
_SUPPORTED_FORMATS = {"mp3": ("MP3", "audio/mpeg"), "wav": ("WAV", "audio/wav")}


def _canonical_format(response_format: str | None) -> str:
    return (response_format or "mp3").strip().lower()


def _encode(wav: Any, sr: int, response_format: str) -> tuple[bytes, str]:
    fmt = _canonical_format(response_format)
    try:
        sf_format, media_type = _SUPPORTED_FORMATS[fmt]
    except KeyError as exc:
        raise ValueError(
            f"unsupported response_format {fmt!r}; supported: "
            f"{', '.join(sorted(_SUPPORTED_FORMATS))}"
        ) from exc
    output = io.BytesIO()
    sf.write(output, wav, sr, format=sf_format)
    return output.getvalue(), media_type


def _ready():
    return model.model is not None and model.voice_clone_prompt is not None


def _json_body():
    return request.get_json(force=True, silent=True)


def _generation_fields(data: dict[str, Any]) -> tuple[str, str]:
    return (data.get("text") or "").strip(), (data.get("language") or "English").strip()


@app.get("/health")
def health():
    return jsonify(model.health_state())


@app.post("/generate")
def generate():
    if not _ready():
        return jsonify({"error": "Model not loaded"}), 503
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    text, language = _generation_fields(data)
    if not text:
        return jsonify({"error": "text is required"}), 400
    fmt = _canonical_format(data.get("response_format"))
    if fmt not in _SUPPORTED_FORMATS:
        return jsonify({"error": f"unsupported response_format {fmt!r}; supported: "
                        f"{', '.join(sorted(_SUPPORTED_FORMATS))}"}), 400
    try:
        wav, sr = model.executor.submit(model._run_generate, text, language).result(timeout=300)
        audio, media_type = _encode(wav, sr, fmt)
    except Exception as exc:
        return jsonify({"error": f"Inference error: {exc}"}), 500
    return Response(audio, content_type=media_type)


@app.post("/v1/audio/speech")
def openai_audio_speech():
    if not _ready():
        return _openai_error("Model not loaded", 503, "api_error")
    data = _json_body()
    if not data:
        return _openai_error("Invalid JSON", 400)
    text = (data.get("input") or data.get("text") or "").strip()
    if not text:
        return _openai_error("'input' is required", 400)
    fmt = _canonical_format(data.get("response_format"))
    if fmt not in _SUPPORTED_FORMATS:
        return _openai_error(
            f"unsupported response_format {fmt!r}; supported: "
            f"{', '.join(sorted(_SUPPORTED_FORMATS))}",
            400,
        )
    language = (data.get("language") or "English").strip()
    try:
        wav, sr = model.executor.submit(model._run_generate, text, language).result(timeout=300)
        audio, media_type = _encode(wav, sr, fmt)
    except Exception as exc:
        return _openai_error(f"Inference error: {exc}", 500, "api_error")
    return Response(audio, content_type=media_type)


@app.post("/generate/stream")
def generate_stream():
    if not _ready():
        return jsonify({"error": "Model not loaded"}), 503
    vocoder = getattr(model.ov_runtime, "vocoder_runtime", None)
    if vocoder is None or not vocoder.enabled:
        return jsonify({"error": "Streaming requires the FP32 OpenVINO vocoder"}), 503
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    text, language = _generation_fields(data)
    if not text:
        return jsonify({"error": "text is required"}), 400

    events: queue.Queue[tuple[str, Any]] = queue.Queue()

    def on_chunk(pcm: Any) -> None:
        import numpy as np

        payload = np.asarray(pcm, dtype="<f4").reshape(-1).tobytes()
        if payload:
            events.put(("audio", payload))

    def produce() -> None:
        try:
            model._run_generate_with_streaming(
                text, language, on_chunk, reuse_streamed_decode=True
            )
        except BaseException as exc:
            events.put(("error", exc))
        finally:
            events.put(("done", None))

    future = model.executor.submit(produce)

    def body():
        while True:
            kind, payload = events.get()
            if kind == "audio":
                yield payload
            elif kind == "error":
                raise RuntimeError(f"streaming inference failed: {payload}") from payload
            else:
                future.result()
                return

    return Response(
        body(),
        content_type="application/octet-stream",
        headers={
            "X-Audio-Format": "f32le",
            "X-Audio-Sample-Rate": str(vocoder.sample_rate),
            "X-Audio-Channels": "1",
            "X-Stream-Error-Semantics": "connection-close",
        },
        direct_passthrough=True,
    )


def _parity_kwargs(data: dict[str, Any]) -> dict[str, Any]:
    keys = ("do_sample", "temperature", "top_p", "top_k", "max_new_tokens")
    return {key: data[key] for key in keys if data.get(key) is not None}


@app.post("/stream_internal")
def stream_internal():
    """Dev-only endpoint returning the concatenated incremental decode as WAV."""
    if not _ready():
        return jsonify({"error": "Model not loaded"}), 503
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    text, language = _generation_fields(data)
    if not text:
        return jsonify({"error": "text is required"}), 400

    def work():
        import numpy as np

        chunks: list[Any] = []
        chunk_times: list[float] = []
        started = time.monotonic()

        def on_chunk(pcm: Any):
            chunks.append(np.asarray(pcm, dtype=np.float32).ravel())
            chunk_times.append(time.monotonic() - started)

        reuse = bool(data.get("reuse_streamed_decode", False))
        wav, sr, raw, info = model._run_generate_with_streaming(
            text,
            language,
            on_chunk,
            reuse_streamed_decode=reuse,
            seed_value=data.get("seed"),
            **_parity_kwargs(data),
        )
        streamed = np.concatenate(chunks) if chunks else wav
        if streamed.shape != raw.shape:
            raise RuntimeError(f"stream/batch length mismatch: {streamed.size} != {raw.size}")
        diff = streamed.astype(np.float64) - raw.astype(np.float64)
        signal, noise = float(np.sum(raw.astype(np.float64) ** 2)), float(np.sum(diff ** 2))
        snr = float("inf") if noise == 0.0 else 10.0 * np.log10(signal / noise)
        audio, media_type = _encode(streamed, sr, "wav")
        headers = {
            "X-Streaming-Frames": str(streamed.size // 1920),
            "X-Streaming-Reference-Frames": str(info["reference_frames"]),
            "X-Streaming-Decode-Boundaries": ",".join(map(str, info["decode_boundaries"])),
            "X-Streaming-Chunk-Count": str(len(chunks)),
            "X-Streaming-Reused-Decode": str(reuse).lower(),
            "X-Streaming-TTFB-Seconds": f"{chunk_times[0]:.6f}" if chunk_times else "none",
            "X-Streaming-Total-Seconds": f"{info['elapsed_seconds']:.6f}",
            "X-Streaming-Max-Abs": f"{float(np.max(np.abs(diff), initial=0.0)):.9g}",
            "X-Streaming-SNR-Db": "inf" if np.isinf(snr) else f"{snr:.6f}",
        }
        return audio, media_type, headers

    try:
        audio, media_type, headers = model.executor.submit(work).result(timeout=300)
    except Exception as exc:
        return jsonify({"error": f"Inference error: {exc}"}), 500
    return Response(audio, content_type=media_type, headers=headers)


@app.post("/batch_internal")
def batch_internal():
    """Dev-only endpoint returning stock batch decode as WAV."""
    if not _ready():
        return jsonify({"error": "Model not loaded"}), 503
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    text, language = _generation_fields(data)
    if not text:
        return jsonify({"error": "text is required"}), 400

    def work():
        model._apply_optional_seed(data.get("seed"))
        started = time.monotonic()
        wavs, sr = model.model.generate_voice_clone(
            text=text,
            language=language,
            voice_clone_prompt=model.voice_clone_prompt,
            **_parity_kwargs(data),
        )
        elapsed = time.monotonic() - started
        audio, media_type = _encode(wavs[0], sr, "wav")
        return audio, media_type, {
            "X-Batch-Frames": str(len(wavs[0]) // 1920),
            "X-Batch-Elapsed-Seconds": f"{elapsed:.6f}",
            "X-Batch-Seed": str(data.get("seed")),
        }

    try:
        audio, media_type, headers = model.executor.submit(work).result(timeout=300)
    except Exception as exc:
        return jsonify({"error": f"Inference error: {exc}"}), 500
    return Response(audio, content_type=media_type, headers=headers)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8318)

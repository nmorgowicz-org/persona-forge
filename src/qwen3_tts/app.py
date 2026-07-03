"""Single-process HTTP service for Qwen3-TTS."""

from __future__ import annotations

import base64
import io
import os
import queue
import time
import uuid
from pathlib import Path
from typing import Any

import soundfile as sf
from flask import Flask, Response, jsonify, request, send_from_directory

from qwen3_tts import model, omnivoice_engine, voice_design, voice_library

# candidate_id -> (wav, sample_rate). In-memory only, single-user local tool (locked decision,
# PLAN_persona_forge_studio.md §5): cleared at the start of every /omnivoice/audition call, so
# a candidate is only ever addressable up until the next audition job is kicked off.
_omnivoice_candidates: dict[str, tuple[Any, int]] = {}

app = Flask(__name__)

# Static frontend export (frontend/, built by `npm run build`; see docs/plans/PLAN_voice_design.md
# §8.1). The Dockerfile copies the build output to /app/frontend/dist; app.py lives at
# /app/src/qwen3_tts/app.py, so parent.parent.parent is /app in the container by construction.
# Auto-disables (falls back to a bare API service) if the dist directory isn't present, e.g. a
# local `python -m qwen3_tts.app` run without ever building the frontend.
_FRONTEND_DIR = Path(
    os.getenv("FRONTEND_DIST_DIR", str(Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"))
)
_frontend_enabled = os.getenv("FRONTEND_ENABLED", "1").strip().lower() not in (
    "0",
    "false",
) and _FRONTEND_DIR.is_dir()

if _frontend_enabled:

    @app.get("/")
    def frontend_index():
        return send_from_directory(_FRONTEND_DIR, "index.html")

    @app.get("/assets/<path:filename>")
    def frontend_assets(filename: str):
        return send_from_directory(_FRONTEND_DIR / "assets", filename)

    @app.get("/favicon.svg")
    def frontend_favicon():
        return send_from_directory(_FRONTEND_DIR, "favicon.svg")


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
    # True once the service has successfully loaded at least once.
    # With IDLE_UNLOAD_SECONDS set, model may be None temporarily — requests reload it.
    # During a VoiceDesign/OmniVoice swap or a runtime-config reload, Base is briefly
    # unloaded so treat all three as not-ready too (503).
    return (
        model._service_started
        and not voice_design.swap_in_progress()
        and not omnivoice_engine.swap_in_progress()
        and not model.reconfig_in_progress()
    )


def _generation_ready():
    # Like _ready(), but deliberately does NOT treat an in-flight VoiceDesign swap as
    # not-ready: /generate and /v1/audio/speech both submit through model.executor, the
    # same single-worker queue voice_design.run_voice_design_request runs on, so a
    # generation request submitted mid-swap just queues behind it (FIFO) and runs once
    # Base is reloaded, instead of failing fast with 503. A runtime-config reload is a
    # separate, much shorter operation and is still treated as not-ready.
    return model._service_started and not model.reconfig_in_progress()


def _json_body():
    return request.get_json(force=True, silent=True)


def _generation_fields(data: dict[str, Any]) -> tuple[str, str]:
    return (data.get("text") or "").strip(), (data.get("language") or "English").strip()


@app.get("/health")
def health():
    state = model.health_state()
    # Swap-in-progress is tracked in voice_design.py, not model.py, to avoid a circular
    # import; merged here so the frontend can poll one endpoint for a prominent
    # swap-in-progress banner (PLAN_voice_design.md §3, §11 frontend checklist).
    state["swap_in_progress"] = voice_design.swap_in_progress() or omnivoice_engine.swap_in_progress()
    state["reconfig_in_progress"] = model.reconfig_in_progress()
    # model_loaded only reflects Base/VoiceDesign (model.model) — OmniVoice bypasses that
    # slot entirely (see omnivoice_engine.py docstring), so surface its residency too.
    state["omnivoice_loaded"] = omnivoice_engine.omnivoice_loaded()
    return jsonify(state)


@app.post("/voice_design")
def voice_design_create():
    # Checked separately from the generic _ready() 503 below: while a swap is already in
    # flight this *is* the expected state (another /voice_design call is mid-swap), not an
    # unloaded-model error, so it gets its own message.
    if voice_design.swap_in_progress():
        return jsonify({"error": "VoiceDesign swap already in progress"}), 503
    if not model._service_started:
        return jsonify({"error": "Model not loaded"}), 503
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    description = (data.get("description") or "").strip()
    sample_text = (data.get("sample_text") or "").strip()
    language = (data.get("language") or "English").strip()
    seed = data.get("seed")
    selections = data.get("selections")
    if not description:
        return jsonify({"error": "description is required"}), 400
    if not sample_text:
        return jsonify({"error": "sample_text is required"}), 400
    if seed is not None and not isinstance(seed, int):
        return jsonify({"error": "seed must be an integer"}), 400
    try:
        voice_design.validate_sample_text(sample_text)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        wav, sr, resolved_seed = model.executor.submit(
            voice_design.run_voice_design_request, description, sample_text, language, seed
        ).result(timeout=300)
        wav_bytes, _ = _encode(wav, sr, "wav")
        meta = voice_library.save_voice(
            wav_bytes,
            description=description,
            sample_text=sample_text,
            language=language,
            seed=resolved_seed,
            selections=selections,
        )
    except Exception as exc:
        return jsonify({"error": f"VoiceDesign error: {exc}"}), 500
    return jsonify(
        {
            "voice_id": meta["voice_id"],
            "sample_rate": sr,
            "seed": resolved_seed,
            "audio_base64": base64.b64encode(wav_bytes).decode("ascii"),
        }
    )


@app.get("/voices")
def voices_list():
    return jsonify({"voices": voice_library.list_voices()})


@app.get("/voices/<voice_id>")
def voices_get(voice_id: str):
    meta = voice_library.get_voice(voice_id)
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404
    wav_bytes = voice_library.get_voice_wav_bytes(voice_id)
    response = dict(meta)
    if wav_bytes is not None:
        response["audio_base64"] = base64.b64encode(wav_bytes).decode("ascii")
    response.pop("wav_path", None)
    return jsonify(response)


@app.delete("/voices/<voice_id>")
def voices_delete(voice_id: str):
    deleted = voice_library.delete_voice(voice_id)
    if not deleted:
        return jsonify({"error": "voice_id not found"}), 404
    return jsonify({"deleted": voice_id})


@app.post("/omnivoice/audition")
def omnivoice_audition():
    # Same "in-flight swap is expected, not an error" framing as /voice_design above.
    if voice_design.swap_in_progress() or omnivoice_engine.swap_in_progress():
        return jsonify({"error": "Another swap already in progress"}), 503
    if not model._service_started:
        return jsonify({"error": "Model not loaded"}), 503
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    segments = data.get("segments")
    if (
        not isinstance(segments, list)
        or not segments
        or not all(isinstance(s, str) and s.strip() for s in segments)
    ):
        return jsonify({"error": "segments must be a non-empty list of non-empty strings"}), 400
    instruct = (data.get("instruct") or "").strip()
    if not instruct:
        return jsonify({"error": "instruct is required"}), 400
    language = (data.get("language") or "english").strip()
    candidates_per_segment = data.get("candidates_per_segment", 3)
    if not isinstance(candidates_per_segment, int) or candidates_per_segment < 1:
        return jsonify({"error": "candidates_per_segment must be a positive integer"}), 400
    seed = data.get("seed")
    if seed is not None and not isinstance(seed, int):
        return jsonify({"error": "seed must be an integer"}), 400

    try:
        results = model.executor.submit(
            omnivoice_engine.run_omnivoice_job,
            segments,
            instruct,
            language,
            candidates_per_segment,
            seed,
        ).result(timeout=1800)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"OmniVoice error: {exc}"}), 500

    # Cleared here rather than TTL-expired (locked decision, PLAN_persona_forge_studio.md §5):
    # single-user local tool, no concurrent-job requirement, so "candidates from the previous
    # audition call" is a simple and sufficient invalidation rule.
    _omnivoice_candidates.clear()
    response_segments = []
    for seg_candidates in results:
        cand_payload = []
        for wav, sr in seg_candidates:
            candidate_id = uuid.uuid4().hex
            wav_bytes, _ = _encode(wav, sr, "wav")
            _omnivoice_candidates[candidate_id] = (wav, sr)
            cand_payload.append(
                {
                    "candidate_id": candidate_id,
                    "sample_rate": sr,
                    "audio_base64": base64.b64encode(wav_bytes).decode("ascii"),
                }
            )
        response_segments.append({"candidates": cand_payload})
    return jsonify({"segments": response_segments})


def _resolve_omnivoice_selections(selections: Any) -> list[tuple[Any, int]] | None:
    """Look up each candidate_id in the audition cache; returns None on the first miss."""
    if (
        not isinstance(selections, list)
        or not selections
        or not all(isinstance(c, str) for c in selections)
    ):
        return None
    selected = []
    for candidate_id in selections:
        entry = _omnivoice_candidates.get(candidate_id)
        if entry is None:
            return None
        selected.append(entry)
    return selected


@app.post("/omnivoice/stitch")
def omnivoice_stitch():
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    selections = data.get("selections")
    selected = _resolve_omnivoice_selections(selections)
    if selected is None:
        return jsonify({"error": "selections must be a list of known, non-expired candidate_ids"}), 400

    try:
        wav, sr = omnivoice_engine.stitch_selected(selected)
        wav_bytes, media_type = _encode(wav, sr, "wav")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Stitch error: {exc}"}), 500
    return Response(wav_bytes, content_type=media_type)


@app.post("/omnivoice/save")
def omnivoice_save():
    # Persists a stitched OmniVoice clip into the same voice library /voice_design writes to
    # (voice_library.save_voice), so a clip auditioned here is reusable everywhere voices are
    # (Speak page, /generate, /v1/audio/speech) instead of only existing as an ephemeral
    # in-browser preview blob.
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    selections = data.get("selections")
    selected = _resolve_omnivoice_selections(selections)
    if selected is None:
        return jsonify({"error": "selections must be a list of known, non-expired candidate_ids"}), 400
    instruct = (data.get("instruct") or "").strip()
    if not instruct:
        return jsonify({"error": "instruct is required"}), 400
    segments = data.get("segments")
    if (
        not isinstance(segments, list)
        or not segments
        or not all(isinstance(s, str) and s.strip() for s in segments)
    ):
        return jsonify({"error": "segments must be a non-empty list of non-empty strings"}), 400
    language = (data.get("language") or "english").strip()
    accent_id = data.get("accent_id")

    try:
        wav, sr = omnivoice_engine.stitch_selected(selected)
        wav_bytes, _ = _encode(wav, sr, "wav")
        meta = voice_library.save_voice(
            wav_bytes,
            description=instruct,
            sample_text=" ".join(segments),
            language=language,
            selections={
                "engine": "omnivoice",
                "accent_id": accent_id,
                "instruct": instruct,
                "segments": segments,
                "candidate_ids": selections,
            },
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"OmniVoice save error: {exc}"}), 500
    return jsonify(
        {
            "voice_id": meta["voice_id"],
            "sample_rate": sr,
            "audio_base64": base64.b64encode(wav_bytes).decode("ascii"),
        }
    )


@app.get("/runtime/config")
def runtime_config_get():
    return jsonify(model.runtime_config_state())


@app.post("/runtime/config")
def runtime_config_post():
    # No auth gate on this mutating route — deliberate decision (PLAN_voice_design.md §8.8
    # security note): the whole service already runs unauthenticated on a trusted-network-only
    # posture (SECURITY.md), and this stays consistent with that rather than special-casing
    # one route.
    if model.reconfig_in_progress() or voice_design.swap_in_progress():
        return jsonify({"error": "Another runtime reconfiguration or swap is already in progress"}), 503
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    try:
        state = model.executor.submit(model.apply_runtime_config, data).result(timeout=300)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Runtime config error: {exc}"}), 500
    return jsonify(state)


@app.post("/generate")
def generate():
    if not _generation_ready():
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
    voice_id = (data.get("voice_id") or "").strip() or None
    instruct = (data.get("instruct") or "").strip() or None
    seed = data.get("seed")
    if seed is not None and not isinstance(seed, int):
        return jsonify({"error": "seed must be an integer"}), 400
    resolved_seed = model.resolve_seed(seed)
    try:
        # Longer than the other routes' 300s: this can now queue behind an in-flight
        # VoiceDesign swap (unload + load + generate + unload + reload, observed ~90-120s,
        # longer on a cold OpenVINO kernel cache) before its own generation even starts.
        wav, sr = model.executor.submit(
            model._run_generate,
            text,
            language,
            voice_id=voice_id,
            seed_value=resolved_seed,
            instruct=instruct,
        ).result(timeout=480)
        audio, media_type = _encode(wav, sr, fmt)
    except Exception as exc:
        return jsonify({"error": f"Inference error: {exc}"}), 500
    response = Response(audio, content_type=media_type)
    response.headers["X-Seed"] = str(resolved_seed)
    return response


@app.post("/v1/audio/speech")
def openai_audio_speech():
    if not _generation_ready():
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
    voice_id = (data.get("voice_id") or "").strip() or None
    instruct = (data.get("instruct") or "").strip() or None
    seed = data.get("seed")
    if seed is not None and not isinstance(seed, int):
        return _openai_error("seed must be an integer", 400)
    resolved_seed = model.resolve_seed(seed)
    try:
        # See /generate's matching comment: this can queue behind an in-flight VoiceDesign
        # swap, so it gets the same longer timeout.
        wav, sr = model.executor.submit(
            model._run_generate,
            text,
            language,
            voice_id=voice_id,
            seed_value=resolved_seed,
            instruct=instruct,
        ).result(timeout=480)
        audio, media_type = _encode(wav, sr, fmt)
    except Exception as exc:
        return _openai_error(f"Inference error: {exc}", 500, "api_error")
    response = Response(audio, content_type=media_type)
    response.headers["X-Seed"] = str(resolved_seed)
    return response


@app.post("/generate/stream")
def generate_stream():
    if not _ready():
        return jsonify({"error": "Model not loaded"}), 503
    # Fast-fail only when model is loaded — if it's idle-unloaded, the executor will reload
    # and _run_generate_with_streaming will raise RuntimeError if vocoder isn't available.
    if model.model is not None:
        vocoder = getattr(model.ov_runtime, "vocoder_runtime", None)
        if vocoder is None or not vocoder.enabled:
            return jsonify({"error": "Streaming requires the FP32 OpenVINO vocoder"}), 503
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    text, language = _generation_fields(data)
    if not text:
        return jsonify({"error": "text is required"}), 400
    voice_id = (data.get("voice_id") or "").strip() or None

    events: queue.Queue[tuple[str, Any]] = queue.Queue()

    def on_chunk(pcm: Any) -> None:
        import numpy as np

        payload = np.asarray(pcm, dtype="<f4").reshape(-1).tobytes()
        if payload:
            events.put(("audio", payload))

    def produce() -> None:
        try:
            model._run_generate_with_streaming(
                text,
                language,
                on_chunk,
                reuse_streamed_decode=True,
                voice_id=voice_id,
                seed_value=data.get("seed"),
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

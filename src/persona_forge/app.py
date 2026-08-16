"""Single-process HTTP service for Qwen3-TTS."""

from __future__ import annotations

import base64
import io
import json
import os
import queue
import sys
import time
import threading
import uuid
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


import soundfile as sf
from flask import Flask, Response, jsonify, request, send_from_directory, send_file

from persona_forge import (
    audio_diagnostics,
    audio_style,
    model,
    omnivoice_engine,
    project_library,
    prosody_repair,
    segment_library,
    voice_design,
    voice_library,
)
from persona_forge.asr_check import validate_reference_text
from persona_forge.alignment_jobs import AlignmentJobManager

# candidate_id -> (wav, sample_rate). In-memory only, single-user local tool (locked decision,
# docs/dev/features/persona_forge_studio.md §5): cleared at the start of every /omnivoice/audition call, so
# a candidate is only ever addressable up until the next audition job is kicked off.
_omnivoice_candidates: dict[str, tuple[Any, int]] = {}

# preview_id -> dict of metadata for a VoiceDesign preview that has NOT yet been saved to the
# library. Single-user, ephemeral: overwritten on each new /voice_design call so only the latest
# preview is addressable (consistent with the Omnivoice candidates pattern).
_voice_design_previews: dict[str, dict[str, Any]] = {}

# Streaming audition jobs: job_id -> dict.
# Fields:
#   - status: "queued" | "running" | "completed" | "failed"
#   - total_segments
#   - segments_completed: list of {segment_index, text, candidates}
#   - current_segment_index: 0-based or null
#   - message: info/error text
#   - created_at: time.time()
# Eviction runs lazily on each /audition or /audition/progress call.
_OV_AUDITION_JOBS: dict[str, dict[str, Any]] = {}
_OV_AUDITION_JOBS_LOCK = threading.Lock()
_OV_AUDITION_MAX_JOBS = 50
_OV_AUDITION_TTL_SECONDS = 600  # 10 minutes

# Queue + lock to serialize job dispatch when model is not yet loaded.
_OV_AUDITION_QUEUE: list[str] = []
_OV_AUDITION_QUEUE_LOCK = threading.Lock()
_OV_AUDITION_DISPATCH_IN_PROGRESS = False


def _evict_old_audition_jobs() -> None:
    now = time.time()
    with _OV_AUDITION_JOBS_LOCK:
        if len(_OV_AUDITION_JOBS) <= _OV_AUDITION_MAX_JOBS:
            return
        # CPU-bound OmniVoice jobs can legitimately run 20-30+ min, well past the TTL —
        # never evict a still-running/queued job out from under a resume-after-refresh.
        to_remove = []
        for jid, job in _OV_AUDITION_JOBS.items():
            if job.get("status") in ("running", "queued"):
                continue
            if now - job.get("created_at", now) >= _OV_AUDITION_TTL_SECONDS:
                to_remove.append(jid)
        for jid in to_remove:
            _OV_AUDITION_JOBS.pop(jid, None)
        if len(_OV_AUDITION_JOBS) > _OV_AUDITION_MAX_JOBS:
            evictable_ids = sorted(
                (jid for jid, job in _OV_AUDITION_JOBS.items() if job.get("status") not in ("running", "queued")),
                key=lambda k: _OV_AUDITION_JOBS[k].get("created_at", 0),
            )
            excess = len(_OV_AUDITION_JOBS) - _OV_AUDITION_MAX_JOBS
            for jid in evictable_ids[:excess]:
                _OV_AUDITION_JOBS.pop(jid, None)

app = Flask(__name__)

_shutdown_hook = None


@app.route("/_shutdown", methods=["GET"])
def _test_shutdown():
    """Test-only hook used by fake_model_server to shut down a test instance."""
    if _shutdown_hook is not None:
        _shutdown_hook()
    return "ok"


# Static frontend export (frontend/, built by `npm run build`; see docs/dev/architecture/voice_design.md
# §8.1). The Dockerfile copies the build output to /app/frontend/dist; app.py lives at
# /app/src/persona_forge/app.py, so parent.parent.parent is /app in the container by construction.
# Auto-disables (falls back to a bare API service) if the dist directory isn't present, e.g. a
# local `python -m persona_forge.app` run without ever building the frontend.
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
# silently returned as mislabeled WAV. (opus/aac are future work — see docs/plans.)
# pcm = raw int16 LE mono at 24kHz (Hermes streaming expectation).
_SUPPORTED_FORMATS = {
    "mp3": ("MP3", "audio/mpeg"),
    "wav": ("WAV", "audio/wav"),
    "pcm": ("RAW", "audio/pcm"),
}


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

    if fmt == "pcm":
        # Hermes expects int16 LE mono PCM at 24kHz.
        import numpy as np
        # Normalize float32 [-1,1] to int16 range
        if wav.dtype != np.int16:
            wav = np.clip(wav, -1.0, 1.0)
            wav = (wav * 32767).astype(np.int16)
        return wav.tobytes(), media_type

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


def _generation_repair_requested(data: dict[str, Any]) -> tuple[bool, str | None]:
    value = data.get("prosody_repair", False)
    if not isinstance(value, bool):
        return False, "prosody_repair must be a boolean"
    return value, None


def _add_generation_repair_headers(response: Response, progress: dict[str, Any]) -> None:
    metadata = progress.get("prosody_repair")
    if not isinstance(metadata, dict):
        return
    outcome = metadata.get("outcome")
    if outcome:
        response.headers["X-Prosody-Repair-Outcome"] = str(outcome)
    for key, header in (
        ("duration_seconds", "X-Prosody-Repair-Duration-Seconds"),
        ("budget_seconds", "X-Prosody-Repair-Budget-Seconds"),
        ("boundary_count", "X-Prosody-Repair-Boundaries"),
    ):
        if metadata.get(key) is not None:
            response.headers[header] = str(metadata[key])


@app.get("/health")
def health():
    # Always 200: lets the container be considered "up" while the model loads in the background.
    state = model.health_state()
    # Swap-in-progress is tracked in voice_design.py, not model.py, to avoid a circular
    # import; merged here so the frontend can poll one endpoint for a prominent
    # swap-in-progress banner (docs/dev/architecture/voice_design.md §3, §11 frontend checklist).
    state["swap_in_progress"] = voice_design.swap_in_progress() or omnivoice_engine.swap_in_progress()
    state["reconfig_in_progress"] = model.reconfig_in_progress()
    # model_loaded only reflects Base/VoiceDesign (model.model) — OmniVoice bypasses that
    # slot entirely (see omnivoice_engine.py docstring), so surface its residency too.
    state["omnivoice_loaded"] = omnivoice_engine.omnivoice_loaded()
    state["alignment_performance"] = _alignment_jobs.performance()

    # Human-readable hint when model is still loading at startup.
    if not model._service_started:
        state["loading_message"] = "Loading model…"

    return jsonify(state)


@app.post("/health/validate-ref-text")
def health_validate_ref_text():
    if not model._service_started:
        return jsonify({"error": "Model not loaded"}), 503
    from persona_forge.config import REF_AUDIO_PATH
    ref_audio = (os.getenv("REF_AUDIO") or REF_AUDIO_PATH or "").strip() or None
    ref_text = (os.getenv("REF_TEXT") or "").strip() or None
    if not ref_audio or not ref_text:
        return jsonify({"error": "REF_AUDIO or REF_TEXT not configured"}), 400

    def _run():
        return validate_reference_text(ref_audio, ref_text)

    try:
        result = model.executor.submit(_run).result(timeout=15)
    except Exception as exc:
        return jsonify({"error": f"Validation failed: {exc}"}), 500

    sev = result["severity"]
    if sev in ("fail", "no_speech"):
        print(
            f"[REF-TEXT-VALID] STATUS=fail  score={result.get('match_score')}",
            flush=True,
            file=sys.stderr,
        )
        print(f"  REF_AUDIO: {ref_audio}", flush=True, file=sys.stderr)
        print(f"  REF_TEXT:  {ref_text!r}", flush=True, file=sys.stderr)
        print(f"  Whisper:   {result.get('whisper_transcript')!r}", flush=True, file=sys.stderr)
        print(f"  SUGGESTION: {result.get('suggestion')}", flush=True, file=sys.stderr)
    elif sev == "warn":
        print(
            f"[REF-TEXT-VALID] STATUS=warn  score={result.get('match_score')}",
            flush=True,
            file=sys.stderr,
        )
        print(f"  REF_AUDIO: {ref_audio}", flush=True, file=sys.stderr)
        print(f"  REF_TEXT:  {ref_text!r}", flush=True, file=sys.stderr)
        print(f"  Whisper:   {result.get('whisper_transcript')!r}", flush=True, file=sys.stderr)
        print(f"  SUGGESTION: {result.get('suggestion')}", flush=True, file=sys.stderr)
    else:
        print(
            f"[REF-TEXT-VALID] STATUS=ok  score={result.get('match_score')}",
            flush=True,
        )
    return jsonify(result)


@app.post("/voice_design")
def voice_design_create():
    # Checked separately from the generic _ready() 503 below: while a swap is already in
    # flight this *is* the expected state (another /voice_design call is mid-swap), not an
    # unloaded-model error, so it gets its own message.
    if voice_design.swap_in_progress():
        return jsonify({"error": "VoiceDesign swap already in progress"}), 503
    if not model._service_started:
        return jsonify({"error": "Model not loaded"}), 503
    # Qwen VoiceDesign only exists on the Qwen3-TTS backends — under pocket_tts the loaded
    # TTSModel has no generate_voice_design, so reject up front (501) instead of swapping
    # the model and failing mid-request. The UI routes voice design through OmniVoice there.
    if getattr(model, "TTS_BACKEND", None) == "pocket_tts":
        return (
            jsonify(
                {
                    "error": (
                        "Qwen VoiceDesign is not available under TTS_BACKEND=pocket_tts; "
                        "use the OmniVoice engine or TTS_BACKEND=pytorch/openvino."
                    )
                }
            ),
            501,
        )
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
        # Generate an ephemeral preview_id — does NOT save to the voice library yet.
        preview_id = uuid.uuid4().hex
        _voice_design_previews[preview_id] = {
            "wav_bytes": wav_bytes,
            "sample_rate": sr,
            "seed": resolved_seed,
            "description": description,
            "sample_text": sample_text,
            "language": language,
            "selections": selections,
        }
    except Exception as exc:
        return jsonify({"error": f"VoiceDesign error: {exc}"}), 500
    return jsonify(
        {
            "preview_id": preview_id,
            "sample_rate": sr,
            "seed": resolved_seed,
            "audio_base64": base64.b64encode(wav_bytes).decode("ascii"),
        }
    )


@app.post("/voice_design/preview/<preview_id>/save")
def voice_design_save(preview_id: str):
    """Persist a VoiceDesign preview into the voice library (explicit user approval step)."""
    if not model._service_started:
        return jsonify({"error": "Model not loaded"}), 503
    data = _json_body() or {}
    entry = _voice_design_previews.pop(preview_id, None)
    if entry is None:
        return jsonify({"error": "Unknown or expired preview_id"}), 400
    try:
        meta = voice_library.save_voice(
            entry["wav_bytes"],
            description=entry["description"],
            sample_text=entry["sample_text"],
            language=entry["language"],
            seed=entry["seed"],
            selections=entry["selections"],
            family_id=data.get("family_id"),
            variant_name=data.get("variant_name"),
            variant_kind=data.get("variant_kind"),
            source="VoiceDesign",
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"VoiceDesign save error: {exc}"}), 500
    return jsonify(
        {
            "voice_id": meta["voice_id"],
        }
    )


@app.get("/voice_design/progress")
def voice_design_progress():
    # Mirrors GET /omnivoice/progress — polled by the frontend while a /voice_design call is
    # in flight. See voice_design._progress for field semantics (phase + ETA from a running
    # average, no completed/total counter since this checkpoint is a single blocking call).
    return jsonify(voice_design.get_progress())


# ── Built-in Pocket Voices ────────────────────────────────────────────────────────────────────

POCKET_BUILTIN_VOICES = {
    "vera": {"display_name": "Vera", "license": "CC BY 4.0", "language": "English", "language_code": "en", "category": "conversation", "note": "Female, natural Aussie"},
    "jane": {"display_name": "Jane", "license": "CC0", "language": "English", "language_code": "en", "category": "conversation", "note": "Female conversation"},
    "anna": {"display_name": "Anna", "license": "CC0", "language": "English", "language_code": "en", "category": "conversation", "note": "Female conversation"},
    "fantine": {"display_name": "Fantine", "license": "CC BY 4.0", "language": "English", "language_code": "en", "category": "reading", "note": "Female reading"},
    "alba": {"display_name": "Alba", "license": "CC BY 4.0", "language": "English", "language_code": "en", "category": "reading", "note": "Reading / character"},
    "marius": {"display_name": "Marius", "license": "CC BY 4.0", "language": "English", "language_code": "en", "category": "reading", "note": "Male reading"},
    "jean": {"display_name": "Jean", "license": "CC0", "language": "English", "language_code": "en", "category": "reading", "note": "Male reading"},
    "azelma": {"display_name": "Azelma", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Female"},
    "bill_boerst": {"display_name": "Bill Boerst", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "caro_davy": {"display_name": "Caro Davy", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Female"},
    "charles": {"display_name": "Charles", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "cosette": {"display_name": "Cosette", "license": "CC BY 4.0", "language": "English", "language_code": "en", "category": "other", "note": "Female"},
    "eponine": {"display_name": "Eponine", "license": "CC BY 4.0", "language": "English", "language_code": "en", "category": "other", "note": "Female"},
    "eve": {"display_name": "Eve", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Female"},
    "george": {"display_name": "George", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "javert": {"display_name": "Javert", "license": "CC BY 4.0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "mary": {"display_name": "Mary", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Female"},
    "michael": {"display_name": "Michael", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "paul": {"display_name": "Paul", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "peter_yearsley": {"display_name": "Peter Yearsley", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "stuart_bell": {"display_name": "Stuart Bell", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "estelle": {"display_name": "Estelle", "license": "CC BY 4.0", "language": "French", "language_code": "fr", "category": "multilingual", "note": "French"},
    "giovanni": {"display_name": "Giovanni", "license": "CC BY 4.0", "language": "Italian", "language_code": "it", "category": "multilingual", "note": "Italian"},
    "juergen": {"display_name": "Juergen", "license": "CC BY 4.0", "language": "German", "language_code": "de", "category": "multilingual", "note": "German"},
    "lola": {"display_name": "Lola", "license": "CC BY 4.0", "language": "Spanish", "language_code": "es", "category": "multilingual", "note": "Spanish"},
    "rafael": {"display_name": "Rafael", "license": "CC BY 4.0", "language": "Portuguese", "language_code": "pt", "category": "multilingual", "note": "Portuguese"},
    "hf_expresso_happy": {"display_name": "Expresso Happy", "license": "CC BY-NC 4.0", "language": "English", "language_code": "en", "category": "other", "note": "Happy delivery", "path": "hf://kyutai/tts-voices/expresso/ex03-ex01_happy_001_channel1_334s.wav"},
    "hf_voice_zero_bill": {"display_name": "Bill (Zero)", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male", "path": "hf://kyutai/tts-voices/voice-zero/bill_boerst.wav"},
    "hf_voice_donations_0a67": {"display_name": "Donation 0a67", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Female", "path": "hf://kyutai/tts-voices/voice-donations/0a67_enhanced.wav"},
    "hf_cml_fr_10087": {"display_name": "French 10087", "license": "CC BY 4.0", "language": "French", "language_code": "fr", "category": "multilingual", "note": "Female", "path": "hf://kyutai/tts-voices/cml-tts/fr/10087_11650_000028-0002_enhanced.wav"},
}

@app.get("/voices")
def voices_list():
    """Return list of all saved voices in the library, flagging the runtime API default."""
    voices = voice_library.list_voices()
    active_id = None
    if getattr(model, "TTS_BACKEND", None) == "pocket_tts":
        try:
            from persona_forge import pocket_tts_runtime

            active_id = pocket_tts_runtime.get_active_default_voice_id()
        except Exception:
            active_id = None
    for voice in voices:
        voice["api_active"] = active_id is not None and voice.get("voice_id") == active_id
    return jsonify({"voices": voices})

@app.get("/voices/built-in")
def voices_builtin():
    """Return a list of curated built-in voices for the Pocket TTS backend."""
    voices = []
    for vid, meta in POCKET_BUILTIN_VOICES.items():
        voices.append({
            "voice_id": f"pocket:{vid}",
            "builtin_voice": vid,
            "backend": "pocket_tts",
            "display_name": meta["display_name"],
            "source": "kyutai/tts-voices",
            "license": meta["license"],
            "language": meta["language"],
            "language_code": meta["language_code"],
            "category": meta["category"],
            "note": meta["note"],
            "prompt": vid,
            "requires_backend": "pocket_tts",
        })
    return jsonify({"voices": voices})


def _resolve_builtin_voice(data: dict, voice_id: str | None) -> tuple[str | None, str | None]:
    builtin_voice = (data.get("builtin_voice") or "").strip()
    if not builtin_voice:
        # Also check voice parameter for pocket: prefixed builtins
        voice_val = (data.get("voice") or "").strip()
        if voice_val.startswith("pocket:"):
            return voice_val, None
        return voice_id, None
    active_backend = getattr(model, "TTS_BACKEND", getattr(model, "tts_backend", None))
    if active_backend != "pocket_tts":
        return voice_id, "builtin_voice is only supported when TTS_BACKEND=pocket_tts"
    return (
        builtin_voice if builtin_voice.startswith("pocket:") else f"pocket:{builtin_voice}",
        None,
    )


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


@app.patch("/voices/<voice_id>")
def voices_update(voice_id: str):
    data = request.get_json(silent=True) or {}
    sample_text = (data.get("sample_text") or "").strip()
    if not sample_text:
        return jsonify({"error": "sample_text is required"}), 400
    meta = voice_library.update_voice(voice_id, sample_text=sample_text)
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404
    model.invalidate_voice_clone_prompt(voice_id)
    return jsonify(meta)


@app.post("/voices/<voice_id>/duplicate")
def voices_duplicate(voice_id: str):
    """Fork a voice into an independent voice_id (also used as a safety copy before
    destructive reference-audio editing). Optionally fork a specific prosody variant
    rather than whichever one is currently active."""
    data = request.get_json(silent=True) or {}
    variant_filename = data.get("variant_filename")
    try:
        meta = voice_library.duplicate_voice(voice_id, variant_filename)
    except Exception as exc:
        return jsonify({"error": f"Duplicate failed: {exc}"}), 500
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404
    return jsonify(meta), 201


@app.post("/voices/<voice_id>/analyze")
def voices_analyze(voice_id: str):
    """Backfill reference metrics without changing the saved WAV."""
    try:
        meta = voice_library.analyze_reference(voice_id)
    except Exception as exc:
        return jsonify({"error": f"Reference analysis failed: {exc}"}), 500
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404
    return jsonify(meta)


@app.post("/voices/<voice_id>/undo-reference-edit")
def voices_undo_reference_edit(voice_id: str):
    meta = voice_library.undo_reference_edit(voice_id)
    if meta is None:
        return jsonify({"error": "No audio edit to undo"}), 409
    _invalidate_voice_clone_state(voice_id)
    return jsonify(meta)


@app.delete("/voices/<voice_id>")
def voices_delete(voice_id: str):
    deleted = voice_library.delete_voice(voice_id)
    if not deleted:
        return jsonify({"error": "voice_id not found"}), 404
    model.invalidate_voice_clone_prompt(voice_id)
    try:
        from persona_forge import pocket_tts_runtime
        pocket_tts_runtime.invalidate_voice_state(voice_id)
    except ImportError:
        pass  # pocket-tts package not installed (non-pocket_tts deployment); nothing to invalidate.
    return jsonify({"deleted": voice_id})


def _invalidate_voice_clone_state(voice_id: str) -> None:
    model.invalidate_voice_clone_prompt(voice_id)
    try:
        from persona_forge import pocket_tts_runtime
        pocket_tts_runtime.invalidate_voice_state(voice_id)
    except ImportError:
        return  # pocket-tts package not installed (non-pocket_tts deployment); nothing to invalidate.

    # This voice_id's per-id cache entry is gone, but no-voice_id requests read a
    # separate module-level default_voice_state that isn't keyed by voice_id at all —
    # if voice_id is the persisted API default, that global state is now stale and
    # must be rebuilt from the (just-changed) current.wav, or default requests keep
    # serving pre-mutation audio until the next idle-unload/reload.
    if (
        getattr(model, "TTS_BACKEND", None) == "pocket_tts"
        and model._service_started
        and pocket_tts_runtime.get_active_default_voice_id() == voice_id
    ):
        try:
            model.executor.submit(
                pocket_tts_runtime.set_default_voice_state_from_library, voice_id
            ).result(timeout=30)
        except Exception:
            logger.exception("Failed to rebuild API default voice_state after mutating %s", voice_id)


@app.post("/voices/<voice_id>/normalize")
def voices_normalize(voice_id: str):
    """Re-normalize a saved reference clip's loudness/peak in place (-20 LUFS, -1dBTP)."""
    try:
        meta = voice_library.normalize_reference(voice_id)
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        return jsonify({"error": f"Normalize failed: {exc}"}), 500
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404
    _invalidate_voice_clone_state(voice_id)
    return jsonify(meta)


@app.post("/voices/<voice_id>/trim-silence")
def voices_trim_silence(voice_id: str):
    """Trim leading/trailing silence from a saved reference clip in place."""
    try:
        meta = voice_library.trim_reference_silence(voice_id)
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        return jsonify({"error": f"Trim failed: {exc}"}), 500
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404
    _invalidate_voice_clone_state(voice_id)
    return jsonify(meta)


@app.post("/voices/<voice_id>/set-default")
def voices_set_default(voice_id: str):
    """Mark voice_id as the default variant within its family."""
    meta = voice_library.set_default_variant(voice_id)
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404
    return jsonify(meta)


@app.post("/voices/<voice_id>/project")
def voices_set_project(voice_id: str):
    """Assign or clear the Accent Design Project this voice belongs to (§4)."""
    data = request.get_json(silent=True) or {}
    project_id = data.get("project_id")
    project_name = data.get("project_name")
    meta = voice_library.set_voice_project(voice_id, project_id, project_name)
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404
    return jsonify(meta)


@app.post("/voices/<voice_id>/set-active-variant")
def voices_set_active_variant(voice_id: str):
    """Set the active prosody variant for a voice, or reset to original."""
    data = request.get_json(silent=True) or {}
    variant_filename = data.get("variant_filename")
    try:
        success = voice_library.set_active_variant(voice_id, variant_filename)
    except Exception as exc:
        return jsonify({"error": f"Failed to set active variant: {exc}"}), 500
    if not success:
        return jsonify({"error": "Could not set active variant (invalid voice or file)"}), 400
    _invalidate_voice_clone_state(voice_id)
    meta = voice_library.get_voice(voice_id) or {}
    return jsonify({
        **meta,
        "status": "active variant updated",
        "active_variant": variant_filename or "original",
    })


@app.get("/voices/<voice_id>/variants")
def voices_get_variants(voice_id: str):
    """List the original reference plus all saved prosody variants for a voice."""
    if not voice_library._is_valid_voice_id(voice_id):
        return jsonify({"error": "invalid voice_id"}), 400
    voice_dir = voice_library._voice_dir(voice_id)
    if not voice_dir.is_dir():
        return jsonify({"error": "voice not found"}), 404

    # Find which filename is currently active/served.
    current_wav = voice_dir / "current.wav"
    active_filename = current_wav.resolve().name if current_wav.is_symlink() else "original.wav"

    entries = [{
        "id": voice_id,
        "filename": "original.wav",
        "label": "Original",
        "is_original": True,
    }]
    variants_meta = voice_library._load_variants_meta(voice_id)
    for slug, entry in sorted(variants_meta.items(), key=lambda kv: kv[1].get("created_at", 0)):
        entries.append({
            "id": f"{voice_id}.{slug}",
            "slug": slug,
            "filename": entry.get("filename"),
            "label": entry.get("label", slug),
            "source": entry.get("source"),
            "created_at": entry.get("created_at"),
            "is_original": False,
        })

    variants = [e["filename"] for e in entries if not e["is_original"]]
    active_variant = active_filename if active_filename in variants else None

    return jsonify({
        "entries": entries,
        "variants": sorted(variants),
        "active_variant": active_variant,
        "active_filename": active_filename,
    })


@app.get("/voices/<voice_id>/variants/<variant_filename>/audio")
def voices_get_variant_audio(voice_id: str, variant_filename: str):
    """Fetch a single variant's raw audio (base64), for per-variant preview playback."""
    wav_bytes = voice_library.get_variant_wav_bytes(voice_id, variant_filename)
    if wav_bytes is None:
        return jsonify({"error": "variant not found"}), 404
    return jsonify({"audio_base64": base64.b64encode(wav_bytes).decode("ascii")})


@app.get("/voices/<voice_id>/variants/<variant_filename>/metrics")
def voices_get_variant_metrics(voice_id: str, variant_filename: str):
    """Compute a single variant's quality metrics without persisting them (preview-only)."""
    metrics = voice_library.compute_variant_metrics(voice_id, variant_filename)
    if metrics is None:
        return jsonify({"error": "variant not found"}), 404
    return jsonify(metrics)


@app.delete("/voices/<voice_id>/variants/<variant_filename>")
def voices_delete_variant(voice_id: str, variant_filename: str):
    """Delete a prosody variant. If it was active, the voice falls back to original.wav."""
    deleted = voice_library.delete_variant(voice_id, variant_filename)
    if not deleted:
        return jsonify({"error": "variant not found"}), 404
    _invalidate_voice_clone_state(voice_id)
    return jsonify({"deleted": variant_filename})


@app.post("/voices/<voice_id>/activate")
def voices_activate(voice_id: str):
    """Make a saved voice the runtime API default (hot-swap Pocket's default voice_state)."""
    active_backend = getattr(model, "TTS_BACKEND", None)
    if active_backend != "pocket_tts":
        return (
            jsonify({"error": "Activate-for-API requires TTS_BACKEND=pocket_tts"}),
            409,
        )
    if not model._service_started:
        return jsonify({"error": "Model not loaded"}), 503
    meta = voice_library.get_voice(voice_id)
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404

    from persona_forge import pocket_tts_runtime

    def _run():
        pocket_tts_runtime.set_default_voice_state_from_library(voice_id)

    try:
        # Run on the model executor so the voice-state forward pass never races generation.
        model.executor.submit(_run).result(timeout=60)
    except Exception as exc:
        return jsonify({"error": f"Activate failed: {exc}"}), 500
    return jsonify({**meta, "api_active": True})


@app.post("/voices/<voice_id>/warm")
def voices_warm(voice_id: str):
    """Ensure a specific voice's clone state is loaded and cached before generation.

    The Speak tab's "Use in Speak" action and voice dropdown call this right when a
    voice is selected, so the runtime is bounced back from an idle-unloaded state and
    that voice's state is resolved/cached up front -- instead of deferring both the
    reload and the first-time voice-state build to the user's first Generate click.
    """
    active_backend = getattr(model, "TTS_BACKEND", None)
    if active_backend != "pocket_tts":
        return jsonify({"warmed": False, "reason": "not pocket_tts backend"})
    if not model._service_started and not _ensure_service_started(timeout_seconds=240):
        return jsonify({"error": "Model not loaded"}), 503
    meta = voice_library.get_voice(voice_id)
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404

    from persona_forge import pocket_tts_runtime

    def _run():
        model._ensure_base_loaded()
        pocket_tts_runtime.get_pocket_tts_voice_state(
            model.model,
            voice_id=voice_id,
            default_voice_state=model.voice_clone_prompt,
            ref_audio_path=model.REF_AUDIO,
        )

    try:
        model.executor.submit(_run).result(timeout=120)
    except Exception as exc:
        return jsonify({"error": f"Warm-up failed: {exc}"}), 500
    return jsonify({"warmed": True, "voice_id": voice_id})


@app.get("/voices/<voice_id>/preview-prosody")
def voices_preview_prosody(voice_id: str):
    """Preview prosody adjustments without saving a variant.
    Returns JSON with base64 audio and calculated metrics.
    """
    style_preset = request.args.get("style_preset", "Neutral").strip()
    try:
        pace_multiplier = float(request.args.get("pace_multiplier", 1.0))
    except (TypeError, ValueError):
        return jsonify({"error": "pace_multiplier must be a number"}), 400
    try:
        pause_offset = float(request.args.get("pause_offset", 0.0))
    except (TypeError, ValueError):
        return jsonify({"error": "pause_offset must be a number"}), 400
    mode = (request.args.get("mode") or "auto").strip().lower()
    if mode not in ("natural", "precise", "auto"):
        return jsonify({"error": "mode must be natural, precise, or auto"}), 400

    # Optional per-boundary target deltas (ms), keyed by rounded at_ms — the UI's
    # drag-to-resize on a manufactured pause. Layered on top of pause_offset.
    target_overrides: dict[str, float] | None = None
    raw_overrides = request.args.get("target_overrides")
    if raw_overrides:
        try:
            parsed = json.loads(raw_overrides)
            target_overrides = {str(k): float(v) for k, v in dict(parsed).items()}
        except (ValueError, TypeError):
            return jsonify({"error": "target_overrides must be a JSON object of numbers"}), 400

    meta = voice_library.get_voice(voice_id)
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404

    # Get the adjusted audio (wav, sr). Preview uses the same engine + mode as the saved
    # render so the waveform the user auditions is sample-equivalent to what they save.
    result = voice_library.get_prosody_adjusted_wav(
        voice_id, style_preset, pace_multiplier, pause_offset, mode, return_plan=True,
        target_overrides=target_overrides,
    )
    if result is None:
        return jsonify({"error": "Preview failed"}), 500

    wav, sr, plan = result
    
    # 1. Calculate metrics for the adjusted audio
    try:
        metrics = audio_style.analyze_reference(wav, sr, transcript=meta.get("sample_text"))
    except Exception as exc:
        logger.warning(f"Preview analysis failed: {exc}")
        metrics = {"error": f"analysis failed: {exc}"}

    try:
        diagnoses = [d.to_dict() for d in audio_diagnostics.diagnose_take(metrics)]
    except Exception as exc:
        logger.warning(f"Take diagnostics failed: {exc}")
        diagnoses = []

    # 2. Encode audio to base64
    buf = io.BytesIO()
    sf.write(buf, wav, sr, format="WAV", subtype="PCM_16")
    audio_base64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return jsonify({
        "audio_base64": audio_base64,
        "metrics": metrics,
        "diagnoses": diagnoses,
        "sample_rate": sr,
        "sample_count": int(wav.size),
        "plan": plan,
    })

@app.post("/voices/<voice_id>/adjust-pauses")
def voices_adjust_pauses(voice_id: str):
    """Adjust interior pauses of a saved reference clip based on a prosody map and pace."""
    data = request.get_json(silent=True) or {}
    style_preset = (data.get("style_preset") or "Neutral").strip()
    try:
        pace_multiplier = float(data.get("pace_multiplier", 1.0))
    except (TypeError, ValueError):
        return jsonify({"error": "pace_multiplier must be a number"}), 400
    try:
        pause_offset = float(data.get("pause_offset", 0.0))
    except (TypeError, ValueError):
        return jsonify({"error": "pause_offset must be a number"}), 400
    mode = (data.get("mode") or "auto").strip().lower()
    if mode not in ("natural", "precise", "auto"):
        return jsonify({"error": "mode must be natural, precise, or auto"}), 400
    try:
        meta = voice_library.adjust_reference_pauses(
            voice_id, style_preset=style_preset, pace_multiplier=pace_multiplier,
            pause_offset_ms=pause_offset, mode=mode,
        )
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        return jsonify({"error": f"Pause adjust failed: {exc}"}), 500
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404
    _invalidate_voice_clone_state(voice_id)
    return jsonify(meta)


@app.post("/voices/<voice_id>/prosody-variants")
def voices_save_prosody_variant(voice_id: str):
    """Bake and save a prosody variant WITHOUT promoting it to active/served audio.

    Split half of adjust-pauses: lets a take (including a precise per-boundary
    correction via target_overrides) be saved and independently addressed as
    vd_<parent_hex>.<slug> without changing what /voices/<id> currently serves.
    """
    data = request.get_json(silent=True) or {}
    style_preset = (data.get("style_preset") or "Neutral").strip()
    try:
        pace_multiplier = float(data.get("pace_multiplier", 1.0))
    except (TypeError, ValueError):
        return jsonify({"error": "pace_multiplier must be a number"}), 400
    try:
        pause_offset = float(data.get("pause_offset", 0.0))
    except (TypeError, ValueError):
        return jsonify({"error": "pause_offset must be a number"}), 400
    mode = (data.get("mode") or "auto").strip().lower()
    if mode not in ("natural", "precise", "auto"):
        return jsonify({"error": "mode must be natural, precise, or auto"}), 400

    target_overrides: dict[str, float] | None = None
    raw_overrides = data.get("target_overrides")
    if raw_overrides:
        try:
            target_overrides = {str(k): float(v) for k, v in dict(raw_overrides).items()}
        except (ValueError, TypeError):
            return jsonify({"error": "target_overrides must be an object of numbers"}), 400

    try:
        meta = voice_library.save_prosody_variant(
            voice_id, style_preset=style_preset, pace_multiplier=pace_multiplier,
            pause_offset_ms=pause_offset, mode=mode, target_overrides=target_overrides,
        )
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        return jsonify({"error": f"Save variant failed: {exc}"}), 500
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404
    return jsonify(meta)


@app.post("/voices/<voice_id>/region-edits")
def voices_region_edits(voice_id: str):
    """Apply a manual RegionEdit list (delete / insert_silence / fade / gain / mute) to a clip."""
    data = request.get_json(silent=True) or {}
    edits = _validate_region_edits(data.get("edits"))
    if edits is None:
        return jsonify({"error": "invalid edits payload"}), 400
    try:
        meta = voice_library.apply_reference_region_edits(voice_id, edits)
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        return jsonify({"error": f"Region edit failed: {exc}"}), 500
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404
    _invalidate_voice_clone_state(voice_id)
    return jsonify(meta)


# --- Prosody triage + forced alignment (plan §5.5) ---------------------------
# Triage is cheap and synchronous; alignment is a lazy model pass, so it runs
# through a bounded, serialized job manager with idle-unload (see
# alignment_jobs.py). The runner delegates to the voice_library cache, which
# computes only on a miss.

def _alignment_unload() -> None:
    from persona_forge import forced_alignment
    forced_alignment.unload_session()


def _alignment_runner(voice_id: str, cancel, **kwargs):
    return voice_library.get_or_compute_alignment(voice_id, cancel=cancel, **kwargs)


def _positive_float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r; using %.3f", name, raw, default)
        return default
    if value <= 0:
        logger.warning("Ignoring non-positive %s=%r; using %.3f", name, raw, default)
        return default
    return value


_alignment_jobs = AlignmentJobManager(
    _alignment_runner,
    unload=_alignment_unload,
    latency_budget_seconds=_positive_float_env("ALIGNER_LATENCY_BUDGET_SECONDS", 5.0),
    idle_unload_seconds=_positive_float_env("ALIGNER_IDLE_UNLOAD_SECONDS", 120.0),
)


@app.get("/alignment/performance")
def alignment_performance():
    """Bounded observed latency window; includes cold starts and cache hits."""
    return jsonify(_alignment_jobs.performance())


@app.post("/voices/<voice_id>/triage")
def voices_triage(voice_id: str):
    """Cheap, synchronous triage: does this reference need forced alignment?"""
    meta = voice_library.get_voice(voice_id)
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404
    wav_bytes = voice_library.get_voice_wav_bytes(voice_id)
    if wav_bytes is None:
        return jsonify({"error": "reference audio missing"}), 404
    try:
        wav, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32", always_2d=False)
        from persona_forge.prosody_triage import triage as _triage
        result = _triage(wav, int(sr), meta.get("sample_text"))
    except Exception as exc:
        return jsonify({"error": f"triage failed: {exc}"}), 500
    return jsonify(result.to_dict())


@app.post("/voices/<voice_id>/align")
def voices_align(voice_id: str):
    """Start (or reuse) a forced-alignment job. Async: returns a job_id to poll."""
    meta = voice_library.get_voice(voice_id)
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404
    if not (meta.get("sample_text") or "").strip():
        return jsonify({"error": "Reference has no transcript; alignment needs text."}), 400
    force = bool((request.get_json(silent=True) or {}).get("force"))
    job = _alignment_jobs.submit(voice_id, force=force)
    return jsonify(job), 202


@app.get("/voices/<voice_id>/align/<job_id>")
def voices_align_status(voice_id: str, job_id: str):
    """Poll a forced-alignment job."""
    job = _alignment_jobs.get(job_id)
    if job is None or job.get("voice_id") != voice_id:
        return jsonify({"error": "job not found"}), 404
    return jsonify(job)


@app.delete("/voices/<voice_id>/align/<job_id>")
def voices_align_cancel(voice_id: str, job_id: str):
    """Cancel a forced-alignment job."""
    job = _alignment_jobs.get(job_id)
    if job is None or job.get("voice_id") != voice_id:
        return jsonify({"error": "job not found"}), 404
    _alignment_jobs.cancel(job_id)
    return jsonify(_alignment_jobs.get(job_id))


@app.post("/voices/<voice_id>/validate")
def voices_validate(voice_id: str):
    if not model._service_started:
        return jsonify({"error": "Model not loaded"}), 503
    meta = voice_library.get_voice(voice_id)
    if meta is None:
        return jsonify({"error": "voice_id not found"}), 404
    wav_path = meta.get("wav_path")
    sample_text = (meta.get("sample_text") or "").strip()
    if not wav_path or not sample_text:
        return jsonify({"error": "Voice missing wav_path or sample_text"}), 400

    def _run():
        return validate_reference_text(wav_path, sample_text)

    try:
        result = model.executor.submit(_run).result(timeout=15)
    except Exception as exc:
        return jsonify({"error": f"Validation failed: {exc}"}), 500

    sev = result["severity"]
    if sev in ("fail", "no_speech"):
        print(
            f"[REF-TEXT-VALID] voice_id={voice_id} STATUS=fail  score={result.get('match_score')}",
            flush=True,
            file=sys.stderr,
        )
        print(f"  WAV_PATH: {wav_path}", flush=True, file=sys.stderr)
        print(f"  SAMPLE_TEXT: {sample_text!r}", flush=True, file=sys.stderr)
        print(f"  Whisper:   {result.get('whisper_transcript')!r}", flush=True, file=sys.stderr)
        print(f"  SUGGESTION: {result.get('suggestion')}", flush=True, file=sys.stderr)
    elif sev == "warn":
        print(
            f"[REF-TEXT-VALID] voice_id={voice_id} STATUS=warn  score={result.get('match_score')}",
            flush=True,
            file=sys.stderr,
        )
        print(f"  WAV_PATH: {wav_path}", flush=True, file=sys.stderr)
        print(f"  SAMPLE_TEXT: {sample_text!r}", flush=True, file=sys.stderr)
        print(f"  Whisper:   {result.get('whisper_transcript')!r}", flush=True, file=sys.stderr)
        print(f"  SUGGESTION: {result.get('suggestion')}", flush=True, file=sys.stderr)
    else:
        print(
            f"[REF-TEXT-VALID] voice_id={voice_id} STATUS=ok  score={result.get('match_score')}",
            flush=True,
        )
    return jsonify(result)


def _ensure_service_started(timeout_seconds: int = 900):
    # Wait until the service has started, with a timeout.
    # Used by the queue dispatcher when a job is queued because model wasn't ready.
    deadline = time.monotonic() + timeout_seconds
    while not model._service_started:
        if model._startup_failed:
            # Background load already failed for good — no point waiting out the
            # full timeout for a result that will never arrive.
            return False
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)
    return True


def _dispatch_audition_jobs():
    # Single-entrypoint dispatcher: picks queued jobs in order and submits them to the executor.
    # Uses a global flag so only one dispatch loop is active at a time.
    global _OV_AUDITION_DISPATCH_IN_PROGRESS

    # Start if not already running
    with _OV_AUDITION_QUEUE_LOCK:
        if _OV_AUDITION_DISPATCH_IN_PROGRESS:
            return
        _OV_AUDITION_DISPATCH_IN_PROGRESS = True

    # Run in current thread (daemon thread caller will wrap)
    try:
        while True:
            # Grab next job_id (if any)
            next_job_id = None
            with _OV_AUDITION_QUEUE_LOCK:
                if _OV_AUDITION_QUEUE:
                    next_job_id = _OV_AUDITION_QUEUE.pop(0)

            if next_job_id is None:
                # No more queued jobs: stop
                break

            # Read job params
            job = None
            with _OV_AUDITION_JOBS_LOCK:
                job = _OV_AUDITION_JOBS.get(next_job_id)

            if job is None:
                continue

            if job.get("cancel_event") is not None and job["cancel_event"].is_set():
                with _OV_AUDITION_JOBS_LOCK:
                    job["status"] = "failed"
                    job["message"] = "Cancelled by user."
                continue

            # Ensure the base service is started (if not, wait)
            if not _ensure_service_started(timeout_seconds=900):
                with _OV_AUDITION_JOBS_LOCK:
                    _OV_AUDITION_JOBS[next_job_id].update(
                        status="failed",
                        message="Service did not become ready in time.",
                    )
                continue

            # Now mark job as running and submit to executor
            with _OV_AUDITION_JOBS_LOCK:
                job["status"] = "running"
                job["message"] = "Starting OmniVoice generation…"
            params = job.get("_params")
            if not params:
                with _OV_AUDITION_JOBS_LOCK:
                    job["status"] = "failed"
                    job["message"] = "Invalid job: missing parameters."
                continue

            (
                segments,
                instruct,
                language,
                candidates_per_segment,
                seed,
                num_step,
                cleaned_durations,
                speed,
                guidance_scale,
                diverse_candidates,
                postprocess_output,
                min_match_score,
            ) = params

            cancel_event = job["cancel_event"]

            def _run_job(job_id):
                try:
                    model.executor.submit(
                        omnivoice_engine.run_omnivoice_job,
                        segments,
                        instruct,
                        language,
                        candidates_per_segment,
                        seed,
                        num_step,
                        cleaned_durations,
                        speed,
                        guidance_scale,
                        diverse_candidates,
                        postprocess_output=postprocess_output,
                        min_match_score=min_match_score,
                        on_candidate_complete=_candidate_callback_factory(job_id, guidance_scale),
                        cancel_event=cancel_event,
                    ).result(timeout=1800)
                    with _OV_AUDITION_JOBS_LOCK:
                        job = _OV_AUDITION_JOBS.get(job_id)
                        if job is not None:
                            if cancel_event.is_set():
                                job["status"] = "failed"
                                job["message"] = "Cancelled by user."
                            else:
                                job["status"] = "completed"
                            job["current_segment_index"] = None
                except Exception as exc:
                    with _OV_AUDITION_JOBS_LOCK:
                        job = _OV_AUDITION_JOBS.get(job_id)
                        if job is not None:
                            job["status"] = "failed"
                            job["current_segment_index"] = None
                            job["message"] = f"OmniVoice error: {exc}"
                finally:
                    omnivoice_engine.clear_swap_pending()

            threading.Thread(target=_run_job, args=(next_job_id,), daemon=True).start()
    finally:
        with _OV_AUDITION_QUEUE_LOCK:
            _OV_AUDITION_DISPATCH_IN_PROGRESS = False


def _encode_omnivoice_candidate(
    wav, sr, flagged, flag_reason, whisper_transcript, match_score, guidance_scale=None
):
    candidate_id = uuid.uuid4().hex
    wav_bytes, _ = _encode(wav, sr, "wav")
    _omnivoice_candidates[candidate_id] = (wav, sr)
    duration_sec = len(wav) / sr if sr > 0 else 0.0
    try:
        metrics = audio_style.analyze_reference(wav, sr)
        diagnoses = [
            d.to_dict() for d in audio_diagnostics.diagnose_take(metrics, guidance_scale=guidance_scale)
        ]
    except Exception:
        diagnoses = []
    return {
        "candidate_id": candidate_id,
        "sample_rate": sr,
        "duration_sec": round(duration_sec, 2),
        "audio_base64": base64.b64encode(wav_bytes).decode("ascii"),
        "flagged": flagged,
        "flag_reason": None if flag_reason == "ok" else flag_reason,
        "whisper_transcript": (whisper_transcript or "").strip() or None,
        "match_score": round(float(match_score), 2) if match_score is not None else None,
        "diagnoses": diagnoses,
    }


def _find_candidate_job(candidate_id: str):
    """Return (job_id, params, candidate_payload, segment_index) or (None, None, None, None).

    Scans in-memory audition jobs for the candidate. Used when saving a segment to
    attach generation parameters (language, seed, etc.) instead of leaving them empty.
    """
    with _OV_AUDITION_JOBS_LOCK:
        for jid, job in _OV_AUDITION_JOBS.items():
            for seg in job.get("segments_completed", []):
                for cand in seg.get("candidates", []):
                    if cand.get("candidate_id") == candidate_id:
                        return (
                            jid,
                            job.get("_params"),
                            cand,
                            seg.get("segment_index"),
                        )
    return None, None, None, None


def _candidate_callback_factory(job_id: str, guidance_scale=None):
    # Build per-candidate callback that updates job state as soon as each candidate is
    # ready, so the frontend can show/play a take without waiting for the rest of that
    # segment's candidates (or the whole job) to finish.
    def _cb(seg_idx, cand_idx, text, candidate):
        wav, sr, flagged, flag_reason, whisper_transcript, match_score = candidate
        cand_payload = _encode_omnivoice_candidate(
            wav, sr, flagged, flag_reason, whisper_transcript, match_score, guidance_scale
        )
        with _OV_AUDITION_JOBS_LOCK:
            job = _OV_AUDITION_JOBS.get(job_id)
            if job is None:
                return
            job["current_segment_index"] = seg_idx
            segs = job["segments_completed"]
            seg_entry = next(
                (s for s in segs if s["segment_index"] == seg_idx), None
            )
            if seg_entry is None:
                seg_entry = {
                    "segment_index": seg_idx,
                    "text": text,
                    "candidates": [],
                }
                segs.append(seg_entry)
            seg_entry["candidates"].append(cand_payload)
    return _cb


@app.post("/omnivoice/audition")
def omnivoice_audition():
    _evict_old_audition_jobs()

    # Parse and validate the complete request before consulting mutable runtime state. Invalid
    # payloads must deterministically return 400 even when another worker/job is swapping.
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

    num_step = data.get("num_step")
    if num_step is not None and not isinstance(num_step, int):
        return jsonify({"error": "num_step must be an integer"}), 400

    # Per-segment durations (preferred) or legacy global duration (for compat)
    durations = data.get("durations")
    if durations is not None:
        if not isinstance(durations, list):
            return jsonify({"error": "durations must be a list of numbers or null"}), 400
        if len(durations) != len(segments):
            return jsonify({"error": "durations length must match segments length"}), 400
        cleaned_durations: list[float | None] = []
        for d in durations:
            if d is None:
                cleaned_durations.append(None)
            elif isinstance(d, (int, float)):
                cleaned_durations.append(float(d))
            else:
                return jsonify({"error": "each duration must be a number or null"}), 400
    else:
        # Backwards compat: single global duration applied to all segments
        duration = data.get("duration")
        if duration is not None and not isinstance(duration, (int, float)):
            return jsonify({"error": "duration must be a number"}), 400
        cleaned_durations = [float(duration) for _ in segments] if duration is not None else None

    speed = data.get("speed")
    if speed is not None and not isinstance(speed, (int, float)):
        return jsonify({"error": "speed must be a number"}), 400

    guidance_scale = data.get("guidance_scale")
    if guidance_scale is not None and not isinstance(
        guidance_scale, (int, float)
    ):
        return jsonify({"error": "guidance_scale must be a number"}), 400

    diverse_candidates_raw = data.get("diverse_candidates")
    diverse_candidates = (
        bool(diverse_candidates_raw)
        if diverse_candidates_raw is not None
        else False
    )

    postprocess_output = data.get("postprocess_output")
    if postprocess_output is not None and not isinstance(postprocess_output, bool):
        return jsonify({"error": "postprocess_output must be a boolean"}), 400

    min_match_score = data.get("min_match_score")
    if min_match_score is not None:
        if not isinstance(min_match_score, (int, float)):
            return jsonify({"error": "min_match_score must be a number"}), 400
        min_match_score = max(0.0, min(1.0, float(min_match_score)))

    # A structurally valid request cannot start while another model swap is in progress.
    if voice_design.swap_in_progress() or omnivoice_engine.swap_in_progress():
        return jsonify({"error": "Another swap already in progress"}), 503

    job_id = uuid.uuid4().hex

    # Candidates are only ever addressable up until the next audition job starts (see
    # module docstring above _omnivoice_candidates); clearing here both enforces that
    # and bounds memory, since each entry holds a decoded float32 waveform.
    _omnivoice_candidates.clear()

    # Mark the swap as pending now, before this job actually starts executing, so a
    # second conflicting swap request can't slip past the swap_in_progress() 503
    # guard during the window between acceptance and execution (including any time
    # spent queued waiting for model startup).
    omnivoice_engine.mark_swap_pending()

    # Decide whether we can run immediately or must queue.
    if model._service_started:
        initial_status = "running"
        initial_message = "Starting OmniVoice generation…"
    else:
        initial_status = "queued"
        initial_message = "Waiting for model to load…"

    with _OV_AUDITION_JOBS_LOCK:
        _OV_AUDITION_JOBS[job_id] = {
            "status": initial_status,
            "total_segments": len(segments),
            "segments_completed": [],
            "current_segment_index": None,
            "message": initial_message,
            "created_at": time.time(),
            "cancel_event": threading.Event(),
            "_params": (
                segments,
                instruct,
                language,
                candidates_per_segment,
                seed,
                num_step,
                cleaned_durations,
                speed,
                guidance_scale,
                diverse_candidates,
                postprocess_output,
                min_match_score,
            ),
        }

    if initial_status == "running":
        # Start immediately on the executor
        cancel_event = _OV_AUDITION_JOBS[job_id]["cancel_event"]

        def _run_job():
            try:
                model.executor.submit(
                    omnivoice_engine.run_omnivoice_job,
                    segments,
                    instruct,
                    language,
                    candidates_per_segment,
                    seed,
                    num_step,
                    cleaned_durations,
                    speed,
                    guidance_scale,
                    diverse_candidates,
                    postprocess_output=postprocess_output,
                    min_match_score=min_match_score,
                    on_candidate_complete=_candidate_callback_factory(job_id),
                    cancel_event=cancel_event,
                ).result(timeout=1800)
                with _OV_AUDITION_JOBS_LOCK:
                    job = _OV_AUDITION_JOBS.get(job_id)
                    if job is not None:
                        if cancel_event.is_set():
                            job["status"] = "failed"
                            job["message"] = "Cancelled by user."
                        else:
                            job["status"] = "completed"
                        job["current_segment_index"] = None
            except Exception as exc:
                with _OV_AUDITION_JOBS_LOCK:
                    job = _OV_AUDITION_JOBS.get(job_id)
                    if job is not None:
                        job["status"] = "failed"
                        job["current_segment_index"] = None
                        job["message"] = f"OmniVoice error: {exc}"
            finally:
                omnivoice_engine.clear_swap_pending()

        threading.Thread(target=_run_job, daemon=True).start()
    else:
        # Enqueue for dispatcher; kick it if not already running.
        with _OV_AUDITION_QUEUE_LOCK:
            _OV_AUDITION_QUEUE.append(job_id)
            if not _OV_AUDITION_DISPATCH_IN_PROGRESS:
                threading.Thread(target=_dispatch_audition_jobs, daemon=True).start()

    return jsonify(
        {
            "job_id": job_id,
            "total_segments": len(segments),
        }
    )


@app.get("/omnivoice/progress")
def omnivoice_progress():
    # Polled by the frontend while an audition job is in flight (nick's feedback 2026-07-03:
    # the prior indeterminate top-of-page banner gave no sense of what was happening or how
    # long it'd take). See omnivoice_engine._progress for field semantics.
    return jsonify(omnivoice_engine.get_progress())


@app.get("/omnivoice/audition/progress")
def omnivoice_audition_progress():
    _evict_old_audition_jobs()
    job_id = request.args.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id query parameter is required"}), 400
    with _OV_AUDITION_JOBS_LOCK:
        job = _OV_AUDITION_JOBS.get(job_id)
    if job is None:
        return jsonify({"error": "Unknown or expired job_id"}), 404
    prog = omnivoice_engine.get_progress()
    message = job.get("message")
    cancel_event = job.get("cancel_event")
    if job["status"] == "running" and cancel_event is not None and cancel_event.is_set():
        remaining = prog.get("estimated_remaining_seconds")
        if isinstance(remaining, (int, float)):
            message = f"Cancelling — finishing current take (~{int(remaining)}s)"
        else:
            message = "Cancelling — finishing current take…"
    return jsonify(
        {
            "status": job["status"],
            "job_id": job_id,
            "total_segments": job["total_segments"],
            "current_segment_index": job["current_segment_index"],
            "segments_completed": job["segments_completed"],
            "message": message,
            "eta": prog.get("estimated_remaining_seconds"),
            "total_candidates": prog.get("total"),
            "completed_candidates": prog.get("completed"),
            "avg_seconds": prog.get("avg_seconds"),
            "estimated_remaining_seconds": prog.get("estimated_remaining_seconds"),
            "current_candidate_index": prog.get("current_candidate_index"),
        }
    )


@app.post("/omnivoice/audition/cancel")
def omnivoice_audition_cancel():
    """Cancel a running OmniVoice audition job.

    Sets the job status to failed and clears any swap pending flag so it doesn't block
    further work. Uses the same cooperative pattern: the OmniVoice engine will stop at
    the next segment/candidate boundary.
    """
    job_id = (request.args.get("job_id") or "").strip()
    if not job_id:
        return jsonify({"error": "job_id is required"}), 400

    with _OV_AUDITION_JOBS_LOCK:
        job = _OV_AUDITION_JOBS.get(job_id)
        if job is None:
            return jsonify({"error": "Unknown or expired job_id"}), 404
        if job["status"] not in ("running", "queued"):
            return jsonify({"error": "Job is not currently running"}), 400

        job["cancel_event"].set()
        if job["status"] == "queued":
            # Never got picked up by the executor at all — safe to finalize immediately.
            job["status"] = "failed"
            job["message"] = "Cancelled by user."
            job["current_segment_index"] = None
        else:
            job["message"] = "Cancelling…"

    return jsonify({"cancelled": True, "job_id": job_id})


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


def _resolve_omnivoice_clips(data: dict[str, Any]) -> list[tuple[Any, int]] | None:
    """Resolve either persisted segment_ids (the segment library) or ephemeral candidate_id
    ``selections`` (the pre-lock-in audition cache) into (wav, sample_rate) tuples.

    segment_ids is the primary path now that lock-in persists immediately (see
    /omnivoice/segments below) — it's what lets stitching mix segments from any past session,
    not just the current one. ``selections`` stays supported for stitching a preview straight
    from freshly-generated, not-yet-locked-in candidates.
    """
    segment_ids = data.get("segment_ids")
    if segment_ids is not None:
        if (
            not isinstance(segment_ids, list)
            or not segment_ids
            or not all(isinstance(s, str) for s in segment_ids)
        ):
            return None
        selected = []
        for segment_id in segment_ids:
            wav_bytes = segment_library.get_segment_wav_bytes(segment_id)
            if wav_bytes is None:
                return None
            wav, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
            selected.append((wav, sr))
        return selected
    return _resolve_omnivoice_selections(data.get("selections"))


def _resolve_one_clip_ref(ref: dict[str, Any]) -> tuple[Any, int] | None:
    """Resolve a single stitch-plan clip ref (``{segment_id}``, ``{candidate_id}``, or
    ``{voice_id}``) into a (wav, sample_rate) tuple. Returns None on any unknown/malformed ref.
    """
    segment_id = ref.get("segment_id")
    if isinstance(segment_id, str) and segment_id:
        wav_bytes = segment_library.get_segment_wav_bytes(segment_id)
        if wav_bytes is None:
            return None
        wav, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
        return wav, sr
    candidate_id = ref.get("candidate_id")
    if isinstance(candidate_id, str) and candidate_id:
        return _omnivoice_candidates.get(candidate_id)
    # voice_id: lets the stitch editor pull in a saved Voice Library entry (a whole finished
    # take, e.g. from Speak/Voice Design) as one clip, same as any segment/candidate.
    voice_id = ref.get("voice_id")
    if isinstance(voice_id, str) and voice_id:
        wav_bytes = voice_library.get_voice_wav_bytes(voice_id)
        if wav_bytes is None:
            return None
        wav, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
        return wav, sr
    return None


_REGION_EDIT_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    # edit type -> (required numeric fields, optional numeric fields defaulted to 0.0)
    "gain": ({"start_ms", "end_ms"}, {"gain_db", "fade_in_ms", "fade_out_ms"}),
    "mute": ({"start_ms", "end_ms"}, {"fade_in_ms", "fade_out_ms"}),
    "fade": ({"start_ms", "end_ms"}, {"fade_in_ms", "fade_out_ms"}),
    "delete": ({"start_ms", "end_ms"}, set()),
    "insert_silence": ({"at_ms", "duration_ms"}, set()),
}


def _validate_region_edits(edits_raw: Any) -> list[dict[str, Any]] | None:
    """Validate/coerce one clip's RegionEdit list (StitchTimeline.tsx's client-side model).

    Returns a list of plain dicts with float fields ready for audio_post.apply_region_edits,
    or None on any structural/type failure (caller responds 400).
    """
    if edits_raw is None:
        return []
    if not isinstance(edits_raw, list):
        return None
    edits: list[dict[str, Any]] = []
    for raw in edits_raw:
        if not isinstance(raw, dict):
            return None
        edit_type = raw.get("type")
        fields = _REGION_EDIT_FIELDS.get(edit_type)
        if fields is None:
            return None
        required, optional = fields
        edit: dict[str, Any] = {"type": edit_type}
        try:
            for key in required:
                edit[key] = float(raw.get(key))
            for key in optional:
                edit[key] = float(raw.get(key) or 0.0)
        except (TypeError, ValueError):
            return None
        edits.append(edit)
    return edits


def _resolve_stitch_plan(
    stitch_plan: Any,
) -> tuple[list[tuple[Any, int]], dict[str, Any]] | None:
    """Resolve a stitch-editor ``stitch_plan`` payload into (clips, stitch_segments kwargs).

    Shape (all optional except ``clips``):
      {
        "clips": [{"segment_id"|"candidate_id": str,
                   "trim_start_ms": float, "trim_end_ms": float,
                   "fade_in_ms": float, "fade_out_ms": float,
                   "edits": [{"type": "gain"|"mute"|"delete"|"fade"|"insert_silence", ...}, ...]},
                  ...],
        "padding_ms": [float, ...],       # len(clips) - 1
        "crossfade_ms": float,
        "segment_target_dbfs": float,
        "final_target_dbfs": float,
        "final_ceiling_db": float,
        "compress": {"threshold_db": float, "ratio": float,
                     "attack_ms": float, "release_ms": float},
      }

    Returns None on any structural/validation failure (caller responds 400). Only
    segment_id-based clips are durably re-editable across restarts; candidate_id clips rely
    on the ephemeral in-memory audition cache, same caveat as the existing selections path.
    """
    if not isinstance(stitch_plan, dict):
        return None
    clips = stitch_plan.get("clips")
    if not isinstance(clips, list) or not clips:
        return None

    selected: list[tuple[Any, int]] = []
    trims: list[tuple[float, float]] = []
    fades: list[tuple[float, float]] = []
    edits: list[list[dict[str, Any]]] = []
    tempos: list[float] = []
    repair_requests: list[tuple[str, str]] = []
    for clip in clips:
        if not isinstance(clip, dict):
            return None
        entry = _resolve_one_clip_ref(clip)
        if entry is None:
            return None
        selected.append(entry)
        repair_mode = clip.get("prosody_mode", "off")
        if repair_mode not in prosody_repair.VALID_REPAIR_MODES:
            return None
        repair_requests.append((repair_mode, str(clip.get("text") or "").strip()))
        try:
            trims.append(
                (float(clip.get("trim_start_ms") or 0.0), float(clip.get("trim_end_ms") or 0.0))
            )
            fades.append(
                (float(clip.get("fade_in_ms") or 0.0), float(clip.get("fade_out_ms") or 0.0))
            )
            tempo_factor = float(clip.get("tempo_factor") or 1.0)
        except (TypeError, ValueError):
            return None
        if not 0.5 <= tempo_factor <= 2.0:
            return None
        tempos.append(tempo_factor)
        clip_edits = _validate_region_edits(clip.get("edits"))
        if clip_edits is None:
            return None
        edits.append(clip_edits)

    kwargs: dict[str, Any] = {}

    style_preset = str(stitch_plan.get("style_preset") or "Neutral")
    try:
        pace_multiplier = float(stitch_plan.get("pace_multiplier", 1.0))
        pause_offset_ms = float(stitch_plan.get("pause_offset_ms", 0.0))
    except (TypeError, ValueError):
        return None
    if not 0.25 <= pace_multiplier <= 4.0 or not -2000.0 <= pause_offset_ms <= 5000.0:
        return None

    if any(t != (0.0, 0.0) for t in trims):
        kwargs["trims"] = trims
    if any(f != (0.0, 0.0) for f in fades):
        kwargs["fades"] = fades
    if any(edits):
        kwargs["edits"] = edits
    if any(abs(t - 1.0) > 1e-3 for t in tempos):
        kwargs["tempos"] = tempos

    padding_ms = stitch_plan.get("padding_ms")
    if padding_ms is not None:
        if not isinstance(padding_ms, list) or len(padding_ms) != len(clips) - 1:
            return None
        try:
            kwargs["padding_ms"] = [float(p) for p in padding_ms]
        except (TypeError, ValueError):
            return None

    for key in ("crossfade_ms", "segment_target_dbfs", "final_target_dbfs", "final_ceiling_db"):
        value = stitch_plan.get(key)
        if value is not None:
            try:
                kwargs[key] = float(value)
            except (TypeError, ValueError):
                return None

    compress_params = stitch_plan.get("compress")
    if compress_params is not None:
        if not isinstance(compress_params, dict):
            return None
        allowed = {"threshold_db", "ratio", "attack_ms", "release_ms"}
        if not set(compress_params).issubset(allowed):
            return None
        try:
            kwargs["compress_params"] = {k: float(v) for k, v in compress_params.items()}
        except (TypeError, ValueError):
            return None

    repaired_selected: list[tuple[Any, int]] = []
    for (wav, sr), (repair_mode, transcript) in zip(selected, repair_requests):
        if repair_mode == "off":
            repaired_selected.append((wav, sr))
            continue
        repaired, _plan, _metadata = prosody_repair.repair_segment_audio(
            wav,
            int(sr),
            transcript,
            mode=repair_mode,
            style_preset=style_preset,
            pace_multiplier=pace_multiplier,
            pause_offset_ms=pause_offset_ms,
        )
        repaired_selected.append((repaired, sr))

    selected = repaired_selected
    return selected, kwargs


@app.post("/omnivoice/stitch/pacing-targets")
def omnivoice_stitch_pacing_targets():
    """Resolve inter-segment pause targets through the canonical prosody target table."""
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    transcripts = data.get("transcripts")
    if (
        not isinstance(transcripts, list)
        or not transcripts
        or not all(isinstance(text, str) for text in transcripts)
    ):
        return jsonify({"error": "transcripts must be a non-empty list of strings"}), 400
    try:
        pace_multiplier = float(data.get("pace_multiplier", 1.0))
        pause_offset_ms = float(data.get("pause_offset_ms", 0.0))
    except (TypeError, ValueError):
        return jsonify({"error": "pace_multiplier and pause_offset_ms must be numeric"}), 400
    if not 0.25 <= pace_multiplier <= 4.0 or not -2000.0 <= pause_offset_ms <= 5000.0:
        return jsonify({"error": "pacing values are out of range"}), 400
    style_preset = str(data.get("style_preset") or "Neutral")
    return jsonify(
        {
            "padding_ms": prosody_repair.suggest_stitch_gap_targets(
                transcripts, style_preset, pace_multiplier, pause_offset_ms
            ),
            "style_preset": style_preset
                if style_preset in audio_style.PROSODY_MAPS
                else "Neutral",
        }
    )


@app.get("/projects")
def projects_list():
    return jsonify(project_library.list_projects())


@app.post("/projects")
def projects_create():
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    description = data.get("description")
    return jsonify(project_library.create_project(name, description))


@app.patch("/projects/<project_id>")
def projects_rename(project_id: str):
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    entry = project_library.rename_project(project_id, name, data.get("description"))
    if entry is None:
        return jsonify({"error": "Unknown project_id"}), 404
    return jsonify(entry)


@app.delete("/projects/<project_id>")
def projects_delete(project_id: str):
    if not project_library.delete_project(project_id):
        return jsonify({"error": "Unknown project_id"}), 404
    return jsonify({"deleted": True})


@app.post("/omnivoice/segments")
def omnivoice_segments_create():
    # Locks in one audition candidate by persisting it to the durable segment library —
    # separate from /omnivoice/save, which persists a *stitched, multi-segment* reference
    # voice. This is the "keep this take" step; discarding a bad take is just not calling
    # this (the ephemeral audition cache is dropped on the next audition call).
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    candidate_id = data.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        return jsonify({"error": "candidate_id is required"}), 400
    entry = _omnivoice_candidates.get(candidate_id)
    if entry is None:
        return jsonify({"error": "Unknown or expired candidate_id"}), 400
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400
    instruct = (data.get("instruct") or "").strip()
    if not instruct:
        return jsonify({"error": "instruct is required"}), 400
    accent_id = data.get("accent_id")
    feature_tags = data.get("feature_tags")
    if not isinstance(feature_tags, list) or not all(isinstance(t, str) for t in feature_tags):
        feature_tags = None
    project_id = data.get("project_id")
    project_name = data.get("project_name")

    wav, sr = entry
    wav_bytes, _ = _encode(wav, sr, "wav")
    duration_sec = len(wav) / sr if sr > 0 else 0.0

    # Enrich metadata from audition job (if candidate still resolvable)
    job_id, params, candidate_payload, segment_index = _find_candidate_job(candidate_id)

    # _params tuple: (segments, instruct, language, candidates_per_segment, seed, num_step,
    #                 cleaned_durations, speed, guidance_scale, diverse_candidates,
    #                 postprocess_output, min_match_score)
    p_len = len(params) if params else 0
    language = params[2] if p_len > 2 else None
    seed = params[4] if p_len > 4 else None
    num_step = params[5] if p_len > 5 else None
    cleaned_durations = params[6] if p_len > 6 else None
    speed = params[7] if p_len > 7 else None
    guidance_scale = params[8] if p_len > 8 else None
    diverse_candidates = params[9] if p_len > 9 else None
    postprocess_output = params[10] if p_len > 10 else None

    # duration_target from per-segment durations list
    duration_target = None
    if (
        isinstance(cleaned_durations, list)
        and isinstance(segment_index, int)
        and 0 <= segment_index < len(cleaned_durations)
    ):
        duration_target = cleaned_durations[segment_index]

    whisper_transcript = (
        (candidate_payload.get("whisper_transcript") or "").strip() or None
        if candidate_payload
        else None
    )
    match_score = candidate_payload.get("match_score") if candidate_payload else None

    meta = segment_library.save_segment(
        wav_bytes,
        text=text,
        instruct=instruct,
        engine="omnivoice",
        sample_rate=sr,
        accent_id=accent_id,
        language=language,
        seed=seed,
        num_step=num_step,
        speed=speed,
        guidance_scale=guidance_scale,
        diverse_candidates=diverse_candidates,
        postprocess_output=postprocess_output,
        duration_target=duration_target,
        candidate_id=candidate_id,
        job_id=job_id,
        whisper_transcript=whisper_transcript,
        match_score=match_score,
        duration_sec=round(duration_sec, 2),
        feature_tags=feature_tags,
        project_id=project_id,
        project_name=project_name,
    )
    meta["audio_base64"] = base64.b64encode(wav_bytes).decode("ascii")
    return jsonify(meta)


@app.get("/omnivoice/segments")
def omnivoice_segments_list():
    segments = []
    for meta in segment_library.list_segments():
        entry = dict(meta)
        entry.pop("wav_path", None)
        segments.append(entry)
    return jsonify({"segments": segments})


@app.get("/omnivoice/segments/<segment_id>/audio")
def omnivoice_segments_audio(segment_id: str):
    seg = segment_library.get_segment(segment_id)
    if not seg or not seg.get("wav_path"):
        return jsonify({"error": "Unknown segment_id"}), 404
    wav_bytes = Path(seg["wav_path"]).read_bytes()
    return Response(
        wav_bytes,
        status=200,
        mimetype="audio/wav",
        headers={"Content-Disposition": f'inline; filename="{segment_id}.wav"'},
    )


@app.delete("/omnivoice/segments/<segment_id>")
def omnivoice_segments_delete(segment_id: str):
    if not segment_library.delete_segment(segment_id):
        return jsonify({"error": "Unknown segment_id"}), 404
    return jsonify({"deleted": True})


@app.post("/omnivoice/segments/<segment_id>/project")
def omnivoice_segments_set_project(segment_id: str):
    """Assign or clear the Accent Design Project this segment belongs to (§4)."""
    data = request.get_json(silent=True) or {}
    project_id = data.get("project_id")
    project_name = data.get("project_name")
    meta = segment_library.set_segment_project(segment_id, project_id, project_name)
    if meta is None:
        return jsonify({"error": "Unknown segment_id"}), 404
    return jsonify(meta)


# (Time-stretch endpoints removed; duration is now controlled via generation-time durations parameter per-segment.)


@app.post("/omnivoice/stitch")
def omnivoice_stitch():
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    plan_kwargs: dict[str, Any] = {}
    if data.get("stitch_plan") is not None:
        resolved = _resolve_stitch_plan(data["stitch_plan"])
        if resolved is None:
            return jsonify({"error": "stitch_plan is malformed or references unknown clips"}), 400
        selected, plan_kwargs = resolved
    else:
        selected = _resolve_omnivoice_clips(data)
        if selected is None:
            return jsonify(
                {"error": "segment_ids or selections must be a list of known ids"}
            ), 400

    try:
        wav, sr = omnivoice_engine.stitch_selected(selected, plan=plan_kwargs or None)
        wav_bytes, media_type = _encode(wav, sr, "wav")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Stitch error: {exc}"}), 500
    return Response(wav_bytes, content_type=media_type)


@app.post("/omnivoice/save")
def omnivoice_save():
    # Persists a stitched OmniVoice clip into the same voice library /voice_design writes to
    # (voice_library.save_voice), so a clip assembled here is reusable everywhere voices are
    # (Speak page, /generate, /v1/audio/speech) instead of only existing as an ephemeral
    # in-browser preview blob.
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    plan_kwargs: dict[str, Any] = {}
    if data.get("stitch_plan") is not None:
        resolved = _resolve_stitch_plan(data["stitch_plan"])
        if resolved is None:
            return jsonify({"error": "stitch_plan is malformed or references unknown clips"}), 400
        selected, plan_kwargs = resolved
    else:
        selected = _resolve_omnivoice_clips(data)
        if selected is None:
            return jsonify(
                {"error": "segment_ids or selections must be a list of known ids"}
            ), 400
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
        wav, sr = omnivoice_engine.stitch_selected(selected, plan=plan_kwargs or None)
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
                "segment_ids": data.get("segment_ids"),
                "candidate_ids": data.get("selections"),
                "stitch_plan": data.get("stitch_plan"),
            },
            family_id=data.get("family_id"),
            variant_name=data.get("variant_name"),
            variant_kind=data.get("variant_kind"),
            source="OmniVoice",
            project_id=data.get("project_id"),
            project_name=data.get("project_name"),
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
    # No auth gate on this mutating route — deliberate decision (docs/dev/architecture/voice_design.md §8.8
    # security note): the whole service already runs unauthenticated on a trusted-network-only
    # posture (SECURITY.md), and this stays consistent with that rather than special-casing
    # one route.
    if (
        model.reconfig_in_progress()
        or voice_design.swap_in_progress()
        or omnivoice_engine.swap_in_progress()
    ):
        return jsonify({"error": "Another runtime reconfiguration or swap is already in progress"}), 503
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    dry_run = bool(data.pop("dry_run", False))
    if dry_run:
        # Read-only preview: no mutation, so no executor serialization needed.
        try:
            preview = model.preview_runtime_config(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(preview)
    try:
        state = model.executor.submit(model.apply_runtime_config, data).result(timeout=300)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Runtime config error: {exc}"}), 500
    return jsonify(state)


@app.post("/runtime/config/reset")
def runtime_config_reset():
    # Phase A7b: drop runtime.json (keeping locked keys) and revert unlocked persisted
    # keys to their hardcoded defaults. Same no-auth-gate rationale as the POST above.
    if (
        model.reconfig_in_progress()
        or voice_design.swap_in_progress()
        or omnivoice_engine.swap_in_progress()
    ):
        return jsonify({"error": "Another runtime reconfiguration or swap is already in progress"}), 503
    try:
        state = model.executor.submit(model.reset_runtime_config).result(timeout=300)
    except Exception as exc:
        return jsonify({"error": f"Runtime config reset error: {exc}"}), 500
    return jsonify(state)


@app.post("/generate")
def generate():
    # Bridge the same startup race /omnivoice/audition already queues through, instead
    # of hard-failing any request that lands before the background model load finishes.
    if not model._service_started and not _ensure_service_started(timeout_seconds=240):
        return jsonify({"error": "Model not loaded"}), 503
    if not _generation_ready():
        return jsonify({"error": "Model not loaded"}), 503
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    text, language = _generation_fields(data)
    if not text:
        return jsonify({"error": "text is required"}), 400
    repair_requested, repair_error = _generation_repair_requested(data)
    if repair_error:
        return jsonify({"error": repair_error}), 400
    fmt = _canonical_format(data.get("response_format"))
    if fmt not in _SUPPORTED_FORMATS:
        return jsonify({"error": f"unsupported response_format {fmt!r}; supported: "
                        f"{', '.join(sorted(_SUPPORTED_FORMATS))}"}), 400
    voice_id = (data.get("voice_id") or "").strip() or None
    voice_id, builtin_error = _resolve_builtin_voice(data, voice_id)
    if builtin_error:
        return jsonify({"error": builtin_error}), 400
    instruct = (data.get("instruct") or "").strip() or None
    seed = data.get("seed")
    if seed is not None and not isinstance(seed, int):
        return jsonify({"error": "seed must be an integer"}), 400
    resolved_seed = model.resolve_seed(seed)

    try:
        wav, sr, job_id = model.executor.submit(
            model._run_generate,
            text,
            language,
            voice_id=voice_id,
            voice_variant_id=data.get("voice_variant_id"),
            style_preset=data.get("style_preset"),
            postprocess=data.get("postprocess"),
            prosody_repair=repair_requested,
            seed_value=resolved_seed,
            instruct=instruct,
        ).result(timeout=480)
        audio, media_type = _encode(wav, sr, fmt)
    except Exception as exc:
        if isinstance(exc, RuntimeError) and "cache capacity exceeded" in str(exc):
            print(
                f"[OV-CAPACITY] capacity exceeded; text_len={len(text)}; "
                f"likely no EOS or REF_TEXT mismatch.",
                flush=True,
            )
            return jsonify({
                "error": (
                    "Generation aborted: model exceeded its allowed audio length. "
                    "This often indicates a mismatch between REF_TEXT and REF_AUDIO, "
                    "or text that is too long for this deployment's TTS_MAX_SPEECH_SECONDS. "
                    f"Current request text length: {len(text)}"
                )
            }), 422
        return jsonify({"error": f"Inference error: {exc}"}), 500
    response = Response(audio, content_type=media_type)
    response.headers["X-Seed"] = str(resolved_seed)
    if job_id:
        response.headers["X-Job-Id"] = job_id
        prog = model.get_job_progress(job_id)
        if prog:
            _add_generation_repair_headers(response, prog)
            if prog.get("applied_steps"):
                steps = prog["applied_steps"]
                response.headers["X-Applied-Steps"] = ", ".join(steps) if isinstance(steps, list) else str(steps)
    return response


@app.post("/generate/with_metrics")
def generate_with_metrics():
    # VariantCompare (frontend/src/components/VariantCompare.tsx) needs LUFS/pause/speech-rate
    # for freshly generated audio, not just the saved reference — /generate can't grow a JSON
    # response shape without breaking every existing raw-bytes caller, so this is a small
    # companion endpoint instead: same generation path as /generate, plus analyze_reference()
    # (the same metrics function used for saved voice references) run on the result.
    if not model._service_started and not _ensure_service_started(timeout_seconds=240):
        return jsonify({"error": "Model not loaded"}), 503
    if not _generation_ready():
        return jsonify({"error": "Model not loaded"}), 503
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    text, language = _generation_fields(data)
    if not text:
        return jsonify({"error": "text is required"}), 400
    repair_requested, repair_error = _generation_repair_requested(data)
    if repair_error:
        return jsonify({"error": repair_error}), 400
    voice_id = (data.get("voice_id") or "").strip() or None
    voice_id, builtin_error = _resolve_builtin_voice(data, voice_id)
    if builtin_error:
        return jsonify({"error": builtin_error}), 400
    instruct = (data.get("instruct") or "").strip() or None
    seed = data.get("seed")
    if seed is not None and not isinstance(seed, int):
        return jsonify({"error": "seed must be an integer"}), 400
    resolved_seed = model.resolve_seed(seed)

    try:
        wav, sr, job_id = model.executor.submit(
            model._run_generate,
            text,
            language,
            voice_id=voice_id,
            voice_variant_id=data.get("voice_variant_id"),
            style_preset=data.get("style_preset"),
            postprocess=data.get("postprocess"),
            prosody_repair=repair_requested,
            seed_value=resolved_seed,
            instruct=instruct,
        ).result(timeout=480)
        audio, media_type = _encode(wav, sr, "wav")
    except Exception as exc:
        if isinstance(exc, RuntimeError) and "cache capacity exceeded" in str(exc):
            return jsonify({
                "error": (
                    "Generation aborted: model exceeded its allowed audio length. "
                    f"Current request text length: {len(text)}"
                )
            }), 422
        return jsonify({"error": f"Inference error: {exc}"}), 500

    try:
        metrics = audio_style.analyze_reference(wav, sr, transcript=text)
    except Exception as exc:
        metrics = {"error": f"analysis failed: {exc}"}

    try:
        diagnoses = [
            d.to_dict()
            for d in audio_diagnostics.diagnose_take(metrics, guidance_scale=data.get("guidance_scale"))
        ]
    except Exception as exc:
        logger.warning(f"Take diagnostics failed: {exc}")
        diagnoses = []

    response_payload = {
        "audio_base64": base64.b64encode(audio).decode("ascii"),
        "media_type": media_type,
        "seed": resolved_seed,
        "metrics": metrics,
        "diagnoses": diagnoses,
    }
    if job_id:
        response_payload["job_id"] = job_id
        progress = model.get_job_progress(job_id)
        if progress and progress.get("prosody_repair"):
            response_payload["prosody_repair"] = progress["prosody_repair"]
    return jsonify(response_payload)


@app.post("/v1/audio/speech")
def openai_audio_speech():
    # Bridge the same startup race /omnivoice/audition already queues through, instead
    # of hard-failing any request that lands before the background model load finishes.
    if not model._service_started and not _ensure_service_started(timeout_seconds=240):
        return _openai_error("Model not loaded", 503, "api_error")
    if not _generation_ready():
        return _openai_error("Model not loaded", 503, "api_error")
    data = _json_body()
    if not data:
        return _openai_error("Invalid JSON", 400)
    text = (data.get("input") or data.get("text") or "").strip()
    if not text:
        return _openai_error("'input' is required", 400)
    repair_requested, repair_error = _generation_repair_requested(data)
    if repair_error:
        return _openai_error(repair_error, 400)
    fmt = _canonical_format(data.get("response_format"))
    if fmt not in _SUPPORTED_FORMATS:
        return _openai_error(
            f"unsupported response_format {fmt!r}; supported: "
            f"{', '.join(sorted(_SUPPORTED_FORMATS))}",
            400,
        )
    language = (data.get("language") or "English").strip()
    # OpenAI SDK sends "voice", our internal convention uses "voice_id" — accept both.
    voice_id = (data.get("voice_id") or data.get("voice") or "").strip() or None
    voice_id, builtin_error = _resolve_builtin_voice(data, voice_id)
    if builtin_error:
        return _openai_error(builtin_error, 400)
    instruct = (data.get("instruct") or "").strip() or None
    seed = data.get("seed")
    if seed is not None and not isinstance(seed, int):
        return _openai_error("seed must be an integer", 400)
    resolved_seed = model.resolve_seed(seed)

    # Pocket-TTS streaming path: Hermes TTS streaming via OpenAI SDK with_streaming_response.
    # Returns chunked PCM (int16 LE, 24kHz) — no post-processing for low latency.
    # Only activates for PCM format (Hermes requirement); mp3/wav use batch for compatibility.
    if (
        model.TTS_BACKEND == "pocket_tts"
        and fmt == "pcm"
        and not repair_requested
    ):
        return _openai_audio_speech_stream_pocket_tts(
            text, language, voice_id, resolved_seed, instruct, data
        )

    # Batch path: all other backends/formats, plus repair-enabled requests.
    try:
        wav, sr, job_id = model.executor.submit(
            model._run_generate,
            text,
            language,
            voice_id=voice_id,
            voice_variant_id=data.get("voice_variant_id"),
            style_preset=data.get("style_preset"),
            postprocess=data.get("postprocess"),
            prosody_repair=repair_requested,
            seed_value=resolved_seed,
            instruct=instruct,
        ).result(timeout=480)
        audio, media_type = _encode(wav, sr, fmt)
    except Exception as exc:
        if isinstance(exc, RuntimeError) and "cache capacity exceeded" in str(exc):
            print(
                f"[OV-CAPACITY] capacity exceeded; text_len={len(text)}; "
                f"likely no EOS or REF_TEXT mismatch.",
                flush=True,
            )
            return _openai_error(
                "Generation aborted: model exceeded its allowed audio length. "
                "This often indicates a mismatch between REF_TEXT and REF_AUDIO, "
                "or text that is too long for this deployment's TTS_MAX_SPEECH_SECONDS.",
                422,
                "invalid_request_error",
            )
        return _openai_error(f"Inference error: {exc}", 500, "api_error")
    response = Response(audio, content_type=media_type)
    response.headers["X-Seed"] = str(resolved_seed)
    if job_id:
        response.headers["X-Job-Id"] = job_id
        prog = model.get_job_progress(job_id)
        if prog:
            _add_generation_repair_headers(response, prog)
            if prog.get("voice_family_id"):
                response.headers["X-Voice-Family-Id"] = prog["voice_family_id"]
            if prog.get("variant_kind"):
                response.headers["X-Variant-Kind"] = prog["variant_kind"]
            if prog.get("style_preset"):
                response.headers["X-Style-Preset"] = prog["style_preset"]
            if prog.get("postprocess_applied"):
                response.headers["X-Postprocess-Applied"] = "true"
            if prog.get("audio_seconds"):
                response.headers["X-Audio-Seconds"] = str(prog["audio_seconds"])
            if prog.get("rtf"):
                response.headers["X-RTF"] = str(prog["rtf"])
            if prog.get("applied_steps"):
                steps = prog["applied_steps"]
                response.headers["X-Applied-Steps"] = ", ".join(steps) if isinstance(steps, list) else str(steps)
    return response


def _openai_audio_speech_stream_pocket_tts(
    text: str,
    language: str,
    voice_id: str | None,
    resolved_seed: int | None,
    instruct: str | None,
    data: dict,
):
    """Stream Pocket-TTS audio as raw PCM for Hermes TTS streaming integration."""
    if instruct:
        print(f"[audio/stream] instruct field ignored on Pocket-TTS: {instruct!r}", flush=True)

    events: "queue.Queue[tuple[str, Any]]" = queue.Queue()

    def produce() -> None:
        try:
            for pcm_chunk in model._run_generate_pocket_tts_stream(
                text,
                language,
                voice_id=voice_id,
                seed_value=resolved_seed,
            ):
                events.put(("audio", pcm_chunk))
        except Exception as exc:
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
                print(f"[audio/stream] error: {payload}", flush=True)
                raise RuntimeError(f"streaming inference failed: {payload}") from payload
            else:
                future.result()
                return

    return Response(
        body(),
        content_type="audio/pcm",
        headers={
            "X-Seed": str(resolved_seed) if resolved_seed is not None else "",
            "X-Audio-Sample-Rate": "24000",
            "X-Audio-Channels": "1",
            "X-Audio-Bits": "16",
        },
        direct_passthrough=True,
    )

@app.post("/generate/async")
def generate_async():
    """Start a generation job and return immediately with job_id.

    Caller then polls /generate/progress?job_id=... for live progress/ETA and cancel.
    """
    if not model._service_started and not _ensure_service_started(timeout_seconds=240):
        return jsonify({"error": "Model not loaded"}), 503
    if not _generation_ready():
        return jsonify({"error": "Model not loaded"}), 503
    data = _json_body()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    text, language = _generation_fields(data)
    if not text:
        return jsonify({"error": "text is required"}), 400
    repair_requested, repair_error = _generation_repair_requested(data)
    if repair_error:
        return jsonify({"error": repair_error}), 400
    fmt = _canonical_format(data.get("response_format"))
    if fmt not in _SUPPORTED_FORMATS:
        return jsonify({"error": f"unsupported response_format {fmt!r}; supported: "
                        f"{', '.join(sorted(_SUPPORTED_FORMATS))}"}), 400
    voice_id = (data.get("voice_id") or "").strip() or None
    voice_id, builtin_error = _resolve_builtin_voice(data, voice_id)
    if builtin_error:
        return jsonify({"error": builtin_error}), 400
    instruct = (data.get("instruct") or "").strip() or None
    seed = data.get("seed")
    if seed is not None and not isinstance(seed, int):
        return jsonify({"error": "seed must be an integer"}), 400
    resolved_seed = model.resolve_seed(seed)

    # Pre-create the job so the frontend knows the job_id immediately.
    job = model._create_job(text, seed=resolved_seed)
    job_id = job.job_id
    if hasattr(job, "metadata"):
        job.metadata["prosody_repair"] = {
            "requested": repair_requested,
            "outcome": "pending" if repair_requested else "not_requested",
            "budget_seconds": None,
            "duration_seconds": None,
            "boundary_count": 0,
        }
    active_job_id = job_id

    def _run():
        try:
            wav, sr, _completed_job_id = model.executor.submit(
                model._run_generate,
                text,
                language,
                voice_id=voice_id,
                voice_variant_id=data.get("voice_variant_id"),
                style_preset=data.get("style_preset"),
                postprocess=data.get("postprocess"),
                prosody_repair=repair_requested,
                seed_value=resolved_seed,
                instruct=instruct,
                job_id=active_job_id,
            ).result(timeout=480)
            audio, media_type = _encode(wav, sr, fmt)
        except Exception as exc:
            with model._active_jobs_lock:
                j = model._active_jobs.get(active_job_id)
            if j:
                j.status = "failed"
                j.error = str(exc)
        finally:
            # Clean up after some time; caller has downloaded audio.
            import time as _t
            _t.sleep(120)
            model._cleanup_job(active_job_id)

    threading.Thread(target=_run, daemon=True).start()

    return jsonify({
        "job_id": job_id,
        "prosody_repair": {
            "requested": repair_requested,
            "outcome": "pending" if repair_requested else "not_requested",
        },
    })


@app.get("/generate/progress")
def generate_progress():
    """Return live progress for an async generation job."""
    job_id = request.args.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id query parameter is required"}), 400

    with model._active_jobs_lock:
        job = model._active_jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Unknown or expired job_id"}), 404

    # Build a rich progress response from the job state.
    prog = model.get_job_progress(job_id)
    if prog is None:
        return jsonify({"error": "Unknown or expired job_id"}), 404

    # Add status-specific data.
    if job.status == "completed":
        prog["audio_available"] = True
    elif job.status in ("cancelled", "failed"):
        # If cancelled, there may be partial audio; still expose it.
        prog["audio_available"] = job.wav is not None and job.sr > 0

    return jsonify(prog)


@app.post("/generate/cancel")
def generate_cancel():
    """Cancel an async generation job cooperatively."""
    job_id = (request.args.get("job_id") or "").strip()
    if not job_id:
        # Also check JSON body.
        data = _json_body()
        if data:
            job_id = (data.get("job_id") or "").strip()
    if not job_id:
        return jsonify({"error": "job_id is required"}), 400

    cancelled = model.cancel_job(job_id)
    if not cancelled:
        return jsonify({"error": "Unknown or not-running job_id"}), 404

    return jsonify({"cancelled": True, "job_id": job_id})


@app.get("/generate/job/<job_id>/audio")
def generate_job_audio(job_id: str):
    """Return the audio for a completed or cancelled (partial) generation job."""
    with model._active_jobs_lock:
        job = model._active_jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Unknown or expired job_id"}), 404

    if job.status not in ("completed", "cancelled"):
        return jsonify({"error": "Job not completed yet"}), 400

    wav = job.wav
    sr = job.sr
    if wav is None or sr <= 0:
        return jsonify({"error": "No audio available"}), 404

    fmt = (request.args.get("response_format") or "mp3").strip().lower()
    try:
        audio_bytes, media_type = _encode(wav, sr, fmt)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    response = Response(audio_bytes, content_type=media_type)
    if job.seed is not None:
        response.headers["X-Seed"] = str(job.seed)
    response.headers["X-Job-Id"] = job_id
    prog = model.get_job_progress(job_id)
    if prog:
        _add_generation_repair_headers(response, prog)
        if prog.get("style_preset"):
            response.headers["X-Style-Preset"] = prog["style_preset"]
        if prog.get("postprocess_applied"):
            response.headers["X-Postprocess-Applied"] = "true"
        if prog.get("audio_seconds"):
            response.headers["X-Audio-Seconds"] = str(prog["audio_seconds"])
        if prog.get("rtf"):
            response.headers["X-RTF"] = str(prog["rtf"])
        if prog.get("applied_steps"):
            steps = prog["applied_steps"]
            response.headers["X-Applied-Steps"] = ", ".join(steps) if isinstance(steps, list) else str(steps)
    return response


# ── Streaming endpoint ─────────────────────────────────────────────────────────────────────

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
    repair_requested, repair_error = _generation_repair_requested(data)
    if repair_error:
        return jsonify({"error": repair_error}), 400
    if repair_requested:
        return jsonify({
            "error": (
                "prosody_repair is not supported by /generate/stream; "
                "use /generate or /generate/async for complete-file repair"
            )
        }), 400
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

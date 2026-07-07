import gc
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Apply thread and runtime envs before heavy imports
from qwen3_tts.asr_check import validate_reference_text
from qwen3_tts.config import REF_AUDIO_PATH, apply_preset_env
from qwen3_tts.openvino.runtime_config import apply_thread_env, resolve_inference_threads
from qwen3_tts.presets import get_voice_design_preset, seconds_for_capacity

apply_preset_env()

apply_thread_env()

import torch

from qwen3_tts.model_config import (
    configure_hf_token,
    resolve_model_repo,
    resolve_torch_load_config,
    resolve_voice_design_model_repo,
)
from qwen3_tts.streaming import StreamingVocoderSession
from qwen3_tts.transformers_compat import (
    patch_eager_attention_mask_broadcast,
    patch_talker_prepare_inputs,
    repair_rotary_buffers,
)

configure_hf_token()

from qwen_tts import Qwen3TTSModel

MODEL_ID = resolve_model_repo()
MODEL_REVISION = os.getenv("MODEL_REVISION") or None
DEVICE = os.getenv("DEVICE", "cpu")
REF_AUDIO = os.getenv("REF_AUDIO", REF_AUDIO_PATH)
REF_TEXT = os.getenv(
    "REF_TEXT",
    "Welcome to Rosies. What can I get for you today? You know, Im a good girl. "
    "You want me, dont you? I am on the menu too.",
)

TTS_BACKEND = (os.getenv("TTS_BACKEND", "pytorch") or "pytorch").strip().lower()
IDLE_UNLOAD_SECONDS = int(os.environ.get("IDLE_UNLOAD_SECONDS", "0") or "0")
OV_MODEL_DIR = os.getenv("OV_MODEL_DIR")
OPENVINO_RELEASE_TORCH = os.getenv("OPENVINO_RELEASE_TORCH", "0").strip() == "1"
OPENVINO_MAIN_STATEFUL_MODEL = (os.getenv("OPENVINO_MAIN_STATEFUL_MODEL") or "").strip() or None
OPENVINO_PREDICTOR_STATEFUL_MODEL = (
    (os.getenv("OPENVINO_PREDICTOR_STATEFUL_MODEL") or "").strip() or None
)
TORCH_DTYPE, TORCH_DTYPE_NAME, OPENVINO_LOW_CPU_MEM_USAGE = resolve_torch_load_config(torch)

torch.set_num_threads(resolve_inference_threads())


@dataclass(frozen=True)
class ModelProfile:
    """A checkpoint + IR pairing that ``load_model`` can install.

    ``load_model()`` used to read MODEL_ID/OV_MODEL_DIR/etc. as module-level
    constants computed once at import time. Swapping in a second checkpoint (e.g.
    VoiceDesign, see docs/dev/architecture/voice_design.md) needs those to vary per call,
    so they now travel as a profile instead. OVTalkerRuntime still reads its IR
    paths from the environment (OV_MODEL_DIR / OPENVINO_*_STATEFUL_MODEL), so
    ``load_model`` writes the profile's values into ``os.environ`` before
    constructing it — the env vars stay the single source of truth for that layer.
    """

    name: str
    model_repo: str
    revision: str | None
    ov_model_dir: str | None
    main_stateful_model: str | None
    predictor_stateful_model: str | None
    vocoder_dir: str | None = None
    build_voice_clone_prompt: bool = True
    ref_audio: str | None = None
    ref_text: str | None = None


BASE_PROFILE = ModelProfile(
    name="base",
    model_repo=MODEL_ID,
    revision=MODEL_REVISION,
    ov_model_dir=OV_MODEL_DIR,
    main_stateful_model=OPENVINO_MAIN_STATEFUL_MODEL,
    predictor_stateful_model=OPENVINO_PREDICTOR_STATEFUL_MODEL,
    vocoder_dir=os.getenv("OPENVINO_VOCODER_DIR"),
    build_voice_clone_prompt=True,
    ref_audio=REF_AUDIO,
    ref_text=REF_TEXT,
)

_voice_design_max_speech_seconds = os.getenv("VOICE_DESIGN_MAX_SPEECH_SECONDS", "").strip()
_voice_design_preset = get_voice_design_preset(
    os.getenv("VOICE_DESIGN_MODEL_SIZE"),
    float(_voice_design_max_speech_seconds) if _voice_design_max_speech_seconds else None,
)

# VoiceDesign is never the model loaded at startup — it is only ever installed via the
# lazy model-swap path in qwen3_tts.voice_design (docs/dev/architecture/voice_design.md §3/§4.2).
# generate_voice_design() synthesizes the sample_text directly from the description; there
# is no reference audio/transcript to build a voice_clone_prompt from.
VOICE_DESIGN_PROFILE = ModelProfile(
    name="voice_design",
    model_repo=resolve_voice_design_model_repo(),
    revision=(os.getenv("VOICE_DESIGN_MODEL_REVISION") or "").strip() or None,
    ov_model_dir=_voice_design_preset["ov_model_dir"],
    main_stateful_model=_voice_design_preset["main_stateful_model"],
    predictor_stateful_model=_voice_design_preset["predictor_stateful_model"],
    vocoder_dir=_voice_design_preset["vocoder_dir"],
    build_voice_clone_prompt=False,
)

model = None
voice_clone_prompt = None
active_profile: ModelProfile | None = None

ov_metadata = None
ov_config = None
ov_runtime = None

executor = ThreadPoolExecutor(max_workers=1)

_service_started: bool = False
_model_loaded: bool = False
_startup_failed: bool = False
_startup_error: str | None = None
_last_request_time: float = time.time()
_unload_pending: bool = False
_ref_text_validation_result: dict | None = None


def _process_rss_mib() -> float | None:
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except Exception:
        pass
    return None


def _touch_last_request():
    global _last_request_time, _unload_pending
    _last_request_time = time.time()
    _unload_pending = False


def force_unload():
    """Unconditionally drop the loaded model/runtime and return freed heap to the OS.

    Runs inside the executor thread; serialized with inference. Used by the idle-unload
    watcher (via ``_do_unload``, which adds the idle-timeout gate) and by the VoiceDesign
    model-swap manager (``qwen3_tts.voice_design``), which must unload unconditionally
    regardless of how recently a request came in.
    """
    global model, voice_clone_prompt, ov_runtime
    if model is None:
        return
    model = None
    voice_clone_prompt = None
    ov_runtime = None
    # Unload Pocket TTS model/runtime if loaded (safe no-op if not).
    try:
        from qwen3_tts import pocket_tts_runtime
        pocket_tts_runtime.unload_pocket_tts()
    except Exception:
        pass
    gc.collect()
    gc.collect()
    # Ask glibc to return freed heap to the OS. No-op with jemalloc (which handles
    # this automatically via its background thread), harmless either way.
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass
    print("[app_worker] Model unloaded.", flush=True)


_foreign_engines: list[tuple[Callable[[], bool], Callable[[], None]]] = []


def register_foreign_engine(is_loaded: Callable[[], bool], unload: Callable[[], None]) -> None:
    """Let a bespoke swap-manager participate in idle-unload and Base-priority swap-back.

    OmniVoice (qwen3_tts.omnivoice_engine) is the only current user: unlike VoiceDesign,
    it's a third-party checkpoint that never goes through load_model()/active_profile (it
    isn't wired through OVTalkerRuntime), so this module has no visibility into it unless
    the engine registers itself.
    """
    _foreign_engines.append((is_loaded, unload))


def _any_foreign_loaded() -> bool:
    return any(is_loaded() for is_loaded, _ in _foreign_engines)


def unload_foreign_models() -> None:
    for is_loaded, unload in _foreign_engines:
        if is_loaded():
            unload()


def _do_unload():
    """Runs inside the executor thread; serialized with inference."""
    global _unload_pending
    _unload_pending = False
    if model is None and not _any_foreign_loaded():
        return
    if time.time() - _last_request_time < IDLE_UNLOAD_SECONDS:
        return
    print("[app_worker] Idle timeout reached; unloading model to free RAM...", flush=True)
    force_unload()
    unload_foreign_models()


def _ensure_base_loaded():
    """Runs inside the executor thread. /generate and /v1/audio/speech always need the
    Base voice-clone checkpoint. Design engines (VoiceDesign, OmniVoice) are left resident
    after their own requests instead of eagerly swapping back to Base every time — so this
    swaps back on demand, unloading whatever design engine was left loaded.
    """
    if model is not None and active_profile is BASE_PROFILE and not _any_foreign_loaded():
        return
    print("[app_worker] Swapping back to Base for generation request...", flush=True)
    unload_foreign_models()
    force_unload()
    load_model(BASE_PROFILE)


def _validate_ov_metadata(model_dir: str, model_repo: str, revision: str | None):
    global ov_metadata, ov_config
    path = Path(model_dir)
    meta_path = path / "metadata.json"
    if not meta_path.is_file():
        raise RuntimeError(f"OV_MODEL_DIR missing metadata.json: {meta_path}")

    ov_metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    from qwen3_tts.openvino.runtime_config import get_ov_config, resolve_inference_threads
    ov_config = get_ov_config()

    # Validate metadata matches loaded model
    if ov_metadata.get("model_repo") != model_repo:
        raise RuntimeError(
            f"OV metadata model_repo {ov_metadata.get('model_repo')!r} "
            f"!= {model_repo!r}"
        )

    # Revision check: only enforced when a revision is explicitly pinned. When it is
    # unset, accept whatever the export recorded (an auto-resolved commit SHA or "main"),
    # so easy/ad-hoc exports don't block worker startup.
    artifact_revision = ov_metadata.get("model_revision")
    if revision and artifact_revision != revision:
        raise RuntimeError(
            f"OV metadata model_revision {artifact_revision!r} != pinned {revision!r}"
        )
    if not revision:
        print(
            f"[app_worker] revision unpinned; accepting artifact revision "
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


def load_model(profile: ModelProfile | None = None):
    global model, voice_clone_prompt, ov_runtime, active_profile
    global MODEL_ID, OV_MODEL_DIR, OPENVINO_MAIN_STATEFUL_MODEL, OPENVINO_PREDICTOR_STATEFUL_MODEL

    profile = profile or BASE_PROFILE

    if TTS_BACKEND not in ("pytorch", "openvino", "pocket_tts"):
        raise RuntimeError(f"Invalid TTS_BACKEND: {TTS_BACKEND!r}")

    if TTS_BACKEND == "openvino":
        if not profile.ov_model_dir:
            raise RuntimeError(
                "TTS_BACKEND=openvino requires OV_MODEL_DIR"
            )
        # Downstream OpenVINO helpers (get_ov_config, OVTalkerRuntime) read their IR
        # paths from the environment, not from this function's arguments, so mirror
        # the active profile into os.environ before anything reads it.
        os.environ["OV_MODEL_DIR"] = profile.ov_model_dir
        if profile.main_stateful_model:
            os.environ["OPENVINO_MAIN_STATEFUL_MODEL"] = profile.main_stateful_model
        else:
            os.environ.pop("OPENVINO_MAIN_STATEFUL_MODEL", None)
        if profile.predictor_stateful_model:
            os.environ["OPENVINO_PREDICTOR_STATEFUL_MODEL"] = profile.predictor_stateful_model
        else:
            os.environ.pop("OPENVINO_PREDICTOR_STATEFUL_MODEL", None)
        if profile.vocoder_dir:
            os.environ["OPENVINO_VOCODER_DIR"] = profile.vocoder_dir
        else:
            os.environ.pop("OPENVINO_VOCODER_DIR", None)

        _validate_ov_metadata(profile.ov_model_dir, profile.model_repo, profile.revision)

    # ── Pocket TTS backend branch ──────────────────────────────────────────────
    if TTS_BACKEND == "pocket_tts":
        from qwen3_tts import pocket_tts_runtime

        language = (os.getenv("POCKET_TTS_LANGUAGE") or "english").strip() or "english"
        temp = float(os.getenv("POCKET_TTS_TEMP", "0.7"))
        lsd_steps = int(os.getenv("POCKET_TTS_LSD_DECODE_STEPS", "1"))
        eos_threshold = float(os.getenv("POCKET_TTS_EOS_THRESHOLD", "-4.0"))
        noise_clamp_raw = os.getenv("POCKET_TTS_NOISE_CLAMP", "").strip()
        noise_clamp = float(noise_clamp_raw) if noise_clamp_raw else None
        frames_after_eos_raw = os.getenv("POCKET_TTS_FRAMES_AFTER_EOS", "").strip()
        frames_after_eos = int(frames_after_eos_raw) if frames_after_eos_raw else None
        quantize = int(os.getenv("POCKET_TTS_QUANTIZE", "0"))

        pocket_tts_runtime.load_pocket_tts_model(
            language=language,
            temp=temp,
            lsd_decode_steps=lsd_steps,
            eos_threshold=eos_threshold,
            noise_clamp=noise_clamp,
            frames_after_eos=frames_after_eos,
            quantize=bool(quantize),
        )

        model = pocket_tts_runtime.pocket_tts_model

        voice_clone_prompt = pocket_tts_runtime.build_default_voice_state(
            model,
            profile.ref_audio,
        )

        active_profile = profile

        global _service_started, _model_loaded, _ref_text_validation_result
        _service_started = True
        _model_loaded = True

        _ref_text_validation_result = {
            "severity": "info",
            "suggestion": "Pocket TTS ignores REF_TEXT; clones from REF_AUDIO only.",
        }

        print("[app_worker] Pocket TTS loaded and ready", flush=True)

    # ── PyTorch / OpenVINO backends (unchanged) ────────────────────────────────
    elif TTS_BACKEND in ("pytorch", "openvino"):
        # PyTorch-only backend log
        if TTS_BACKEND == "pytorch" and profile.ov_model_dir:
            print(
                "[app_worker] OV_MODEL_DIR set but TTS_BACKEND=pytorch; "
                "ignoring OpenVINO directory.",
                flush=True,
            )

        print(
            f"[app_worker] Backend={TTS_BACKEND}, loading profile={profile.name!r} "
            f"({profile.model_repo}) at {TORCH_DTYPE_NAME} "
            f"(low_cpu_mem_usage={OPENVINO_LOW_CPU_MEM_USAGE})...",
            flush=True,
        )
        wrapped = Qwen3TTSModel.from_pretrained(
            profile.model_repo,
            revision=profile.revision,
            device_map=DEVICE,
            dtype=TORCH_DTYPE,
            low_cpu_mem_usage=OPENVINO_LOW_CPU_MEM_USAGE,
        )
        rotary_report = repair_rotary_buffers(wrapped.model, torch)
        print(f"[app_worker] Repaired and validated RoPE buffers: {rotary_report}", flush=True)

        # T5-generation fixes for both backends: stale inputs_embeds + input_ids clip + attention_mask.
        patch_talker_prepare_inputs()

        # Fix attention_mask Q/K broadcast bug in eager_attention_forward (PyTorch backend).
        patch_eager_attention_mask_broadcast()

        gc.collect()

        model = wrapped
        voice_clone_prompt = None
        if profile.build_voice_clone_prompt:
            print("[app_worker] Model loaded. Creating voice clone prompt...", flush=True)
            voice_clone_prompt = model.create_voice_clone_prompt(
                ref_audio=profile.ref_audio,
                ref_text=profile.ref_text,
                x_vector_only_mode=False,
            )

            # Opt-in, deterministic artifact for controlled Transformers 4/5 comparisons.
            # The dump contains codec token IDs and package versions, never reference audio/text.
            _prompt_dump_dir = os.getenv("TTS_PROMPT_DUMP_DIR", "").strip()
            if not _prompt_dump_dir and os.path.exists("/tmp/tts_prompt_dump"):
                _prompt_dump_dir = "/tmp/tts-prompt-dump"
            if _prompt_dump_dir:
                from qwen3_tts.prompt_diagnostics import (
                    dump_reference_prompt,
                    dump_talker_parameter_manifest,
                )

                manifest_path = dump_reference_prompt(voice_clone_prompt, _prompt_dump_dir)
                print(f"[prompt_diag] reference prompt saved: {manifest_path}", flush=True)
                parameter_path = dump_talker_parameter_manifest(model.model.talker, _prompt_dump_dir)
                print(f"[prompt_diag] talker parameters saved: {parameter_path}", flush=True)
        else:
            print("[app_worker] Model loaded. (profile skips voice clone prompt)", flush=True)

        # Validate REF_TEXT against REF_AUDIO at startup.
        global _ref_text_validation_result
        if profile.build_voice_clone_prompt and profile.ref_audio and profile.ref_text:
            _ref_text_validation_result = validate_reference_text(
                profile.ref_audio, profile.ref_text
            )
            sev = _ref_text_validation_result["severity"]
            if sev in ("fail", "no_speech"):
                print(
                    f"[REF-TEXT-VALID] STATUS=fail  score={_ref_text_validation_result.get('match_score')}",
                    flush=True,
                    file=sys.stderr,
                )
                print(f"  REF_AUDIO: {profile.ref_audio}", flush=True, file=sys.stderr)
                print(f"  REF_TEXT:  {profile.ref_text!r}", flush=True, file=sys.stderr)
                print(f"  Whisper:   {_ref_text_validation_result.get('whisper_transcript')!r}", flush=True, file=sys.stderr)
                print(f"  SUGGESTION: {_ref_text_validation_result.get('suggestion')}", flush=True, file=sys.stderr)
                print(
                    "  ACTION: Fix REF_TEXT in your .env or Compose file to match what's spoken in the audio, then restart.",
                    flush=True,
                    file=sys.stderr,
                )
                if os.getenv("REF_TEXT_FAIL_ON_MISMATCH", "").strip() == "1":
                    raise RuntimeError(
                        "REF_TEXT/REF_AUDIO mismatch (REF_TEXT_FAIL_ON_MISMATCH=1): "
                        f"{_ref_text_validation_result.get('suggestion')}"
                    )
            elif sev == "warn":
                print(
                    f"[REF-TEXT-VALID] STATUS=warn  score={_ref_text_validation_result.get('match_score')}",
                    flush=True,
                    file=sys.stderr,
                )
                print(f"  REF_AUDIO: {profile.ref_audio}", flush=True, file=sys.stderr)
                print(f"  REF_TEXT:  {profile.ref_text!r}", flush=True, file=sys.stderr)
                print(f"  Whisper:   {_ref_text_validation_result.get('whisper_transcript')!r}", flush=True, file=sys.stderr)
                print(f"  SUGGESTION: {_ref_text_validation_result.get('suggestion')}", flush=True, file=sys.stderr)
        else:
            _ref_text_validation_result = None

        if TTS_BACKEND == "openvino":
            # Milestone 4: install the OpenVINO talker runtime by swapping the two inner
            # transformer core forwards. All other generation glue stays in PyTorch.
            from qwen3_tts.openvino.talker import OVTalkerRuntime

            talker = model.model.talker
            # speech_tokenizer is a sibling of talker on the parent model, not a child of it;
            # pass it explicitly so the OV vocoder patch can find it.
            ov_runtime = OVTalkerRuntime(
                profile.ov_model_dir, talker, ov_config=ov_config,
                speech_tokenizer=model.model.speech_tokenizer,
            )
            ov_runtime.install()

            # The codec encoder has done its one job (voice_clone_prompt was built above) and
            # the OV vocoder now owns decode, so free the ~0.3 GiB PyTorch speech_tokenizer.
            # Self-gates on OPENVINO_KEEP_CODEC_ENCODER; no-op when set (the default) so
            # per-request/voice_id cloning keeps working.
            ov_runtime.release_codec()

            # Startup policy logs
            if OPENVINO_RELEASE_TORCH:
                print(
                    "[app_worker] OPENVINO_RELEASE_TORCH active: "
                    "PyTorch core weights may be released during OpenVINO compilation.",
                    flush=True,
                )
            if profile.main_stateful_model:
                print(
                    f"[app_worker] OPENVINO_MAIN_STATEFUL_MODEL active: "
                    f"{profile.main_stateful_model}",
                    flush=True,
                )
            if profile.predictor_stateful_model:
                print(
                    f"[app_worker] OPENVINO_PREDICTOR_STATEFUL_MODEL active: "
                    f"{profile.predictor_stateful_model}",
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

        # Mirror the active profile into the module-level constants that health_state()
        # and callers still read directly, so behavior is unchanged when profile is None
        # (BASE_PROFILE) and correct when a non-base profile is swapped in.
        MODEL_ID = profile.model_repo
        OV_MODEL_DIR = profile.ov_model_dir
        OPENVINO_MAIN_STATEFUL_MODEL = profile.main_stateful_model
        OPENVINO_PREDICTOR_STATEFUL_MODEL = profile.predictor_stateful_model
        active_profile = profile

        global _service_started, _model_loaded
        _service_started = True
        _model_loaded = True
        print(f"[app_worker] Model loaded and ready (profile={profile.name!r}).")


def model_loaded() -> bool:
    return _model_loaded


def _load_model_background():
    global _service_started, _startup_failed, _startup_error
    try:
        load_model(BASE_PROFILE)
    except Exception as exc:
        _startup_failed = True
        _startup_error = str(exc)
        print(
            f"[app_worker] FATAL: model load failed: {exc}",
            flush=True,
            file=sys.stderr,
        )
        raise


import sys
threading.Thread(target=_load_model_background, daemon=True, name="model-loader").start()


def _idle_watcher():
    # Always runs (not gated on the startup value of IDLE_UNLOAD_SECONDS) so that
    # apply_runtime_config() can flip idle-unload on/off live by just reassigning the
    # global — there's no separate thread lifecycle to manage.
    while True:
        time.sleep(30)
        global _unload_pending
        if (
            IDLE_UNLOAD_SECONDS > 0
            and not _unload_pending
            and (model is not None or _any_foreign_loaded())
            and time.time() - _last_request_time > IDLE_UNLOAD_SECONDS
        ):
            _unload_pending = True
            executor.submit(_do_unload)


threading.Thread(target=_idle_watcher, daemon=True, name="idle-watcher").start()
if IDLE_UNLOAD_SECONDS > 0:
    print(f"[app_worker] Idle unload enabled: {IDLE_UNLOAD_SECONDS}s cooldown.", flush=True)


def health_state() -> dict[str, Any]:
    """Return JSON-serializable model and backend readiness state."""
    if _startup_failed:
        return {
            "status": "error",
            "service_started": False,
            "model_loaded": False,
            "error": _startup_error,
        }

    idle_unload_seconds = IDLE_UNLOAD_SECONDS if IDLE_UNLOAD_SECONDS > 0 else None
    base = {
        "status": "ok",
        "model_loaded": model is not None,
        # Distinct from model_loaded: stays true forever after the first successful load,
        # even through later idle-unload cycles. Lets callers tell "never loaded yet, please
        # wait" apart from "idle-unloaded, will lazy-reload transparently on next request".
        "service_started": _service_started,
        "process_rss_mib": _process_rss_mib(),
        "idle_unload_seconds": idle_unload_seconds,
        "backend": TTS_BACKEND,
        "model": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "device": DEVICE,
        "torch_dtype": TORCH_DTYPE_NAME,
        "low_cpu_mem_usage": OPENVINO_LOW_CPU_MEM_USAGE,
        "ref_audio": REF_AUDIO,
        "ref_text_validation": _ref_text_validation_result,
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
                    "cache_dir": ov_config.get("CACHE_DIR"),
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
                    "max_speech_seconds": (
                        seconds_for_capacity(main_capacity)
                        if (main_capacity := getattr(getattr(ov_runtime, "main", None), "capacity", None))
                        is not None
                        else None
                    ),
                    "release_torch": OPENVINO_RELEASE_TORCH,
                    "vocoder": vocoder_info,
                }
            }
        )

    # Pocket TTS health metadata
    if TTS_BACKEND == "pocket_tts":
        base["pocket_tts"] = {
            "backend": "pocket_tts",
            "runtime_wired": True,
            "language": os.getenv("POCKET_TTS_LANGUAGE", "english"),
        }

    def _json_safe(obj):
        if isinstance(obj, Path):
            return obj.as_posix()
        if isinstance(obj, dict):
            return {k: _json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_json_safe(v) for v in obj]
        return obj

    return _json_safe(base)


# ── Runtime control panel (docs/dev/architecture/voice_design.md §8.8) ──────────────────────────────────
#
# Category 1 (live-adjustable): applied via apply_runtime_config(), always inside
# model.executor so it never races inference. Two flavors:
#   - "hot" keys are read fresh from os.environ on every use elsewhere in this module
#     (SILENCE_TRIM*), so just writing the env var is enough.
#   - "reload" keys are only read inside load_model()/_validate_ov_metadata() at call
#     time, so they need force_unload() + load_model(active_profile) to take effect
#     (TTS_BACKEND, OV_DYNAMIC_QUANT_GROUP_SIZE) or are read directly by the idle
#     watcher loop each tick (IDLE_UNLOAD_SECONDS, effectively "hot" too but listed here
#     since it's a plain global rather than an os.environ lookup).
_HOT_ENV_KEYS = {"SILENCE_TRIM", "SILENCE_TRIM_THRESH", "SILENCE_TRIM_PAD_MS"}
_RELOAD_ENV_KEYS = {"OV_DYNAMIC_QUANT_GROUP_SIZE"}
_GLOBAL_KEYS = {"TTS_BACKEND", "IDLE_UNLOAD_SECONDS"}
_POCKET_TTS_RUNTIME_KEYS = {
    "POCKET_TTS_TEMP",
    "POCKET_TTS_LSD_DECODE_STEPS",
    "POCKET_TTS_EOS_THRESHOLD",
    "POCKET_TTS_NOISE_CLAMP",
    "POCKET_TTS_FRAMES_AFTER_EOS",
}
LIVE_RUNTIME_KEYS = _HOT_ENV_KEYS | _RELOAD_ENV_KEYS | _GLOBAL_KEYS | _POCKET_TTS_RUNTIME_KEYS

_reconfig_in_progress = False


def reconfig_in_progress() -> bool:
    return _reconfig_in_progress


def runtime_config_state() -> dict[str, Any]:
    """Snapshot of every knob the runtime control panel can show, in its three categories."""
    mounts = {
        "model_cache": os.getenv("MODEL_CACHE_CONTAINER_PATH", "/root/.cache/huggingface/hub"),
        "ov_data": OV_MODEL_DIR and str(Path(OV_MODEL_DIR).parent) or None,
        "voice_library": os.getenv("VOICE_LIBRARY_PATH_CONTAINER", "/voices"),
    }
    mount_access = {}
    for name, path in mounts.items():
        if not path or not os.path.isdir(path):
            mount_access[name] = None
            continue
        mount_access[name] = "rw" if os.access(path, os.W_OK) else "ro"

    live: dict[str, Any] = {
        "TTS_BACKEND": TTS_BACKEND,
        "IDLE_UNLOAD_SECONDS": IDLE_UNLOAD_SECONDS,
        "SILENCE_TRIM": os.getenv("SILENCE_TRIM", "1").strip() != "0",
        "SILENCE_TRIM_THRESH": float(os.getenv("SILENCE_TRIM_THRESH", "0.01")),
        "SILENCE_TRIM_PAD_MS": float(os.getenv("SILENCE_TRIM_PAD_MS", "30")),
        "OV_DYNAMIC_QUANT_GROUP_SIZE": int(os.getenv("OV_DYNAMIC_QUANT_GROUP_SIZE", "32")),
    }

    # Pocket TTS knobs only shown/active when TTS_BACKEND == "pocket_tts"
    if TTS_BACKEND == "pocket_tts":
        _ptts_noise = os.getenv("POCKET_TTS_NOISE_CLAMP", "").strip()
        _ptts_frames = os.getenv("POCKET_TTS_FRAMES_AFTER_EOS", "").strip()
        live["POCKET_TTS_TEMP"] = float(os.getenv("POCKET_TTS_TEMP", "0.7"))
        live["POCKET_TTS_LSD_DECODE_STEPS"] = int(os.getenv("POCKET_TTS_LSD_DECODE_STEPS", "1"))
        live["POCKET_TTS_EOS_THRESHOLD"] = float(os.getenv("POCKET_TTS_EOS_THRESHOLD", "-4.0"))
        live["POCKET_TTS_NOISE_CLAMP"] = float(_ptts_noise) if _ptts_noise else None
        live["POCKET_TTS_FRAMES_AFTER_EOS"] = int(_ptts_frames) if _ptts_frames else None

    return {
        "reconfig_in_progress": _reconfig_in_progress,
        "live": live,
        "read_only": {
            "mounts": mount_access,
            "ref_audio_path_set": bool(REF_AUDIO),
            "hf_token_set": bool(os.getenv("HF_TOKEN")),
            "device": DEVICE,
            "torch_dtype": TORCH_DTYPE_NAME,
        },
        "not_live": {
            "TTS_MAX_SPEECH_SECONDS": os.getenv("TTS_MAX_SPEECH_SECONDS"),
            "MODEL_SIZE": os.getenv("MODEL_SIZE"),
            "compression": ov_metadata.get("compression") if ov_metadata else None,
            "reason": "Baked into the OpenVINO IR at export time; requires re-export (see docs/HOW_TO_RUN.md).",
        },
    }


def apply_runtime_config(updates: dict[str, Any]) -> dict[str, Any]:
    """Apply a partial set of live-adjustable runtime knobs.

    Must run inside model.executor (same serialization discipline as load_model()/
    force_unload() elsewhere) — callers submit via
    ``model.executor.submit(apply_runtime_config, updates)``, never call directly
    off-thread. Unknown keys are rejected up front (before mutating anything) so a
    partially-applied bad request can't leave the service in a half-updated state.
    """
    unknown = set(updates) - LIVE_RUNTIME_KEYS
    if unknown:
        raise ValueError(f"Not a live-adjustable key: {sorted(unknown)}")

    global TTS_BACKEND, IDLE_UNLOAD_SECONDS, _reconfig_in_progress

    # Pocket TTS knobs are always writable (they are live keys).
    # They only trigger a reload when the active backend is pocket_tts.
    ptts_changed = bool(set(updates) & _POCKET_TTS_RUNTIME_KEYS)

    needs_reload = bool(set(updates) & _RELOAD_ENV_KEYS) or "TTS_BACKEND" in updates

    _reconfig_in_progress = True
    try:
        if "TTS_BACKEND" in updates:
            backend = str(updates["TTS_BACKEND"]).strip().lower()
            if backend not in ("pytorch", "openvino", "pocket_tts"):
                raise ValueError(f"Invalid TTS_BACKEND: {backend!r}")
            TTS_BACKEND = backend

        if "IDLE_UNLOAD_SECONDS" in updates:
            IDLE_UNLOAD_SECONDS = int(updates["IDLE_UNLOAD_SECONDS"])

        for key in _HOT_ENV_KEYS | _RELOAD_ENV_KEYS:
            if key in updates:
                os.environ[key] = str(updates[key])

        # Write Pocket TTS knobs to os.environ.
        for key in _POCKET_TTS_RUNTIME_KEYS:
            if key in updates:
                value = updates[key]
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = str(value)

        # Pocket TTS knobs: reload only if current backend is pocket_tts.
        if ptts_changed and TTS_BACKEND == "pocket_tts":
            needs_reload = True

        if needs_reload:
            print(
                f"[app_worker] Runtime config change requires reload: {sorted(set(updates))}",
                flush=True,
            )
            force_unload()
            load_model(active_profile)
            _voice_clone_prompt_cache.clear()
    finally:
        _reconfig_in_progress = False

    return runtime_config_state()


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


# ── Async job system (cooperative cancel + live progress/ETA) ─────────────────────────────────
#
# Each generation (Speak, VoiceDesign, OmniVoice) gets a job_id. The job state holds:
#   - cancel_event: set to signal cooperative cancel
#   - progress: frames_generated, elapsed, status, ETA
#   - completed: (wav, sr) or error once done
#
# A _ProgressLogitsProcessor is injected into the generation loop:
#   - Increments frames_generated each decode step
#   - On cancel, forces EOS → loop terminates cleanly with partial audio
#
# The single-worker executor ensures only one job runs at a time, so cancel is safe.


@dataclass
class _JobState:
    job_id: str
    cancel_event: threading.Event = field(default_factory=threading.Event)
    status: str = "running"  # running | completed | failed | cancelled
    frames_generated: int = 0
    reference_frames: int = 0
    started_at: float = field(default_factory=time.monotonic)
    text_length: int = 0
    message: str | None = None
    wav: Any = None
    sr: int = 0
    seed: int | None = None
    error: str | None = None
    expected_total_frames: int = 0
    _watchdog_limit: float = 120.0


_active_jobs: dict[str, _JobState] = {}
_active_jobs_lock = threading.Lock()


def _create_job(text: str, seed: int | None = None) -> _JobState:
    job_id = uuid.uuid4().hex
    chars_per_sec_speech = 9.3
    expected_audio_seconds = max(1.5, len(text) / chars_per_sec_speech if len(text) > 0 else 3.0)
    expected_total_frames = max(40, int(expected_audio_seconds * 12))
    watchdog_limit = float(os.getenv("TTS_WATCHDOG_SECONDS", "120"))

    job = _JobState(
        job_id=job_id,
        text_length=len(text),
        seed=seed,
        expected_total_frames=expected_total_frames,
        _watchdog_limit=watchdog_limit,
    )
    with _active_jobs_lock:
        _active_jobs[job_id] = job
    return job


def _cleanup_job(job_id: str):
    # Evict completed jobs to bound memory.
    with _active_jobs_lock:
        _active_jobs.pop(job_id, None)


def cancel_job(job_id: str) -> bool:
    """Signal cooperative cancel for a running job.

    Returns True if the job was found and its cancel_event was set; False otherwise.
    The generation loop checks cancel_event via a logits_processor and forces EOS on next step.
    """
    with _active_jobs_lock:
        job = _active_jobs.get(job_id)
    if job is None:
        return False
    if job.status not in ("running",):
        return False
    job.cancel_event.set()
    job.status = "cancelled"
    job.message = "Cancelled by user."
    print(f"[generate] cancel_job: {job_id}", flush=True)
    return True


def get_job_progress(job_id: str) -> dict[str, Any] | None:
    """Return a JSON-serializable snapshot of the job, or None if not found."""
    with _active_jobs_lock:
        job = _active_jobs.get(job_id)
    if job is None:
        return None

    elapsed = time.monotonic() - job.started_at
    frames = job.frames_generated

    # ETA: use a live moving average of speed (frames/sec).
    # We know 1 frame = 1/12s of audio. Estimate expected total frames from text length.
    # Typical speech rate ≈ 2.33 words/sec, with ~4 chars per word → ~9.3 chars/sec.
    # So expected_audio_seconds ≈ text_length / 9.3, expected_total_frames ≈ audio_seconds × 12.
    chars_per_sec_speech = 9.3
    text_len = job.text_length if job.text_length > 0 else 0
    expected_audio_seconds = max(1.5, text_len / chars_per_sec_speech if text_len > 0 else 3.0)
    expected_total_frames = max(40, int(expected_audio_seconds * 12))

    speed = frames / elapsed if elapsed > 0.5 and frames > 5 else None
    eta_seconds = None
    progress_pct = 0.0

    if speed is not None and speed > 0 and frames > 0:
        remaining_frames = max(0, expected_total_frames - frames)
        eta_seconds = remaining_frames / speed
        progress_pct = min(100.0, (frames / max(expected_total_frames, 1)) * 100.0)

    return {
        "job_id": job.job_id,
        "status": job.status,
        "frames_generated": frames,
        "expected_total_frames": expected_total_frames,
        "progress_pct": round(progress_pct, 1),
        "elapsed_seconds": round(elapsed, 1),
        "eta_seconds": round(eta_seconds, 1) if eta_seconds is not None else None,
        "message": job.message,
    }


class _ProgressLogitsProcessor:
    """Tracks decode steps and implements cooperative cancel.

    Each call corresponds to one decode step (one frame for codebook 1).
    On cancel, forces EOS so generation ends cleanly.
    """

    def __init__(self, job: _JobState, eos_token_id: int):
        self._job = job
        self._eos = eos_token_id
        self._step = 0

    def __call__(self, input_ids, scores):
        import torch

        self._step += 1
        self._job.frames_generated = self._step

        if self._job.cancel_event.is_set():
            # Force EOS: make EOS the only non -inf logit.
            new_scores = torch.full_like(scores, float("-inf"))
            new_scores[:, self._eos] = scores[:, self._eos]
            return new_scores

        # Stuck detection: exceeded 3x expected frames; likely REF_TEXT/REF_AUDIO mismatch.
        if (
            self._job.status == "running"
            and self._step > self._job.expected_total_frames * 3
        ):
            new_scores = torch.full_like(scores, float("-inf"))
            new_scores[:, self._eos] = scores[:, self._eos]
            self._job.status = "failed"
            self._job.message = (
                "Generation stuck: exceeded 3x expected frames; "
                "possible REF_TEXT/REF_AUDIO mismatch."
            )
            return new_scores

        # Time watchdog: overall wall-time limit; likely REF_TEXT/REF_AUDIO mismatch.
        if (
            self._job.status == "running"
            and (time.monotonic() - self._job.started_at) > self._job._watchdog_limit
        ):
            new_scores = torch.full_like(scores, float("-inf"))
            new_scores[:, self._eos] = scores[:, self._eos]
            self._job.status = "failed"
            self._job.message = (
                "Generation timed out (watchdog); "
                "possible REF_TEXT/REF_AUDIO mismatch."
            )
            return new_scores

        return scores


def _get_eos_token_id(model_instance):
    """Resolve the EOS token ID for the talker's codec."""
    try:
        config = model_instance.model.config.talker_config
        return getattr(config, "codec_eos_token_id", 2150)
    except Exception:
        return 2150


class _DiagLogitsProcessor:
    """Diagnostic: logs top tokens and EOS probability at early decode steps.

    Enabled by TTS_DIAG=1 in the environment. Hooks into the talker's
    generation loop to catch what is actually being sampled — useful to
    distinguish garbage hidden-state output (uniform/degenerate distribution)
    from a genuine EOS-detection failure.
    """

    _LOG_AT = frozenset({1, 2, 3, 5, 10, 30, 50})

    def __init__(self, eos_token_id: int):
        self._step = 0
        self._eos = eos_token_id

    def __call__(self, input_ids, scores):
        import torch

        self._step += 1
        if self._step in self._LOG_AT:
            probs = torch.softmax(scores[0].float(), dim=-1)
            top = probs.topk(5)
            tok_str = ", ".join(
                f"{int(i)}({float(p):.3f})" for i, p in zip(top.indices, top.values)
            )
            eos_p = float(probs[self._eos]) if self._eos < probs.shape[0] else 0.0
            argmax = int(probs.argmax())
            print(
                f"[diag] step={self._step:3d}  top5=[{tok_str}]"
                f"  eos({self._eos})={eos_p:.5f}  argmax={argmax}",
                flush=True,
            )
        return scores


_voice_clone_prompt_cache: dict[str, Any] = {}


def get_voice_clone_prompt(voice_id: str | None = None):
    """Resolve the voice_clone_prompt to generate with.

    voice_id=None returns the startup-built module-global prompt unchanged — this is the
    Hermes/default path and must stay byte-for-byte identical to pre-voice_id behavior.
    A given voice_id is built from its library reference sample on first use and cached
    (building requires model.create_voice_clone_prompt, i.e. must run inside model.executor
    with Base loaded).
    """
    if voice_id is None:
        return voice_clone_prompt
    if voice_id in _voice_clone_prompt_cache:
        return _voice_clone_prompt_cache[voice_id]
    from qwen3_tts import voice_library

    meta = voice_library.get_voice(voice_id)
    if meta is None:
        raise ValueError(f"voice_id not found: {voice_id!r}")
    if model is None:
        raise RuntimeError("Model not loaded")
    if getattr(ov_runtime, "codec_released", False):
        raise RuntimeError(
            "Cannot build a voice_clone_prompt for a new voice_id: the PyTorch codec was "
            "released at startup (OPENVINO_KEEP_CODEC_ENCODER=0) and encoding new "
            "reference audio requires it. Restart the container with "
            "OPENVINO_KEEP_CODEC_ENCODER=1 (the default) to use per-request/voice_id cloning."
        )
    prompt = model.create_voice_clone_prompt(
        ref_audio=meta["wav_path"],
        ref_text=meta["sample_text"],
        x_vector_only_mode=False,
    )
    _voice_clone_prompt_cache[voice_id] = prompt
    return prompt


def invalidate_voice_clone_prompt(voice_id: str) -> None:
    """Drop a cached voice_clone_prompt so the next request rebuilds it from meta.json.

    Must be called whenever a voice's reference audio or sample_text changes on disk
    (see voice_library.update_voice) — the cache in get_voice_clone_prompt is keyed by
    voice_id only and never re-reads meta.json once built.
    """
    _voice_clone_prompt_cache.pop(voice_id, None)


def _run_generate(
    text: str,
    language: str,
    *,
    voice_id: str | None = None,
    seed_value=None,
    instruct: str | None = None,
    job_id: str | None = None,
    **gen_kwargs,
):
    _touch_last_request()
    _apply_optional_seed(seed_value)
    _ensure_base_loaded()
    if model is None:
        raise RuntimeError("Model not loaded")

    # ── Pocket TTS backend branch ──────────────────────────────────────────────
    if TTS_BACKEND == "pocket_tts":
        from qwen3_tts import pocket_tts_runtime

        if instruct:
            print(f"[generate] instruct field ignored on Base checkpoint: {instruct!r}", flush=True)
        import traceback as _tb
        t0 = time.monotonic()
        print(f"[generate] batch  lang={language!r}  chars={len(text)}  job={job_id or '-'}", flush=True)

        # Create or use provided job state for progress tracking + cancel.
        job: _JobState | None = None
        if job_id:
            with _active_jobs_lock:
                job = _active_jobs.get(job_id)
            if job is None:
                job = _create_job(text, seed=seed_value)
                job_id = job.job_id
        else:
            job = _create_job(text, seed=seed_value)
            job_id = job.job_id

        # Pre-generate cancel check
        if job.cancel_event.is_set():
            job.status = "cancelled"
            job.message = "Cancelled by user."
            raise RuntimeError("Job cancelled before generation started.")

        # Use Pocket TTS voice_state resolution instead of Qwen3TTS voice_clone_prompt.
        voice_state = pocket_tts_runtime.get_pocket_tts_voice_state(
            model,
            voice_id=voice_id,
            default_voice_state=voice_clone_prompt,
            ref_audio_path=REF_AUDIO,
        )

        # Give progress a non-zero start so async/progress endpoints behave.
        if job:
            job.frames_generated = job.expected_total_frames

        try:
            audio_tensor, sr = pocket_tts_runtime.generate_pocket_tts(model, voice_state, text)
        except Exception:
            if job:
                job.status = "failed"
                try:
                    job.error = "Generation failed; see server logs."
                except Exception:
                    pass
            _tb.print_exc()
            raise

        wav = _trim_silence(audio_tensor.cpu().numpy().ravel(), sr)
        duration = len(wav) / sr
        elapsed = time.monotonic() - t0
        print(f"[generate] done   elapsed={elapsed:.1f}s  audio={duration:.1f}s  RTF={elapsed/duration:.2f}x", flush=True)

        # If cancelled after generation (unlikely but consistent)
        if job and job.cancel_event.is_set():
            job.status = "cancelled"
            job.message = "Cancelled by user."
        elif job:
            job.status = "completed"
            job.wav = wav
            job.sr = sr

        return wav, sr, job_id

    # ── PyTorch / OpenVINO backends (unchanged) ────────────────────────────────
    voice_prompt = get_voice_clone_prompt(voice_id)
    if voice_prompt is None:
        raise RuntimeError("Model not loaded")
    if instruct:
        # Base's generate_voice_clone has no tone/instruct parameter — VoiceDesign is the only
        # checkpoint that consumes free-text instruct. No-op here rather than erroring, so a
        # frontend that always sends `instruct` doesn't need to special-case Base.
        print(f"[generate] instruct field ignored on Base checkpoint: {instruct!r}", flush=True)
    import traceback as _tb
    t0 = time.monotonic()
    print(f"[generate] batch  lang={language!r}  chars={len(text)}  job={job_id or '-'}", flush=True)

    # Create or use provided job state for progress tracking + cancel.
    job: _JobState | None = None
    if job_id:
        with _active_jobs_lock:
            job = _active_jobs.get(job_id)
        if job is None:
            job = _create_job(text, seed=seed_value)
            job_id = job.job_id
    else:
        # Always create a lightweight job for cancel + progress (even for blocking /generate).
        job = _create_job(text, seed=seed_value)
        job_id = job.job_id

    # Inject progress logits processor for cancel + live ETA.
    eos_id = _get_eos_token_id(model)
    progress_processor = _ProgressLogitsProcessor(job, eos_id)
    gen_kwargs.setdefault("logits_processor", [])
    gen_kwargs["logits_processor"] = list(gen_kwargs["logits_processor"]) + [progress_processor]

    if (os.getenv("TTS_DIAG", "0").strip() == "1" or os.path.exists("/tmp/tts_diag")) and TTS_BACKEND == "openvino":
        diag_kwargs = gen_kwargs.copy()
        diag_kwargs.setdefault("logits_processor", [])
        diag_kwargs["logits_processor"] = list(diag_kwargs["logits_processor"]) + [
            _DiagLogitsProcessor(eos_id)
        ]
        gen_kwargs = diag_kwargs
        print(f"[diag] TTS_DIAG active  eos_token_id={eos_id}", flush=True)

    # Diagnostic/safety override: cap generation length so a non-terminating
    # decode returns partial audio for inspection instead of crashing at the
    # stateful cache capacity. Unset in normal operation.
    _max_new = os.getenv("TTS_MAX_NEW_TOKENS", "").strip()
    if not _max_new and os.path.exists("/tmp/tts_max_new"):
        try:
            with open("/tmp/tts_max_new") as _f:
                _max_new = _f.read().strip()
        except Exception:
            _max_new = ""
    if _max_new:
        gen_kwargs.setdefault("max_new_tokens", int(_max_new))
        print(f"[diag] TTS_MAX_NEW_TOKENS override -> {_max_new}", flush=True)

    # Safety cap: ensure max_new_tokens is within sane bounds based on speech duration.
    system_limit = int(os.getenv("TTS_SYSTEM_MAX_NEW_TOKENS", "800"))
    max_speech_secs_str = os.getenv("TTS_MAX_SPEECH_SECONDS", "64")
    max_speech_secs = float(max_speech_secs_str) if max_speech_secs_str else 64.0
    from qwen3_tts.presets import capacity_for_seconds
    safe_capacity = capacity_for_seconds(max_speech_secs)
    hard_cap_frames = int(safe_capacity * 0.8)
    expected_frames = job.expected_total_frames if job else 40
    safety_max = max(expected_frames * 2, hard_cap_frames)
    chosen = min(system_limit, safety_max)
    if "max_new_tokens" not in gen_kwargs:
        gen_kwargs["max_new_tokens"] = chosen
    else:
        gen_kwargs["max_new_tokens"] = min(gen_kwargs["max_new_tokens"], chosen)
    print(f"[generate] effective max_new_tokens={gen_kwargs['max_new_tokens']}", flush=True)

    # Batch/complete-file consumers (hermes) don't need the streaming internal
    # text-delivery path. non_streaming_mode=True bakes the whole target text into
    # the prefill instead of feeding it incrementally via trailing_text_hidden.
    if os.getenv("TTS_NON_STREAMING", "").strip() == "1" or os.path.exists("/tmp/tts_non_streaming"):
        gen_kwargs.setdefault("non_streaming_mode", True)
        print("[diag] non_streaming_mode=True (batch prefill text delivery)", flush=True)

    try:
        wavs, sr = model.generate_voice_clone(
            text=text,
            language=language,
            voice_clone_prompt=voice_prompt,
            **gen_kwargs,
        )
    except Exception:
        if job:
            job.status = "failed"
            try:
                job.error = "Generation failed; see server logs."
            except Exception:
                pass
        _tb.print_exc()
        raise
    if job and job.status == "failed":
        print(
            f"[GEN-ABORT] {job.message} job_id={job.job_id} text_len={job.text_length}",
            flush=True,
        )
    wav, sr = _trim_silence(wavs[0], sr), sr
    duration = len(wav) / sr
    elapsed = time.monotonic() - t0
    print(f"[generate] done   elapsed={elapsed:.1f}s  audio={duration:.1f}s  RTF={elapsed/duration:.2f}x  frames={job.frames_generated if job else '-'}", flush=True)

    # If cancelled, we got partial audio but treat as cancelled.
    if job and job.cancel_event.is_set():
        job.status = "cancelled"
        job.message = "Cancelled by user."
    elif job:
        job.status = "completed"
        job.wav = wav
        job.sr = sr

    return wav, sr, job_id


def _apply_optional_seed(seed_value):
    """Apply an optional seed to torch, numpy, and Python RNGs for deterministic runs."""
    if seed_value is None:
        return
    import random
    import numpy as np
    torch.manual_seed(seed_value)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed_value)
    np.random.seed(seed_value)
    random.seed(seed_value)


# Comfortably inside a signed 63-bit range so resolved seeds round-trip cleanly through
# JSON/int() parsing and response headers.
_MAX_SEED = 2**32 - 1


def resolve_seed(seed_value: int | None) -> int:
    """Return seed_value, or a fresh random seed if not supplied.

    Callers that want every generation to be reproducible and inspectable (not just
    optionally seedable) should call this instead of passing seed_value straight through —
    it guarantees a concrete seed always exists to report back to the caller, rather than
    silently depending on whatever ambient RNG state happens to exist.
    """
    if seed_value is not None:
        return seed_value
    import secrets
    return secrets.randbelow(_MAX_SEED)


def _run_generate_with_streaming(
    text: str,
    language: str,
    on_audio_chunk: Callable[[Any], None],
    *,
    reuse_streamed_decode: bool = False,
    seed_value=None,
    voice_id: str | None = None,
    **gen_kwargs,
):
    """Run generation while emitting incremental untrimmed PCM chunks.

    The terminal return preserves the existing trimmed batch behavior. Internal
    parity tests may retain the stock decode; transport reuses the final prefix.
    """

    import numpy as np

    _touch_last_request()
    _apply_optional_seed(seed_value)
    _ensure_base_loaded()

    if model is None:
        raise RuntimeError("Model not loaded")
    voice_prompt = get_voice_clone_prompt(voice_id)
    if voice_prompt is None:
        raise RuntimeError("Model not loaded")

    print(f"[generate] stream lang={language!r}  chars={len(text)}", flush=True)

    vr = getattr(ov_runtime, "vocoder_runtime", None)
    if vr is None or not vr.enabled:
        raise RuntimeError("streaming parity requires the FP32 OpenVINO vocoder")

    reference_codes = None
    if isinstance(voice_prompt, list) and voice_prompt:
        reference_codes = getattr(voice_prompt[0], "ref_code", None)
    elif isinstance(voice_prompt, dict):
        ref_code_list = voice_prompt.get("ref_code")
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

    # Safety cap for streaming: same logic as _run_generate.
    system_limit_stream = int(os.getenv("TTS_SYSTEM_MAX_NEW_TOKENS", "800"))
    max_speech_secs_str_stream = os.getenv("TTS_MAX_SPEECH_SECONDS", "64")
    max_speech_secs_stream = float(max_speech_secs_str_stream) if max_speech_secs_str_stream else 64.0
    from qwen3_tts.presets import capacity_for_seconds as capacity_for_seconds_stream
    safe_capacity_stream = capacity_for_seconds_stream(max_speech_secs_stream)
    hard_cap_frames_stream = int(safe_capacity_stream * 0.8)
    expected_frames_stream = max(40, int(len(text) / 9.3 * 12))
    safety_max_stream = max(expected_frames_stream * 2, hard_cap_frames_stream)
    chosen_stream = min(system_limit_stream, safety_max_stream)
    if "max_new_tokens" not in gen_kwargs:
        gen_kwargs["max_new_tokens"] = chosen_stream
    else:
        gen_kwargs["max_new_tokens"] = min(gen_kwargs["max_new_tokens"], chosen_stream)
    print(f"[generate] stream effective max_new_tokens={gen_kwargs['max_new_tokens']}", flush=True)

    with session:
        if reuse_streamed_decode:
            speech_tokenizer.decode = reuse_decode
        try:
            wavs, sr = model.generate_voice_clone(
                text=text,
                language=language,
                voice_clone_prompt=voice_prompt,
                **gen_kwargs,
            )
        finally:
            if reuse_streamed_decode:
                speech_tokenizer.decode = original_decode

    # Existing batch behavior: still return the complete trimmed wav. The raw
    # waveform is returned only to the internal parity harness so it can compare
    # the side-channel chunks against the stock decode from the same generation.
    wav_raw = np.asarray(wavs[0], dtype=np.float32).ravel()
    elapsed = time.monotonic() - started
    duration = len(wav_raw) / sr
    print(f"[generate] done   elapsed={elapsed:.1f}s  audio={duration:.1f}s  RTF={elapsed/duration:.2f}x  chunks={len(session.decode_boundaries)}", flush=True)
    return _trim_silence(wav_raw, sr), sr, wav_raw, {
        "elapsed_seconds": elapsed,
        "generated_frames": session.generated_frames,
        "reference_frames": session.reference_frames,
        "decode_boundaries": session.decode_boundaries,
    }

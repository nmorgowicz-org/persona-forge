import gc
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

# Apply thread and runtime envs before heavy imports
from qwen3_tts.config import REF_AUDIO_PATH, apply_preset_env
from qwen3_tts.openvino.runtime_config import apply_thread_env

apply_preset_env()

apply_thread_env()
os.environ.setdefault("ORT_INTRA_OP_NUM_THREADS", "6")
os.environ.setdefault("ORT_INTER_OP_NUM_THREADS", "2")
os.environ.setdefault("OMP_NUM_THREADS", "6")
os.environ.setdefault("MKL_NUM_THREADS", "6")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import torch

from qwen3_tts.model_config import (
    configure_hf_token,
    resolve_model_repo,
    resolve_torch_load_config,
)
from qwen3_tts.streaming import StreamingVocoderSession

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

torch.set_num_threads(int(os.environ.get("OV_INFERENCE_THREADS", "6")))

model = None
voice_clone_prompt = None

ov_metadata = None
ov_config = None
ov_runtime = None

executor = ThreadPoolExecutor(max_workers=1)

_service_started: bool = False
_last_request_time: float = time.time()
_unload_pending: bool = False


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


def _do_unload():
    """Runs inside the executor thread; serialized with inference."""
    global model, voice_clone_prompt, ov_runtime, _unload_pending
    _unload_pending = False
    if model is None:
        return
    if time.time() - _last_request_time < IDLE_UNLOAD_SECONDS:
        return
    print("[app_worker] Idle timeout reached; unloading model to free RAM...", flush=True)
    model = None
    voice_clone_prompt = None
    ov_runtime = None
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


def _ensure_loaded():
    """Runs inside the executor thread; reloads model if idle-unloaded."""
    if model is None:
        print("[app_worker] Reloading model after idle unload...", flush=True)
        load_model()


def _validate_ov_metadata(model_dir: str):
    global ov_metadata, ov_config
    path = Path(model_dir)
    meta_path = path / "metadata.json"
    if not meta_path.is_file():
        raise RuntimeError(f"OV_MODEL_DIR missing metadata.json: {meta_path}")

    ov_metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    from qwen3_tts.openvino.runtime_config import get_ov_config
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
        from qwen3_tts.openvino.talker import OVTalkerRuntime

        talker = model.model.talker
        # speech_tokenizer is a sibling of talker on the parent model, not a child of it;
        # pass it explicitly so the OV vocoder patch can find it.
        ov_runtime = OVTalkerRuntime(
            OV_MODEL_DIR, talker, ov_config=ov_config,
            speech_tokenizer=model.model.speech_tokenizer,
        )
        ov_runtime.install()

        # The codec encoder has done its one job (voice_clone_prompt was built above) and
        # the OV vocoder now owns decode, so free the ~0.3 GiB PyTorch speech_tokenizer.
        # Self-gates on OPENVINO_RELEASE_CODEC; no-op when disabled for per-request cloning.
        ov_runtime.release_codec()

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

    global _service_started
    _service_started = True
    print("[app_worker] Model loaded and ready.")


load_model()


def _idle_watcher():
    while True:
        time.sleep(30)
        global _unload_pending
        if (
            not _unload_pending
            and model is not None
            and time.time() - _last_request_time > IDLE_UNLOAD_SECONDS
        ):
            _unload_pending = True
            executor.submit(_do_unload)


if IDLE_UNLOAD_SECONDS > 0:
    threading.Thread(target=_idle_watcher, daemon=True, name="idle-watcher").start()
    print(f"[app_worker] Idle unload enabled: {IDLE_UNLOAD_SECONDS}s cooldown.", flush=True)


def health_state() -> dict[str, Any]:
    """Return JSON-serializable model and backend readiness state."""
    idle_unload_seconds = IDLE_UNLOAD_SECONDS if IDLE_UNLOAD_SECONDS > 0 else None
    base = {
        "status": "ok",
        "model_loaded": model is not None,
        "process_rss_mib": _process_rss_mib(),
        "idle_unload_seconds": idle_unload_seconds,
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

    return _json_safe(base)


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


def _run_generate(text: str, language: str, **gen_kwargs):
    _touch_last_request()
    _ensure_loaded()
    if model is None or voice_clone_prompt is None:
        raise RuntimeError("Model not loaded")
    import traceback as _tb
    t0 = time.monotonic()
    print(f"[generate] batch  lang={language!r}  chars={len(text)}", flush=True)

    if (os.getenv("TTS_DIAG", "0").strip() == "1" or os.path.exists("/tmp/tts_diag")) and TTS_BACKEND == "openvino":
        eos_id = getattr(
            getattr(getattr(model, "model", None), "config", None), "talker_config", None
        )
        eos_id = getattr(eos_id, "codec_eos_token_id", 2150) if eos_id is not None else 2150
        gen_kwargs.setdefault("logits_processor", [])
        gen_kwargs["logits_processor"] = list(gen_kwargs["logits_processor"]) + [
            _DiagLogitsProcessor(eos_id)
        ]
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
            voice_clone_prompt=voice_clone_prompt,
            **gen_kwargs,
        )
    except Exception:
        _tb.print_exc()
        raise
    wav, sr = _trim_silence(wavs[0], sr), sr
    duration = len(wav) / sr
    elapsed = time.monotonic() - t0
    print(f"[generate] done   elapsed={elapsed:.1f}s  audio={duration:.1f}s  RTF={elapsed/duration:.2f}x", flush=True)
    return wav, sr


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


def _run_generate_with_streaming(
    text: str,
    language: str,
    on_audio_chunk: Callable[[Any], None],
    *,
    reuse_streamed_decode: bool = False,
    seed_value=None,
    **gen_kwargs,
):
    """Run generation while emitting incremental untrimmed PCM chunks.

    The terminal return preserves the existing trimmed batch behavior. Internal
    parity tests may retain the stock decode; transport reuses the final prefix.
    """

    import numpy as np

    _touch_last_request()
    _apply_optional_seed(seed_value)
    _ensure_loaded()

    if model is None or voice_clone_prompt is None:
        raise RuntimeError("Model not loaded")

    print(f"[generate] stream lang={language!r}  chars={len(text)}", flush=True)

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
    elapsed = time.monotonic() - started
    duration = len(wav_raw) / sr
    print(f"[generate] done   elapsed={elapsed:.1f}s  audio={duration:.1f}s  RTF={elapsed/duration:.2f}x  chunks={len(session.decode_boundaries)}", flush=True)
    return _trim_silence(wav_raw, sr), sr, wav_raw, {
        "elapsed_seconds": elapsed,
        "generated_frames": session.generated_frames,
        "reference_frames": session.reference_frames,
        "decode_boundaries": session.decode_boundaries,
    }

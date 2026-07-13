from __future__ import annotations

import io
import random
import sys
import threading
import time
import types
import wave
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np


def _make_silent_wav(num_samples: int = 2400, sr: int = 24000) -> bytes:
    samples = np.zeros(num_samples, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(samples.tobytes())
    return buf.getvalue()









class FakeOmniVoiceEngine:
    """Fake OmniVoice engine for mocking audio stitching."""
    def stitch_selected(self, selected, plan=None):
        return np.zeros(2400, dtype=np.float32), 24000


class FakeVoiceLibrary:
    """Fake voice library for mocking voice saving/loading.

    It maintains a simple in-memory dictionary of 'saved' voices.
    """
    def __init__(self):
        self.voices = {}
        self.wav_bytes = {}
        self._voice_counter = 0

    def save_voice(
        self,
        wav_bytes,
        *,
        description,
        sample_text,
        language,
        seed=None,
        selections=None,
        family_id=None,
        variant_name=None,
        variant_kind=None,
        source=None,
        **_kwargs,
    ):
        voice_id = f"fake_voice_{len(self.voices)}"
        meta = {
            "voice_id": voice_id,
            "description": description,
            "sample_text": sample_text,
            "language": language,
            "seed": seed,
            "selections": selections,
            "family_id": family_id,
            "variant_name": variant_name,
            "variant_kind": variant_kind,
            "source": source,
            "quality_score": 100.0,
            "quality_warnings": [],
            "needs_review": False,
            "auto_fixed": False,
            "metrics": {},
        }
        self.voices[voice_id] = meta
        self.wav_bytes[voice_id] = wav_bytes
        return meta

    def get_voice(self, voice_id):
        return self.voices.get(voice_id)

    def get_voice_wav_bytes(self, voice_id):
        return self.wav_bytes.get(voice_id)

    def update_voice(self, voice_id, *, sample_text):
        meta = self.voices.get(voice_id)
        if meta is None:
            return None
        meta["sample_text"] = sample_text
        meta["sample_text_source"] = "user"
        meta["needs_review"] = False
        return meta

    def delete_voice(self, voice_id):
        if voice_id in self.voices:
            del self.voices[voice_id]
            self.wav_bytes.pop(voice_id, None)
        return True

    def list_voices(self):
        return list(self.voices.values())

    def __len__(self):
        return len(self.voices)


class _FakeLoadedModel:
    """Stands in for model.model — matches real shape: model.model.model.tts_model_type."""

    def __init__(self, profile: str = "BASE") -> None:
        # Nested .model to match real: model.model.model.tts_model_type
        self.model = types.SimpleNamespace(
            tts_model_type="voice_design" if profile == "VOICE_DESIGN" else "base",
        )

    def generate_voice_clone(self, **kwargs: Any) -> Tuple[List[Any], int]:
        return [np.zeros(2400, dtype=np.float32)], 24000

    def generate_voice_design(self, **kwargs: Any) -> Tuple[List[Any], int]:
        return [np.zeros(2400, dtype=np.float32)], 24000


class _FakeJobState:
    """Matches model._JobState shape so app.py reads are valid."""

    def __init__(
        self,
        job_id: str,
        text: str,
        seed: Optional[int],
        status: str = "running",
    ) -> None:
        self.job_id = job_id
        self.status = status
        self.cancel_event = threading.Event()
        self.frames_generated = 0
        self.reference_frames = 0
        self.text_length = len(text)
        self.message: str | None = None
        # Small fake waveform so /generate/job/<id>/audio can return 200.
        self.wav: Any = np.zeros(480, dtype=np.float32)
        self.sr = 24000
        self.seed = seed
        self.error: Optional[str] = None
        self.started_at = time.monotonic()
        self.expected_total_frames = 60
        self._watchdog_limit = 120.0
        self.voice_family_id: str | None = None
        self.variant_kind: str | None = None
        self.style_preset: str | None = None
        self.postprocess_applied = False
        self.metadata: Dict[str, Any] = {}


class _FakeModule(types.ModuleType):
    """Proxy module that delegates attribute access to FakeModelRuntime instance.
    
    This ensures model.X and rt.X are always in sync; patching one immediately
    affects the other, which is critical when tests manipulate rt.model,
    rt.generate_should_fail, etc. and then the app code reads from model.*.
    """
    _rt: Any  # reference to FakeModelRuntime
    def __init__(self, rt: Any, name: str) -> None:
        super().__init__(name)
        self._rt = rt

    def __getattr__(self, name: str) -> Any:
        return getattr(self._rt, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_rt":
            super().__setattr__("_rt", value)
        else:
            setattr(self._rt, name, value)



class FakeModelRuntime:
    """Central fake for qwen3_tts.model.
    
    install() creates a _FakeModelModule proxy and puts it into
    sys.modules["qwen3_tts.model"] so imports of qwen3_tts.model resolve here.
    All attribute access on model.* is live-delegated to this instance.
    """
 
    # Basic flags
    _service_started: bool
    _model_loaded: bool
    startup_failed: bool
    tts_backend: str
    initial_service_started: bool
    model: Any
    omnivoice_engine: Any
    voice_library: Any
    _startup_error: Optional[str]
    
    # Call tracking
    load_model_calls: List[Dict[str, Any]]
    force_unload_calls: List[Dict[str, Any]]
    generate_calls: List[Dict[str, Any]]
 
    # Async-job store
    jobs: Dict[str, Dict[str, Any]]
 
    # Configurable behaviors
    generate_should_fail: bool
    generate_error_code: int
    generate_delay_ms: int
    swap_in_progress: bool
    stream_vocoder_enabled: bool
    async_jobs_complete_immediately: bool
 
    _job_counter: int
    _active_jobs: Dict[str, _FakeJobState]
    _active_jobs_lock: threading.Lock
    executor: ThreadPoolExecutor
 
    def __init__(
        self,
        initial_service_started: bool = True,
        model_loaded: bool = True,
        startup_failed: bool = False,
        tts_backend: str = "openvino",
        generate_delay_ms: int = 0,
        generate_should_fail: bool = False,
        generate_error_code: int = 500,
        swap_in_progress: bool = False,
        stream_vocoder_enabled: bool = True,
        async_jobs_complete_immediately: bool = True,
    ) -> None:
        self._service_started = initial_service_started
        self._model_loaded = model_loaded
        self.startup_failed = startup_failed
        self.tts_backend = tts_backend
        self.initial_service_started = initial_service_started
        self._startup_failed = startup_failed
        self._startup_error: Optional[str] = (
            "fake startup error" if startup_failed else None
        )
        self.omnivoice_engine = FakeOmniVoiceEngine()
        self.voice_library = FakeVoiceLibrary()
 
        self.load_model_calls: List[Dict[str, Any]] = []
        self.force_unload_calls: List[Dict[str, Any]] = []
        self.generate_calls: List[Dict[str, Any]] = []
 
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._job_counter: int = 0
        self._jobs_lock = threading.Lock()
 
        self.generate_should_fail = generate_should_fail
        self.generate_error_code = generate_error_code
        self.generate_delay_ms = generate_delay_ms
        self.swap_in_progress = swap_in_progress
        self.stream_vocoder_enabled = stream_vocoder_enabled
        self._slow_async = False
        self.async_jobs_complete_immediately = async_jobs_complete_immediately
 
        # Async-job lock: app.py accesses model._active_jobs_lock directly.
        self._active_jobs: Dict[str, _FakeJobState] = {}
        self._active_jobs_lock = threading.Lock()
 
        # Executor: app.py uses model.executor.submit(...).
        self.executor = ThreadPoolExecutor(max_workers=1)
 
        # model.model: loaded checkpoint wrapper.
        self.model: Any = _FakeLoadedModel("BASE")
 
        # ov_runtime: used by app.py to gate streaming.
        self.ov_runtime = types.SimpleNamespace(
            vocoder_runtime=types.SimpleNamespace(
                enabled=stream_vocoder_enabled,
                sample_rate=24000,
            )
        )
 
        # voice_clone_prompt: app.py / model.py usage.
        self.voice_clone_prompt = object()
 
        # Profiles: used by voice_design.py.
        self.BASE_PROFILE = "BASE"
        self.VOICE_DESIGN_PROFILE = "VOICE_DESIGN"
 
        # active_profile
        self.active_profile = self.BASE_PROFILE
 
        # Runtime config internals: /runtime/config endpoints.
        self._runtime_live: Dict[str, Any] = {
            "TTS_BACKEND": self.tts_backend,
            "IDLE_UNLOAD_SECONDS": 0,
            "SILENCE_TRIM": True,
            "SILENCE_TRIM_THRESH": 0.01,
            "SILENCE_TRIM_PAD_MS": 30,
            "OV_DYNAMIC_QUANT_GROUP_SIZE": 32,
        }
        self._runtime_read_only: Dict[str, Any] = {
            "mounts": {"model_cache": "ro", "ov_data": "rw", "voice_library": "rw"},
            "ref_audio_path_set": True,
            "hf_token_set": False,
            "device": "CPU",
            "torch_dtype": "float32",
        }
        self._runtime_not_live: Dict[str, Any] = {
            "TTS_MAX_SPEECH_SECONDS": "64",
            "MODEL_SIZE": "1.7B",
            "compression": "int4_asym",
            "reason": "Baked into the OpenVINO IR at export time.",
        }
        self._reconfig_in_progress = False


    # ── install ──

    def install(self, overrides: Optional[Dict[str, Any]] = None) -> "FakeModelRuntime":
        rt = self

        # Use proxy module so all model.* attribute access is live-delegated to rt.
        fake_module = _FakeModule(rt, "qwen3_tts.model")

        def health_state() -> Dict[str, Any]:
            if rt._startup_failed:
                return {
                    "status": "error",
                    "service_started": False,
                    "model_loaded": False,
                    "error": rt._startup_error,
                }
            status = "ok" if (rt._service_started and rt._model_loaded) else "degraded"
            result: Dict[str, Any] = {
                "status": status,
                "service_started": rt._service_started,
                "model_loaded": rt._model_loaded,
                "backend": rt.tts_backend,
            }
            # app.py reads model._service_started and adds loading_message itself,
            # but we include it here for direct model-level callers.
            if not rt._service_started:
                result["loading_message"] = "Loading model…"
            return result

        def reconfig_in_progress() -> bool:
            return rt._reconfig_in_progress

        def runtime_config_state() -> Dict[str, Any]:
            return {
                "reconfig_in_progress": rt._reconfig_in_progress,
                "live": dict(rt._runtime_live),
                "read_only": dict(rt._runtime_read_only),
                "not_live": dict(rt._runtime_not_live),
            }

        _LIVE_KEYS = {
            "TTS_BACKEND",
            "IDLE_UNLOAD_SECONDS",
            "SILENCE_TRIM",
            "SILENCE_TRIM_THRESH",
            "SILENCE_TRIM_PAD_MS",
            "OV_DYNAMIC_QUANT_GROUP_SIZE",
        }

        def apply_runtime_config(updates: Dict[str, Any]) -> Dict[str, Any]:
            unknown = set(updates) - _LIVE_KEYS
            if unknown:
                raise ValueError(f"Not a live-adjustable key: {sorted(unknown)}")
            for k, v in updates.items():
                rt._runtime_live[k] = v
            if "TTS_BACKEND" in updates:
                rt.tts_backend = updates["TTS_BACKEND"]
            return runtime_config_state()

        def resolve_seed(seed_value: Any) -> int:
            if seed_value is None:
                return random.randint(0, 2**31 - 1)
            if isinstance(seed_value, int) and 0 <= seed_value <= 2**32 - 1:
                return seed_value
            if isinstance(seed_value, (int, float)):
                return int(seed_value) % (2**32)
            raise ValueError(f"Invalid seed: {seed_value!r}")

        def _run_generate(text: str, language: str, **kwargs: Any) -> Tuple[Any, int, str]:
            if rt.generate_delay_ms > 0:
                time.sleep(rt.generate_delay_ms / 1000.0)
            rt.generate_calls.append({
                "text": text,
                "language": language,
                "kwargs": {k: v for k, v in kwargs.items()},
            })
            if rt.generate_should_fail:
                raise RuntimeError("fake generate error")
            wav = np.zeros(480, dtype=np.float32)
            job_id = kwargs.get("job_id")
            created_here = job_id is None
            if created_here:
                with rt._jobs_lock:
                    rt._job_counter += 1
                    job_id = f"fake-job-{rt._job_counter}"
                job = _FakeJobState(job_id=job_id, text=text, seed=kwargs.get("seed_value"))
                job.status = "completed"
                job.wav = wav
                job.sr = 24000
                with rt._active_jobs_lock:
                    rt._active_jobs[job_id] = job
            else:
                job = rt._active_jobs.get(job_id)
            if job is not None:
                requested = bool(kwargs.get("prosody_repair", False))
                job.metadata["prosody_repair"] = {
                    "requested": requested,
                    "outcome": "unnecessary" if requested else "not_requested",
                    "budget_seconds": 5.0 if requested else None,
                    "duration_seconds": 0.001 if requested else None,
                    "boundary_count": 0,
                }
            return wav, 24000, job_id

        def _run_generate_with_streaming(
            text: str,
            language: str,
            on_audio_chunk: Callable,
            **kw: Any,
        ) -> Any:
            if not rt.stream_vocoder_enabled:
                raise RuntimeError("streaming requires the FP32 OpenVINO vocoder")
            chunk1 = np.zeros(600, dtype=np.float32)
            chunk2 = np.zeros(600, dtype=np.float32)
            chunk3 = np.zeros(300, dtype=np.float32)
            on_audio_chunk(chunk1)
            on_audio_chunk(chunk2)
            on_audio_chunk(chunk3, is_final=True)
            all_pcm = chunk1.tobytes() + chunk2.tobytes() + chunk3.tobytes()
            return (
                np.zeros(1500, dtype=np.float32),
                24000,
                all_pcm,
                {
                    "elapsed_seconds": 0.05,
                    "reference_frames": 0,
                    "decode_boundaries": [600, 1200, 1500],
                    "generated_frames": 60,
                },
            )

        def _create_job(text: str, seed: Optional[int] = None) -> _FakeJobState:
            with rt._jobs_lock:
                rt._job_counter += 1
                job_id = f"job-{rt._job_counter}"
            job = _FakeJobState(job_id=job_id, text=text, seed=seed)
            # Start as "running" so /generate/cancel can cancel.
            with rt._active_jobs_lock:
                rt._active_jobs[job_id] = job

            rt.jobs[job_id] = {
                "job_id": job_id,
                "text": text,
                "seed": seed,
                "status": "running",
                "message": None,
                "frames_generated": 0,
                "expected_total_frames": 60,
                "progress_pct": 0.0,
                "started_at": time.monotonic(),
                "wav": None,
                "sr": 24000,
                "error": None,
            }

            # If async_jobs_complete_immediately, complete synchronously.
            if rt.async_jobs_complete_immediately:
                job.status = "completed"
                job.frames_generated = 60
                rt.jobs[job_id]["status"] = "completed"
                rt.jobs[job_id]["frames_generated"] = 60
                rt.jobs[job_id]["progress_pct"] = 100.0
                rt.jobs[job_id]["wav"] = _make_silent_wav(2400)

            return job

        def get_job_progress(job_id: str) -> Optional[Dict[str, Any]]:
            job = rt._active_jobs.get(job_id)
            if job is None:
                return None
            elapsed = time.monotonic() - job.started_at
            return {
                "job_id": job_id,
                "status": job.status,
                "frames_generated": job.frames_generated,
                "expected_total_frames": 60,
                "progress_pct": 100.0 if job.status == "completed" else 25.0,
                "elapsed_seconds": round(elapsed, 1),
                "audio_seconds_generated": round(job.frames_generated / 12, 2),
                "live_rtf_estimate": round(elapsed / max(1, job.frames_generated / 12), 2)
                if job.frames_generated > 0
                else None,
                "eta_seconds": None,
                "message": job.message,
                "voice_family_id": job.voice_family_id,
                "variant_kind": job.variant_kind,
                "style_preset": job.style_preset,
                "postprocess_applied": job.postprocess_applied,
                "applied_steps": job.metadata.get("applied_steps"),
                "prosody_repair": job.metadata.get("prosody_repair"),
            }

        def cancel_job(job_id: str) -> bool:
            job = rt._active_jobs.get(job_id)
            if job is None or job.status != "running":
                return False
            job.status = "cancelled"
            job.message = "Cancelled by user."
            job.cancel_event.set()
            return True

        def _cleanup_job(job_id: str) -> None:
            rt._active_jobs.pop(job_id, None)

        def force_unload() -> None:
            rt.force_unload_calls.append({})
            rt._model_loaded = False
            rt.model = None

        def load_model(profile: Optional[str] = None) -> None:
            rt.load_model_calls.append({"profile": profile})
            rt._model_loaded = True
            rt.model = _FakeLoadedModel(profile or "BASE")
            rt.active_profile = profile or "BASE"

        def _touch_last_request() -> None:
            pass

        def invalidate_voice_clone_prompt(voice_id: Optional[str] = None) -> None:
            pass

        def register_foreign_engine(
            is_loaded: Callable[[], bool], unload: Optional[Callable] = None
        ) -> None:
            pass

        def unload_foreign_models() -> None:
            pass

        def _apply_optional_seed(seed_value: Any) -> None:
            pass

        def _trim_silence(wav: Any, sr: int) -> Any:
            return wav

        def swap_in_progress_fn() -> bool:
            return rt.swap_in_progress

        # Attach callables
        fake_module.health_state = health_state
        fake_module.reconfig_in_progress = reconfig_in_progress
        fake_module.runtime_config_state = runtime_config_state
        fake_module.apply_runtime_config = apply_runtime_config
        fake_module.resolve_seed = resolve_seed
        fake_module._run_generate = _run_generate
        fake_module._run_generate_with_streaming = _run_generate_with_streaming
        fake_module._create_job = _create_job
        fake_module.get_job_progress = get_job_progress
        fake_module.cancel_job = cancel_job
        fake_module._cleanup_job = _cleanup_job
        fake_module.force_unload = force_unload
        fake_module.load_model = load_model
        fake_module._touch_last_request = _touch_last_request
        fake_module.invalidate_voice_clone_prompt = invalidate_voice_clone_prompt
        fake_module.register_foreign_engine = register_foreign_engine
        fake_module.unload_foreign_models = unload_foreign_models
        fake_module._apply_optional_seed = _apply_optional_seed
        fake_module._trim_silence = _trim_silence
        fake_module.swap_in_progress = swap_in_progress_fn

        # Ensure _ensure_service_started is callable for app startup race.
        def _ensure_service_started(timeout_seconds: int = 900) -> bool:
            # Fake: just return current _service_started.
            return rt._service_started

        fake_module._ensure_service_started = _ensure_service_started

        if overrides:
            for k, v in overrides.items():
                setattr(fake_module, k, v)

        sys.modules["qwen3_tts.model"] = fake_module

        qwen3_tts_pkg = sys.modules.get("qwen3_tts")
        if qwen3_tts_pkg is not None:
            setattr(qwen3_tts_pkg, "model", fake_module)

        return self

    # ── instance helpers for tests ──

    def force_unload(self) -> None:
        self.force_unload_calls.append({})
        self._model_loaded = False
        self.model = None

    def load_model(self, profile: Optional[str] = None) -> None:
        self.load_model_calls.append({"profile": profile})
        self._model_loaded = True
        self.model = _FakeLoadedModel(profile or "BASE")
        self.active_profile = profile or "BASE"

    def wait_for_job_completion(
        self, job_id: str, timeout: float = 2.0
    ) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout
        progress: Dict[str, Any] | None = None
        while time.monotonic() < deadline:
            progress = self.get_job_progress(job_id)
            if progress is None:
                return {"status": "not_found"}
            repair = progress.get("prosody_repair")
            repair_done = not isinstance(repair, dict) or repair.get("outcome") != "pending"
            if progress.get("status") in ("completed", "failed", "cancelled") and repair_done:
                return progress
            time.sleep(0.01)
        return progress or {"status": "not_found"}

    def ensure_job_status(self, job_id: str, status: str) -> bool:
        job = self._active_jobs.get(job_id)
        if job is None:
            return False
        job.status = status
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = status
        if status == "completed":
            job.frames_generated = 60
            if job_id in self.jobs:
                self.jobs[job_id]["frames_generated"] = 60
                self.jobs[job_id]["progress_pct"] = 100.0
                self.jobs[job_id]["wav"] = _make_silent_wav(2400)
        return True


def get_fake_runtime(**kwargs: Any) -> FakeModelRuntime:
    rt = FakeModelRuntime(**kwargs)
    rt.install()
    return rt

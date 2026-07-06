# Environment Reference

Authoritative list of every environment variable read by this service, grouped logically.
Defaults are as implemented in code — not marketing.

Legend:
- Required: must be set for normal operation.
- Recommended: strongly advised; omission changes behavior noticeably.
- Advanced: leave alone unless you know what you're doing.

---

## Required

| Var | Default | Read (file:line) | Description |
|-----|---------|------------------|-------------|
| `MODEL_SIZE` | `0.6B` | `config.py:35`, `model_config.py:67` | Selects 0.6B or 1.7B Base checkpoint. Drives `MODEL_REPO`, `OV_MODEL_DIR`, compression, stateful model, and vocoder settings via `apply_preset_env()`. |
| `REF_AUDIO` | `/voice/reference.wav` | `model.py:47` | Path to the reference WAV used to build the voice-clone prompt at startup. Override only if your mount differs from the compose default. |
| `REF_TEXT` | `"Welcome to Rosies..."` (see code) | `model.py:48` | Transcript of REF_AUDIO. Must match what is spoken or cloning quality suffers. |

## Runtime / backend

| Var | Default | Read (file:line) | Description |
|-----|---------|------------------|-------------|
| `TTS_BACKEND` | `openvino` (via preset; `pytorch` in model.py fallback) | `config.py:44`, `model.py:54` | Which inference backend: `openvino` or `pytorch`. `pytorch` ignores OpenVINO IR and is slower; used as rollback. |
| `DEVICE` | `cpu` | `model.py:46` | Torch/OpenVINO device. Always `cpu` for current deployment. |
| `TTS_MAX_SPEECH_SECONDS` | Preset-specific (64 for 1.7B, 64 for 0.6B) | `config.py:40` | Max speech duration per request. Baked into the IR at export time; changing it requires re-exporting. |
| `IDLE_UNLOAD_SECONDS` | `0` (disabled) | `model.py:55` | Seconds after last request to unload model and free RAM. Reload is transparent but adds latency. LOW_RAM_MODE=1 sets this. |
| `TTS_DIAG` | `0` | `model.py:803` | `1` enables diagnostic logits processor during early decode steps (for debugging generation issues). |
| `TTS_MAX_NEW_TOKENS` | unset | `model.py:817` | Diagnostic override: caps `max_new_tokens` to avoid non-terminating decode. Unset in normal operation. |
| `TTS_NON_STREAMING` | unset | `model.py:831` | `1` forces `non_streaming_mode=True` (batch prefill text delivery instead of streaming internal text-delivery). |
| `TTS_LOGITS_DIAG` | `0` | `openvino/talker.py:795` | `1` enables per-step logits diagnostics inside OVTalkerRuntime for debugging. |
| `TTS_PROMPT_DUMP_DIR` | unset (falls back to `/tmp/tts-prompt-dump`) | `model.py:367` | If set, writes a JSON dump of the voice-clone prompt and talker parameter manifest for inspection. |

## Memory / OpenVINO

| Var | Default | Read (file:line) | Description |
|-----|---------|------------------|-------------|
| `OV_MODEL_DIR` | Preset-specific (from `apply_preset_env`) | `config.py:48`, `model.py:56`, `model.py:307` | Path to the exported OpenVINO IR directory for the active profile. |
| `OV_INFERENCE_THREADS` | `6` | `model.py:64`, `runtime_config.py:15` | Number of inference threads for OpenVINO and Torch. Set close to physical core count for best latency. |
| `OV_DYNAMIC_QUANT_GROUP_SIZE` | `32` | `runtime_config.py:19`, `model.py:612` | OpenVINO dynamic quantization group size. 0 = disabled; 32 = default; 64 = faster but slightly less accurate. |
| `OV_KV_CACHE_PRECISION` | `f32` | `runtime_config.py:20` | Precision for K/V cache. |
| `OV_CACHE_DIR` | `/ov/cache` | `runtime_config.py:25` | Compiled kernel cache directory. Eliminates 60–120s JIT recompilation on restart. Set to empty string to disable. |
| `OPENVINO_MAIN_STATEFUL_MODEL` | Preset-specific | `config.py:49`, `model.py:58` | Filename of the stateful IR for the main (talker) transformer core. |
| `OPENVINO_PREDICTOR_STATEFUL_MODEL` | Preset-specific | `config.py:50`, `model.py:59` | Filename of the stateful IR for the predictor (codebook 2–16). |
| `OPENVINO_VOCODER_DIR` | Preset-specific | `config.py:55`, `model.py:99`, `runtime_config.py:43` | Path to the vocoder's IR directory. |
| `OPENVINO_VOCODER_ENABLED` | `0` (but preset may set to `1`) | `config.py:56`, `runtime_config.py:42` | Whether to use OpenVINO-accelerated vocoder (FP32-only). |
| `OPENVINO_VOCODER_DEVICE` | `CPU` | `runtime_config.py:44` | Device for vocoder (CPU is only meaningful option today). |
| `OPENVINO_VOCODER_COMPRESSION` | `fp32` | `runtime_config.py:46` | Vocoder compression metadata; runtime only supports FP32. |
| `OPENVINO_RELEASE_TORCH` | `1` (for openvino backend) | `config.py:69`, `model.py:57` | `1`: releases PyTorch core weights after OpenVINO compilation to save RAM. |
| `OPENVINO_KEEP_CODEC_ENCODER` | `1` | `openvino/talker.py:658` | `1` (default): keeps the ~0.3 GiB speech_tokenizer codec encoder resident for per-request voice cloning of new voice_ids. Set `0` to free it after startup (only for deployments that never clone a non-default voice_id). |
| `OPENVINO_LOW_CPU_MEM_USAGE` | `1` | `config.py:70`, `model_config.py:95` | Enables `low_cpu_mem_usage=True` at model load for reduced peak memory. |
| `OPENVINO_TORCH_DTYPE` | Preset-specific (`bfloat16` for OpenVINO, `float32` for PyTorch) | `config.py:68`, `model_config.py:78` | Dtype for loading the Qwen3TTSModel in Torch. |
| `OPENVINO_BUFFER_KV` | `0` | `openvino/talker.py:152` | `1` enables K/V buffering behavior in OVTalkerRuntime. Advanced tuning. |
| `OV_MAIN_COMPRESSION` | Preset-specific | `config.py:59`, `openvino/talker.py:612` | Compression mode for main core; used in metadata/active_compression reporting. |
| `OV_PREDICTOR_COMPRESSION` | Preset-specific | `config.py:60`, `openvino/talker.py:613` | Compression mode for predictor core; used in metadata/active_compression reporting. |
| `OMP_NUM_THREADS` | `6` | `model.py:21`, `runtime_config.py:72` | OpenMP threads. Set to physical core count. |
| `MKL_NUM_THREADS` | `6` | `model.py:22`, `runtime_config.py:73` | Intel MKL threads. Set to physical core count. |
| `OPENBLAS_NUM_THREADS` | `1` | `model.py:23`, `runtime_config.py:74` | OpenBLAS threads. |
| `OMP_WAIT_POLICY` | `PASSIVE` | `runtime_config.py:71` | OpenMP wait policy for thread pool behavior. |
| `ORT_INTRA_OP_NUM_THREADS` | `6` | `model.py:19`, `runtime_config.py:77` | ONNX Runtime intra-op threads (used for vocoder ONNX session if in use). |
| `ORT_INTER_OP_NUM_THREADS` | `2` | `model.py:20`, `runtime_config.py:78` | ONNX Runtime inter-op threads. |

## Voice library

| Var | Default | Read (file:line) | Description |
|-----|---------|------------------|-------------|
| `VOICE_LIBRARY_DIR` | `/voices` | `voice_library.py:23` | Container-side mount point for voice library (`vd_<id>/reference.wav` + `meta.json`). Bound from host via compose. |
| `VOICE_LIBRARY_PATH_CONTAINER` | `/voices` | `model.py:595` | Alias used only in `runtime_config_state()` mount reporting. |

## Segment library

| Var | Default | Read (file:line) | Description |
|-----|---------|------------------|-------------|
| `SEGMENT_LIBRARY_DIR` | `/segments` | `segment_library.py:25` | Container-side mount for OmniVoice segment library (`seg_<id>/clip.wav` + `meta.json`). Bound from host via compose. |

## Frontend

| Var | Default | Read (file:line) | Description |
|-----|---------|------------------|-------------|
| `FRONTEND_ENABLED` | `1` | `app.py:80` | Serve web UI at `/`. Set `0` for API-only deployments. |
| `FRONTEND_DIST_DIR` | `parent.parent.parent / "frontend" / "dist"` | `app.py:78` | Path to the compiled frontend static files. Normally auto-resolved. |

## VoiceDesign / model

| Var | Default | Read (file:line) | Description |
|-----|---------|------------------|-------------|
| `VOICE_DESIGN_MODEL_SIZE` | `1.7B` | `model.py:107`, `model_config.py:30` | Size of the VoiceDesign checkpoint. Must be `1.7B` unless an override is exported. |
| `VOICE_DESIGN_MODEL_REPO` | Preset from `VOICE_DESIGN_MODEL_SIZE` | `model_config.py:26` | Expert override for the VoiceDesign model repo. |
| `VOICE_DESIGN_MODEL_REVISION` | unset | `model.py:118` | Revision for the VoiceDesign checkpoint. |
| `VOICE_DESIGN_MAX_SPEECH_SECONDS` | Preset-specific | `model.py:105` | Capacity baked into the VoiceDesign IR at export time. |
| `MODEL_REPO` | Preset from `MODEL_SIZE` | `model_config.py:63` | Expert override for the Base model repo. |
| `MODEL_REVISION` | unset (auto-resolved) | `model.py:45` | Pin a specific Hugging Face revision; must match exported IR metadata if set. |
| `HF_TOKEN` | (from `HF_TOKEN_FILE` if set) | `model_config.py:43` | Hugging Face access token for gated checkpoints. Never log or commit. |
| `HF_TOKEN_FILE` | unset | `model_config.py:46` | Path to a file containing `HF_TOKEN`, used when token is provided as a Docker secret. |
| `MODEL_CACHE_CONTAINER_PATH` | `/root/.cache/huggingface/hub` | `model.py:593` | Internal: mount reporting path for HF model cache. |

## OmniVoice / ASR-specific

| Var | Default | Read (file:line) | Description |
|-----|---------|------------------|-------------|
| `ASR_MIN_MATCH_SHORT` | `0.70` | `asr_check.py:88` | Minimum fuzzy transcript match score for short segments (up to ASR_SHORT_SEGMENT_WORDS words). |
| `ASR_MIN_MATCH_LONG` | `0.80` | `asr_check.py:89` | Minimum fuzzy transcript match score for longer segments. |
| `ASR_SHORT_SEGMENT_WORDS` | `5` | `asr_check.py:90` | Word count boundary: segment with <= this many words is "short." |
| `ASR_SOFT_MAX_SCORE` | `0.75` | `asr_check.py:91` | Soft-reject threshold: candidates below ASR_MIN_MATCH but above this may still be accepted if logprob is high. |
| `ASR_SOFT_LOGPROB` | `-1.5` | `asr_check.py:92` | If Whisper average logprob is below this, borderline match candidates are rejected instead of accepted. |

## Silence trim

| Var | Default | Read (file:line) | Description |
|-----|---------|------------------|-------------|
| `SILENCE_TRIM` | `1` (enabled) | `model.py:609,685` | Trim leading/trailing silence from generated audio. Set `0` to disable. |
| `SILENCE_TRIM_THRESH` | `0.01` | `model.py:610,693` | Silence threshold as a fraction of the clip's peak amplitude. |
| `SILENCE_TRIM_PAD_MS` | `30` | `model.py:611,697` | Padding (ms) kept after detected silence boundary to avoid clipping consonants. |

## Debug / dev (do not use in production)

| Var | Default | Read (file:line) | Description |
|-----|---------|------------------|-------------|
| `TTS_DIAG` | `0` | `model.py:803` | Enables diagnostic logits logging in early decode steps (OpenVINO only). Also triggered by `/tmp/tts_diag` file. |
| `TTS_MAX_NEW_TOKENS` | unset | `model.py:817` | Caps max_new_tokens; used for catching non-terminating decode. Also from `/tmp/tts_max_new` file. |
| `TTS_NON_STREAMING` | unset | `model.py:831` | Forces non_streaming_mode=True. Also from `/tmp/tts_non_streaming` file. |
| `TTS_LOGITS_DIAG` | `0` | `openvino/talker.py:795` | Per-step logits diagnostics inside OVTalkerRuntime. |
| `TTS_PROMPT_DUMP_DIR` | unset | `model.py:367` | Write reference prompt and talker parameter manifests. Fallback `/tmp/tts-prompt-dump` if file `/tmp/tts_prompt_dump` exists. |

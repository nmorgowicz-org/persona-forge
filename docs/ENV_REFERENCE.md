# Environment Reference

Authoritative list of environment variables for this service.
Defaults are as implemented in code.

For a minimal setup, see “Minimal required” below; everything else is optional.

Legend:
- Required: must be set.
- Recommended: omission changes behavior noticeably.
- Advanced: leave alone unless you know what you're doing.

---

## Minimal required

These are the only variables a normal user must set. All others have safe defaults.

| Var | Required? | Description |
|-----|-----------|-------------|
| `REF_AUDIO_PATH` | **Yes** | Host path to the reference WAV. Mounted as `/voice/reference.wav` in the container. |
| `REF_TEXT` | **Yes** | Exact transcript of REF_AUDIO. Must match what is spoken; startup fails if unset. |
| `HF_TOKEN` | Yes, if gated | Hugging Face access token for gated checkpoints. Never log or commit. |

Recommended (simple knobs):

| Var | Default | Description |
|-----|---------|-------------|
| `MODEL_SIZE` | `1.7B` | Base checkpoint size. Leave at 1.7B unless you specifically need 0.6B. |
| `TTS_BACKEND` | `openvino` | Inference backend. Use `openvino` (default) or `pytorch` as rollback. |
| `LOW_RAM_MODE` | `1` | Enables idle unload + malloc tuning; recommended on 10–15 GiB hosts. |
| `FRONTEND_ENABLED` | `1` | Serves the web UI at `/`. Set `0` for API-only deployments. |

---

## Runtime / backend

| Var | Default | Description |
|-----|---------|-------------|
| `TTS_BACKEND` | `openvino` | `openvino` (default, accelerated) or `pytorch` (rollback, slower). |
| `DEVICE` | `cpu` | Torch/OpenVINO device; always `cpu` in current deployments. |
| `TTS_MAX_SPEECH_SECONDS` | Preset-specific (e.g. 64) | Max speech duration per request. Baked into IR at export time; changing it requires re-export. |
| `IDLE_UNLOAD_SECONDS` | `0` | Seconds after last request to unload model and free RAM; reload is transparent but adds latency. Set by LOW_RAM_MODE. |

## Memory / OpenVINO (advanced)

Unless you're tuning performance, leave these at defaults.

| Var | Default | Description |
|-----|---------|-------------|
| `OV_MODEL_DIR` | Preset-specific | Path to exported OpenVINO IR. |
| `OV_INFERENCE_THREADS` | Auto (cores-2) | Inference threads for OpenVINO and Torch. |
| `OV_DYNAMIC_QUANT_GROUP_SIZE` | `32` | OpenVINO dynamic quant group size: 0 = off; 32 = default; 64 = faster, slightly less accurate. |
| `OV_KV_CACHE_PRECISION` | `f32` | K/V cache precision. |
| `OV_CACHE_DIR` | `/ov/cache` | Compiled kernel cache; set to empty to disable (slower restarts). |
| `OPENVINO_MAIN_STATEFUL_MODEL` | Preset-specific | Stateful IR for the main transformer core. |
| `OPENVINO_PREDICTOR_STATEFUL_MODEL` | Preset-specific | Stateful IR for the predictor (codebook 2–16). |
| `OPENVINO_VOCODER_DIR` | Preset-specific | Vocoder IR path. |
| `OPENVINO_VOCODER_ENABLED` | `1` (via preset) | Use OpenVINO-accelerated vocoder (FP32-only). |
| `OPENVINO_VOCODER_DEVICE` | `CPU` | Device for vocoder. |
| `OPENVINO_VOCODER_COMPRESSION` | `fp32` | Vocoder compression metadata (FP32 only). |
| `OPENVINO_RELEASE_TORCH` | `1` | Release PyTorch weights after OpenVINO compilation to save RAM. |
| `OPENVINO_KEEP_CODEC_ENCODER` | `1` | Keep ~0.3 GiB codec encoder for per-request voice cloning. Set `0` only if you never clone a non-default voice. |
| `OPENVINO_LOW_CPU_MEM_USAGE` | `1` | Use low CPU memory mode at model load. |
| `OPENVINO_TORCH_DTYPE` | Preset-specific | Torch load dtype (bfloat16 for OpenVINO). |
| `OPENVINO_BUFFER_KV` | `0` | K/V buffering in OVTalkerRuntime (advanced tuning). |
| `OV_MAIN_COMPRESSION` | Preset-specific | Compression mode for main core (metadata). |
| `OV_PREDICTOR_COMPRESSION` | Preset-specific | Compression mode for predictor (metadata). |
| `OMP_NUM_THREADS` | Auto | OpenMP threads. |
| `MKL_NUM_THREADS` | Auto | MKL threads. |
| `OPENBLAS_NUM_THREADS` | `1` | OpenBLAS threads. |
| `OMP_WAIT_POLICY` | `PASSIVE` | OpenMP wait policy. |
| `ORT_INTRA_OP_NUM_THREADS` | Auto | ONNX Runtime intra-op threads. |
| `ORT_INTER_OP_NUM_THREADS` | `2` | ONNX Runtime inter-op threads. |

## Voice library

| Var | Default | Description |
|-----|---------|-------------|
| `VOICE_LIBRARY_DIR` | `/voices` | Container-side path for voice library (`vd_<id>/reference.wav` + `meta.json`). Mounted via compose. |

## Segment library

| Var | Default | Description |
|-----|---------|-------------|
| `SEGMENT_LIBRARY_DIR` | `/segments` | Container-side path for OmniVoice segment library. Mounted via compose. |

## Frontend

| Var | Default | Description |
|-----|---------|-------------|
| `FRONTEND_ENABLED` | `1` | Serve web UI at `/`. Set `0` for API-only. |
| `FRONTEND_DIST_DIR` | Auto-resolved | Path to compiled frontend static files; normally auto-resolved. |

## VoiceDesign / model (advanced)

Leave at defaults unless you know what you're doing.

| Var | Default | Description |
|-----|---------|-------------|
| `VOICE_DESIGN_MODEL_SIZE` | `1.7B` | VoiceDesign checkpoint size. |
| `VOICE_DESIGN_MODEL_REPO` | Preset | Expert override for VoiceDesign model repo. |
| `VOICE_DESIGN_MODEL_REVISION` | unset | Pin specific VoiceDesign revision. |
| `VOICE_DESIGN_MAX_SPEECH_SECONDS` | Preset-specific | Capacity baked into VoiceDesign IR. |
| `MODEL_REPO` | Preset from MODEL_SIZE | Expert override for Base model repo. |
| `MODEL_REVISION` | unset | Pin specific Base revision; must match exported IR metadata. |
| `HF_TOKEN` | (from HF_TOKEN_FILE if set) | Hugging Face token for gated checkpoints. |
| `HF_TOKEN_FILE` | unset | Path to a file containing HF_TOKEN (Docker secret pattern). |
| `MODEL_CACHE_CONTAINER_PATH` | `/root/.cache/huggingface/hub` | Internal: mount reporting path for HF cache. |

## OmniVoice / ASR (advanced)

| Var | Default | Description |
|-----|---------|-------------|
| `ASR_MIN_MATCH_SHORT` | `0.70` | Min fuzzy transcript match for short segments. |
| `ASR_MIN_MATCH_LONG` | `0.80` | Min fuzzy transcript match for longer segments. |
| `ASR_SHORT_SEGMENT_WORDS` | `5` | Word count boundary for “short” vs “long.” |
| `ASR_SOFT_MAX_SCORE` | `0.75` | Soft-reject fuzzy score threshold. |
| `ASR_SOFT_LOGPROB` | `-1.5` | Whisper logprob threshold for soft-reject. |

## Silence trim

| Var | Default | Description |
|-----|---------|-------------|
| `SILENCE_TRIM` | `1` | Trim leading/trailing silence from generated audio. Set `0` to disable. |
| `SILENCE_TRIM_THRESH` | `0.01` | Silence threshold as fraction of peak amplitude. |
| `SILENCE_TRIM_PAD_MS` | `30` | Padding (ms) after detected silence to avoid clipping consonants. |

## Debug / dev (do not use in production)

| Var | Default | Description |
|-----|---------|-------------|
| `TTS_DIAG` | `0` | Diagnostic logits logging in early decode steps. Also via `/tmp/tts_diag`. |
| `TTS_MAX_NEW_TOKENS` | unset | Caps max_new_tokens to catch non-terminating decode. Also via `/tmp/tts_max_new`. |
| `TTS_NON_STREAMING` | unset | Forces non_streaming_mode=True. Also via `/tmp/tts_non_streaming`. |
| `TTS_LOGITS_DIAG` | `0` | Per-step logits diagnostics inside OVTalkerRuntime. |
| `TTS_PROMPT_DUMP_DIR` | unset | Write reference prompt and talker parameter manifests. |

## Export

For the `export` service (compose profile `export`):

| Var | Default | Description |
|-----|---------|-------------|
| `EXPORT_TARGET` | `base` | `base` (Base only), `voice_design` (VoiceDesign only), or `both` (unified export for all targets). |
| `OV_OUTPUT_ROOT` | `/ov` | Root directory for exported IR. |

Normal users should run the export via Docker Compose; `EXPORT_TARGET` is already set to `both` in compose.yml.

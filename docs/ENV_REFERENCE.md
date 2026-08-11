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

The app starts without a default reference voice. Normal users can add or generate voices in the UI.

| Var | Required? | Description |
|-----|-----------|-------------|
| `REF_AUDIO_PATH` | No | Optional host path to a default reference WAV. When present, it is mounted as `/voice/reference.wav`, promoted into the Voice Library, and analyzed with Whisper. |
| `REF_TEXT` | No | Optional power-user transcript override for `REF_AUDIO_PATH`. Qwen backends use it if supplied; Pocket TTS ignores it. |
| `REF_TEXT_AUTO` | No (`whisper`) | Transcript bootstrap when `REF_AUDIO_PATH` is set and `REF_TEXT` is omitted. Default `whisper` transcribes the audio and stores review metadata. Set `0` to disable. |
| `HF_TOKEN` | Yes, if gated | Hugging Face access token for gated checkpoints. Never log or commit. |

Recommended (simple knobs):

| Var | Default | Description |
|-----|---------|-------------|
| `MODEL_SIZE` | `1.7B` | Base checkpoint size. Leave at 1.7B unless you specifically need 0.6B. |
| `TTS_BACKEND` | `pocket_tts` | Inference backend. `pocket_tts` is the product default (self-contained, no export step); switch to `openvino` for the accelerated Qwen path on Intel CPUs (requires export), or `pytorch` as a portable rollback. |
| `LOW_RAM_MODE` | `1` | Enables idle unload + malloc tuning; recommended on 10–15 GiB hosts. |
| `FRONTEND_ENABLED` | `1` | Serves the web UI at `/`. Set `0` for API-only deployments. |

---

## Runtime / backend

| Var | Default | Description |
|-----|---------|-------------|
| `TTS_BACKEND` | `pocket_tts` | `pocket_tts` (default, self-contained, no export needed), `openvino` (opt-in accelerated Qwen path on Intel CPUs, requires export), or `pytorch` (portable rollback, slower). When the Qwen3-TTS engine is invoked without an explicit value, the preset fallback auto-selects `openvino` if a valid IR export already exists on disk, else `pytorch` — it never triggers the export itself. `/health` reports `backend_source`/`backend_fallback_choice`. |
| `TTS_DEVICE` | auto-detect | Forces the torch device the Qwen3-TTS PyTorch backend and OmniVoice load onto: `cuda`, `xpu`, `mps`, or `cpu`. Unset auto-detects the best available (`cuda` > `xpu` > `mps` > `cpu`). A forced-but-unavailable device warns and falls back to `cpu` rather than failing. `DEVICE` is accepted as a legacy alias. |
| `OPENVINO_DEVICE` | `AUTO` | OpenVINO compile target for the talker/main/predictor cores (`CPU`/`GPU`/`AUTO`); `GPU` targets an Intel iGPU. Separate from the vocoder's own `OPENVINO_VOCODER_DEVICE`. |
| `TTS_MAX_SPEECH_SECONDS` | Preset-specific (e.g. 64) | Max speech duration per request. Baked into IR at export time; changing it requires re-export. |
| `IDLE_UNLOAD_SECONDS` | `0` | Seconds after last request to unload model and free RAM; reload is transparent but adds latency. Set by LOW_RAM_MODE. |
| `ALIGNER_MODEL_PATH` | (unset) | Optional override path to the MMS-300M forced-aligner ONNX model used by Precise prosody. When unset (the default) the model auto-downloads from Hugging Face on first alignment (pinned to an immutable revision, cached like the base checkpoints) — no manual placement needed. Set this only to point at a locally-provisioned copy on air-gapped hosts. Lazily loaded on first alignment and idle-unloaded. |
| `ALIGNER_PROVIDERS` | `CPUExecutionProvider` | Comma-separated onnxruntime execution providers for the aligner (portable CPU baseline; add OpenVINO/CoreML where available). |
| `ALIGNER_LATENCY_BUDGET_SECONDS` | `5` | Fail-closed warm p95 budget for Precise alignment. Job responses and `GET /alignment/performance` expose observed duration and budget status. |
| `ALIGNER_IDLE_UNLOAD_SECONDS` | `120` | Seconds after the serialized alignment queue drains before releasing the ONNX session. |
| `GENERATION_REPAIR_BUDGET_SECONDS` | `5` | Hard per-request deadline for explicit `prosody_repair` on complete-file generation routes. Timeout returns the original un-repaired output with a `budget_fallback` outcome. |

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
| `TTS_DEFAULT_DSP` | `on` | Applies the transparent `default` house preset (-16 LUFS normalization and -1 dBFS sample-peak limiting) when `style_preset` is omitted. Set `off` to restore trim-only output by default; explicit presets still apply. |

## Pocket TTS backend

Only used when TTS_BACKEND=pocket_tts. Pocket TTS does not use or require REF_TEXT; it builds voice state from reference audio only.

| Var | Default | Description |
|-----|---------|-------------|
| `POCKET_TTS_TEMP` | `1.2` | Sampling temperature. |
| `POCKET_TTS_LSD_DECODE_STEPS` | `5` | LSD refinement steps per audio frame. |
| `POCKET_TTS_EOS_THRESHOLD` | `-4.0` | Logits-based EOS threshold. |
| `POCKET_TTS_FRAMES_AFTER_EOS` | `4` | Extra audio frames kept after the last speech frame before truncating trailing silence. Each frame ≈ 1/12 s at 24 kHz. Higher → longer tail; lower → more aggressive trim; 0 → trim aggressively. |
| `POCKET_TTS_NOISE_CLAMP` | unset | Noise magnitude cap (logged; wiring TBD). |
| `POCKET_TTS_QUANTIZE` | `0` | Enable int8 quantization (0/1). |

When cloning is available, the mounted REF_AUDIO is automatically registered as a voice named "Mounted reference (Default)" in the library so it can be selected explicitly as well as used as the default.

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

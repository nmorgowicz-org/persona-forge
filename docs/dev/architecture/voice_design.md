# VoiceDesign + Web Frontend

> Audience: a fresh AI coding agent with **zero prior context** on this repo. Read this doc top
> to bottom before writing code. It tells you what exists, how it works, and why decisions were made.
> Where a decision was made, the reasoning is included so you don't need to re-derive it — but you may
> challenge it with the human if you find a contradiction.

## 0. Orientation

This is `qwen3-tts-openvino`: a CPU-only Docker image that serves the Qwen3-TTS voice-cloning
model over HTTP (Flask + Gunicorn, single worker, single model in memory, port 8318), using
OpenVINO for the two transformer cores (talker "main" model + "predictor") and an FP32 OpenVINO
vocoder. PyTorch is kept only for glue code (prompt construction, sampling loop, tokenizer).

Key source files (`src/qwen3_tts/`):
- `app.py` — Flask routes: `/health`, `/generate`, `/v1/audio/speech`, `/generate/stream`,
  `/stream_internal`, `/batch_internal`, `/voice_design`, `/voices`, frontend serving.
- `model.py` — model load/lifecycle, `ModelProfile`, `_run_generate`, `_run_generate_with_streaming`,
  `_apply_optional_seed`, `health_state()`. Holds module-level globals: `model`,
  `voice_clone_prompt`, `ov_runtime`.
- `voice_design.py` — lazy model-swap manager, `run_voice_design_request()`,
  `swap_in_progress()`, `get_progress()`.
- `voice_library.py` — filesystem-backed library mapping `voice_id` to WAV + metadata.
- `presets.py` — `MODEL_SIZE` → preset dict (compression, IR paths, capacity). Pure, no env I/O.
  Also defines `VOICE_DESIGN_PRESETS` and `get_voice_design_preset()`.
- `config.py` — `apply_preset_env()` reads `os.environ`, resolves the preset, writes low-level
  `OPENVINO_*`/`OV_*` env vars via `_setdefault()` (never overwrites an explicit user override).
- `openvino/talker.py` — `OVTalkerRuntime`, wraps the stateful K/V cache graph.
- `openvino/runtime_config.py` — thread/env setup, `get_ov_config()`.
- `model_config.py` — `MODEL_PRESETS` (MODEL_SIZE → HF repo), HF token/auth helpers,
  `resolve_voice_design_model_repo()`.

Deployment surface: `compose.yml` (`qwen3-tts` service + `export` + `export-voice-design` services,
same image, different command), `.env.example`, `README.md`, `docs/HOW_TO_RUN.md`.

The current production deployment (dockermisc1) runs `MODEL_SIZE=1.7B`.

## 1. Goal

We let a user design a voice by natural-language prompt, preview/test it, tweak it, and — once
satisfied — feed the result into the existing Base-model zero-shot cloning flow so the resulting
cloned voice is usable through the OpenAI-compatible `/v1/audio/speech` endpoint, for Hermes or
other TTS consumers.

Source material: `docs/plans/alexandria_ideas.md` (from
https://github.com/Finrandojin/alexandria-audiobook), §§2–3, 8, 10. That doc is the design
authority for this feature; this doc translates it into concrete file-level decisions for this
repo. Where alexandria_ideas.md was vague, we made a concrete decision — follow those decisions
unless you find a reason not to, and note the deviation if you deviate.

## 2. Architecture constraints (decisions that shaped this design)

These constraints explain why the implementation looks the way it does:

1. **One model in memory at a time.** `model.py` module-level globals (`model`,
   `voice_clone_prompt`, `ov_runtime`) assume exactly one loaded checkpoint. No multi-model or
   multi-tenant abstraction.

2. **Single-worker Gunicorn + single `ThreadPoolExecutor(max_workers=1)`.** All inference
   (`model.executor.submit(...)`) is serialized through one executor thread. Any new endpoint
   submits its work through this same executor, not its own thread pool.

3. **Originally one fixed reference voice per container**, set at startup from `REF_AUDIO_PATH` /
   `REF_TEXT`. VoiceDesign's "feed into the base model for cloning" requirement meant we had to
   relax this (see §4.4: per-request / named-voice cloning).

4. **`OPENVINO_RELEASE_CODEC=0` is required for VoiceDesign's "capture → clone" handoff.**
   The PyTorch codec encoder must remain resident so `create_voice_clone_prompt()` can run at
   runtime. Any deployment wanting `voice_id` requests must set `OPENVINO_RELEASE_CODEC=0`.

5. **`qwen_tts` package (v0.1.1) exposes three separate top-level generation methods**, gated by
   checkpoint type (`self.model.tts_model_type`), not by a runtime flag:
   - `generate_voice_clone()` — requires a **Base** checkpoint. No instruct support.
   - `generate_voice_design()` — requires a **VoiceDesign** checkpoint (different HF repo,
     structurally same 1.7B-class architecture as Base 1.7B, different weights).
     Takes `instruct` (the full natural-language voice description prompt — for VoiceDesign,
     `instruct` defines both voice identity AND delivery style/emotion: gender, age, accent,
     timbre, personality, energy, pacing. No separation between "identity" and "emotion"; it is
     a single holistic description).
   - `generate_custom_voice()` — requires a **CustomVoice** checkpoint, 9 built-in speakers.
     For CustomVoice, `instruct` is ONLY emotion/delivery style; voice identity is fixed by the
     `speaker` argument. This is a fundamentally different semantic role than VoiceDesign's instruct.

   Each requires loading a **different HF checkpoint**. There is no single checkpoint that supports
   both cloning and design. This is why we chose a **lazy model-swap** approach: VoiceDesign is
   not "always on."

6. **Export is model-checkpoint-specific.** `scripts/export.py` and
   `src/export/export_openvino.py` map one `MODEL_SIZE` → one HF repo. The VoiceDesign checkpoint
   gets its own export pass into its own `/ov/<size>-voicedesign` directory tree — same export
   tooling, different source repo and destination.

7. **No auth/multi-tenancy.** The service has no user accounts, no auth, and is meant to run on a
   trusted network or behind an authenticated reverse proxy (see `SECURITY.md`). Voice storage
   (§7) is simple filesystem-backed, not a database with per-user ACLs.

## 3. High-level architecture (implemented)

We adopted the alexandria_ideas.md lazy-model-swap design:

```
┌─────────────────────────────────────────────────────────────┐
│ qwen3-tts container (single process, single executor thread) │
│                                                              │
│  Base 1.7B (always resident, serves /v1/audio/speech,       │
│             /generate, /generate/stream)                     │
│                                                              │
│  On POST /voice_design:                                      │
│    1. Reject new /v1/audio/speech etc. with 503 (busy)       │
│       while swap is in progress (readiness flag)             │
│    2. Unload Base model + IR from memory                     │
│    3. Load VoiceDesign model + IR from /ov/<size>-voicedesign│
│    4. generate_voice_design(text=sample_text,                │
│                              instruct=description)            │
│    5. Save resulting WAV to the voice library (§7)           │
│    6. Unload VoiceDesign model + IR                          │
│    7. Reload Base model + IR (same as startup)               │
│    8. Clear readiness flag — service is "up" again            │
│  Return: voice_id + WAV (or reference) to the caller          │
│                                                              │
│  Client then either:                                         │
│    a) POSTs /v1/audio/speech with {"voice_id": "<id>"} to    │
│       use the newly captured reference for cloning, or       │
│    b) POSTs the returned WAV directly as ref_audio to a new  │
│       per-request-clone code path (§4.4)                     │
└─────────────────────────────────────────────────────────────┘
```

This keeps "one container, one port, one primary model in memory at a time" while adding
VoiceDesign as an occasional, slower, blocking operation — not a concurrently-resident second
model.

**Model-swap cost is real and visible.** We expect tens of seconds (unload + IR load + first-inference
JIT unless the OV kernel cache is warm for both graphs). We document this prominently; we do not
hide it behind a spinner with no explanation.

## 4. Backend changes

### 4.1 Export: VoiceDesign IR

We added support for exporting the VoiceDesign checkpoint:

- `model_config.py::MODEL_PRESETS` got a companion: `VOICE_DESIGN_MODEL_PRESETS`:
  ```python
  VOICE_DESIGN_MODEL_PRESETS = {
      "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
  }
  ```
  Confirmed (2026-07-02): this repo exists on Hugging Face and its model card documents using
  `generate_voice_design(text=<target text>, instruct=<natural-language voice description>)`,
  matching the `qwen_tts` 0.1.1 signature. Only 1.7B exists (no 0.6B-VoiceDesign); this is
  consistent with alexandria_ideas.md.

- `presets.py` defines a `voice_design` preset keyed by size (only `1.7B`), pointing its
  `_ir_paths()` at `/ov/1.7B-voicedesign/...` so it never collides with the Base IR tree.
  We use a smaller capacity (20s / 240 frames) — VoiceDesign only generates a short sample
  utterance for reference capture.

- A new Compose service `export-voice-design` runs `scripts/export.py` against the VoiceDesign
  preset. We reuse `src/export/export_openvino.py` and `scripts/transform_stateful_ir.py` as-is —
  parameterized via `--output-dir` and HF repo/compression flags.

- The VoiceDesign checkpoint's `tts_model_type` is confirmed to be `"voice_design"`. This is
  asserted inside `qwen_tts`'s `generate_voice_design()` — if it fires, it means the wrong
  repo was configured.

### 4.2 Runtime: model-swap manager

We added `src/qwen3_tts/voice_design.py`, responsible for:

- **`run_voice_design_request()`** — called via `model.executor.submit(...)`. Swaps to VoiceDesign
  checkpoint, runs `generate_voice_design()`, saves the WAV, swaps back to Base. All work runs
  inside `model.executor` (the single serialized worker thread), never off-thread, to avoid racing
  with in-flight generation calls.

- **`swap_in_progress()`** — a module-level flag checked by `app.py`'s `_ready()` and all generation
  endpoints. During a swap, `/health` and all generation endpoints return 503. After first
  successful load, idle-unloaded requests block in the executor and reload transparently.

- **`get_progress()`** — exposes phase + ETA to the frontend via `GET /voice_design/progress`.

To support swapping, we refactored `model.py::load_model()` to accept a `ModelProfile` argument
(model repo, revision, OV model dir, stateful model paths, compression settings) rather than
reading frozen module-level constants. Two instances exist at import time:
`BASE_PROFILE` and `VOICE_DESIGN_PROFILE`. This was the largest refactor in this feature — we
tested that the Base path still works identically afterward before adding VoiceDesign on top.

### 4.3 New endpoint: `POST /voice_design`

Added to `app.py`, following existing conventions:

```
POST /voice_design
Request:
{
  "description": "Deep male baritone, rich chest resonance, warm smooth timbre, hint of gravelly texture.",
  "sample_text": "Hello, this is my voice.",
  "language": "English"          # optional, default "English"
}
Response (200):
{
  "voice_id": "vd_3f9a...",       # opaque id, see §7
  "sample_rate": 24000,
  "audio_base64": "<wav bytes, base64>"
}
Response (503): {"error": "Model busy (voice design swap in progress)"}
Response (500): {"error": "Voice design failed: <reason>"}
```

Implementation:
1. Validate `description` and `sample_text` are non-empty.
2. Submit to executor: swap to VoiceDesign → call `generate_voice_design(text=sample_text,
   language=language, instruct=description)` → get `(wavs, sr)` → swap back to Base.
3. Persist the WAV + description + sample_text to the voice library, get a `voice_id`.
4. Return WAV as base64 for immediate client preview, and keep it retrievable via `voice_id`.
5. On any exception, `finally` block restores Base profile.

### 4.4 Per-request / named-voice cloning

We extended the generation endpoints to accept an optional `voice_id`:

```
POST /v1/audio/speech
{
  "input": "...",
  "voice_id": "vd_3f9a...",   # optional; if omitted, use the startup-time default voice
  "language": "English",
  "response_format": "mp3"
}
```

How it works:
1. If `voice_id` is present: look it up in the voice library, get stored reference WAV + `sample_text`.
   For VoiceDesign-captured samples, `ref_text = sample_text` (VoiceDesign directly synthesizes
   `sample_text` in the described voice). No ASR step needed.
2. Call `model.create_voice_clone_prompt(ref_audio=<captured wav>, ref_text=<sample_text>)` to
   build a fresh `voice_clone_prompt` for this request. Requires `OPENVINO_RELEASE_CODEC=0`.
3. **We cache the built `voice_clone_prompt` per `voice_id`** (in-process dict, invalidated on
   model reload/idle-unload) so repeated requests don't rebuild it.
4. If `voice_id` is omitted, behavior is unchanged (uses the startup default). The Hermes
   production path must not regress.

Implemented once in `_run_generate` / `_run_generate_with_streaming` (threaded through as a
parameter, defaulting to the module global when not provided).

## 5. Instruct/tone (supported in API, behavior depends on checkpoint)

We added optional `"instruct"` to `/v1/audio/speech` and `/generate`. Behavior:

- **Base** (current deployment): instruct is not supported — the model ignores it. We accept the
  field in the API for forward-compatibility, log a brief note, treat it as a no-op.
- **CustomVoice** (future, not in scope): instruct controls emotion/delivery of the built-in
  speaker.
- **VoiceDesign**: instruct IS the voice description (identity + delivery) — see §2.

We do not error on unknown instruct when using Base. Full CustomVoice support
(`generate_custom_voice()`) is out of scope.

## 6. Voice library (implemented)

A minimal persistence layer mapping `voice_id -> {wav_path, description, sample_text, created_at, seed}`.

Decision: **filesystem-backed, not a database.** Matches the existing "no database, bind-mounted
host directories" pattern.

- Bind-mounted directory: `VOICE_LIBRARY_PATH` (default `./data/voices`) → `/voices` in the container.
- Layout: `/voices/<voice_id>/reference.wav` + `/voices/<voice_id>/meta.json`
  (`{"description": ..., "sample_text": ..., "language": ..., "created_at": ..., "seed": ...}`).
- `voice_id`: `vd_` prefix + 12-hex random id.
- Endpoints: `GET /voices` (list), `GET /voices/<voice_id>` (metadata + WAV). Path-traversal guard
  is in place.
- No auth (consistent with the rest of the service).

The `seed` field in each voice's metadata was added to support the tune/tweak workflow: re-rolling
the same seed reproduces the same reference audio.

## 7. Web frontend (implemented)

The frontend is a Vite + React + TypeScript + Tailwind + shadcn/ui + Radix + Framer Motion SPA.
This stack was deliberate and non-optional. Rationale:

- Control-panel SPA with chips, dropdowns, modals, and waveform states — not a landing page.
- shadcn/ui + Radix: copy-pasted, typed components with correct ARIA, keyboard nav, focus
  trapping. Only what you use is in your bundle.
- Framer Motion: required for motion (chip selection, swap-in-progress, waveforms).
- Served as a static export (`vite build` → `dist/`) from Flask at `/`, same port 8318, no SSR,
  no Node.js at runtime.

### 7.1 Layout

Three-zone layout (alexandria_ideas.md §10.3):
- **Left: Voice control** — VoiceDesign panel, cloning panel, presets, runtime settings.
- **Center: Text editor + generate controls + waveform.**
- **Right: History** — past generations with seed/voice/replay.

### 7.2 Guided Voice Design UX

Unstructured prompts create unstable or unusable voices (alexandria VOICE_REFERENCE.md). We do not
expose the full lexicon as raw text — we encode it into chips/selectors and a composed prompt.

The VoiceDesign API has one free-text lever (`description` → `instruct`). The frontend assembles it
in this fixed order: accent → demographics → register → texture/timbre → persona/character.
Physical descriptors first, character/energy last.

Chip categories:

- **Accent / language:** Tier 1: English (US/UK/AU/IE). Tier 2: labeled "Experimental" (Boston,
  NY, Southern US, Scottish, RP, Kiwi, etc.).
- **Demographics:** Gender, age range.
- **Register:** Bass/Baritone/Tenor/Alto/Mezzo-Soprano/Soprano.
- **Texture/timbre:** Smooth (Silky, Even, Warm, Rich), Resonance (Dark, Deep, Full, Grounded),
  Precision (Crisp, Clear, Precise), Grit (Slight gravel), Bright.
- **Persona:** Assistant-forward (Warm Assistant, Confident Professional, Calm & Grounded, Bubbly),
  Companion/social (Playful, Flirty, Mysterious, Sultry/Intimate), Power dynamic
  (Authoritative/Dominant, Soft/Submissive).

**Composition rules:**
- The UI assembles a description string from selections.
- The user can accept, switch to advanced text mode, or adjust individual chips.
- Known unstable combinations (e.g. Bright + Bubbly) trigger inline warnings.
- Starter presets (3-5 curated bundles) ship as one-click templates.

### 7.3 Sample text

Short by default (10-12s max). We enforce persona-linked defaults (Warm Assistant, Confident
Professional, etc.) and validate <= 15s at the API level.

### 7.4 History and state

History panel backed by `GET /voices` + local generation log (localStorage/IndexedDB).
Client store uses Zustand.

### 7.5 Runtime control panel

We exposed a control panel (`GET /runtime/config` + `PATCH /runtime/config`) for selected knobs.
Three categories:

1. **Live-adjustable** via swap mechanism: `TTS_BACKEND`, `IDLE_UNLOAD_SECONDS`,
   `SILENCE_TRIM`-related flags, `OV_DYNAMIC_QUANT_GROUP_SIZE`. Live `MODEL_SIZE` swap (0.6B ↔ 1.7B)
   is supported if both IR trees are exported and present.
2. **Read-only display:** Docker/host-level settings (mem_limit, volume mounts, token presence).
   Shown for transparency, not editable.
3. **Not exposable without restart/re-export:** baked into OpenVINO IR (e.g. `TTS_MAX_SPEECH_SECONDS`).

Security note: category 1 is an unauthenticated mutating endpoint on a service with no auth/TLS.
This is a known decision — "trusted network only" is the existing posture.

### 7.6 Opt-out

`FRONTEND_ENABLED=1` controls whether the frontend is served; backend works standalone via
curl/Hermes with no frontend present.

## 8. Implementation sequence (for reference)

The work was done in this order:

1. Confirmed the VoiceDesign HF checkpoint repo (`Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`).
2. Refactored `model.py::load_model()` to take `ModelProfile`; verified Base-only behavior unchanged.
3. Exported VoiceDesign IR; verified it loads and `generate_voice_design()` runs standalone.
4. Added model-swap manager + `/voice_design` endpoint; verified swap-in-progress 503,
   fail-safe restore of Base on error, and normal `/v1/audio/speech` after swap.
5. Added voice library and `voice_id` support in generation endpoints; verified end-to-end
   VoiceDesign → clone → speak with `OPENVINO_RELEASE_CODEC=0`.
6. Updated docs: `README.md`, `docs/HOW_TO_RUN.md`, `.env.example`, `compose.yml`.
7. Built frontend after backend loop worked via curl: scaffolded Vite + React + shadcn/ui,
   wired `/voice_design`, `voice_id`, history, runtime panel, and polish pass.

## 9. Explicit non-goals (decisions made)

Carried from alexandria_ideas.md §1 "We intentionally drop":
- Audiobook-centric workflows (M4B, Audacity, large scripts)
- Persona auto-casting / LLM-driven script annotation
- LoRA/PEFT voice baking (alexandria §9 — revisit only if zero-shot cloning proves insufficient)
- CustomVoice's 9 built-in speakers (out of scope)
- Authentication/multi-tenancy beyond what already exists

We did not scope-creep into these.

# Plan: Capacity UX (`TTS_MAX_SPEECH_SECONDS`) + VoiceDesign & Web Frontend

> Audience: a fresh AI coding agent with **zero prior context** on this repo. Read this doc top
> to bottom before writing code. It tells you what already exists, what to build, in what order,
> and how to verify each step. Where a decision was made for you, the reasoning is included so you
> don't need to re-derive it — but you may challenge it with the human if you find a contradiction.

## 0. Orientation — read this first

This is `qwen3-tts-openvino`: a CPU-only Docker image that serves the Qwen3-TTS voice-cloning
model over HTTP (Flask + Gunicorn, single worker, single model in memory, port 8318), using
OpenVINO for the two transformer cores (talker "main" model + "predictor") and an FP32 OpenVINO
vocoder. PyTorch is kept only for glue code (prompt construction, sampling loop, tokenizer).

Key source files (`src/qwen3_tts/`):
- `app.py` — Flask routes: `/health`, `/generate`, `/v1/audio/speech`, `/generate/stream`,
  `/stream_internal`, `/batch_internal`.
- `model.py` — model load/lifecycle, `_run_generate`, `_run_generate_with_streaming`,
  `_apply_optional_seed`, `health_state()`. Holds module-level globals: `model`,
  `voice_clone_prompt`, `ov_runtime`.
- `presets.py` — `MODEL_SIZE` → preset dict (compression, IR paths, capacity). Pure, no env I/O.
- `config.py` — `apply_preset_env()` reads `os.environ`, resolves the preset, writes low-level
  `OPENVINO_*`/`OV_*` env vars via `_setdefault()` (never overwrites an explicit user override).
- `openvino/talker.py` — `OVTalkerRuntime`, wraps the stateful K/V cache graph.
- `openvino/runtime_config.py` — thread/env setup, `get_ov_config()`.
- `model_config.py` — `MODEL_PRESETS` (MODEL_SIZE → HF repo), HF token/auth helpers.

Deployment surface: `compose.yml` (`qwen3-tts` service + `export` service, same image, different
command), `.env.example`, `README.md`, `docs/HOW_TO_RUN.md`.

The current production deployment (dockermisc1, see repo memory / `docs/HOW_TO_RUN.md`
"dockermisc1" section) runs `MODEL_SIZE=1.7B` with the **768-frame (64s) default capacity**.
**Do not change that default.** Everything in Part A below is designed so the existing deployment
sees zero behavior change unless it explicitly opts in.

## Part A — `TTS_MAX_SPEECH_SECONDS` capacity knob

### A.1 Status: **already implemented**

This part is done, on branch `feat/max-speech-seconds-capacity` (commit `5643b8d`, not yet
pushed/PR'd as of this doc). It is included here as background/reference because the frontend and
VoiceDesign work in Part B depend on understanding it, and because the user asked for one planning
doc covering both features.

### A.2 What it does

The OpenVINO stateful K/V cache graph (`src/export/ov_stateful_cache.py::make_static_kv_stateful`)
bakes a fixed maximum frame count into the exported IR at export time — this cannot change at
runtime. Historically this was hardcoded to 768 frames (64s of audio at the 12 Hz codec frame
rate). `TTS_MAX_SPEECH_SECONDS` makes that a configurable, human-readable knob instead of a
hardcoded constant, while **defaulting to exactly the old behavior**.

### A.3 Implementation summary (already done)

- `presets.py`: `FRAME_RATE_HZ = 12`, `DEFAULT_MAX_SPEECH_SECONDS = 64.0`,
  `capacity_for_seconds(seconds) -> int` / `seconds_for_capacity(capacity) -> float`.
  `get_preset(model_size, max_speech_seconds=None)` now computes `stateful_capacity` and
  capacity-keyed IR paths (`main_stateful_cap{capacity}.xml`) at call time instead of hardcoding
  them in the `PRESETS` dict, so different capacities never collide on disk in the same
  `/ov/<size>` directory.
- `config.py::apply_preset_env()`: reads `TTS_MAX_SPEECH_SECONDS` from `environ`, passes it into
  `get_preset()`, and writes the resolved value back via `_setdefault()` (so an explicit override
  always wins, consistent with every other preset-derived var).
- `scripts/export.py`: uses `get_preset()` to determine capacity, names the stateful IR file
  accordingly, prints a human-readable summary.
- `openvino/talker.py`: capacity-exceeded `RuntimeError` message now reports both frames and
  seconds and tells the operator which env var to change.
- `model.py`: `health_state()` includes `"max_speech_seconds"` derived from the loaded runtime's
  actual capacity (not just the env var — this reflects the IR that's actually loaded).
- Docs updated: `README.md` (profiles table), `docs/HOW_TO_RUN.md` (new subsection + updated
  memory-ceiling and operational-settings sections), `compose.yml` (`TTS_MAX_SPEECH_SECONDS` in
  `x-model-environment` anchor, shared by `export` and `qwen3-tts` services), `.env.example`.
- Tests: `tests/test_presets.py` (7 new tests including an explicit regression test that the
  default reproduces `main_stateful_cap768.xml` / capacity `768` exactly).

### A.4 Remaining work for Part A

1. Push branch `feat/max-speech-seconds-capacity` and open a PR (not yet done as of this doc).
2. No production behavior change is required — dockermisc1 stays on the 64s/768-frame default.
3. This knob is a **prerequisite building block** for VoiceDesign in Part B: the VoiceDesign
   generation step (§B.4) produces a *short* reference sample (a few seconds), so a VoiceDesign IR
   export should use a small `TTS_MAX_SPEECH_SECONDS` (e.g. `20`) to keep its memory/latency
   footprint down — VoiceDesign is not used for long-form generation.

## Part B — VoiceDesign + Web Frontend

### B.1 Goal (verbatim from the user)

Let a user design a voice by natural-language prompt, preview/test it, tweak it, and — once
satisfied — feed the result into the existing Base-model zero-shot cloning flow so the resulting
cloned voice becomes usable through the existing OpenAI-compatible `/v1/audio/speech` endpoint,
for Hermes or other TTS consumers.

Source material: `docs/plans/alexandria_ideas.md` (from
https://github.com/Finrandojin/alexandria-audiobook), §§2–3, 8, 10. That doc is the design
authority for this feature; this plan translates it into concrete file-level changes for *this*
repo. Where alexandria_ideas.md is vague, this doc makes a concrete decision — follow this doc's
decisions unless you find a reason not to, and note the deviation if you deviate.

### B.2 Current architecture constraints that shape this design

Read these before writing code — they explain *why* the plan looks the way it does:

1. **One model in memory at a time.** `model.py` module-level globals (`model`,
   `voice_clone_prompt`, `ov_runtime`) assume exactly one loaded checkpoint. There is no existing
   multi-model or multi-tenant abstraction.
2. **Single-worker Gunicorn + single `ThreadPoolExecutor(max_workers=1)`.** All inference
   (`model.executor.submit(...)`) is serialized through one executor thread. This is deliberate —
   it avoids duplicate model memory and concurrent-inference races. Any new endpoint must submit
   its work through this same executor, not spawn its own thread pool.
3. **One fixed reference voice per container**, set at startup from `REF_AUDIO_PATH` / `REF_TEXT`
   env vars, and used to build one cached `voice_clone_prompt` (`model.py` line ~213,
   `model.create_voice_clone_prompt(ref_audio=REF_AUDIO, ref_text=REF_TEXT)`). There is currently
   **no per-request voice-clone path** — every `/v1/audio/speech` call uses the same startup-time
   voice. VoiceDesign's "feed into the base model for cloning" requirement means this constraint
   must be relaxed (see §B.6).
4. **`OPENVINO_RELEASE_CODEC=1` (default) frees the PyTorch codec encoder after startup** for
   memory savings, and is explicitly documented (`docs/HOW_TO_RUN.md`) as "required for future
   per-request voice cloning" to be disabled (`OPENVINO_RELEASE_CODEC=0`) if kept resident. Any
   deployment that wants runtime `create_voice_clone_prompt()` calls (which VoiceDesign's "capture
   → clone" handoff needs) must set `OPENVINO_RELEASE_CODEC=0`.
5. **`qwen_tts` package (v0.1.1) exposes three separate top-level generation methods, gated by
   checkpoint type** (`self.model.tts_model_type`), not by a runtime flag:
   - `generate_voice_clone()` — requires a **Base** checkpoint. No instruct.
   - `generate_voice_design()` — requires a **VoiceDesign** checkpoint (a different HF repo,
     structurally same 1.7B-class architecture as Base 1.7B, but different trained weights).
     Takes `instruct` (the natural-language voice description — despite the parameter name
     "instruct", for VoiceDesign this *is* the voice-identity description, not a delivery/tone
     modifier).
   - `generate_custom_voice()` — requires a **CustomVoice** checkpoint, 9 built-in speakers.
   Each requires loading a **different HF checkpoint** into `Qwen3TTSModel.from_pretrained(...)`.
   There is no single checkpoint that supports both cloning and design. This is the reason the
   alexandria_ideas.md architecture proposes a **lazy model-swap**: VoiceDesign is not "always on."
6. **Export is model-checkpoint-specific.** `scripts/export.py` and
   `src/export/export_openvino.py` currently hardcode the assumption of one `MODEL_SIZE` → one HF
   repo (`model_config.py::MODEL_PRESETS`). A VoiceDesign checkpoint needs its own export pass into
   its own `/ov/<size>-voicedesign` directory tree — same export tooling, different source repo
   and destination.
7. **No auth/multi-tenancy.** The service has no user accounts, no auth, and is meant to run on a
   trusted network or behind an authenticated reverse proxy (see `SECURITY.md`). Voice storage
   (§B.7) should be simple filesystem-backed, not a database with per-user ACLs, unless the human
   operator explicitly asks for that later.

### B.3 High-level architecture decision

Adopt the alexandria_ideas.md lazy-model-swap design, made concrete:

```
┌─────────────────────────────────────────────────────────────┐
│ qwen3-tts container (single process, single executor thread) │
│                                                                │
│  Base 1.7B (always resident, serves /v1/audio/speech,        │
│             /generate, /generate/stream)                      │
│                                                                │
│  On POST /voice_design:                                       │
│    1. Reject new /v1/audio/speech etc. with 503 (busy)        │
│       while swap is in progress (readiness flag)              │
│    2. Unload Base model + IR from memory                      │
│    3. Load VoiceDesign model + IR from /ov/<size>-voicedesign │
│    4. generate_voice_design(text=sample_text,                 │
│                              instruct=description)             │
│    5. Save resulting WAV to the voice library (§B.7)          │
│    6. Unload VoiceDesign model + IR                            │
│    7. Reload Base model + IR (same as startup)                 │
│    8. Clear readiness flag — service is "up" again             │
│  Return: voice_id + WAV (or reference) to the caller           │
│                                                                │
│  Client then either:                                          │
│    a) POSTs /v1/audio/speech with {"voice_id": "<id>"} to use │
│       the newly captured reference for cloning, or             │
│    b) POSTs the returned WAV directly as ref_audio to a new    │
│       per-request-clone code path (§B.6)                       │
└─────────────────────────────────────────────────────────────┘
```

This keeps "one container, one port, one primary model in memory at a time" (the hard constraint
stated at the top of alexandria_ideas.md) while adding VoiceDesign as an occasional, slower,
blocking operation — not a concurrently-resident second model.

**Model-swap cost is real and must be visible to the caller.** Expect tens of seconds (unload +
IR load + first-inference JIT unless the OV kernel cache is warm for both graphs — see repo memory
"OV JIT cache behavior": cold JIT ~13 min, warm-cache-from-disk ~7 min, same-container repeat
~seconds). Document this prominently; do not hide it behind a spinner with no explanation.

### B.4 Backend changes — step by step

#### B.4.1 Export: VoiceDesign IR

1. Add a second entry set to `model_config.py::MODEL_PRESETS`, or a parallel dict, e.g.:
   ```python
   VOICE_DESIGN_MODEL_PRESETS = {
       "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",  # verify exact HF repo id before using
   }
   ```
   **Verify the exact HF repo name** on the Qwen org before hardcoding it — do not guess a repo id
   that hasn't been confirmed to exist. Check https://huggingface.co/Qwen for the actual
   VoiceDesign checkpoint id (search terms: "Qwen3-TTS VoiceDesign"). alexandria_ideas.md
   confirms VoiceDesign exists as a same-class 1.7B checkpoint but does not give the exact repo
   string — that must be confirmed against the live HF Hub before export.
2. Extend `presets.py` with a `voice_design` preset (or a new sibling dict —
   `VOICE_DESIGN_PRESETS`), keyed by size (only `1.7B` needed, per alexandria_ideas.md — no
   0.6B-VoiceDesign requirement stated). Point its `_ir_paths()` at `/ov/1.7B-voicedesign/...`
   instead of `/ov/1.7B/...` so it never collides with the Base IR tree. Use a **small**
   `TTS_MAX_SPEECH_SECONDS`-equivalent default for this preset (e.g. 20s / 240 frames) — see A.4
   note above; VoiceDesign only ever generates a short sample utterance.
3. Add a new Compose service `export-voice-design` (or a `--target voice_design` flag on the
   existing `export` service/script) that runs `scripts/export.py` against the VoiceDesign preset.
   Reuse `src/export/export_openvino.py` and `scripts/transform_stateful_ir.py` as-is — they
   already take `--output-dir` and generic HF repo/compression flags; only the source repo and
   destination directory differ. Do not fork the exporter; parameterize it.
4. Confirm the VoiceDesign checkpoint's `tts_model_type` is `"voice_design"` (this is asserted
   inside `qwen_tts`'s `generate_voice_design()` — see
   `qwen_tts/inference/qwen3_tts_model.py:637` in the installed `qwen-tts==0.1.1` package,
   `self.model.tts_model_type != "voice_design"` raises `ValueError`). This confirms at runtime
   whether the exported/loaded checkpoint is the right type — surface that error clearly if it
   fires (it means the wrong repo was configured).

#### B.4.2 Runtime: model-swap manager

Add a new module, e.g. `src/qwen3_tts/voice_design.py`, responsible for:

- `swap_to_voice_design()` — unload Base (mirror `_do_unload()` in `model.py`), load the
  VoiceDesign checkpoint + OV runtime (mirror `load_model()` in `model.py` but parameterized by
  repo id / OV dir / stateful IR path instead of the Base-only globals). This will require
  **refactoring `load_model()` in `model.py`** to accept parameters (model repo, OV model dir,
  stateful model path, compression settings) rather than reading them from module-level constants
  computed once at import time — currently `MODEL_ID`, `OV_MODEL_DIR`, `OPENVINO_MAIN_STATEFUL_MODEL`
  etc. are frozen at import time (lines ~37–54 of `model.py`). Introduce a small config object or
  named tuple, e.g. `ModelProfile(model_repo, model_revision, ov_model_dir, main_stateful_model,
  predictor_stateful_model, torch_dtype, ...)`, build two instances (`BASE_PROFILE`,
  `VOICE_DESIGN_PROFILE`) at import time from the existing preset logic, and change
  `load_model()` to take a `ModelProfile` argument. This is the single largest refactor required
  by this feature — budget real time for it and test the Base path still works identically
  afterward (`/health`, `/v1/audio/speech` unchanged behavior) before adding VoiceDesign on top.
- `swap_to_base()` — the inverse, reloading the Base profile. This is exactly what
  `_ensure_loaded()` already does after idle-unload, so this should become a thin call into the
  same `load_model(BASE_PROFILE)` path, not a separate implementation.
- A module-level lock/flag (e.g. `_swap_in_progress: bool`) that `_ready()` in `app.py` checks in
  addition to `model._service_started`, so `/health` and all generation endpoints correctly return
  503 during a swap. Reuse the existing `_ready()` helper in `app.py` (line ~45) — extend it, don't
  duplicate it.
- All swap work must run **inside `model.executor`** (the single serialized worker thread), exactly
  like every other model operation, to avoid racing with an in-flight `/generate` call. Concretely:
  `model.executor.submit(voice_design.run_voice_design_request, description, sample_text,
  language).result(timeout=<swap budget, e.g. 180s>)`.

#### B.4.3 New endpoint: `POST /voice_design`

Add to `app.py`, following the existing route conventions (JSON in, `_json_body()`,
`model.executor.submit(...).result(timeout=...)`, matching error-handling style of
`/v1/audio/speech`):

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
  "voice_id": "vd_3f9a...",       # opaque id, see §B.7
  "sample_rate": 24000,
  "audio_base64": "<wav bytes, base64>"    # so the client can preview immediately without a 2nd request
}
Response (503): {"error": "Model busy (voice design swap in progress)"} — during swap
Response (500): {"error": "Voice design failed: <reason>"}
```

Implementation:
1. Validate `description` and `sample_text` are non-empty strings (same pattern as existing
   `text`/`input` validation in `/generate` and `/v1/audio/speech`).
2. Submit to executor: swap to VoiceDesign profile → call
   `model.model.generate_voice_design(text=sample_text, language=language, instruct=description)`
   → get `(wavs, sr)` → swap back to Base profile.
3. Persist the WAV + description + sample_text to the voice library (§B.7), get back a `voice_id`.
4. Return WAV as base64 in the JSON response (simplest for a browser client to preview inline
   without a second round-trip) **and** keep it retrievable later via `voice_id` (§B.7) so the
   "Use this voice" step doesn't require the client to re-upload audio bytes.
5. Wrap the whole executor call in try/except mirroring existing endpoints; **on any exception,
   still attempt to swap back to Base** (use `finally`) so a failed VoiceDesign call doesn't leave
   the service stuck serving no model. This fail-safe is important — test it explicitly (e.g. force
   `generate_voice_design` to raise and confirm `/v1/audio/speech` works immediately after).

#### B.4.4 Per-request / named-voice cloning

Currently `/v1/audio/speech`, `/generate`, `/generate/stream` all use the single startup-time
`voice_clone_prompt` global. To let a VoiceDesign-captured voice actually be used for cloning
(the user's explicit end goal — "feed it into the base model for cloning and ultimately use that
cloned voice in the openai endpoint"), extend these endpoints to accept an optional `voice_id`:

```
POST /v1/audio/speech
{
  "input": "...",
  "voice_id": "vd_3f9a...",   # optional; if omitted, use the startup-time default voice (unchanged)
  "language": "English",
  "response_format": "mp3"
}
```

Implementation:
1. If `voice_id` is present: look it up in the voice library (§B.7), get its stored reference WAV
   + transcript-equivalent. **Note:** `create_voice_clone_prompt()` requires `ref_text` for
   ICL mode (the default, non-`x_vector_only_mode` path) — but a VoiceDesign-captured sample has no
   *transcript* the user typed as "the exact words in this reference," it has the `sample_text`
   the user provided to VoiceDesign, which *is* exactly what was spoken (VoiceDesign directly
   synthesizes `sample_text` in the described voice), so `ref_text = sample_text` is correct and
   already available — no ASR step is needed. Confirm this assumption by listening to a captured
   sample against its `sample_text` before shipping.
2. Call `model.create_voice_clone_prompt(ref_audio=<captured wav>, ref_text=<sample_text>)` to
   build a fresh `voice_clone_prompt` for this request (this is the "feed into the base model for
   cloning" step). This requires the PyTorch speech-tokenizer encoder to still be resident — i.e.
   **`OPENVINO_RELEASE_CODEC=0` must be set** for any deployment that wants to support `voice_id`
   requests. Document this prerequisite prominently (README + HOW_TO_RUN) and consider having
   `/voice_design` and the `voice_id` code path return a clear 500 error if
   `OPENVINO_RELEASE_CODEC=1` at startup, rather than a confusing downstream `AttributeError`.
3. **Cache the built `voice_clone_prompt` per `voice_id`** (simple in-process dict keyed by
   `voice_id`, invalidated on model reload/idle-unload) so repeated requests for the same
   `voice_id` don't rebuild it every time — `create_voice_clone_prompt()` runs speaker-embedding
   extraction and speech-tokenizer encoding, which is not free. This cache is separate from (and
   in addition to) the always-present startup-time default `voice_clone_prompt`.
4. If `voice_id` is omitted, behavior is byte-for-byte unchanged from today (uses the startup
   default). This must stay true — it's the Hermes production path and must not regress.

This is additive to all three generation endpoints; implement it once in `_run_generate` /
`_run_generate_with_streaming` (both already take `voice_clone_prompt` as effectively a closure
over the module global — thread a `voice_clone_prompt` parameter through instead of reading the
global directly, defaulting to the module global when not provided) rather than duplicating logic
per-route.

### B.5 Instruct/tone (optional, lower priority — alexandria_ideas.md §4)

Not required to satisfy the user's core ask, but cheap to add alongside the above since the
endpoints are already being touched. Add optional `"instruct"` to `/v1/audio/speech` and
`/generate`. If the currently-loaded model is Base (the common case), log-and-ignore with a
one-line no-op note in the response or headers (do **not** error — Base has no meaningful instruct
support per alexandria_ideas.md §2). Defer full CustomVoice support (`generate_custom_voice()`
with its 9 built-in speakers) — out of scope for this plan; it's a different checkpoint again and
isn't part of the user's stated goal (cloning + design, not built-in speakers).

### B.6 Streaming / seed refinements (optional, lower priority — alexandria_ideas.md §5–6)

Not required for the core VoiceDesign ask. If time permits after B.4 and the frontend (B.8) are
working end-to-end: add public `seed` to the three generation endpoints (the internal
`_apply_optional_seed()` already exists and is wired to dev-only endpoints — just thread it
through the public ones the same way `/stream_internal`/`/batch_internal` already do). SSE
wrapper mode and bounded-queue backpressure for `/generate/stream` are nice-to-haves; do not block
VoiceDesign delivery on them.

### B.7 Voice library (new, required by B.4.3/B.4.4)

A minimal persistence layer mapping `voice_id -> {wav_path, description, sample_text, created_at}`.

Decision: **filesystem-backed, not a database.** This matches the project's existing "no
database, bind-mounted host directories" pattern (`MODEL_CACHE_PATH`, `OV_DATA_PATH`).

- New bind-mounted directory, e.g. `VOICE_LIBRARY_PATH` (default `./data/voices`) →
  `/voices` in the container, read/write, alongside the existing `model`/`ov` mounts in
  `compose.yml`.
- Layout: `/voices/<voice_id>/reference.wav` + `/voices/<voice_id>/meta.json`
  (`{"description": ..., "sample_text": ..., "language": ..., "created_at": ...}`).
- `voice_id` generation: short random id (e.g. `secrets.token_hex(6)` prefixed `vd_`) — collision
  probability is negligible at this scale; no need for anything fancier.
- Add a `GET /voices` (list) and `GET /voices/<voice_id>` (fetch metadata + WAV) endpoint so the
  frontend history panel (§B.8) can repopulate on reload without client-side-only storage.
- No auth on these endpoints (consistent with the rest of the service — see `SECURITY.md`; the
  whole service is meant to sit behind a trusted network or auth proxy).

### B.8 Web frontend

Follow alexandria_ideas.md §10 as the design authority; the summary below is the actionable
subset. **This is a new, separate deliverable from the backend work in B.4** — it can be built and
iterated on independently once `/voice_design`, `/v1/audio/speech` (with `voice_id`), and
`/voices` exist and are stable.

Decisions (concrete, not left open):
- **Framework: Next.js 15, App Router, TypeScript, Tailwind.** (alexandria_ideas.md
  recommendation — accepted as-is, no reason to deviate found during this planning pass.)
- **New top-level directory in this repo: `frontend/`** (sibling to `src/`, `scripts/`, `docs/`).
  Own `package.json`, own `Dockerfile` (multi-stage Next.js build → `next start` or static
  export, whichever ends up simpler once implemented — decide during implementation, not here).
- **Deployment: Option A from alexandria_ideas.md §10.8** — second container on the same host,
  Nginx (or Caddy — pick whichever is already used elsewhere in this operator's infra, check
  before introducing a new reverse proxy technology) in front, `/` → frontend, `/api/*` → the
  existing `qwen3-tts` container on 8318. Add a new Compose service `frontend` (`profiles:
  [frontend]` so it's opt-in, mirroring how `export` uses `profiles: [export]`) plus an `nginx`
  or `caddy` service if one doesn't already front this host. **Do not couple the core TTS image
  release process to the frontend** — they should version and deploy independently; the backend
  image must keep working standalone via curl/Hermes with no frontend present.
- **Three-zone layout** (alexandria_ideas.md §10.3): left = voice control (VoiceDesign panel +
  cloning panel + presets), center = text editor + generate controls + waveform, right = history
  (past generations with seed/voice/replay).
- **VoiceDesign UX must implement the structured prompt assistant** from alexandria_ideas.md
  §10.1 (register chips, texture chips, character chips, composed description string, "Advanced"
  raw-text escape hatch, warning on known-unstable combos e.g. "bright" + energy terms). This is
  explicitly called out in the source doc as "a killer feature" — do not ship a bare freeform
  textarea as the only input; that reproduces the instability alexandria_ideas.md §10 warns about.
- **Instruct/tone kept separate from voice description** (alexandria_ideas.md §10.2) — a distinct
  "Tone" control under the main text editor, mapped to canned instruct strings, not merged into
  the VoiceDesign description field.
- **Streaming playback**: Web Audio API `AudioContext`, decode `/generate/stream`'s raw PCM
  (`X-Audio-Sample-Rate` / `X-Audio-Channels` headers — already implemented server-side, see
  `docs/HOW_TO_RUN.md` "Streaming and validation endpoints"). SSE mode is optional (§B.6) — if not
  implemented server-side yet, the frontend should use the raw PCM stream directly first and add
  SSE support later without blocking initial ship.
- **State**: React Server Components for static layout, a lightweight client store (Zustand)
  for playback/history/settings. History can start as `localStorage`/`IndexedDB`-only and later
  sync against `GET /voices` — don't build a sync layer until the basic flow works end-to-end.

Suggested build order for whoever implements this:
1. Scaffold `frontend/` (Next.js + TS + Tailwind), talk to the *existing* `/v1/audio/speech` and
   `/generate/stream` endpoints only — prove basic "type text → hear audio" works with zero new
   backend changes.
2. Wire up `/voice_design` once B.4 backend work lands — VoiceDesign panel, preview playback,
   "Use this voice" → capture `voice_id`.
3. Wire `voice_id` into the main generate call (B.4.4) — this closes the loop the user asked for:
   design → capture → clone → speak, end to end.
4. History panel backed by `GET /voices` + local generation log.
5. Polish pass against alexandria_ideas.md §10.9 (latency feel, dark theme, keyboard shortcuts,
   offline resilience) — last, not first.

### B.9 Suggested implementation order (whole plan, backend-first)

1. Confirm the exact VoiceDesign HF checkpoint repo id (§B.4.1 step 1) — blocks everything else in
   Part B.
2. Refactor `model.py::load_model()` to take a `ModelProfile` parameter (§B.4.2) — land this alone
   first, verify Base-only behavior is unchanged (`/health`, `/v1/audio/speech`,
   `/generate/stream` all still pass existing manual smoke tests) before adding VoiceDesign.
3. Export VoiceDesign IR (§B.4.1), verify it loads and `generate_voice_design()` runs standalone
   in a scratch script before wiring it into the Flask app.
4. Add the model-swap manager + `/voice_design` endpoint (§B.4.2–B.4.3). Verify: swap correctly
   fails back to Base on error (test by injecting a forced exception); `/health` correctly 503s
   during swap; a normal `/v1/audio/speech` call immediately after a `/voice_design` call succeeds
   and still uses the default voice (no `voice_id`).
5. Add the voice library (§B.7) and `voice_id` support in the generation endpoints (§B.4.4).
   Verify: a VoiceDesign-captured voice can be used to clone and speak new text, end to end, via
   curl, with `OPENVINO_RELEASE_CODEC=0` set.
6. Update docs (`README.md`, `docs/HOW_TO_RUN.md`, `.env.example`, `compose.yml`) for
   `VOICE_LIBRARY_PATH`, the `/voice_design` and `/voices` endpoints, the `OPENVINO_RELEASE_CODEC=0`
   prerequisite, and the new `export-voice-design` Compose profile — same rigor as Part A's docs
   update.
7. Only after the backend loop (design → capture → clone → speak) works via curl: build the
   frontend (§B.8), in the suggested sub-order there.

### B.10 Explicit non-goals for this plan

Carried over from alexandria_ideas.md §1 "We intentionally drop": audiobook-centric workflows
(M4B, Audacity, large scripts), persona auto-casting / LLM-driven script annotation, LoRA/PEFT
voice baking (alexandria_ideas.md §9 — revisit only if zero-shot cloning proves insufficient for a
specific voice), CustomVoice's 9 built-in speakers, authentication/multi-tenancy beyond what
already exists. Do not scope-creep into these while implementing this plan.

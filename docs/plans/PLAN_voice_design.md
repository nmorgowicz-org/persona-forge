# Plan: VoiceDesign + Web Frontend

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

The current production deployment (dockermisc1) runs `MODEL_SIZE=1.7B`.

## 1. Goal (verbatim from the user)

Let a user design a voice by natural-language prompt, preview/test it, tweak it, and — once
satisfied — feed the result into the existing Base-model zero-shot cloning flow so the resulting
cloned voice becomes usable through the existing OpenAI-compatible `/v1/audio/speech` endpoint,
for Hermes or other TTS consumers.

Source material: `docs/plans/alexandria_ideas.md` (from
https://github.com/Finrandojin/alexandria-audiobook), §§2–3, 8, 10. That doc is the design
authority for this feature; this plan translates it into concrete file-level changes for *this*
repo. Where alexandria_ideas.md is vague, this doc makes a concrete decision — follow this doc's
decisions unless you find a reason not to, and note the deviation if you deviate.

## 2. Current architecture constraints that shape this design

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
   must be relaxed (see §6).
4. **`OPENVINO_RELEASE_CODEC=1` (default) frees the PyTorch codec encoder after startup** for
   memory savings, and is explicitly documented (`docs/HOW_TO_RUN.md`) as "required for future
   per-request voice cloning" to be disabled (`OPENVINO_RELEASE_CODEC=0`) if kept resident. Any
   deployment that wants runtime `create_voice_clone_prompt()` calls (which VoiceDesign's "capture
   → clone" handoff needs) must set `OPENVINO_RELEASE_CODEC=0`.
5. **`qwen_tts` package (v0.1.1) exposes three separate top-level generation methods, gated by
   checkpoint type** (`self.model.tts_model_type`), not by a runtime flag:
   - `generate_voice_clone()` — requires a **Base** checkpoint. No instruct support.
   - `generate_voice_design()` — requires a **VoiceDesign** checkpoint (a different HF repo,
     structurally same 1.7B-class architecture as Base 1.7B, but different trained weights).
     Takes `instruct` (the full natural-language voice description prompt — for VoiceDesign,
     `instruct` defines both voice identity AND delivery style/emotion: gender, age, accent,
     timbre, personality, energy, pacing. There is no separation between "identity" and
     "emotion" parameters; it is a single holistic description).
   - `generate_custom_voice()` — requires a **CustomVoice** checkpoint, 9 built-in speakers.
     For CustomVoice, `instruct` is ONLY emotion/delivery style; voice identity is fixed by the
     `speaker` argument (e.g. "Vivian", "Ryan"). This is a fundamentally different semantic role
     than VoiceDesign's instruct.
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
   (§7) should be simple filesystem-backed, not a database with per-user ACLs, unless the human
   operator explicitly asks for that later.

## 3. High-level architecture decision

Adopt the alexandria_ideas.md lazy-model-swap design, made concrete:

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
│       per-request-clone code path (§6)                       │
└─────────────────────────────────────────────────────────────┘
```

This keeps "one container, one port, one primary model in memory at a time" (the hard constraint
stated at the top of alexandria_ideas.md) while adding VoiceDesign as an occasional, slower,
blocking operation — not a concurrently-resident second model.

**Model-swap cost is real and must be visible to the caller.** Expect tens of seconds (unload +
IR load + first-inference JIT unless the OV kernel cache is warm for both graphs — see repo memory
"OV JIT cache behavior": cold JIT ~13 min, warm-cache-from-disk ~7 min, same-container repeat
~seconds). Document this prominently; do not hide it behind a spinner with no explanation.

## 4. Backend changes — step by step

### 4.1 Export: VoiceDesign IR

1. Add a second entry set to `model_config.py::MODEL_PRESETS`, or a parallel dict, e.g.:
   ```python
   VOICE_DESIGN_MODEL_PRESETS = {
       "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
   }
   ```
   **Confirmed** (2026-07-02, web search): `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` exists on
   Hugging Face and its model card documents using
   `generate_voice_design(text=<target text>, instruct=<natural-language voice description>)`,
   matching the `qwen_tts` 0.1.1 signature. No 0.6B-VoiceDesign checkpoint was found; only the
   1.7B-class checkpoint exists, consistent with alexandria_ideas.md's "same 1.7B-class
   architecture as Base 1.7B" description.
2. Extend `presets.py` with a `voice_design` preset (or a new sibling dict —
   `VOICE_DESIGN_PRESETS`), keyed by size (only `1.7B` needed). Point its `_ir_paths()` at
   `/ov/1.7B-voicedesign/...` instead of `/ov/1.7B/...` so it never collides with the Base IR tree.
   Use a **small** `TTS_MAX_SPEECH_SECONDS`-equivalent default for this preset (e.g. 20s / 240
   frames) — VoiceDesign only ever generates a short sample utterance for reference capture; the IR
   capacity just needs to be large enough to accommodate testing.
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

### 4.2 Runtime: model-swap manager

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

### 4.3 New endpoint: `POST /voice_design`

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
  "voice_id": "vd_3f9a...",       # opaque id, see §7
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
3. Persist the WAV + description + sample_text to the voice library (§7), get back a `voice_id`.
4. Return WAV as base64 in the JSON response (simplest for a browser client to preview inline
   without a second round-trip) **and** keep it retrievable later via `voice_id` (§7) so the
   "Use this voice" step doesn't require the client to re-upload audio bytes.
5. Wrap the whole executor call in try/except mirroring existing endpoints; **on any exception,
   still attempt to swap back to Base** (use `finally`) so a failed VoiceDesign call doesn't leave
   the service stuck serving no model. This fail-safe is important — test it explicitly (e.g. force
   `generate_voice_design` to raise and confirm `/v1/audio/speech` works immediately after).

### 4.4 Per-request / named-voice cloning

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
1. If `voice_id` is present: look it up in the voice library (§7), get its stored reference WAV
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

## 5. Instruct/tone (optional, lower priority — alexandria_ideas.md §4)

Not required to satisfy the user's core ask, but cheap to add alongside the above since the
endpoints are already being touched.

Add optional `"instruct"` to `/v1/audio/speech` and `/generate`. Behavior depends on the loaded
checkpoint:

- **Base** (current deployment): instruct is not supported — the model ignores it. Accept the
  field in the API for forward-compatibility, log a brief note, and treat it as a no-op.
- **CustomVoice** (future, not in scope): instruct controls emotion, delivery, pacing of the
  built-in speaker; identity is fixed by the `speaker` parameter.
- **VoiceDesign**: instruct IS the voice description (identity + delivery) — see §2.5.

Do not error on unknown instruct when using Base. Defer full CustomVoice support
(`generate_custom_voice()` with its 9 built-in speakers) — out of scope for this plan.

## 6. Streaming / seed refinements (optional, lower priority — alexandria_ideas.md §5–6)

Not required for the core VoiceDesign ask. If time permits after the backend endpoints and
frontend are working end-to-end: add public `seed` to the three generation endpoints (the internal
`_apply_optional_seed()` already exists and is wired to dev-only endpoints — just thread it
through the public ones the same way `/stream_internal`/`/batch_internal` already do). SSE
wrapper mode and bounded-queue backpressure for `/generate/stream` are nice-to-haves; do not block
VoiceDesign delivery on them.

## 7. Voice library (new, required by 4.3/4.4)

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
  frontend history panel (§8) can repopulate on reload without client-side-only storage.
- No auth on these endpoints (consistent with the rest of the service — see `SECURITY.md`; the
  whole service is meant to sit behind a trusted network or auth proxy).

## 8. Web frontend

Follow alexandria_ideas.md §10 as the design authority; the summary below is the actionable
subset. **This is a new, separate deliverable from the backend work in §4** — it can be built and
iterated on independently once `/voice_design`, `/v1/audio/speech` (with `voice_id`), and
`/voices` exist and are stable.

### 8.1 Deployment: no extra reverse proxy

The operator's host (dockermisc1) is RAM-constrained; we must not add a Nginx/Caddy container
unless one is already running.

Decision: **serve the frontend from the same Flask process on port 8318.**

- New top-level directory in this repo: `frontend/` (sibling to `src/`, `scripts/`, `docs/`).
- **Framework: Vite + React + TypeScript + Tailwind + shadcn/ui, not Next.js** (revised
  2026-07-02, supersedes alexandria_ideas.md's Next.js recommendation). Rationale: this is a
  fully client-driven single-page control panel with no server-rendering need — we're already
  doing a static export either way, so Next.js's App Router/RSC machinery buys nothing here and
  only adds build complexity and a slower dev loop. Vite gives instant HMR, a plain `dist/`
  static output (same "Flask serves it at `/`" deployment story), and a lighter dependency tree.
  shadcn/ui (Radix primitives + Tailwind, copy-in components, no runtime UI-kit dependency) for
  premium-feeling chips/dropdowns/sliders without a heavy component library; Framer Motion for
  the polish pass (§8.7 step 5) — chip selection, waveform, and swap-in-progress states should
  feel alive, not static forms.
- Build the frontend as a **static export** (`vite build` → `dist/`) during container build.
- Flask serves static frontend files at `/` (or all non-API routes). API endpoints remain at
  `/v1/audio/speech`, `/voice_design`, `/voices`, `/health`, etc.
- This gives: `http://host:8318/` = the UI; same port, same container, zero extra processes.
- Add a Compose profile or env var (e.g. `FRONTEND_ENABLED=1`) so deployments can opt-out and run
  the TTS container without the frontend (curl/Hermes-only).
- **Do not couple the core TTS image release process to the frontend** — the backend must keep
  working standalone via curl/Hermes with no frontend present.

This is a deliberate simplification from alexandria_ideas.md §10.8 ("Option A with Nginx"). We
get the same functional outcome (UI + API on same host, same port) without a third container. If
the operator ever has Nginx/Caddy running for other services, they can wire the frontend through
that instead; Nginx/Caddy is not required.

### 8.2 Layout (alexandria_ideas.md §10.3)

Three-zone layout:
- **Left: Voice control** — VoiceDesign panel, cloning panel, presets, runtime settings (§8.8).
- **Center: Text editor + generate controls + waveform** — primary "type → hear" loop.
- **Right: History** — past generations with seed/voice/replay.

### 8.3 Guided Voice Design UX (CRITICAL — not a bare textarea)

**Scope note (2026-07-02):** this repo's downstream consumer is Hermes Agent — an AI
assistant/companion voice, not audiobook narration. alexandria's VOICE_REFERENCE.md gives us the
*mechanics* (tested vocabulary, composition order, known-unstable combos); it does not give us the
right *taxonomy* (its archetypes are professional-VO roles — announcer, trusted advisor, hard
sell — which don't fit an assistant persona). The chip categories below adapt the mechanics to an
assistant/companion taxonomy, explicitly including NSFW/roleplay personas as just another
persona-chip category — no different mechanically than "professional."

Unstructured prompts create unstable or unusable voices (alexandria empirical findings,
VOICE_REFERENCE.md). The VoiceDesign UI must guide the user with proven, tested patterns.
Do not expose the full lexicon as raw text — encode it into chips/selectors and a composed prompt.

Our `/voice_design` API has exactly one free-text lever (`description`, sent as VoiceDesign's
`instruct`) — there is no separate identity/delivery split at the API level (see §2 point 5). The
"anatomy-first, no mixing" rule below is therefore how the frontend **assembles** that single
string from chip categories, in this fixed order: accent → demographics → register →
texture/timbre → persona/character. Physical descriptors first, character/energy descriptors last
— this ordering is what alexandria found stable; it's a UX assembly rule, not a model-enforced field.

#### Accent / language (own chip row, independent lever)
- **Tier 1 (always visible, high confidence):** English (US), English (UK), English (AU),
  English (IE).
- **Tier 2 (available, labeled "Experimental — verify by listening"):** Boston, New York,
  Southern US, Scottish, Received Pronunciation / "posh" UK, Kiwi (NZ), plus finer Irish/Scottish
  regional flavors on request. These are plausible but unverified with the actual VoiceDesign
  checkpoint — before shipping any Tier 2 accent as "confirmed" (removing the experimental label),
  do a manual listening pass on dockermisc1: same sample text and same demographic/register chips,
  swap only the accent word, listen for a distinct and stable result. Promote or drop per accent
  based on that pass; track results as a short table in this doc once run.
- Accent is part of the description, not a separate API field — the frontend prepends it.

#### Demographics (own chip row — explicit, not inferred from persona)
- Gender: `[Female]` `[Male]` `[Neutral/androgynous]`
- Age range: `[Young adult]` `[Adult]` `[Mature]`
- (Alexandria left this implicit inside archetype choices; assistant-voice users expect to set it
  directly.)

#### Register selector
Chips: `[Bass]` `[Baritone]` `[Tenor]` `[Alto]` `[Mezzo-Soprano]` `[Soprano]`

#### Texture / timbre chips (tested stable, from alexandria's Section I)
- Smooth: `[Silky]` `[Even]` `[Warm]` `[Rich]` `[Soft rounded]`
- Resonance: `[Dark]` `[Deep]` `[Full]` `[Grounded]`
- Precision: `[Crisp]` `[Clear]` `[Precise]`
- Grit: `[Slight gravel]`
- Bright: `[Bright]` (include, but warn if combined with energy/persona terms — see rules)

#### Persona / character chips (assistant-and-companion taxonomy — our own, not alexandria's)
Grouped so the picker doesn't read as one flat undifferentiated list:
- **Assistant-forward:** `[Warm Assistant]` `[Confident Professional]` `[Calm & Grounded]`
  `[Bubbly & Energetic]`
- **Companion/social:** `[Playful]` `[Flirty]` `[Mysterious]` `[Sultry / Intimate]`
- **Power dynamic:** `[Authoritative / Dominant]` `[Soft / Submissive]`
These are treated exactly like any other persona chip in the API/model sense — no separate
moderation path, no separate field. They compose into the same description string as everything
else.

Note: The VoiceDesign model treats the entire `instruct` holistically. These chips compose into
a single description string.

#### Composition
- The UI assembles a single description string from selections, e.g.:
  - "Young Australian female, mezzo-soprano, clear forward tone, silky even timbre, playful and flirty personality."
- The user sees the composed description and can:
  - Accept it as-is
  - Switch to "Advanced" text mode to edit freely
  - Adjust individual chips

#### Known unstable combinations (warn inline)
If user selects `[Bright]` + `[Bubbly & Energetic]` (or similar bright+energy pairing): show a
warning: "This combination tends to create emotional instability. Consider using 'Bright' alone
and moving energy-related traits to the 'Tone' field for delivery control."

This is a killer feature: users get great, stable voices without needing to know the model's
quirks.

#### Starter presets (one-click, satisfies "options already in place to play with")
Ship 3-5 curated chip bundles the user can generate immediately, no composing required, e.g.
"Warm Assistant (US, female)", "Confident Professional (UK, male)", "Playful Companion (AU,
female)". Each preset also carries a persona-matched sample_text (§8.4) so the first thing a new
user hears is a good result, not a blank textarea. Presets are just pre-filled chip selections —
same composition path, same API call, nothing special server-side.

### 8.4 Sample text: short by default (10-12 second max reference)

The Base model only needs 3-15 seconds of reference audio for zero-shot cloning. To ensure
VoiceDesign output is usable as a high-quality reference, enforce practical limits:

- **Frontend:** Default sample_text is **persona-linked**, not one generic greeting — the wav
  that gets stored is what the Base model clones from, so its prosody should already match the
  persona (a dominant/authoritative voice and a bubbly/playful voice reading the same flat line
  don't showcase either well). Suggest text per persona chip (§8.3), still short (2-4 sentences,
  ~10-12s), still editable:
  - Warm Assistant: "Hi, I'm here to help. What can I do for you today?"
  - Confident Professional: "Let's get straight to it — here's exactly what we're going to do."
  - Playful / Flirty: "Well hello there. I was hoping you'd show up."
  - Authoritative / Dominant: "Listen closely, because I'm only going to say this once."
  - Sultry / Intimate: "Come a little closer. I don't bite... much."
  - Calm & Grounded: "Take a breath. We've got plenty of time to figure this out."
- **API (`/voice_design`):** Validate `sample_text` length — reject if the estimated duration
  exceeds ~15 seconds. A rough heuristic: 130-150 words/min → about 35-40 words max for 15s.
  Return a 400 error if exceeded: "Sample text is too long; keep it under 15 seconds of speech."
- The IR capacity for VoiceDesign (§4.1) can be larger (e.g. 20s / 240 frames) to accommodate
  testing — the hard limit applies to what is **stored** as the reference, not necessarily what
  the model can generate. But for simplicity, enforce it at the API level.

Document: "The shorter and clearer the reference sample, the better the cloning quality."

### 8.5 Tone control (alexandria_ideas.md §10.2)

Provide a "Tone" control under the main editor for delivery/emotion:
- Chips or dropdown with proven patterns:
  - `[Neutral]` `[Calm, thoughtful]` `[Warm and amused]` `[Tense, whispered]` `[Softly excited]` `[Frustrated, clipped]`
- Map these to instruct strings for CustomVoice (future). For Base (current), treat as no-op
  (see §5).
- Explain briefly: "Voice = what it sounds like. Tone = how it delivers this line."

### 8.6 Streaming playback

Web Audio API `AudioContext`, decode `/generate/stream`'s raw PCM
(`X-Audio-Sample-Rate` / `X-Audio-Channels` headers — already implemented server-side, see
`docs/HOW_TO_RUN.md` "Streaming and validation endpoints"). SSE mode is optional (§6) — if not
implemented server-side yet, use the raw PCM stream directly first and add SSE support later.

### 8.7 State

A lightweight client store (Zustand) for playback/history/settings — no server-rendering, so no
RSC layer. History can start as `localStorage`/`IndexedDB`-only and later sync against
`GET /voices` — don't build a sync layer until the basic flow works end-to-end.

Suggested build order for whoever implements this:
1. Scaffold `frontend/` (Vite + React + TS + Tailwind, static export), talk to the *existing*
   `/v1/audio/speech` and `/generate/stream` endpoints only — prove basic "type text → hear
   audio" works with zero new backend changes, served from Flask on port 8318.
2. Wire up `/voice_design` once backend work lands — VoiceDesign panel with guided UX (chips,
   preview playback, "Use this voice" → capture `voice_id`).
3. Wire `voice_id` into the main generate call (4.4) — this closes the loop the user asked for:
   design → capture → clone → speak, end to end.
4. History panel backed by `GET /voices` + local generation log.
5. Polish pass against alexandria_ideas.md §10.9 (latency feel, dark theme, keyboard shortcuts,
   offline resilience) — last, not first.
6. Runtime control panel (§8.8) — after the core design/clone/speak loop is solid, not before.

### 8.8 Runtime control panel (sketch — scoped into this milestone, detailed design deferred)

The user also wants the frontend to expose "all the dials and knobs" for how the container runs,
not just VoiceDesign — within reason. This is a sketch of the shape, not a committed spec; work it
out in detail when we get here (step 6 above).

**Constraint that shapes everything below:** almost all current tuning knobs are read from
`os.environ` once at process import time into module-level constants in `model.py` (`MODEL_ID`,
`TTS_BACKEND`, `IDLE_UNLOAD_SECONDS`, thread counts via `torch.set_num_threads`, etc. — see
`src/qwen3_tts/model.py:1-60`). The container also can't know at build time what the operator
mounted read-only, what env vars they set, or their memory limits. So "control panel" has to mean
three different things depending on the knob, not one uniform settings form:

1. **Live-adjustable via the existing swap mechanism** (unload → reconfigure → reload, same
   pattern as `voice_design.py`'s Base↔VoiceDesign swap): `TTS_BACKEND` (openvino/pytorch),
   `IDLE_UNLOAD_SECONDS`, `SILENCE_TRIM`/`SILENCE_TRIM_THRESH`/`SILENCE_TRIM_PAD_MS`,
   `OV_DYNAMIC_QUANT_GROUP_SIZE`. Also plausible: **live `MODEL_SIZE` swap** (0.6B ↔ 1.7B) reusing
   the exact `ModelProfile` pattern already built for VoiceDesign, *if* both size's IR trees are
   already exported and present under `OV_DATA_PATH` — genuinely new capability, not just exposing
   an existing lever, worth calling out as the most interesting item here.
2. **Read-only display, not editable from the app:** anything set by Docker/the host at container
   creation and outside the app's control — `mem_limit`/`memswap_limit` (cgroup), port mapping,
   volume mounts and their ro/rw mode, whether `REF_AUDIO_PATH`/`HF_TOKEN` are set (presence only,
   never echo the token value). Show these for transparency ("here's what you're actually running
   with") without implying they're changeable — a control that silently no-ops or lies about
   effect is worse than no control.
3. **Genuinely not exposable without a restart:** things baked into the OpenVINO IR itself at
   export time (`TTS_MAX_SPEECH_SECONDS`, quantization precision) — these need an
   `export`/`export-voice-design` re-run, not a runtime toggle. Surface as "requires re-export,
   see docs/HOW_TO_RUN.md" rather than a disabled-looking control.

**Security note to resolve before implementing:** category 1 introduces a *mutating*,
unauthenticated endpoint that can trigger a full model reload/backend swap — a bigger blast radius
than today's read-mostly generate endpoints, on a service the docs already flag as having no
auth/TLS (SECURITY.md). Decide then whether category-1 controls need their own lightweight gate
(e.g. a bearer token via an env var, checked only on `/runtime/*` mutating routes) even though the
rest of the service stays open, or whether "trusted network only" (the existing posture) is judged
sufficient. Don't build this silently — flag it for an explicit decision at implementation time.

## 9. Suggested implementation order (whole plan, backend-first)

1. Confirm the exact VoiceDesign HF checkpoint repo id (§4.1 step 1) — blocks everything else.
2. Refactor `model.py::load_model()` to take a `ModelProfile` parameter (§4.2) — land this alone
   first, verify Base-only behavior is unchanged (`/health`, `/v1/audio/speech`,
   `/generate/stream` all still pass existing manual smoke tests) before adding VoiceDesign.
3. Export VoiceDesign IR (§4.1), verify it loads and `generate_voice_design()` runs standalone
   in a scratch script before wiring it into the Flask app.
4. Add the model-swap manager + `/voice_design` endpoint (§4.2–4.3). Verify: swap correctly
   fails back to Base on error (test by injecting a forced exception); `/health` correctly 503s
   during swap; a normal `/v1/audio/speech` call immediately after a `/voice_design` call succeeds
   and still uses the default voice (no `voice_id`).
5. Add the voice library (§7) and `voice_id` support in the generation endpoints (§4.4).
   Verify: a VoiceDesign-captured voice can be used to clone and speak new text, end to end, via
   curl, with `OPENVINO_RELEASE_CODEC=0` set.
6. Update docs (`README.md`, `docs/HOW_TO_RUN.md`, `.env.example`, `compose.yml`) for
   `VOICE_LIBRARY_PATH`, the `/voice_design` and `/voices` endpoints, the `OPENVINO_RELEASE_CODEC=0`
   prerequisite, and the new `export-voice-design` Compose profile — same rigor as previous docs
   updates.
7. Only after the backend loop (design → capture → clone → speak) works via curl: build the
   frontend (§8), in the suggested sub-order there.

## 10. Explicit non-goals for this plan

Carried over from alexandria_ideas.md §1 "We intentionally drop": audiobook-centric workflows
(M4B, Audacity, large scripts), persona auto-casting / LLM-driven script annotation, LoRA/PEFT
voice baking (alexandria_ideas.md §9 — revisit only if zero-shot cloning proves insufficient for a
specific voice), CustomVoice's 9 built-in speakers, authentication/multi-tenancy beyond what
already exists. Do not scope-creep into these while implementing this plan.

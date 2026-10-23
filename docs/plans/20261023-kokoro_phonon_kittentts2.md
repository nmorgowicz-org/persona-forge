# Multi-engine speech: Kokoro, Phonon, Kitten TTS, and first-class built-in voices

**Date:** 2026-10-23 (revised same day after review). **Status:** research-backed proposal; no
integration implemented, no model installed, no synthesis or listening test performed.

**Purpose:** turn Persona Forge from a single-renderer app (Pocket-TTS) into a **multi-engine**
speech studio where:

- several speech engines can be installed side by side, and each user picks the one(s) that suit
  their hardware (CPU-only, Apple silicon, NVIDIA CUDA) and their ear;
- **built-in (out-of-the-box) voices are as first-class as cloned voices**: discoverable,
  auditionable, usable in Speak, and servable as the API default;
- cloning keeps working through the existing OmniVoice → saved reference → render workflow, with
  each saved voice prepared per cloning-capable engine;
- the UI/UX around engines, voices, A/B comparison and API serving is substantially improved.

Pocket-TTS remains installed by default and the safe choice everywhere. Other engines are added
when an A/B listening pass shows they sound good on at least one supported target; there is no
single "winner" replacing Pocket.

## 0. Agreed policy decisions

| Topic | Decision |
| --- | --- |
| Network | **Offline-only inference and voice preparation.** The only network use is downloading pinned model weights/runtime packages from Hugging Face / PyPI / GitHub releases, and only when the user clicks Install/Download. No Gradium cloud cloning, no uploads, no implicit downloads during audio requests or browsing.
Single exception: user-clicked upstream preview samples, cached per §9.2. |
| Licensing | Personal project only; licences do **not** gate features (Kitten 2 community licence and Phonon 40M CC BY-NC are acceptable). Keep a one-line source/licence/attribution note per engine in the detail drawer for reference. Gated HF repos still need the user to accept terms on HF and supply a token. |
| Engine choice | Multiple engines coexist. Users choose; the app recommends based on detected hardware but never silently switches. |
| Inclusion bar | An engine ships (as optional install) if it passes A/B listening on at least one target and meets lifecycle/memory gates there. CPU/Docker support is a bonus, not a requirement; GPU-only engines are fine. |
| Default | Pocket stays the default engine for new installs and the rollback target. |

## 1. Candidate engines at a glance

All reviewed families output 24 kHz; adapters must still report the actual rate.

| Engine | Cloning | Built-in voices | Best targets (to be verified) | Streaming | Role in Persona Forge |
| --- | --- | --- | --- | --- | --- |
| **Pocket-TTS** (current) | Local, from reference audio; cached states | 31 curated app entries (24 English + 7 non-English) | CPU everywhere; existing accelerator families | PCM frame streaming (existing) | Default, universal, low-resource |
| **Kitten TTS 2** 1.7B | Local in-context, 5–30 s ref + transcript (Python); native C++ needs offline-prepared refs | 115 entries in pinned manifest, multiple languages (docs disagree on totals) | CUDA GPU (Python), Apple silicon (MLX, documented), x86 CPU (C++/GGML) | Sentence-chunk (Python and C++ binding) | High-quality cloning + large preset catalog |
| **KokoClone** (Kokoro + Kanade + vocoder) | Local voice conversion of Kokoro output toward a reference | Inherits Kokoro presets as source | CUDA or CPU; no MPS in wrapper | None (complete audio) | Cloning alternative; batch quality tier |
| **Kokoro 82M** (native or ONNX) | None (blending ≠ cloning) | ~54 voices, US/UK English + other languages | CPU (ONNX), CUDA, MPS (native, unverified) | Sentence/segment | Fast, light preset engine |
| **Phonon 31M English** | No local cloning from recordings (released speaker codec unavailable); imports prepared voice files | 102 catalog voices, 37 English | CPU (Rust, AVX2/ARM), no Torch | Frame-level | Very light streaming preset engine |
| **Phonon 40M** (en/fr/de/es/pt + multilingual) | Same as 31M | Same catalog | Same | Frame-level | Multilingual preset engine; gated HF download |
| **Kitten 0.8** mini/micro/nano(-int8) | None | 8 English presets | CPU (ONNX) | Treat as batch | Tiny footprint option; low priority |

Counts are upstream observations, not constants to bake into UI or tests. Sources:
[Kokoro card][k-card], [voices][k-voices], [Phonon card][p-card], [runtime][p-runtime],
[catalog][p-voices], [Kitten README][t-readme], [Kitten 2 card][t-card], [ONNX guide][t-onnx],
[KokoClone][kc-source].

## 2. Engine research notes

### 2.1 Kitten TTS 2

- **Python (`kittenml`):** `reference=` + `reference_text=` enable local cloning. Supplying our
  stored, reviewed transcript avoids a Whisper pass (extra model/memory). Conditioning uses a
  speaker embedding plus codec tokens; Pocket voice-state caches are not reusable.
- `generate_stream` yields completed **sentence chunks**; short inputs yield one chunk. Long text
  can truncate/repeat without chunking — test long narration specifically.
- Expression tags are beta and engine-specific; expose them only for this engine.
- **Native C++ (`kitten_tts_cpp`):** custom ternary GGUF + CPU LibTorch decoder; stock llama.cpp is
  not interchangeable. Python binding supports sentence-chunk streaming but rejects raw
  `reference=`; clones must be prepared offline with `prepare_reference.py` (needs the Python stack
  and a transcript) into a local `voices.json`. Cancellation finishes the current chunk. The C++
  runtime also carries the expressive controls once Python-only: emotion tags (`[joyful]`), vocal
  events (`<laugh>`), emphasis (`(((really)))`), stable/expressive sampling presets, and seeds via
  advanced options. Published wheels vary by release — 0.1.0 shipped macOS-arm64/Windows-x64/Linux
  wheels, while 0.2.0 pins `torch==2.13.0` with wheels pending re-publication — so pin a release
  that has wheels. Assets cache under `$XDG_CACHE_HOME/kitten-tts`; on AMX-capable CPUs weights
  repack at load (the docker-agent i7-1360P has no AMX and uses the compact kernels). See
  [binding source][tc-binding], [package][tc-pypi], [C++ runtime][t-cpp].
- **Footprint:** Python packing ~506 MiB; native bundle ~1.35–1.66 GB (GGUF + decoder + voice
  assets), excluding libraries. Distilled decoders need separate listening.
- **Dependencies:** `kittenml` pulls Torch/torchaudio/Transformers/diffusers; the C++ wheel pins an
  exact Torch differing from the app's. Must live in its own environment. Upstream Docker guide is
  GPU/vLLM-oriented. Versioning: PyPI (`kittenml` 0.9.4, 2026-10-06) runs ahead of GitHub release
  tags (still 0.8.1) — pin PyPI version + commit, never release tags. See
  [Docker guide][t-docker], [package metadata][t-pypi].
- **RTX 5090 (Blackwell, sm_120):** requires CUDA 12.8+ Torch builds. First Phase B check is whether
  the Kitten stack loads and runs kernels on the GPU natively on Windows, not falls back to CPU.
- **Apple silicon:** MLX path is documented upstream; verify on the user's MacBook.
- Licence ([text][t-license]): community licence with attribution; acceptable for this personal
  project.

### 2.2 KokoClone

- Pipeline: Kokoro preset synthesis (English source voice currently `af_bella`) →
  `frothywater/kanade-12.5hz` voice conversion → vocoder. A composite renderer, not Kokoro cloning.
  Kanade tokenizer alone is ~120M parameters ([card][kanade-card]).
- Synthesizes all source audio, converts internal chunks, assembles the full mel, then vocodes:
  **no playable streaming** ([chunking][kc-chunks]).
- Wrapper selects CUDA or CPU only; MPS is unsupported without a validated port. Verify each stage's
  device on Windows; check ONNX providers separately.
- Dependency manifest requests `kokoro-onnx[gpu]` and an unpinned Git Kanade dependency
  ([manifest][kc-deps]); build target-specific locked environments instead.
- Risks to listen for: source-preset accent/prosody leakage, conversion artifacts, whether
  OmniVoice-designed characteristics survive. Allow choosing the source Kokoro voice (closest
  gender/accent to the reference) as a tunable.
- Holds 3 models for one pipeline: needs the composite-adapter lifecycle exception in §4.3.

### 2.3 Kokoro 82M

- Native `KPipeline(lang_code='a')` with `af_heart` is the reference; `kokoro-onnx` is the CPU path
  (~300 MB full / ~80 MB quantized model, plus voices). Pin conversion release and voice bundle
  together with hashes.
- English G2P is Misaki with espeak-ng fallback; non-English needs extra packages/dictionaries.
  espeak-ng is a native dependency that must be packaged per platform.
- Upstream warns of weak very short utterances and rushing on long inputs — both in the corpus.
- Native `kokoro` metadata excludes Python 3.13 ([pypi][k-pypi]); the app uses 3.13. Native Kokoro
  therefore needs its own interpreter; ONNX permits 3.13 but needs NumPy 2 + ONNX Runtime
  ([pypi][ko-pypi]) — prove the full G2P stack imports before considering in-process.

### 2.4 Phonon

- Rust runtime, no Torch; Python wheel (`ptts`) depends on NumPy. q8 model files 64.5/74.6 MB
  (31M/40M), excluding the audio tokenizer. Wheels: Linux and Windows x86_64 require x86-64-v3
  (AVX2 — the docker-agent i7-1360P qualifies; older CPUs need a source build); macOS arm64 wheels
  shipped in earlier releases — re-verify the abi3 set for the pinned version.
- API: `ptts.TTS(..., lang='en', quant='q8')`, `tts.add_voice(name, file)`, `tts.stream(...)`.
  Speaking rate maps to the `speed` capability via `conditions={'duration_delta': …}`; streams use
  bounded-buffer backpressure (unread chunks pause generation — a natural cancel/disconnect
  mapping). **Catalog voices download lazily on first use**: the adapter must prefetch selected
  voices during Install/Prepare or the offline policy breaks. Pin model + catalog revisions;
  store opaque voice IDs.
- **No local cloning from audio:** the runtime has `clone_voice`, but the released assets lack the
  speaker codec ([Transformers docs][p-transformers]). Offline policy means Phonon offers catalog
  voices plus user-imported prepared voice files only. Pocket safetensors are not assumed compatible.
- 40M: HF gate requires accepting terms then a server-side `HF_TOKEN`/HF login. Setup errors must
  distinguish missing token, unaccepted gate, and network failure. Choose correct normalization
  language per checkpoint; an English checkpoint does not speak French by picking a French voice.
- The upstream OpenAI server ([contract][p-server]) is prior art only: no auth, ignores `model` and
  `instructions`, rejects `speed`. We do not expose it.

### 2.5 Kitten 0.8 tiny models and small Pocket models

- Eight English presets, ONNX, no cloning. Evaluate nano-int8 first; add only if it sounds good
  enough to justify a slot.
- Pocket upstream announced small English models (18.2M/6.9M/1.9M) and a Rust binary
  ([upstream][pocket-upstream]). Treat as a possible future "Pocket Lite" engine variant, separately
  pinned; evaluation scope in §9.5.

## 3. Current app: prior art and extension points

Repository inspected at `0d9b8114d8b576b221b1b621d435176d4d9c8f7c`. No prior Kokoro/Phonon/Kitten
integration found in the tree or `git log --all` messages.

| Surface | Finding and implication |
| --- | --- |
| `config.py`, `model.py` | Backends: Pocket / PyTorch / OpenVINO; centralized load/unload/routing. Keep "engine family" distinct from accelerator family and Qwen model size. |
| `pocket_tts_runtime.py` | Load, cached voice state, batch, streaming, unload. Template for the adapter interface; becomes the first adapter. |
| `pocket_artifact_resolver.py`, `pocket_english_config.py` | Pinned revisions with size/SHA-256 verification. Generalize into a per-engine artifact manifest. |
| `accelerator_manifest.py`, `gpu_probe.py`, `gpu_family.py`, `device.py` | Hardware detection and accelerator wheel selection. Reuse for engine hardware-fit and recommendations. |
| Desktop app (`desktop/`, [DESKTOP_APP](../architecture/DESKTOP_APP.md)) | Already provisions a **versioned Python environment** and accelerator-matched PyTorch wheel on first launch, with CPU fallback. Engine packs should reuse this provisioning machinery (§4.4). |
| `app.py::POCKET_BUILTIN_VOICES`, `/voices/built-in` | 31 curated Pocket entries (24 English + 7 non-English). Becomes the Pocket slice of the unified catalog. |
| `app.py::openai_audio_speech`, `_resolve_builtin_voice` | Accepts `voice`, `voice_id`, `builtin_voice`, `pocket:<name>`. Does not route on `model`; PCM streaming is Pocket-specific. |
| `voice_library.py`, `/voices/<id>/activate` | Strict `vd_...` IDs; default must be a saved voice. A preset cannot be API default today — fixed in Phase A. |
| `omnivoice_engine.py`, `segment_library.py` | Creation is separate from rendering; keep design/segments/stitch/variants intact. |
| `VoiceSelector.tsx` | Mixes saved and Pocket presets in a dropdown with hard-coded Pocket labels; no search/audition. |
| `EngineSelector.tsx` | Existing card-style selector for *design* engines (OmniVoice/Qwen); reuse its visual pattern for speech-engine selection. |
| `VoiceLibraryPage`, `SpeakPage`, `RuntimeConfigPage`, `lib/api.ts`, `store.ts` | Extend shared voice/engine metadata rather than adding per-engine pages. |
| `IntegrationsPage.tsx` | Snippets derive from selected/first saved voice, not the API default; ID list is saved-only; idle-unloaded shown as offline. Phase A1 fixes. |
| `VariantCompare.tsx` | Existing A/B UI for variants; basis for the cross-engine A/B feature. |

See [runtime invariants](../agent-reference/RUNTIME_AND_MEMORY.md),
[Pocket integration](../architecture/pocket_tts_integration.md),
[model swap and queueing](../architecture/MODEL_SWAP_AND_QUEUEING.md),
[HTTP API](../api/HTTP_API_REFERENCE.md), [operations](../dev/INTERNAL_OPERATIONS.md).

## 4. Architecture

### 4.1 Core concepts

- **Engine:** a speech-model family + runtime, e.g. `pocket`, `kitten2`, `kokoclone`, `kokoro`,
  `phonon-31m`, `phonon-40m`. Has a manifest (pinned artifacts, hashes, sizes), runtime variants
  (`python-cuda`, `python-mlx`, `cpp-cpu`, `onnx-cpu`, `rust-cpu`…), and capabilities.
- **Capabilities:** `clone` (local from audio), `presets`, `import_prepared_voice`, `streaming`
  (`frame` | `sentence` | `none`), languages (per engine and per voice; "unknown" is shown, never
  guessed), `speed`, `expression_tags`, `seed`, `instructions`.
  The UI and API derive every control from this; unsupported controls are hidden in UI and rejected
  with explicit errors in the API.
- **Voice:** either a saved voice (`vd_...`, unchanged) or a preset with a namespaced ID
  (`pocket:vera`, `kokoro:af_heart`, `kitten2:Bruno`, `phonon:<opaque-id>`). Never derive
  filesystem paths from IDs; resolve via pinned allowlist maps.
- **Binding:** (saved voice × engine) prepared state: `ready` | `needs_preparation` | `preparing` |
  `failed` | `unsupported`, keyed by reference audio hash, transcript hash, engine revision, runtime
  variant, and preparation settings. Changing the reference/variant invalidates bindings.
- **Engine state (shown in UI):** `not_installed` → `downloading` → `installed` (idle, loads on
  demand) → `loading` → `active` → (`idle_unloaded` = still "Ready") ; plus `failed` with reason and
  `needs_token` for gated downloads. Keep install state, active engine, and API default separate.
- Imported prepared voices (Phonon files, Kitten native `voices.json` entries) are untrusted: validate
  schema, shapes/dtypes, sizes, revision; reject pickle/object arrays and arbitrary paths/URLs.

### 4.2 Adapter interface

Each engine implements: `describe()` (capabilities, languages, rates); `install/verify`;
`load/unload`; `list_presets()`; `prepare(saved_voice)`; `synthesize(text, voice, options)` →
mono PCM at declared rate; optional `stream(...)`; `cancel()`; `metrics()`. The existing endpoint
encoding layer handles MP3/WAV/PCM. Pocket is refactored into the first adapter with no behaviour
change (guarded by `tests/tier1_unit/test_pocket_tts_runtime.py`).
Adapters declare `max_input_chars` and own per-engine text chunking/joining for engines that rush
or truncate long inputs (Kokoro long-form, Kitten long text); the API rejects oversized input with
an explicit error rather than silently degrading.

### 4.3 Lifecycle: one active engine

- Keep one web worker and the single-thread inference executor as the sole lifecycle authority.
  Load, prepare, generate, stream ownership, unload and OmniVoice swaps remain serialized.
- **One active engine at a time** (multi-model composites like KokoClone count as one, with
  aggregate RAM/VRAM accounting, staged loading, and full teardown). Switching engines unloads the
  current one first; OmniVoice creation unloads any active engine.
- Requests targeting a non-active engine trigger a queued, visible swap only if the user enabled
  "allow API requests to switch engines" (default **off**: return a clear error naming the active
  engine). Swaps reuse the existing swap banner/queue UX.
- Preview, quick-benchmark and Compare jobs run at a lower queue priority than API and Speak
  audio; they never delay endpoint requests.
- Each engine carries its own idle-unload timer (pack-manifest field `idle_unload_after`),
  mirroring the existing Pocket idle-unload policy.
- Non-Pocket engines run as a **managed child process** in their own environment, with bounded local
  IPC, health checks, kill-on-cancel/timeout, RSS/VRAM accounting, and no shell interpolation.
  ONNX/Rust engines may move in-process only after import/native-library compatibility is proved.
- Amend `RUNTIME_AND_MEMORY.md` before implementation: parent owns a single managed adapter/child;
  native compute threads allowed; no second request scheduler; no always-on sidecars.
- Persona, Stitch and segment renders route through the same engine rules: each render uses its
  voice's per-engine binding and the API-default/Speak selection rules; an unprepared binding fails
  with a clear error and never falls back to a different engine or speaker silently. Per-segment
  engine overrides are out of scope for v1.

### 4.4 Engine packs and packaging

- The installers do **not** bundle every engine. Each non-Pocket engine is an **engine pack**
  installed on demand into its own versioned environment under the app data directory, reusing the
  desktop provisioning machinery (versioned env, accelerator-matched wheels, progress UI, CPU
  fallback reporting).
- Pack manifest: engine revision, runtime variant per platform/accelerator, locked dependency set,
  artifact URLs + SHA-256 + sizes, Python version (e.g. 3.12 for native Kokoro), native deps
  (espeak-ng, LibTorch), and smoke-test command.
- Install is user-triggered, resumable, verifiable, removable (with disk-space reclaim shown), and
  survives app updates; an app update may mark a pack "update available" but never silently
  reinstalls.
- Token and caches: the Hugging Face token is stored in app settings and passed only to the pack
  process; model caches are shared across engines (Pocket already uses the shared HF cache) while
  virtualenvs stay per-pack; the preview cache lives under the app data directory. Install shows
  required disk space and pre-checks free space.
- After install, run a **smoke test** that proves the intended device is used (e.g. CUDA kernel
  execution on sm_120, not CPU fallback) and records it in the engine card.
- Docker: optional engine packs via image variants or volume-installed packs; not a gate.

### 4.5 API

- Keep `POST /v1/audio/speech`, `voice`/`voice_id`/`builtin_voice`, `pocket:<name>`, saved
  variants, MP3/WAV/PCM. Legacy requests with no or unknown legacy `model` strings keep current
  behaviour (served by the API default).
- New opt-in: `model` = an engine ID (`kitten2`, `kokoro`, …). Validate before any audio: unknown
  engine, voice/engine mismatch, unprepared clone, unsupported format/control, engine not installed
  → OpenAI-shaped errors; loading/busy → documented retryable responses.
- Voice IDs imply their engine (`kokoro:af_heart`); saved voices use the API-default engine unless
  `model` says otherwise.
- Parameter inventory: existing `voice`/`voice_id`/`builtin_voice`/`pocket:<name>`,
  `response_format`, `seed`, `speed` and `instruct` map per engine via capabilities; accept both
  the current `instruct` and OpenAI's `instructions` spelling; unsupported controls fail with
  OpenAI-shaped errors naming the engine. Phonon's `duration_delta` backs `speed`.
- New endpoints: `GET /v1/models` (installed engines + capabilities), `GET /v1/audio/voices`
  (unified catalog; local extension), engine management (`/engines`, install/remove/activate/prepare,
  progress), and `PUT /api-default`.
- Engine-management endpoints (`/engines` install/activate/prepare) fetch and run code: when
  network exposure is enabled they accept only local-origin requests, or require explicit
  confirmation in settings.
- **API default** = engine + voice + variant, persisted separately from Speak's transient selection.
  Migrate the existing saved default on upgrade; activation is transactional on the executor
  (validate/prepare → persist → else restore). Missing selections surface a repair action, never a
  silent speaker fallback. Optional user-defined aliases (`alloy` → `kokoro:af_heart`).
- Streaming is advertised honestly (`frame`/`sentence`/`none`); batch engines still serve PCM as a
  single chunk when requested. Cancel on disconnect; release the executor only after worker cleanup.

## 5. UI/UX

Guiding principles: one voice catalog, one engine manager, one way to choose defaults; every state
explained; no surprise downloads, swaps or speaker fallbacks; keyboard accessible throughout.

### 5.1 Navigation changes

- **Voices** (was Voice Library): tabs **My voices | Built-in voices | Compare**.
- **Settings → Speech engines** (new section next to Acceleration in `RuntimeConfigPage`).
- **Integrations**: reworked around the API default.
- Global status chip in the shell: active engine, state (Ready / Loading / Busy / Error), device.
  Engine state reaches the UI via the existing polling pattern first — no new SSE/WebSocket
  transport in v1.

### 5.2 Speech engines manager

One card per engine (pattern from `EngineSelector.tsx`):

- Name, one-line description, capability chips (Cloning, N presets, Streaming: frame/sentence/none,
  languages), source + licence note.
- **Hardware fit for this machine**, computed from `gpu_probe`/`device`: "Recommended for your
  RTX 5090", "Runs well on CPU", "Needs NVIDIA GPU — not available", "Apple silicon (MLX)". Unknown
  is shown as unknown.
- Download size, disk used, install state with progress, measured speed on this machine (RTF and
  first-audio latency from the last benchmark run) or "not measured".
- Actions: **Install**, **Remove**, **Make active**, **Run quick benchmark**, **Hugging Face token**
  (gated only), **Details** (pins, smoke-test device result, logs).
- Make active shows a confirmation with memory impact and what will unload.
- First-run nudge (dismissible): "Your GPU can run higher-quality engines — browse engines".
- Section setting **Languages**: "English only" (default) or "All languages". English only hides
  non-English voices and language-specific checkpoints (e.g. Phonon fr/de/es/pt) across the
  catalog, Speak, Compare and the IDs table, with a "Show N hidden by language filter" affordance;
  it never uninstalls anything. Preparing a clone whose transcript is non-English warns but is
  allowed. Engines are never hidden as a whole, only their non-English variants.

### 5.3 Built-in voices tab

- Searchable grid/list across all engines, including not-installed ones (metadata from pinned
  catalogs, bundled with the app, no download to browse).
- Filters: engine, language/accent, gender/style where upstream provides it, installed/ready,
  streaming. Default view follows the language preference (English only by default); all engines
  still show with "needs install" badges.
- Card: name, engine badge, language/accent, readiness, **Preview** (upstream sample if bundled or
  fetched on click, labelled "upstream sample"; or "generate locally" if engine installed),
  favorite star.
- Detail drawer: description, engine/revision, exact API voice ID with copy button, measured
  performance, and actions **Use in Speak**, **Set as API default**, **Compare…**, **Favorite**.
  If the engine isn't installed: **Install engine** inline.
- No autoplay; one preview playing at a time; previews are queued serialized jobs with cancel.

### 5.4 My voices tab (cloning)

- Existing families/variants preserved.
- Each voice gets an **Engines** row: per cloning-capable engine status chips (Pocket ✓ Ready,
  Kitten 2 • Prepare, KokoClone • Prepare, Kokoro — not supported, Phonon — not supported (no local
  cloning)). Hover/tap explains why.
- **Prepare for…** runs preparation (transcript review step when the engine needs one and the stored
  transcript is unreviewed or mismatched).
- Import prepared voice (Phonon file / Kitten native) appears as an action under Built-in → "Add
  imported voice", stored with provenance.

### 5.5 Compare (A/B) tab

- Pick text (presets from the evaluation corpus or custom), then 2–4 **slots**, each = engine +
  voice (+ options). Same saved voice across engines is one click ("compare this voice on all ready
  engines").
- Generates serially, shows timings per slot, then plays with **blind mode** (shuffled labels A/B,
  reveal after rating). Rate identity/naturalness/intelligibility 1–5, pick favourite, notes.
- Results saved locally (JSON + audio paths outside Git) and summarized per engine/voice; ratings
  feed the engine card ("Your ratings: 4.3 avg").
- Missing engines show "Install to compare" instead of failing.
- Builds on `VariantCompare.tsx`.

### 5.6 Speak page

- Voice picker becomes a searchable combobox with sections (Favorites, My voices, Built-in by
  engine) and readiness badges.
- Engine is implied by the voice; for saved voices an engine dropdown lists prepared engines.
- Controls are capability-driven (speed, seed, expression tags, prosody presets) with a tooltip on
  hidden ones' absence ("Kokoro doesn't support seeds").
- Clear labels: "Selected in Speak" vs "API default", with **Set as API default** next to the
  picker.
- If the selection needs an engine swap: inline note such as "Generating will switch from Pocket to
  Kitten 2" with measured memory/load time when known (otherwise "not measured").

### 5.7 Integrations page

- Header card: **effective API default** (engine, voice, variant), engine state ("Ready — loads on
  next request" for idle-unloaded), endpoint URL, change button.
- **Test endpoint**: user-triggered short request through `/v1/audio/speech`, shows first-audio
  latency, total time, playback, or error. Never changes defaults.
- Snippets (curl, Python SDK with `base_url="<origin>/v1"`, JS) derived from the API default, with a
  toggle to "use selected Speak voice instead". Validate URL composition (no missing/double `/v1`).
- Available IDs table: all ready voices across installed engines with copy buttons and engine
  column; filter for "servable now".
- Setting: "Allow API requests to switch engines" (off by default) with explanation.
- Optional "Enforce language preference on the API" (off by default): when on, requests for
  non-English voices/models get the §5.8 language error instead of audio; when off, the request is
  served as-is.

### 5.8 States and errors

Every surface uses the same vocabulary: Not installed / Downloading n% / Installed / Loading /
Active / Ready (idle) / Busy (queue position) / Needs preparation / Needs HF token / Failed (with
reason, Retry and View logs). Errors are actionable, e.g. "Kitten 2 failed to use your GPU (installed
CUDA wheel lacks sm_120). Reinstall with a CUDA 12.8+ build or run on CPU". Language mismatches
fail explicitly, e.g. "Voice 'estelle' (French) cannot render with the English-only Pocket
checkpoint — pick a French-capable model or an English voice".

### 5.9 Acceptance journeys

1. Built-in → filter English/Pocket → preview Vera → Set as API default → copy SDK snippet → same
   speaker via `/v1/audio/speech` after idle unload and app restart.
2. Settings → Speech engines → install Kokoro on a CPU-only machine → preview `kokoro:af_heart` →
   Use in Speak → generate → set as API default.
3. On the 5090: install Kitten 2 → smoke test confirms CUDA → My voices → Prepare an OmniVoice
   voice for Kitten 2 (transcript review) → Compare Pocket vs Kitten 2 blind → set Kitten 2 version
   as API default.
4. On the MacBook: install Kitten 2 (MLX) or record "unsupported" with a clear message.
5. Request an unprepared voice/engine pair via API → actionable error, no audio, no swap.
6. Remove an engine that is the API default → blocked with "change API default first" or guided
   repair.
7. Set Languages to "English only" → non-English voices and checkpoints hidden everywhere; a
   requested French voice over the API still serves (enforcement off), then errors with the §5.8
   message after turning enforcement on.

## 6. Evaluation (Phase B)

### 6.1 Targets

| Target | Role | Pre-checks |
| --- | --- | --- |
| Windows RTX 5090, native | GPU quality/performance; Kitten 2, KokoClone, native Kokoro | Driver, CUDA, Torch wheels for sm_120; prove GPU kernel execution per stage; ONNX providers separately; WSL is a separate optional target |
| MacBook, native macOS | Apple silicon quality + light engines | Chip, unified memory, macOS; MLX/MPS only where the runtime supports it; CPU fallback is a valid but separate result |
| CPU (MacBook CPU, Windows CPU, optional docker-agent Intel i7-1360P / 6 vCPU / 13 GiB cgroup) | Light engines (Pocket, Kokoro ONNX, Phonon, Kitten C++/tiny) | Thread counts 1/2/4; avoid oversubscription; on docker-agent no live env changes, no concurrent heavy jobs |

docker-agent snapshot (read-only, 2026-10-23): image `ghcr.io/nmorgowicz-org/persona-forge:v3.2.0`,
Python 3.13.16, AVX2 + AVX-VNNI (no AVX-512/AMX), ~9 GiB available RAM, load ~5–8, Pocket
idle-unloaded. None of the candidate packages installed. Transient; recapture before measuring.

### 6.2 Protocol

- **Setup:** throwaway isolated environments per engine/target; record pins, OS/device/driver/
  runtime metadata; for Docker capture RepoDigest.
- **Corpus (frozen + hashed before first run):** "Hello. Your timer is ready."; a 2–3 sentence
  assistant reply; 500–1,000 characters of narration; structured text ("At 9:45 a.m. on October 23,
  invoice AB-104 totals $1,234.56 for 3.5 kilograms."); questions, abbreviations, URLs, names,
  long multi-chunk input; one French and one German sentence (the catalog already has 7
  non-English entries).
- **Voices:** ≥2 presets per engine per relevant language; 3 saved references with different
  accents/delivery incl. one OmniVoice-designed; reviewed transcripts; 5/10/30 s reference trials
  for cloning engines; KokoClone source-voice variants.
- **Screening pass first** (few trials, labelled preliminary): does it install, run on the intended
  device, and sound good? Blind A/B against Pocket and each other. Engines failing to sound good on
  every target stop here.
- **Measurement pass** for survivors: 2 warmups + ≥20 trials; median/p95; cold download, cold load,
  preparation, warm, idle reload. Time to first playable audio, total time, audio duration, RTF
  (compute s / audio s) and throughput, inter-chunk gaps. Memory: parent + child RSS, VRAM
  allocated/reserved and device-wide, unified-memory pressure, swap delta, unload residual; every
  component in composites. GPU timings synchronized.
- **Quality:** blinded paired listening for identity, naturalness, accent, intelligibility,
  prosody; check omission/repetition/truncation, tail trimming, chunk joins, structured text.
  Automated WER/speaker similarity run separately from timing runs.
- **Endpoint pass** (after Phase C adapters exist): PCM and MP3/WAV, two concurrent clients (queue,
  not parallel), abort/slow-read, worker crash, idle reload, OmniVoice → save → unload → clone → API.
- Store audio/raw output outside Git; commit only text/JSON summaries.

### 6.3 Inclusion criteria and tiers

- **Include** an engine on a target if blind listening rates it good (comparable to or preferred
  over Pocket on at least some voices/use cases), it runs on the intended device, and it fits the
  device's memory with clean unload.
- Label each engine/target with a tier shown in the UI: **Conversational** (p95 first audio ≤ 1 s,
  sustained RTF ≤ 1) or **Batch quality** (slower, labelled). Batch engines are still valuable.
- Record unsupported/untested combinations explicitly; claim only tested combinations.

## 7. Phases

| Phase | Scope | Completion gate |
| --- | --- | --- |
| **A1 — Integrations & status fixes** | Snippets from effective API default; idle-unloaded shown as Ready; preset (`pocket:*`) settable as API default with persisted engine+voice+variant; Test endpoint; IDs table includes presets | Pocket preset served as default after restart; old clients and saved IDs unchanged |
| **A2 — Unified voice catalog (Pocket only)** | Voices tabs, Built-in grid/search/filters/preview/drawer, searchable Speak combobox, favorites, Speak vs API default labelling | Journey 1 passes; keyboard-accessible; no new model dependency |
| **B — Evaluation** | §6 screening on 5090, MacBook, CPU; then measurement pass for survivors | Per-target results table; list of engines to include with tiers; locked env/pin manifests |
| **C — Engine framework + first new engine** | Adapter interface, Pocket refactor, engine packs/provisioning, Speech engines manager, child-process lifecycle, API `model` routing, `/v1/models`, `/v1/audio/voices`, bindings; first engine = best survivor (likely Kitten 2 on GPU or Kokoro on CPU) | Journeys 2/3 (for chosen engine), 5, 6; lifecycle/cancel/unload/memory gates; Pocket rollback |
| **D — Remaining engines** | Each surviving engine, incl. Phonon (31M, 40M with token flow) and KokoClone composite | Per-engine smoke test on each claimed target; capability-correct UI; imported-voice validation |
| **E — Compare & polish** | In-app blind A/B with saved ratings, hardware-aware recommendations, per-machine benchmark, docs | Journey 3 compare flow; recommendations correct on 5090/MacBook/CPU-only |

A1/A2 can proceed in parallel with B.

Docs deliverables ride the phases: Phase C updates `docs/api/HTTP_API_REFERENCE.md`,
`docs/ENV_REFERENCE.md` and `docs/agent-reference/RUNTIME_AND_MEMORY.md`; Phase E adds user-facing
engine-manager and Compare docs.

## 8. Testing

Pre-flight commands (must pass before/after each phase): backend `pytest tests/tier1_unit -q`,
`python3 scripts/validate_repo.py` and `pyright`; frontend `npm run check` (oxlint + `tsc -b` +
`vite build`); CI on GitHub Actions; real-device smoke tests per §6.1 before release.

- Backend: existing Pocket runtime/API/voice tests unchanged; new adapter contract tests (fake
  engine); strict saved-ID path safety; namespace allowlists; capability validation errors; binding
  invalidation on reference/variant change; API-default migration and transactional rollback;
  legacy `voice`/`voice_id`/`builtin_voice`/`model` behaviour; engine swap serialization; child crash,
  timeout, disconnect cleanup; imported-voice rejection (pickle, bad shapes, paths).
- Packs: manifest hash verification, resumable install, removal, update-available marking, smoke
  test device verification (mocked in CI, real on target machines).
- UI: catalog search/filter via keyboard, preview labelling, readiness states, Speak/API default
  separation, snippet URLs, engine manager states including failures, Compare blind mode, language
  preference filtering across catalog/Speak/Compare plus optional API enforcement, preserved
  OmniVoice save/stitch/family flows.
- Real-device smoke tests on Windows 5090 and MacBook per claimed engine before release.

## 9. Confirmed follow-up decisions and remaining tests

These decisions supersede earlier tentative wording about previews and small Pocket models.

1. **Phase B authorized:** throwaway downloads and isolated test environments on the MacBook and
   Windows RTX 5090 are approved. This does not authorize modifying the live docker-agent service,
   uploading voices, or accepting gated terms on the user's behalf. Record environment/cache paths
   and provide cleanup instructions; retain results separately from disposable dependencies.
2. **Preview caching approved:** download upstream samples on explicit click and cache locally.
   Proposed defaults: 30-day inactivity expiry and a 250 MiB least-recently-used limit, configurable;
   prune at startup and after downloads, skip playing/in-flight files, and expose Clear preview cache.
   Cache keys include engine/voice/revision. Delete only app-owned preview files, never library
   recordings, model weights, prepared voices or saved comparison results. Sample downloads are an
   explicit exception to the network-policy wording in §0; never send text or reference audio.
3. **Kitten 2 C++ is a test decision, not a user choice now:** compare Python/MLX/CUDA and native
   CPU serving where supported, including clone preparation cost, output quality, cancellation,
   latency and total dependencies. Choose supported paths from evidence.
4. **KokoClone has two different voices:** the target reference is the existing saved
   OmniVoice-designed voice. Kokoro first speaks the text in a built-in source voice, then Kanade
   converts that speech toward the target reference. The source voice is an intermediate technical
   setting, not a replacement for the library voice. During evaluation vary it to test leakage;
   normally hide it behind an evaluated default, exposing an advanced override only if useful.
5. **Small Pocket checkpoints are in evaluation scope:** these are smaller synthesis models
   (18.2M/6.9M/1.9M), not additional named speakers. Inspect their manifests and test compatible
   built-in voice references for browse/preview/Speak/API use, with model variant distinct from
   voice identity. Expose passing combinations as optional model variants, without upgrading the
   existing Pocket baseline implicitly. Test cloning separately rather than assuming these are
   preset-only or that current cached voice states are compatible. Include available newer Pocket
   preset catalog entries as well, after checking artifact and language compatibility.

## 10. Evidence and reproducibility

Upstream revisions inspected (not approved pins): Kokoro GitHub
`dfb907a02bba8152ca444717ca5d78747ccb4bec`; Phonon runtime `49b9033e44ab0fbb935973eca3213757644d1bbb`;
Kitten Python `afd9dfda7ffdca35dd0151b149c221140c80ec3f`; Kitten C++
`2b9912e72245f5597c664d2be44a6e7ba0a3f293`; Kitten C++ binding `py-interface`
`bfab0cbd31a5697e5cba4779f7eed78368eeede0`. HF: Kokoro `f3ff3571791e39611d31c381e3a41a3af07b4987`;
Phonon 31M `92741c5b07d085ff840e26fea8ce43110b87852f`; 40M English
`cc738b7e4d182c2ba1bafb8062aa4846af000637`; Phonon voices `0ee17205f254b5abc43b266c8a0f215565c352f7`;
Kitten 2 `1f00fee525c7b2e30bbe9ca9ba67529734fce9c9`. Tiny Kitten cards:
[mini](https://huggingface.co/KittenML/kitten-tts-mini-0.8),
[micro](https://huggingface.co/KittenML/kitten-tts-micro-0.8),
[nano-int8](https://huggingface.co/KittenML/kitten-tts-nano-0.8-int8). Kokoro ONNX claims from
[kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx). Phonon Python package
[ptts 0.4.1](https://pypi.org/pypi/ptts/json) and Kitten C++
[kitten-tts-cpp 0.2.0](https://pypi.org/pypi/kitten-tts-cpp/json) metadata re-checked 2026-10-23.
Revalidate before locking.

[k-card]: https://huggingface.co/hexgrad/Kokoro-82M
[k-voices]: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
[k-pypi]: https://pypi.org/pypi/kokoro/json
[ko-pypi]: https://pypi.org/pypi/kokoro-onnx/json
[p-card]: https://huggingface.co/gradium/phonon-31m-en
[p-runtime]: https://github.com/gradium-ai/xn-ptts
[p-voices]: https://huggingface.co/gradium/phonon-voices
[p-server]: https://github.com/gradium-ai/xn-ptts/blob/main/ptts-openai-server/README.md
[p-transformers]: https://huggingface.co/docs/transformers/main/en/model_doc/gradium_phonon_tts
[t-readme]: https://github.com/KittenML/KittenTTS
[t-card]: https://huggingface.co/KittenML/kitten-tts-2
[t-license]: https://huggingface.co/KittenML/kitten-tts-2/blob/main/LICENSE.md
[t-onnx]: https://github.com/KittenML/KittenTTS/blob/main/docs/onnx-models.md
[t-cpp]: https://github.com/KittenML/kitten-tts-2-cpp
[t-docker]: https://github.com/KittenML/KittenTTS/blob/main/docs/docker.md
[t-pypi]: https://pypi.org/pypi/kittenml/json
[tc-pypi]: https://pypi.org/pypi/kitten_tts_cpp/json
[tc-binding]: https://github.com/KittenML/kitten-tts-2-cpp/blob/bfab0cbd31a5697e5cba4779f7eed78368eeede0/python/kitten_tts_cpp/model.py
[pocket-upstream]: https://github.com/kyutai-labs/pocket-tts/blob/44cb63eaa4144f32ff80863968515165a5554353/README.md
[kc-source]: https://github.com/Ashish-Patnaik/kokoclone/blob/main/core/cloner.py
[kc-chunks]: https://github.com/Ashish-Patnaik/kokoclone/blob/main/core/chunked_convert.py
[kc-deps]: https://github.com/Ashish-Patnaik/kokoclone/blob/main/pyproject.toml
[kanade-card]: https://huggingface.co/frothywater/kanade-12.5hz

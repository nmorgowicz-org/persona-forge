# Multi-engine speech: Kokoro, Phonon, Kitten TTS, and first-class built-in voices

**Date:** 2026-10-23 (updated through 2026-10-28). **Status:** implementation in progress; the engine
framework, optional packs and voice UI described as **Built** below are integrated. Phase B
screening and an objective cloning bake-off have run (see
[20261023-phase-b-screening.md](20261023-phase-b-screening.md)); no final engine quality ranking.

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

### 0.1 Phase B outcome (screening, not ranking)

Measured 2026-10-23 on the MacBook (M5 Max), the Windows RTX 5090 (torch 2.14.0+cu130, the app's
pin) and the docker-agent Intel i7-1360P container. Details, caveats and raw numbers are in
[20261023-phase-b-screening.md](20261023-phase-b-screening.md).

| Engine | Result |
| --- | --- |
| Phonon 31M | Fastest on Intel CPU (RTF 0.26-0.31, first audio 0.10 s, about 2x faster than Pocket there). English only, 2 voices, **no local cloning**. |
| Kokoro 82M | Intel CPU RTF 1.4-1.7 with defaults, **0.64-0.70 once ONNX threads are pinned to 4**. Needs explicit thread settings. 5090 RTF 0.008-0.030. No cloning. |
| KokoClone | M5 CPU cloning RTF 0.14-0.30. Speaker similarity near the different-speaker floor (0.85). |
| Kitten TTS 2 | Clones and has 115 voices. M5 MLX RTF 0.15-0.18 (cloning), 5090 compiled 0.25-0.34, **5090 eager 1.2-1.3**, M5 torch CPU 1.7-1.9, not viable on Intel. Compile path needs `triton-windows` plus MSVC Build Tools on Windows. |
| Kitten nano (0.1) | Intel RTF 0.50-0.63, no streaming. Not worth integrating. |
| Pocket-TTS (baseline) | Intel RTF 0.51-0.53 (preset), M5 cloning RTF 0.06-0.10. Best identity **by ear on the two Aussie references** (similarity 4.5 vs 2.4-3.6 of 5). On real US and UK references the objective gap closes (0.92-0.98 for all engines) and listening is pending. Misreads numbers and codes in structured text on three of four references. |

Owner decisions since this plan was written: use is private and personal, every cloning option is in
scope, each is compared against Pocket-TTS, and the product should let users choose. vLLM was
ruled out for Kitten 2.

**Open before any engine is ranked:** the blind listening ratings, Pocket-TTS on the Intel and 5090
targets for a like-for-like speed comparison, the compiled Kitten 2 tail-latency cause, and whether
`kittenml` co-installs with the app's `transformers` lockfile.

## 1. Candidate engines at a glance

All reviewed families output 24 kHz; adapters must still report the actual rate.

| Engine | Cloning | Built-in voices | Best targets (to be verified) | Streaming | Role in Persona Forge |
| --- | --- | --- | --- | --- | --- |
| **Pocket-TTS** (current) | Local, from reference audio; cached states | 30 curated app entries (24 English + 6 non-English) | CPU everywhere; existing accelerator families | PCM frame streaming (existing) | Default, universal, low-resource |
| **Kitten TTS 2** 1.7B | Local in-context, 5–30 s ref + transcript (Python); native C++ needs offline-prepared refs | 115 entries in pinned manifest, multiple languages (docs disagree on totals) | CUDA GPU (Python, **fast only with a static cache and compiled decode step**), Apple silicon (MLX, measured), not Intel CPU (measured on M5 CPU only; C++/GGML path dropped, see §9.3) | Sentence-chunk (Python and C++ binding) | High-quality cloning + large preset catalog |
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
| `app.py::POCKET_BUILTIN_VOICES`, `/voices/built-in` | 30 curated Pocket entries (24 English + 6 non-English). Becomes the Pocket slice of the unified catalog. |
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
- Imported prepared voices are untrusted: validate schema, shapes/dtypes, sizes, revision;
  reject pickle/object arrays and arbitrary paths/URLs. Only engines with a runtime add-voice
  operation and a pinned file schema accept them — Phonon (`TTS.add_voice` safetensors, §5.4).
  Kitten native `voices.json`/NPZ is not importable: its runtime reads the pinned snapshot at
  construction and has no add call.

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
  **Decision (2026-10-28): the switch is not built.** Pack engines run beside the active backend, so
  only a swap among the built-in backends is left, and the lifecycle cannot do that from a request
  without a redesign: only `pocket-tts` is a registered engine (a request cannot name `openvino` or
  `pytorch`), and the one existing swap (`apply_runtime_config` with `TTS_BACKEND`) is a global
  reconfiguration that makes `/generate` and `/v1/audio/speech` answer 503 to everyone else while it
  runs (not a queued swap), persists to `runtime.json`, changes `TTS_BACKEND` before the load
  succeeds and cannot roll back, and loads 5.4-6.9 GiB in 60-120 s or more. See §5.6 and
  `docs/api/HTTP_API_REFERENCE.md` ("Switching engines from a request"). Revisit only with a queued
  swap job (bounded wait, rollback, an engine id per built-in backend). The setting is not shown,
  because a switch that does nothing would mislead.
- Preview, quick-benchmark and Compare jobs run at a lower queue priority than API and Speak
  audio; they never delay endpoint requests.
- Each engine carries its own idle-unload timer (pack-manifest field `idle_unload_after`),
  mirroring the existing Pocket idle-unload policy.
  **Built:** every pack manifest carries `idle_unload_after` (seconds, `0` = never; validated as a
  non-negative number; written by each installer: Kitten 2 1800 s because a reload re-pays the compile,
  the others 600 s). `engine_lifecycle.IdleUnloader` resolves argument > per-engine env
  (`*_IDLE_UNLOAD_S`) > manifest > engine default (older packs lack the field), on every call. All four
  adapters use it; `GET /engines` `load_status` exposes `idle_unload_after` and `idle_unload_source`.
  An idle timer never stops a worker mid-stream. Verified with a real Phonon pack and a 3 s override:
  unloaded to `idle`, reloaded on the next request.
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
  **Built (2026-10-28):** the default can be a pack voice (`kokoro:`, `phonon:`, `kitten2:`,
  `pocket-lite:`) or a saved voice cloned on a cloning pack engine (`kitten2`, `pocket-lite`); see
  §5.3 for the behaviour, `GET/PUT /api-default` in the API reference for the contract.
- Streaming is advertised honestly (`frame`/`sentence`/`none`); batch engines still serve PCM as a
  single chunk when requested. Cancel on disconnect; release the executor only after worker cleanup.

### 4.6 Design deltas from Phase B measurements

The sections above stand. Screening found eight things the design did not yet cover; each is a
change to a section above, not a new subsystem.

1. **Runtime tuning belongs in the pack manifest (§4.4).** Kokoro ONNX ran at RTF 1.4-1.7 with default
   thread settings and 0.64-0.70 with `intra_op_num_threads=4` on the same host, because the runtime
   sized its pool to all 16 logical CPUs. A pack manifest therefore carries named runtime settings
   (thread counts, execution provider, cache implementation) that the adapter applies, and the
   user-visible default is whatever the pack's own benchmark supports.
2. **The smoke test must measure speed, not just device (§4.4).** Today it proves the device is used.
   Kitten 2 on the 5090 used the GPU correctly yet decoded at 17-24 % utilisation and RTF 1.2-1.3.
   The smoke test records a short RTF and shows "runs slower than real time on this machine" instead
   of a plain green tick.
   *Implemented:* every pack install (Kitten 2, Phonon 31M, Kokoro, Pocket Lite) ends with a
   "Measuring speed" step, after the verify step and before the provisioner publishes the stamp. It
   times one short sentence through the pack's own worker after warm-up and records RTF, device or
   mode and load average in `.install_check.json`; `GET /engines` returns it as `install_check` and
   the engine card shows "Install check: RTF 0.18 on mps" or the slower-than-real-time warning. A slow
   or unmeasurable result is a labelled outcome, never an install failure. `src/persona_forge/install_check.py`.
3. **Add a `warming` engine state (§4.1, §4.3).** The compiled Kitten 2 path spends about 33 s on its
   first call and showed one-off trials of 9 s, 41 s and 85 s against 1-4 s medians. The state
   machine becomes `loading` → `warming` → `active`. During `warming`, the API returns a documented
   retryable response and the UI shows progress. Warm-up runs fixed shape buckets, and the compile
   cache lives under the app data directory so a restart does not pay it again. Worst-case latency,
   not the median, is what gets reported on the engine card.
   **Built:** `src/persona_forge/engine_lifecycle.py` (`LoadTracker`) drives `idle` → `loading` →
   `warming` → `ready` (`ready` is this plan's `active`; the name is kept because the cards already
   read it) | `error`. The Kitten 2 worker's `load` no longer warms; the adapter then sends a
   separate `warmup` op, and any pack worker can opt in by answering `warmup_pending`. `GET /engines`
   `load_status` carries `elapsed_s` and `estimated_s` (Kitten warm-up: 35 s). A request to a loading or
   warming engine waits at most `ENGINE_WARM_WAIT_S` (default 5 s), then gets `503` + `Retry-After` +
   code `engine_warming`; the load continues in the background and concurrent requests share it. The
   engine cards, Speak, Compare and voice previews show the state and retry on that signal. Not built:
   shape-bucket warm-up and the app-data compile cache (the worker still compiles in-process).
4. **Normalise output loudness at the serving layer (§4.5).** Kitten 2 output is peak-normalised to
   0.99 with RMS 0.16-0.22; Pocket and KokoClone sit near 0.09. Without correction, changing the API
   default changes the volume every client hears, and any A/B test is biased toward the louder
   engine. Apply one consistent target level before encoding, with an opt-out, and level-match Compare
   playback.
   **Built (serving layer, `/v1/audio/speech`):** `src/persona_forge/output_level.py` moves the RMS of
   the active speech (20 ms frames above -55 dBFS, so pauses do not count) to **-23 dBFS**, boosts by at
   most 12 dB, and soft-limits peaks under -1 dBFS, for every engine including Pocket, before
   encoding. Silent or non-finite audio is returned unchanged. **On by default** (the plan's intent is
   that changing engine must not change volume); opt out with `TTS_NORMALIZE_LOUDNESS=0` or
   `normalize_loudness: false` on the request (the request overrides the env). Responses carry
   `X-Loudness-Normalized` and `X-Loudness-Gain-Db`. Two sources at RMS 0.09 and 0.2 served through the
   route end within 1 dB of each other (route test).
   **Streaming decision: streamed PCM is not normalised.** A stream cannot know the whole clip's
   level, and a fixed per-engine gain table would be a guess (cloned voices vary by several dB; no
   measured table exists for Phonon or Pocket Lite). Those responses say `X-Loudness-Normalized: false`.
   Engines that return a whole clip (Kitten 2, Kokoro) are normalised even for `pcm`. **Not built:** the
   Integrations-page preference (env plus request field only) and level-matching Compare playback.
5. **One shared text normaliser in front of the adapters (§4.2).** Pocket read "AB-104 totals
   $1,234.56" as "AB 10 of 4 totals $1020.34.56"; Kitten 2 and KokoClone read it correctly. Numbers,
   currency and codes are normalised once before synthesis, with a per-engine opt-out because Kitten 2
   already normalises internally and must not be normalised twice. The structured corpus case is a
   regression test for it.
   **Tested:** Pocket misread the sentence on all three references tried (r2 Aussie, r3 US, r4 UK;
   Whisper heard e.g. "1,234 Donfab C6", "$134.34 to $34.5 kilograms"). With the numbers spelled out
   before synthesis it read correctly on all three, in two variants (kittenml's `normalize_text`, and a
   hand-spelled one using "AM", "twenty-third", "three and a half"). `kittenml.normalize_text` is not
   safe to adopt as-is: it raised `ValueError` on "XJ-4471 ... B-12", read a phone number as "five
   hundred fifty-five to one hundred forty-two", and spelled "www.example.com" letter by letter. Neither
   the app nor `pocket-tts` normalises text today, so build a small app-owned normaliser (currency,
   times, ordinals, decimals, units, hyphenated codes read as letters plus digits), with
   `num2words`-style number conversion, fall back to the raw text on any error, and test it against
   the structured corpus case on every cloning engine.
6. **Prepare clones with the transcript (§4.1 binding).** Kitten 2 cloning without `reference_text`
   loads a Whisper model at synthesis time. Saved voices already carry a transcript
   (`sample_text`); the binding is prepared with it, and a missing transcript is resolved once at
   preparation, never during an API request.
7. **Toolchain prerequisites in the manifest (§4.4).** Compiled Kitten 2 on Windows needs
   `triton-windows` and MSVC Build Tools; on Linux it needs a C compiler. The pack declares host
   prerequisites and detects them. If they are missing, the engine card says what is needed and
   offers the slower eager path as a labelled fallback (RTF 1.2-1.3 on a 5090) rather than failing.
8. **Benchmarks are per machine, not per engine (§5.2).** The same engine ranges from RTF 0.15
   (Apple MLX) to 1.9 (the same machine's CPU) to not viable (Intel). Engine cards show the measured
   speed on this machine from a quick benchmark, with the load average at the time, and never a
   fixed global claim.

Cloning identity, as heard (one listener, 8 clips per engine per round): on the owner's two female
Aussie references Pocket-TTS led clearly (similarity 4.5 vs 2.4-3.6). On real American and British
female recordings all four cloners landed within 0.3 of each other (similarity 4.1-4.4, naturalness
4.0-4.5, no artifacts), so the first-round gap is specific to those references. Pocket stays the
default for speed and incumbency; Kitten 2 and KokoClone are credible optional engines. Male voices and
the owner's own recordings are untested.

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

**Manager status (Mac, browser-checked).** Each card shows a hardware-fit line and "Run quick
benchmark" (one cold plus three warm requests; the card shows median and worst seconds per second of
audio, first-request time and the load average, or "Speed not measured"). Fit text claims only what
is tested: Kitten 2 says "Recommended for Apple silicon" or "for your NVIDIA GPU" or the plain
unsupported reason; CPU engines say "Runs on CPU" and add "Not tested on this operating system" on
Windows. First benchmark on the Mac: Pocket 0.10, Kitten 0.18, Phonon 0.03, Kokoro 0.10 (load about
5, so pessimistic).

**Details, token, nudge and "Make active" (built 2026-10-28; Mac, browser-checked against `/tmp/pf_all`'s
packs, an empty `ENGINE_PACKS_DIR` and a real Pocket Lite install attempt).**

- **Details** is an inline expander per pack engine (`GET /engines/<id>/details`, `EngineDetailsPanel`):
  pack version, revision and manifest hash; runtime variant, device and mode; the install check; the
  idle-unload value and where it came from; disk used (the whole pack folder; the card's own
  `disk_bytes` stays artifact-only because it is polled); packages as pinned and as **installed in the
  pack's own virtualenv** (read from `.dist-info`, flagged when they differ); weights as pinned (Hugging
  Face cache models with commit revision and size, and Kokoro's two files with their SHA-256) and the
  last install and worker log lines. Real result for Kokoro: `kokoro-onnx pinned 0.6.1 · installed 0.6.1`,
  `kokoro-v1.0.int8.onnx · 88 MB · sha256 6e742170d309…`, 235 MB on disk, 10 min idle unload (default).
- **Logs** are bounded (last 200 lines), redacted when stored (exact stored and environment tokens,
  `hf_…`-shaped strings, `Authorization`/`Bearer`, `HF_TOKEN=`, `?token=`) and have two sources. The
  install log records step markers and the streamed output of every install command (`run_command` now
  streams instead of buffering) and is also written to `<pack>/install.log` (0600) when the install
  ends, so it survives a restart. The worker log is the pack worker's stderr, in memory only
  (`PackProcess` gained a `log` sink; its `stderr_tail`, which flows into error messages, is redacted
  too). A failed install shows **Retry** and **View logs** (opens the Details panel at the log), plus
  the repository link when the failure is one the user can fix.
- **Hugging Face token** (gated engines only: today Pocket Lite): a masked field on the card
  (`PUT/GET/DELETE /engines/hf-token`). Stored in `<DATA_DIR>/.engine_hf_token`, 0600, separate from
  `HF_TOKEN_FILE` (which may be a read-only Docker secret). Resolution is stored, then `HF_TOKEN`, then
  the user's `huggingface-cli login`; it is handed only to the pack's download child (never put in the
  server's environment, so standard Pocket is unaffected) and no response, log, manifest or error ever
  contains it. Responses carry `{set, source, can_clear}`. The app still never accepts terms for anyone.
- **Install errors now tell the cases apart (§2.4).** `pocket-tts` hides every gate failure behind
  "no cloning weights" (it silently falls back to the ungated model), so the prefetch step asks
  Hugging Face first (`HfApi.auth_check`) and prints the HTTP status: 401 with no token is
  `needs_token`; 401 with a token is `token_rejected` (Hugging Face answers 401 to an unknown token
  exactly as to no token, so those two cannot be told apart by the server, only by whether one was
  sent); 403 is `terms_not_accepted`; connection errors are `network`. Each has an actionable message
  and a link (`install_job.error_code`, `error_link`). Checked for real in a browser with a dummy
  token: save shows only "Token set", the install failed as `token_rejected`, Clear then Retry failed as
  `needs_token`, and neither dummy nor token file remained on disk afterwards. **Not tested:** a real
  403 (it needs an account that has not accepted the terms); that path is covered by the stub tests.
- **First-run nudge:** a dismissible banner at the top of Speech engines, shown only while no pack
  engine is installed and `hardware_fit.first_run_nudge` has something true to say. It states support,
  not quality or speed: "Your NVIDIA GPU can run Kitten TTS 2 (a GPU engine)", "Your Mac's Apple
  silicon can run Kitten TTS 2 (on MLX)", or, with no GPU, "light engines like Phonon, Kokoro and Pocket
  Lite run on this CPU without one. Install one to measure its speed here." (speed is never claimed
  before something is measured). An unknown fit shows nothing. The dismissal is the persisted UI
  preference `engines.nudgeDismissed`; checked after a reload with the local copy wiped.
- **"Make active": decided, not built as a switch.** Pack engines run beside the active backend, so
  there is nothing to make active, and switching built-in backends from a request stays out of scope
  (§4.3). What the verb honestly means here is the API default, which already exists as engine + voice
  (§5.3). Each installed pack card therefore has **Use as API default…**, which opens Voices → Built-in
  filtered to that engine, where **Set as API default** chooses the voice (disabled with "Is the API
  default" when that engine already serves it). No confirmation with "memory impact" is shown because
  nothing is loaded or unloaded by it.
- **Small fix on the way:** a card whose engine reported a mode other than `mlx` always said "Running on
  Apple silicon"; it now says "Running: <mode>".

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

**Catalog status (Mac, browser-checked).** The Built-in tab now lists Pocket plus every installed
engine's presets (`GET /voices/built-in?engines=all`; the plain route is unchanged for Speak).
With Phonon and Kokoro installed it showed 89 English voices; an engine filter, engine badges, and
a note naming engines that are not installed. Preview generates locally through `/v1/audio/speech`
(a real Kokoro preview played). Pack voices can be favourited, copied and set as
the API default (below); "Use in Speak" is hidden for them, with the reason in the drawer. **Preview cache (§9.2) not built,
on purpose:** it exists for downloading upstream sample files, and none of these engines ships
sample URLs, so there is nothing to cache. If an upstream sample source is added later the cache
spec still stands. **Compare from a saved voice's actions menu: built** ("Compare engines" opens the Compare tab with that voice on every installed cloning engine; checked in a real browser with two saved voices). **API default for pack voices: built (2026-10-28).** The drawer's **Set as API default** now works for every installed pack engine's voices ("Use in Speak" stays hidden for them; Speak has its Engine selector). Decisions:

- The API default is **engine + voice**, not "a voice on the active engine". It does not need an engine switch: pack engines already run beside the active backend, so a request with no voice and no named engine is simply routed to the default's engine adapter. Requests that name a *different* engine outright do not use the default's voice.
- **Voice ids imply their engine** (§4.5): a namespaced `voice` (`kokoro:af_heart`) is served by Kokoro even when `model` is a generic label such as `tts-1`. An explicit `model` still wins.
- **Saved voices on a cloning pack engine: included** (`PUT /api-default {voice: "vd_...", engine: "kitten2"|"pocket-lite"}`), because §4.5 already defines the default as engine + voice and saved voices "use the API-default engine". The adapter prepares the clone on the first request, so there is no separate prepare step; Kitten requires the voice's transcript, checked at set time. Saved voices without an `engine` keep the old semantics exactly (active backend, hot-swap, legacy `.active_default` mirror); a pack-engine default clears that mirror and never touches the active backend's runtime voice. On Integrations a "Saved voices run on" select appears when a cloning pack is installed and applies to the **Set default** buttons of saved voices.
- **Persisted, nothing migrated.** The record is the existing `.api_default.json` (`engine` holds the pack engine id); older records and the legacy file are unchanged. Writes are atomic and all-or-nothing (the previous record and mirror are restored if either write fails; a saved-voice activation that was already applied is rolled back).
- **Validated twice.** At set time (engine installed, voice offered, saved voice exists and has what the engine needs; shape checked against a per-namespace allowlist, never used as a path) and at use time on every request that relies on the default.
- **Repair, not fallback.** An engine removed outside the app (or damaged), a voice the pack stopped offering, or a deleted saved voice gives `409 api_default_unavailable` on a request that relies on the default, with the message and repair named; `GET /api-default` returns the record with `servable: false` and a `problem` (`engine_not_installed` | `voice_missing`, plus `repair`). Deleting a saved voice that is a pack-engine default keeps the record so this surfaces (a default on the active backend is still cleared, as before). Integrations shows a "needs repair" banner with **Open Speech engines** and **Choose another default**; the drawer shows the same text on the voice.
- **Removing the engine that serves the default is blocked** (journey 6): `POST /engines/<id>/remove` returns `409` with `code: "api_default_engine"` and "Change the API default first"; the Runtime engine card shows an "API default" badge, a note and a disabled Remove (`GET /engines` carries `api_default`).
- Integrations: the effective default shows the engine badge, readiness, and snippets (curl, Python, Test endpoint) with the namespaced id and `model` set to the engine id. The "Available voice IDs" table still lists saved and Pocket voices only (a pack engine's 40-115 voices would swamp it); pack voices are set from Voices → Built-in.

Checked in a real browser with the packs in `/tmp/pf_all` (Kitten 2, Phonon, Kokoro): set `kokoro:af_heart` from the drawer, Integrations showed "Kokoro 82M · ready" and copyable snippets, the server was restarted, and a bare request returned the same bytes as an explicit Kokoro request; Remove was refused (API 409, UI button disabled with the note); the Phonon default streamed PCM; moving the Phonon pack aside produced the 409 error and the red banner, and a Kitten clone default served a bare request and, after the voice was deleted, reported `voice_missing`. Pocket Lite was not installed on that machine (its weights are gated), so it is covered by the stub-pack route tests only.

**Uninstalled engines' voices: built.** `src/persona_forge/engine_voice_catalog.json` bundles each pack engine's voice names and languages (Kitten 115, Phonon 37, Kokoro 41; Pocket Lite's 21 come from its worker), so the tab lists them before install with a "Needs install" badge, an **Install** button on the card and in the drawer, an "Installed only" toggle, and every engine in the engine filter. The install runs inline with step progress and the list reloads with the engine's real voices when it finishes. The file is generated from installed packs (`python -m persona_forge.voice_catalog`), and `tests/tier2_backend/test_voice_catalog.py` compares it with any pack that is installed, so a stale list fails the test. Preview stays disabled until install (nothing upstream to play). Checked in a real browser: browsed with only Kokoro installed, installed Phonon inline (about 40 s), and its cards switched to Preview, which produced real audio.

**Voice metadata and filters.** The first version kept only names; the engines' own data carries more, so each catalog entry now has `gender`, `gender_source`, `accent`, `age` and a description, and the tab has Gender and Accent filters plus badges. Sources:

| Engine | Gender | Other |
| --- | --- | --- |
| Phonon | upstream `gender` (13 female, 12 male, 12 "character" voices with none) | `locale` as accent, `age`, upstream `description` |
| Kokoro | the second letter of the name (`af_`, `bm_` ...), all 41 voices | accent from the first letter (a American, b British) |
| Pocket, Pocket Lite | the app's existing notes ("Female reading"), 20 of 21 Lite voices | the note |
| Kitten 2 | none upstream. 9 from an explicit word in the name (`NewsAnchorFemale`, `Grandma...`), 106 **estimated** from the median pitch of the voice's reference clip | the name split into words |

The Kitten estimate is shown as "Female (est.)" and is a stopgap until upstream states a gender. Median pitch of at least 165 Hz reads as female. Against 27 voices whose gender I judged from first names it agreed on 22 (10 of 12 female, 12 of 15 male); the misses were Dolores, Martha, Jasper, Laurence and Leo, which is the expected failure for low female and high male voices. That sample is my own judgement, not ground truth. `gender_source` (`upstream`, `name`, `estimated`) is kept per voice so the estimates can be replaced without a UI change.

Finding while doing this: Kitten has no language field, and only some voice ids carry a prefix, so 65 voices named for a language (`KoreanNewsAnchor`) were listed as English and slipped through the English-only filter. `preset_language` now also reads the leading language word; English-only went from 216 to 160 voices on the checked setup. `POCKET_BUILTIN_VOICES` moved to `pocket_voices.py` so the catalog can read it without importing the whole app (which starts the model loader).

### 5.4 My voices tab (cloning)

- Existing families/variants preserved.
- Each voice gets an **Engines** row: per cloning-capable engine status chips (Pocket ✓ Ready,
  Kitten 2 • Prepare, KokoClone • Prepare, Kokoro — not supported, Phonon — not supported (no local
  cloning)). Hover/tap explains why.
- **Prepare for…** runs preparation (transcript review step when the engine needs one and the stored
  transcript is unreviewed or mismatched).
- Import prepared voice appears under Built-in → "Add imported voice", stored with provenance.
  **Format decision:** Phonon 31M safetensors only. Kitten native `voices.json`/NPZ is not
  importable: its runtime reads the pinned snapshot at construction, has no add-voice operation,
  and importing arbitrary archives would open an unpickling-capable path.

**Built (item 7):** `voice_bindings.py`, `voice_prepare.py`, `imported_voices.py`; the My voices
Engines row and Built-in import dialog, provenance and removal. Existing families and saved
variants remain unchanged. Keyboard-focusable chips explain Ready/Prepare/Preparing/Failed and
why preset-only engines cannot clone. Missing/mismatched transcript text is editable/confirmable;
the existing user-clicked Whisper action is separate, never invoked by preparation or synthesis.

Bindings are keyed by resolved audio content, transcript where used, and the pack's
revision/runtime/dependency/artifact/settings identity. Lazy and explicit preparation use that
same key, reject unreviewed Kitten words, and revalidate inputs before publishing readiness.
Explicit jobs use the existing single-worker inference executor, not a second model-work pool;
adapter locks serialize them with pack synthesis. Worker loss clears in-memory prepared caches;
idle unload preserves the validated marker but rebuilds state locally on next use.

Imports are size-bounded, schema-checked non-executable safetensors; names and all stored paths
are app-generated, files carry filename/SHA-256/date/revision provenance, and the real Phonon parser
must accept them before publication. Invalid/stale imports are not served, and removal forgets the
warm copy without touching the source/catalog. HTTP contracts: [API reference](../api/HTTP_API_REFERENCE.md).

**Verified (2026-10-28, Mac, real packs in `/tmp/pf_all`, headless browser):** the Engines row chips
(Pocket ✓ Ready, Kitten 2 • Prepare, Pocket Lite · Install to use, Phonon/Kokoro — not supported);
explicit Prepare for Kitten 2 ran on the real MLX pack and flipped the chip … Preparing → ✓ Ready;
editing the voice's reference text flipped it back to • Prepare; a missing transcript is refused at
Prepare time with a review/edit step (never a request-time Whisper download), and Kitten's worker
returns a plain 400 when asked to clone without words. A real pinned Phonon catalog voice file was
re-imported under a distinct name through the UI (validation, engine round trip, provenance sheet,
`Imported` badge), served through `/v1/audio/speech`, and removed with a confirm dialog that leaves
the catalog file untouched; pickle/shape/path/extension rejects return the documented 400/422 codes.
The catalog roundtrip is also covered by `test_real_catalog_safetensors_roundtrip_when_fixture_is_supplied`
(set `PHONON_CATALOG_VOICE_FILE`).


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

**Compare status (first version built; Mac, real packs, headless browser).** Voices page, Compare
tab: text plus sample sentences, 2-4 slots (engine and voice, "install to compare" for missing
engines), serial generation with generate time and audio length per slot, blind mode with shuffled
letters, Natural and Clean ratings (1-5), a favourite, and a reveal that saves the session. Playback
is level-matched to -23 dB RMS in the browser. Verified with Pocket, Kitten 2, Phonon and Kokoro
slots. A failed slot no longer blocks the reveal. **Update.** Ratings are now saved on the server (`/compare/results`, see the API reference), ratings
from the first browser-only version are uploaded once, a Similar rating appears for cloned voices,
the summary shows median and worst generation time, and each engine card shows "Your ratings".
**Also built (Mac, browser-checked):** the reference clip is played first with its transcript
(or "No transcript saved"), a "Same voice on every cloning engine" button fills up to four slots with
one saved voice, and an engine whose worker is still loading shows "(warming up)" (checked with a
stubbed `/engines` response, not a real slow load). **Still not built:** the optional automatic-check
hints (word error, speaker similarity), deliberately skipped.
Ratings left at the default 3 are saved as 3, so they count in the averages. Cloning a saved voice
that has no transcript on Kitten 2 returns a plain 400 (it used to try a network model download).

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

**Speak and Integrations status (Mac, browser-checked).** Speak has an Engine selector (shown when
more than one engine is installed). The default is the active engine and the old job path. Choosing
a pack engine generates through `/v1/audio/speech` straight into the same player, with that
engine's own preset voices (or the selected saved voice, cloned, when the engine clones). The seed
box is disabled with the reason for engines without seeds, post-processing is disabled for pack
engines, and a note says the engine runs beside the active one and nothing is unloaded. Integrations
has an "Enforce English on the API" checkbox (off by default, saved on the server): when on, a
non-English voice or `language` gets a 400 that names the voice and the setting. **Not built:** the
rest of the §5.6 picker (engine sections inside the voice combobox, an engine dropdown for saved
voices beyond the one above, measured swap time), and "Allow API requests to switch engines".
**Switching: investigated, not built, by decision (see §4.3).** Pack engines never need a switch, and
a swap among the built-in backends from an API request would need a lifecycle redesign. A pack voice
can now be the API default (§5.3).

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
  **Not built:** see §4.3. What clients get instead: the active backend is changed in Runtime; a
  request the active backend cannot serve gets a clear error (a 400 for `builtin_voice` on a
  non-Pocket backend, a 409 for a Pocket preset default while another backend is active, a 503 with
  an install hint for a missing pack). **Header card, snippets, Test endpoint and the repair banner
  are built** around the API default's engine (§5.3).
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
   repair. **Built:** blocked (API 409 and a disabled Remove with a note); a default whose engine
   disappeared outside the app gets the repair banner (§5.3).
7. Set Languages to "English only" → non-English voices and checkpoints hidden everywhere; a
   requested French voice over the API still serves (enforcement off), then errors with the §5.8
   message after turning enforcement on.

### 5.10 Compare refinements from the bake-off

The prototype listening sheet (`bench/listen/index.html`, 8 items by 4 clips) is the working model
for §5.5. What it taught:

- **Level-match every clip** before playback. One engine's output was about twice as loud as the
  others'; unmatched playback would have decided the result.
- **Play the reference first** in each item, with its transcript visible, so "sounds like the
  reference" is a judgement against something heard seconds earlier.
- **Three separate ratings**, not one: similarity to the reference, naturalness, artifacts. The
  objective check already showed these can diverge: the engine that is most similar to the reference
  also misread numbers.
- **Keep the key hidden until export**, and shuffle clip order per item, so A/B/C/D never means the
  same engine twice.
- **Show worst-trial latency next to the median** on each slot, and show a `warming` engine as such.
- **Include the structured text** (numbers, currency, codes) in the default preset corpus. It is the
  case that exposed a real failure.
- Automatic scores (speaker-similarity, Whisper word error rate) may appear as small "auto-check"
  hints under a clip, labelled non-authoritative. The similarity metric used here is not calibrated
  for synthetic voices and must never replace the rating.

## 6. Evaluation (Phase B: technical screening)

Phase B answers **"can this engine run and serve on this target, fast enough?"** It is deliberately
before integration because it decides what is worth integrating. It is **not** the final quality
judgement: blind listening and inclusion tiers are decided in Phase E through the integrated
Compare tab, where engines are compared as the app actually serves them. Preliminary listening in
B only rules out clearly broken output (garbled, leaking, truncated); it does not rank survivors.

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
  long multi-chunk input; one French and one German sentence (the catalog already has 6
  non-English entries).
- **Voices:** ≥2 presets per engine per relevant language; 3 saved references with different
  accents/delivery incl. one OmniVoice-designed; reviewed transcripts; 5/10/30 s reference trials
  for cloning engines; KokoClone source-voice variants.
- **Technical screening pass first** (few trials): does it install, run on the intended device,
  clone/prepare where claimed, and stay within memory? Does output sound clearly broken? This is
  the input to Phase C engine selection. Survivors are measured, then integrated; ranking happens
  in Phase E.
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

- **Include** an engine on a target if it runs on the intended device, fits the device's memory
  with clean unload, and later rates well in Phase E blind listening (comparable to or preferred
  over Pocket on at least some voices/use cases). Phase B applies only the technical half.
- Label each engine/target with a tier shown in the UI: **Conversational** (p95 first audio ≤ 1 s,
  sustained RTF ≤ 1) or **Batch quality** (slower, labelled). Batch engines are still valuable.
- Record unsupported/untested combinations explicitly; claim only tested combinations.

**Screening results (2026-10-23):** [20261023-phase-b-screening.md](20261023-phase-b-screening.md) —
Phonon 31m, Kokoro 82M, Kitten nano and KokoClone on macOS M5 Max and docker-agent; Kokoro on the
RTX 5090. Kitten TTS 2 is blocked on its Windows build.

## 7. Phases

| Phase | Scope | Completion gate |
| --- | --- | --- |
| **A1 — Integrations & status fixes** | Snippets from effective API default; idle-unloaded shown as Ready; preset (`pocket:*`) settable as API default with persisted engine+voice+variant; Test endpoint; IDs table includes presets | Pocket preset served as default after restart; old clients and saved IDs unchanged |
| **A2 — Unified voice catalog (Pocket only)** | Voices tabs, Built-in grid/search/filters/preview/drawer, searchable Speak combobox, favorites, Speak vs API default labelling | Journey 1 passes; keyboard-accessible; no new model dependency |
| **B — Technical screening** | §6 screen on 5090, MacBook, CPU: installs, runs on the intended device, clone/prepare, latency/RTF/footprint; then measurement pass for survivors | Per-target feasibility table; candidate engines for C/D with locked env/pin manifests; no final quality ranking |
| **C — Engine framework + first new engine** | Adapter interface, Pocket refactor, engine packs/provisioning, Speech engines manager, child-process lifecycle, API `model` routing, `/v1/models`, `/v1/audio/voices`, bindings; first engine = best screened survivor (likely Kitten 2 on GPU or Kokoro on CPU) | Journeys 2/3 (for chosen engine), 5, 6; lifecycle/cancel/unload/memory gates; Pocket rollback |
| **D — Remaining engines** | Each surviving engine, incl. Phonon (31M, 40M with token flow) and KokoClone composite | Per-engine smoke test on each claimed target; capability-correct UI; imported-voice validation |
| **E — Compare, listening, polish** | In-app blind A/B with saved ratings (final quality ranking + inclusion tiers), hardware-aware recommendations, per-machine benchmark, docs | Journey 3 compare flow; ranked results per engine/voice; recommendations correct on 5090/MacBook/CPU-only |

A1/A2 can proceed in parallel with B.

### 7.1 Phase C4: Kitten 2 as the first new engine

Owner decision: Kitten 2 goes first (clone-capable, MLX on the Mac, compiled CUDA on the 5090).
Phonon 31M follows as the Intel CPU preset engine.

**Phonon 31M status (implemented, verified on the Mac only).** A pack engine like Kitten 2, but
tiny: `ptts==0.4.1` (native, no torch, GPU or compiler), model and the English catalog prefetched
into the pack and served offline. Real install into a scratch directory: 38 s, 72 MB. Through the
HTTP API: 37 English voices listed as `phonon:<Name>`, warm requests 0.09-0.17 s for 2-4 s of audio,
a saved-voice request returns a clear 400 (no cloning), an unknown preset returns 400, Pocket is
unaffected. **Structured text needs no normaliser:** Whisper heard "Invoice AB 104 totals $1,234.56
due on the 23rd at 3.30pm" with the raw text, and my normaliser made `AB-104` worse, so Phonon opts
out like Kitten 2. Seeded output matches to within one least-significant bit (thread rounding).
**Streaming and speed (done, Mac only):** the worker has a `stream` op, `PackProcess.stream` carries
the chunks, and `/v1/audio/speech` with `pcm` streams Phonon (first byte about 20 ms). `speed` maps
onto `duration_delta` by a table measured with fixed seeds (0.73-1.5x; below -1 the model breaks, so
it is clamped); the length it produces is approximate.
**Kokoro 82M status (implemented; verified on the Mac and the Intel host).** A pack engine on
`kokoro-onnx==0.6.1` with the int8 model and voices downloaded from a pinned release (sha256 checked;
resume keeps a verified file). **The "needs system espeak-ng" worry was wrong for this package:**
`espeakng-loader` bundles the library in its wheel, and a real install with Homebrew's `espeak-ng`
hidden from PATH passed its synthesis check (7 s install on the Mac, 11 s on Intel). Threads are pinned
to min(4, cores). Through the HTTP API on the Mac: 41 voices, English/French/Spanish/Italian/
Portuguese transcribed correctly by Whisper, `speed` 1.4 gave 1.47x shorter audio, unknown voice 400,
saved voice 400. Structured English text is read acceptably as is ("Ways 3. 5 kg" for "weighs 3.5 kg"
was the only slip), and the English-only normaliser would hurt other languages, so Kokoro opts out.
Intel (docker-agent, load average 5.8): first request 2.38 s, warm RTF 0.31-0.34, faster than Pocket
(0.51-0.53) and better than the 0.64 screened earlier. Not done: Japanese/Chinese voices (extra
packages), frame streaming, Windows, the fp32 model as an option. KokoClone (cloning on top of Kokoro)
remains an evaluation item.

**Intel CPU (docker-agent i7-1360P, throwaway container from the app image, live services running,
load average 3.6-5.4, so treat timings as pessimistic):** the real install took 47 s on Python 3.13
(`ptts` has wheels for it), all 37 voices were listed, the first request including worker start took
1.44 s, and warm RTF was 0.175-0.204 (about 2.5x faster than Pocket's 0.51-0.53 measured on this host
earlier). Streaming first audio took 0.26 s there (8 ms on the Mac), 33 chunks for 4.7 s of audio.
The live service was not touched; the scratch directory was deleted.
**Intel re-run after the shared adapter base (same host and image, throwaway container):** both
packs install and synthesize through the refactored classes (Phonon install 51 s, Kokoro 13 s; 37 and
41 presets). Warm RTF was 0.23-0.31 for Phonon and 0.41-0.46 for Kokoro, slower than the earlier
0.175-0.204 and 0.31-0.34. The load average was 4.8-5.8 (earlier 3.6-5.4) on a host with live
services. **A/B on the same host, same packs, alternating pre-refactor (55ad0c6) and current code,
two rounds:** Phonon warm RTF 0.22-0.33 old vs 0.22-0.29 new; Kokoro 0.39-0.45 old vs 0.39-0.47 new,
with the load average climbing from 5.6 to 8.2 during the run. No difference between the two; the
slower numbers come from the busy host, not the refactor.
**Windows (RTX 5090 box, native over SSH, Python 3.12, no WSL):** Phonon installed in 153 s, listed
37 presets and ran warm at RTF 0.16-0.18 (first request 1.64 s); Kokoro installed in 199 s, listed 41
presets and ran warm at RTF 0.23-0.24 (first request 2.59 s). Both ran through the real engine
classes and pack installers, not through the HTTP app. The installs were far slower than on the Mac
(38 s and 7 s); the cause was not investigated. Not confirmed on Windows: whether Kokoro's bundled
espeak was what it used (no system espeak was checked for), and the HTTP path. **Not verified:** the
plain-language message on an unsupported CPU beyond a unit test.
The routes, engine cards and voice catalog now go through `provisioned_engines.py`, so the next pack
engine (tuned Kokoro) is one registry line plus its own pack, worker and adapter modules.

**Already on `feat/multi-engine-speech`:** engine registry and `/v1/models` discovery
(`speech_engines.py`), the `SpeechEngine` adapter protocol with a Pocket adapter, pack manifests,
verification and installer (`engine_packs.py`), and the newline-JSON worker transport
(`pack_process.py`, with `ping` and `synthesize` ops and a hard kill on timeout). The transport's
own docstring says no worker is spawned yet; Kitten 2 is that first worker.

**Dependency check (done):** `kittenml` 0.9.6 resolves against the app's exact pins
(`transformers==5.12.1`, `numpy==2.4.6`; it pulls torch 2.14.x, librosa, phonemizer, espeakng-loader,
onnx). The Mac bench already ran on transformers 5.12.1. It would co-install, but it adds heavy
packages and a second torch consumer, so it stays a **pack with its own venv and child process**, as
§4.4 specifies, not an app dependency.

**Tasks, in order:**

1. **Worker** (`kitten2_worker.py`, runs inside the pack venv): ops `ping`, `load` (device and
   backend chosen at load: `mlx` on Apple silicon, `cuda` with `cache_implementation="static"` on
   NVIDIA, otherwise refuse), `prepare` (reference audio plus reviewed transcript; Whisper never
   runs in the worker or during a request, per §4.6 item 6), `synthesize`, `unload`. A first
   synthesize on CUDA compiles for about 33 s, so `load` runs a warm-up request and the UI shows
   "warming up" instead of hanging.
2. **Pack manifest** for `kitten2` with per-platform runtime variants (`python-mlx`, `python-cuda`),
   locked dependencies, artifact hashes, and the CUDA extras (`triton-windows`, MSVC check on
   Windows) reported as a preflight failure with an actionable message, not a stack trace.
3. **Adapter** `Kitten2Engine` in `speech_engines.py`: maps `voice_id` to a prepared clone or one of
   the 115 presets, forwards `seed_value`, returns `(wav, sample_rate, job_id)`; capability flags
   `clone=True`, `presets=True`, `streaming="none"`, no `instructions`. Register it in `ENGINES`,
   `MODEL_ALIASES` (`kitten2`, `kitten-tts-2`) and `ADAPTERS`.
4. **Text normaliser** (§4.6 item 5) with a per-engine opt-out; Kitten 2 opts out because it
   normalises internally. Pocket gets it first as the proving ground.
5. **Tests:** worker protocol against a stub model (no weights in CI), manifest parsing, adapter
   routing, and an opt-in smoke test that runs real weights on a machine that has the pack.
6. **UI:** Speech engines manager card (install, warm-up state, remove), clone-prepare action on a
   saved voice, and capability-correct controls (no streaming toggle, no instruction field).

**Gate:** a saved voice cloned through the API with `model: kitten2` on the Mac (MLX) and the 5090
(compiled), cancel and unload release memory, Pocket is untouched when the pack is absent, and the
engine is reachable from `/v1/models`.

**Open validations that do not block the start:** seed-matched MLX versus CUDA output, the cause of
the compiled-CUDA latency spikes (9 s, 41 s, 85 s trials; decide warm-up and timeout values from
it), and Pocket on the Intel and 5090 hosts for the speed comparison.

#### 7.1.1 Decision: fast mode is optional, and the upgrade path is one click

Compiled CUDA is the whole speedup: on the 5090, static cache without compiling measured RTF 1.4,
the same as eager, while compiled measured 0.3-0.5 (the machine was under RAM pressure for the
later runs). Compiling needs a C/C++ toolchain through Triton. The owner's rule is to remove
friction wherever possible, so:

- **Nobody is forced to install build tools.** The worker tries compiled mode first. If the warm-up
  fails it reloads eager and reports `mode: "eager"` plus a `fast_mode_issue`
  (`code`, `message`, `action`, `help_url`, raw `detail`). Eager still works, at about 1.4x slower
  than real time; Pocket stays the fast cloner on such machines.
- **Plain-language messages.** The raw Windows error `FileNotFoundError: [WinError 2]` is mapped to
  "Fast mode needs the Microsoft C++ Build Tools" with the Visual Studio download link and the
  workload name; Linux gets a `build-essential` hint; a missing Triton says to use Repair.
- **The golden path needs no restart.** `POST /engines/kitten2/recheck` unloads and reloads in the
  background; the next load re-tests the compiler. Install the tools, press Re-check, done.
- **Detection is by trying, not by looking.** `cl.exe` is not on PATH in a normal shell yet compiled
  mode works, because `triton-windows` finds Visual Studio itself, so a PATH check would give false
  negatives.
- **Mac is unaffected.** MLX is plain Python with no compiler.
- **Recompiles.** A new text length triggers one recompile (76 chars: 9.0 s first, 2.3 s repeated).
  This explains the earlier 9/41/85 s spikes. Warm-up covers one short length only; treat the first
  request at a new length as slow, or pad/bucket lengths later.

#### 7.1.2 Status

Done on `feat/multi-engine-speech`: worker, adapter, registry entry, pack-only routing, 400/503
error mapping, fast-mode fallback, and the provisioner (`kitten2_pack.py`).

- **Provisioner:** detects Apple silicon or an NVIDIA GPU (refusing anything else with a reason),
  creates a private Python 3.12 environment with `uv` (falling back to `venv` and `pip`), installs
  torch from the pinned CUDA index in its own step (so PyPI cannot shadow it), installs
  `kittenml==0.9.6` (plus `triton-windows` on Windows), prefetches every weight into the pack's `hf/`
  folder, checks `import kittenml`, then publishes the verified stamp. Only the provisioner can
  mint the stamp, so an empty or half-finished pack never reads as installed.
- **Background job.** A real install outlives gunicorn's 300 s request timeout, so
  `POST /engines/kitten2/install` returns 202 and `GET` reports `state`, `step`, `step_index`,
  `step_count` and `error`. Retrying resumes: an existing environment is reused.
- **Offline serving.** The worker runs with `HF_HOME` set to the pack and `HF_HUB_OFFLINE=1`, so a
  missing file fails fast instead of stalling a request while 2.4 GB downloads. This removed the
  503 s first request seen when weights downloaded mid-request.
- **Real result on the Mac (scratch pack dir, no dev override):** install 144 s (packages were
  cached; weights dominate), pack 2.0 GB weights + 1.5 GB environment. Serving: first request 9.1 s
  including worker start, then 0.8 s preset and 1.5 s clone; `/engines` reports `verified` and
  `mode: mlx`; Re-check returned to `ready` in under 12 s.
- **Real install on the 5090 (Windows, scratch pack dir):** 159 s with warm package caches (the
  first attempt took 669 s). It picked `cuda13` (cu130, torch 2.14.0) and installed
  `triton-windows`. Serving from the pack: first request 62.6 s including the compile, then 1.0-1.3 s
  for 2.7 s of audio (RTF 0.36-0.5 with the machine busy), mode `compiled`.
- **Broken compiler, through the real adapter:** mode `eager` (RTF 1.3, still works) and the status
  carries `needs_build_tools` with the plain-language message, the "Desktop development with C++"
  workload, the Visual Studio download link and the raw `InductorError ... WinError 2` kept only in
  `detail`.
- **Two bugs the real 5090 run found, both fixed with tests:**
  1. Newer drivers print `CUDA UMD Version: 13.4`, not `CUDA Version:`, so the parser returned
     nothing and the 5090 was given the **cu126** wheels. Those have no `sm_120` kernels, yet the
     old check (`import kittenml`) still reported the pack verified. Detection now parses both
     banners, falls back to the driver release, refuses Blackwell on an unconfirmed driver, and the
     install check asserts that torch has kernels for the GPU's architecture.
  2. Importing `kitten2_engine` before `speech_engines` raised a circular import (the app only
     worked through import order). The adapter is now built on first use via `get_adapter`.
- **Not yet verified:** the engine-manager UI, the text normaliser, Kitten's presets in
  `/v1/audio/voices`, and a Linux CUDA install (the code path is shared but untested). A pack
  installed by the buggy build (wrong torch) must be removed and reinstalled; retrying reuses the
  environment.

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
   **Resolved by Phase B:** the C++ fork fails to build on Windows (MSVC 19.44, `char8_t`) and ships
   no prebuilt binaries, so it is dropped as a shipping path. Python on MLX and on compiled CUDA is
   the supported route, with the Triton/MSVC packaging constraint above.
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

### 9.1 Small Pocket checkpoints: evaluation results (2026-10-25)

`pocket-tts` 4.0.0 ships configs for three smaller English models, each with a reward-fine-tuned
("refl") twin: `english_18m_2026-10` (27.9M parameters loaded, 18.2M by upstream's count),
`english_7m_2026-10` (16.6M) and `english_2m_2026-10` (11.7M), against the baseline `english`
(109.5M loaded). The cloning weights live in the gated `kyutai/pocket-tts` repo (access already
granted on this machine; nothing was accepted on anyone's behalf); the ungated
`pocket-tts-without-voice-cloning` repo carries non-cloning weights for the same sizes. All runs used a
scratch `HF_HOME`; the weights were copied to the Intel host as files, never the token.

- **Loads and clones:** all seven load and clone from a reference; built-in voice `alba` also works.
- **Intelligibility:** Whisper tiny.en WER on the plain sentence 0.06 and on the emotive sentence
  0.0 for every model, baseline included. (The structured-text WER of about 1.0 for every model,
  baseline included, is the metric comparing digits with spoken words; not a model difference.)
- **Speed, Mac (warm RTF):** baseline 0.09-0.13, 18M 0.05-0.07, 7M 0.05-0.06, 2M 0.04-0.05.
- **Speed, Intel (docker-agent, one torch thread, load about 4.5, two rounds, clone path):** baseline
  0.28-0.40, 18M 0.10-0.14, 7M 0.08-0.09, 2M 0.05-0.07 (roughly 3x, 4x and 5-6x faster).
- **Cloning similarity (WavLM-SV cosine to the reference, mean of 3 sentences; different-speaker
  floor 0.854):**

  | Model | r1_default | r2_aussie |
  | --- | --- | --- |
  | baseline `english` | 0.964 | 0.968 |
  | 18M / 18M refl | 0.922 / 0.927 | 0.916 / 0.923 |
  | 7M / 7M refl | 0.889 / 0.895 | 0.904 / 0.892 |
  | 2M / 2M refl | 0.876 / 0.863 | 0.853 / 0.856 |

  The metric is not calibrated for synthetic voices and is a screen only. Read literally: 18M keeps
  most of the identity, 7M keeps some, and 2M is at the different-speaker floor, so 2M does not
  clone in any useful sense. Whether 18M and 7M *sound* acceptable needs a listen:
  `/tmp/pfbench/pocket_small/listen.html` (reference first, then each model on three sentences).
- **Not done:** no integration into the app. The app pins Pocket weights and voice-state caches per
  model, so a variant needs its own pins, its own voice-state cache (states from the baseline are not
  compatible) and a way to choose it that does not change the existing default. The "refl"
  variants did not measurably differ from their base models on any metric here.
- **Listening verdict (owner, 2026-10-25):** 18M is very close to the baseline and acceptable. 7M and
  2M have robotic artifacts and sound much less natural, so they are rejected despite the speed. The
  owner was unsure the "refl" variants are better; no measurable gain, so use plain 18M. This matches
  the similarity ordering (0.92 / 0.89 / 0.86), so the screen was a usable predictor here.
- **Built (18M only):** see §9.3. Candidate shape was: a separate "Pocket Lite" engine (18M, optionally 7M)
  beside Pocket, using the same pack-style isolation so the baseline runtime is untouched.

### 9.2 KokoClone source-voice leakage (2026-10-25, Mac CPU)

The upstream wrapper hard-codes `af_bella` as the Kokoro source voice for English. I overrode it to
`af_bella`, `am_michael`, `bf_emma` and `bm_george` and converted one sentence toward each of the four
bake-off references, scoring WavLM-SV cosine to the reference and to the raw (unconverted) source.
Conversion takes about 0.7-0.8 s per clip after the Kokoro step. Screen only, one sentence, one run.

- **The source voice matters.** The same reference gave outputs that differ from each other by only
  0.90-0.94 similarity across sources, and the similarity to the reference ranged 0.80-0.97 depending on the
  source. Mean similarity to the reference per source: bf_emma 0.92, bm_george 0.91, af_bella 0.90,
  am_michael 0.88, which is within noise of each other.
- **Leakage is real in places.** `r3_us_f` with `bf_emma` scored 0.80 to the reference and 0.96 to the
  raw source, and `r2_aussie` with `af_bella` or `bf_emma` scored higher to the source than to the
  reference: the conversion barely moved those. Mixed-sex pairs (female source, male reference) were
  not systematically worse.
- **No single best source.** `af_bella` is best for one reference and `bf_emma` for three, so a fixed
  default cannot be justified from these numbers, and a per-reference choice needs a listening step.
- **Versus alternatives:** mean similarity to the reference is about 0.90, below the baseline Pocket
  (0.96) and about the same as Pocket 18M (0.92), at the cost of two torch models (Kokoro and the
  ~120M Kanade), an unpinned Git dependency and CUDA/CPU-only support.
- **Assessment:** not recommended for integration. Pocket Lite 18M gives comparable similarity with a
  single small model and no composite dependency. Listening page:
  `/tmp/pfbench/kc_leak/listen.html`. If listening shows the output clearly sounds like the reference,
  revisit this.

### 9.3 Pocket Lite 18M engine (built 2026-10-27)

Engine id `pocket-lite`, pack-style isolation without a virtualenv (the worker runs on the app's
interpreter, which already ships `pocket-tts` 4.0.0). Files: `pocket_lite_worker.py`,
`pocket_lite_pack.py`, `pocket_lite_engine.py` (a subclass of the shared pack adapter, which gained two
small hooks so a pack engine can clone), plus registry lines. Nothing in the standard Pocket runtime
changed.

- **Install (real, Mac):** 93 s, 191 MB, verified offline; needs a Hugging Face token with the terms
  accepted for `kyutai/pocket-tts` (gated); the failure message says so, and since 2026-10-28 the token
  can be pasted on the card and the failure is classified (§5.2).
- **Through HTTP:** clone of a saved voice, English presets, seeded requests, an unknown preset is
  400; `GET /engines` card shows Verified, cloning, hardware fit and the benchmark (RTF 0.051 median
  on the Mac, first request 0.23 s); the Compare tab runs Pocket against Pocket Lite blind on one saved
  voice (1.41 s against 0.26 s for one sentence).
- **Seeds:** a given seed reproduces the audio to within one 16-bit step; the standard Pocket model does
  exactly the same on this machine, so it is a property of torch there, not of this engine. A warm-up
  after load was tried and did not change it, and was removed.
- **Clone similarity through the app:** 0.894 on the app's saved voice with one sentence (the 0.92 in
  §9.1 was the bake-off references). Single sample.
- **Not done:** frame streaming, Windows and Linux runs, an Intel run through the app (the Intel
  speed above is from the model directly), pinning weight hashes ourselves (revisions are the commit
  pins in `pocket-tts` 4.0.0's own config, which it downloads by hash-addressed file).

### 9.4 Phonon 40M screening (2026-10-27, Mac CPU)

With the owner's token (terms accepted by the owner), `gradium/phonon-40m-en@cc738b7e` loads in the
31M pack's own `ptts` 0.4.1 with no code change: `ptts.TTS("hf://gradium/phonon-40m-en@<rev>", lang="en",
quant="q8")`. Same 37 English catalog voices. Warm RTF 0.025-0.028 against 31M's 0.024 (load about 31 s
each on the first, uncached run). Files: `model.q8.gguf` 74.6 MB (31M is smaller), `model.q4k.gguf` 60.4 MB.
**Listening verdict (owner, 2026-10-27):** no audible difference in voice, naturalness or anything else between 31M and 40M on three voices and three sentences (`/tmp/pf_ph40/listen.html`).
**Decision: not integrated.** It would add a gated, token-required install and a larger model for no audible gain. 31M stays the only Phonon model.

### 9.5 Newer Pocket preset catalog entries (2026-10-27)

Compared `pocket-tts` 4.0.0's predefined-voice catalogue (27 names) with the app's built-in list (30
entries). Every English name upstream is already in the app. The only upstream name the app lacks is
`daan`, a Dutch voice (`cml_tts_nl` recording); the app serves English, French, German, Spanish,
Italian and Portuguese and has no Dutch config, so adding it would list a voice nothing can speak, and it
was left out. The app's extra four `hf_*` entries are its own reference-clip voices, not upstream names.
Result: **no preset to add.** Separately, the model repository also carries newer full-size English
checkpoints (for example `english_2026-10`) that 4.0.0 has no config for; those are model variants, not
presets, and are not evaluated here.

#### 9.3.1 Intel through the app, and a version finding (2026-10-27)

- **Intel (docker-agent, throwaway container, app server, load about 3.3):** Pocket warm RTF 0.40-0.41,
  Pocket Lite 0.09-0.10 (about 4x faster), first request 1.4-1.6 s against 0.37 s. A saved-voice clone
  returned 200 in 0.5 s for 5 s of audio, a seeded repeat agreed to within one 16-bit step, an unknown
  preset was 400. The pack was built on the Mac and copied as files; the token never left it.
- **Finding:** the app pins `pocket-tts==4.0.1` (`pyproject.toml`), and each release pins its own
  weight revisions. The 18M cloning weights differ between 4.0.0 (the stale Mac venv used in §9.1 and
  the first Mac run) and 4.0.1 (different file hashes). A pack installed under one release has an
  offline cache that the other cannot find, which first showed up as a bare Hub lookup error. The pack now
  records the `pocket-tts` version in its manifest and the engine says "installed with X, app has Y,
  choose Repair" instead.
- **Re-measured with 4.0.1 (what the app really serves):** clone similarity mean 0.953 for 18M against
  0.965 for the standard model (four references, three sentences). The listening verdict in §9.1 was
  on the 4.0.0 weights; `/tmp/pfbench/pl401/listen.html` has the 4.0.1 pairs for a re-listen.

#### 9.3.2 Windows (RTX 5090 host, CPU torch, 2026-10-27)

Pack built on the Mac with `pocket-tts` 4.0.1 and copied as files with symlinks resolved (the token
did not leave the Mac); the engine class drove a real worker process on Windows (not the HTTP app).
Verified pack; first call (worker start, load, one synthesis) 24 s; presets warm RTF 0.15; a saved voice
cloned from its reference path (Windows paths) at warm RTF 0.16; a seeded repeat agreed to within one
16-bit step; an unknown preset raised the invalid-voice error. This used the default CPU torch
wheel: no GPU was involved. Scratch files removed.

#### 9.3.3 Windows install timing (2026-10-27)

The earlier Windows installs (Phonon 153 s, Kokoro 199 s) were not reproduced. Re-timed per step on the
same host with an empty uv cache and the current code: **Phonon 50 s** (venv 0.5 s, package 4.3 s,
model and 37 voices download 44.5 s, offline check 0.9 s) and **Kokoro 13 s** (venv 0.4 s, package 6.5 s,
model 1.5 s, voices 1.2 s). The download of the model and voices dominates Phonon; nothing in our steps
is slow. The 153 s and 199 s runs probably included first-time Python 3.12 provisioning and a colder
network; that was not isolated, so treat the new numbers as typical and the old ones as a cold-start
worst case. No code change.

#### 9.3.4 Streaming for Pocket Lite and Phonon (2026-10-28)

Pocket Lite gained a worker `stream` op (the model's own chunk generator), `streams = True` on its
adapter and `streaming: "frame"`. The shared adapter's stream path now uses the clone hooks, so a saved
voice streams too, and the route replaced its hard-coded Phonon check with "pack engine whose capability
is frame streaming". Phonon's worker and adapter already streamed, but it had no route or end-to-end
test until now. **Kokoro is deliberately excluded** (no native streaming; sentence-chunking would add
audible seams): a `pcm` request still gets one whole clip, and a test pins that.
Measured over HTTP on the Mac with real packs: first audio 0.02 s warm for both engines against
0.19 s (Phonon) and 0.29-0.34 s (Pocket Lite) for a whole clip; streamed audio matches the whole-clip
render at the same seed (equal length, at most one 16-bit step apart); a client that disconnects
mid-stream leaves no stuck worker (the next request succeeds). Not measured: Intel or Windows
streaming, perceived seams between chunks (none were audible in the one clip described by the numbers,
but nobody has listened).

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

# llama.cpp Native Pocket-TTS — Evaluation and Pivot Plan

- Status: **proposal / research record.** Phases 0-2 are authorized research and throwaway
  scratch work; Phases 3+ require Nick's explicit go/no-go at the Phase 2 gate.
- Plan owner: Claude (Opus), research pass 2026-08-12
- Execution owner: any implementing agent for Phases 0-2; Phases 3-8 are Sonnet-tier with
  Nick gating each phase
- Target branch: not yet cut. Phases 0-2 produce artifacts under
  `docs/screenshots/artifacts/` + a report appended to this file; no source changes.
- Source snapshot: repo at `chore/rebrand-cleanup-and-initiative-c`, `8a5b7c1`, 2026-08-12
- Upstream snapshot: llama.cpp release `b10369` (commit `6e62ba5`), PR
  `ggml-org/llama.cpp#26871` "mtmd: support pocket-tts" (ngxson + Pascal, merged 2026-08-11,
  approved by ggerganov / CISC / ServeurpersoCom)

## Execution status

| Phase | Status | Gate |
|---|---|---|
| 0 — baseline measurement on the current torch backend | Not started | Recorded RTF + WAVs committed to the artifacts dir |
| 1 — upstream capability spike (time-boxed, 1 day) | Not started | `llama-server` synthesizes a test prompt from a converted pocket-tts GGUF |
| 2 — voice-cloning feasibility spike + go/no-go writeup | Not started | **Nick decision.** Cloning parity answered yes/no with evidence |
| 3 — model acquisition + conversion pipeline | Not started | Reproducible `scripts/convert_pocket_tts_gguf.sh` |
| 4 — `llama_cpp_pocket_tts_runtime.py` adapter | Not started | Adapter satisfies the §2.6 contract against a fake server |
| 5 — backend dispatch + server lifecycle | Not started | `TTS_BACKEND=llama_pocket_tts` boots and generates end-to-end |
| 6 — post-processing chain re-validation | Not started | `audio_style.py` presets produce equivalent output |
| 7 — test coverage | Not started | Tier-1 fakes green; tier-3 integration tier marked and skippable |
| 8 — rollout, fallback, docs | Not started | Torch backend still selectable; ENV_REFERENCE updated |
| X — end-of-sentence clipping bug (independent) | **Done** ([#145](https://github.com/nmorgowicz-org/persona-forge/pull/145), merged 2026-08-12, released in 1.0.2) | Shipped independently of this plan; §6 kept as historical record |

---

## 1. Executive summary

llama.cpp shipped **native pocket-tts support** in release `b10369` (2026-08-11/12) via PR
#26871. The headline is a rewrite of the SEANet decoder's upsampling path from many small
per-channel grouped transposed convolutions (a workaround for `ggml_conv_transpose_1d` having
no grouped mode) into a **matmul + col2im** formulation, reported at **-80% per-frame
generation time on CUDA and -50% on CPU**, with output correlation **0.999994** against the
prior implementation — i.e. effectively sample-identical, not a quality/speed trade.

That is a large, credible win for exactly the workload Persona Forge's default backend runs.
Persona Forge is CPU-bound on `pocket_tts` today (the torch `TTSModel` autoregressive loop,
`src/persona_forge/pocket_tts_runtime.py`), and a ~2x CPU speedup would land directly on the
Speak tab's perceived latency and on the `/v1/audio/speech` streaming path Hermes consumes.

**Top-line recommendation: do not commit to a pivot yet. Run a hard two-phase, ≤2-day
time-boxed spike (Phases 0-2) whose only deliverable is a go/no-go answer to one question:**

> Does llama.cpp's mtmd pocket-tts implementation support **arbitrary reference-audio voice
> conditioning** (the equivalent of `TTSModel.get_state_for_audio_prompt()`), or only the
> baked-in voices its converted mmproj ships with?

This is the load-bearing unknown. Persona Forge's entire product surface — the voice library
(`vd_*` voices), "Activate for API", per-voice `.safetensors` state caching, prosody-modified
reference voices — is built on cloning from a user-supplied WAV. PR #26871's discussion says
**nothing** about voice cloning or reference-audio conditioning either way. If llama.cpp only
supports the packaged voices, the pivot is dead for Persona Forge's primary use case
regardless of how fast it is, and the correct outcome is to file the finding and stay on torch.

Secondary reasons not to commit early:

- **No Python bindings.** The feature lands as C++ in `mtmd` plus `tools/server`. There is no
  `pocket-tts`-capable Python API as of `b10369`; integration means running `llama-server` as
  a subprocess and talking HTTP, which is a real packaging/deployment change (see §4.4).
- **Hyperparameters are deliberately hardcoded in C++** (the author's stated design choice, to
  avoid single-use-case GGUF metadata churn). Persona Forge currently exposes
  `POCKET_TTS_TEMP`, `POCKET_TTS_LSD_DECODE_STEPS`, `POCKET_TTS_EOS_THRESHOLD`,
  `POCKET_TTS_NOISE_CLAMP`, `POCKET_TTS_QUANTIZE` as live, hot-reloadable runtime knobs in the
  Runtime Config page. Most of those have no counterpart on the llama.cpp side.
- **The feature is one day old.** `b10369` is the first release containing it.

The counter-argument for doing this eventually is strong and is about more than speed: a
`llama-server` backend is **backend-agnostic and cross-platform by construction** (CPU, CUDA,
Metal, Vulkan, SYCL, ROCm, and — notably — OpenVINO builds are all published per release).
That aligns precisely with the runtime-posture pivot away from a bespoke OpenVINO IR export
path toward portable CPU+GPU support including Apple Silicon and the Iris Xe iGPU goal. If the
cloning question comes back "yes", this becomes the most attractive runtime strategy the
project has.

Finally, note that the two new mmproj metadata keys upstream added —
`clip.gen.audio.frames_after_eos` and `clip.gen.audio.pad_short_text` — are *the same two
knobs* implicated in Persona Forge's end-of-sentence clipping bug (§6). Upstream independently
concluded these need to be per-language-pack tunable. That was corroborating evidence for the
diagnosis in §6, whose near-term fix has since **shipped independently of this plan**
([#145](https://github.com/nmorgowicz-org/persona-forge/pull/145), released in 1.0.2) — §6 is
kept below as the historical diagnosis and as a pointer to what a llama.cpp backend would need
to re-validate (§6.5).

---

## 2. Current state — the contract a replacement must satisfy

All line numbers are the 2026-08-12 snapshot. Re-grep before editing.

### 2.1 Dependency

`pyproject.toml:22` pins `pocket-tts==2.1.0` (PyPI), alongside `torch==2.12.1` /
`torchaudio==2.11.0` at `pyproject.toml:15-16`, with matching entries in
`[tool.uv] override-dependencies` (`pyproject.toml:64-67`). Installed at
`.venv/lib/python3.13/site-packages/pocket_tts/`. The package ships per-language YAML configs
(`pocket_tts/config/{english,french_24l,german,italian,portuguese,spanish,...}.yaml`) whose
weights are `hf://kyutai/pocket-tts/...` URLs — **gated**, hence the HF_TOKEN handling in
`pocket_tts_runtime.py:202-211`.

### 2.2 Backend selection

- `src/persona_forge/config.py:23-62` — `normalize_backend()` canonicalizes `pocket-tts` →
  `pocket_tts`; `TTS_BACKEND` default resolution.
- `src/persona_forge/model.py:53` — `TTS_BACKEND = normalize_backend(os.getenv("TTS_BACKEND") or "pytorch")`.
- `src/persona_forge/model.py:351-352` — valid set is exactly `("pytorch", "openvino", "pocket_tts")`.
  Any new backend must be added here, at `model.py:1053` (runtime reconfig validation) and at
  `model.py:1165` (revert path).
- `compose.yml:61` / `.env.example:20` — `TTS_BACKEND: ${TTS_BACKEND:-pocket_tts}`; pocket_tts
  is the **product default**.

### 2.3 Load path

`src/persona_forge/model.py:424-468` is the pocket_tts load branch. It reads env:

| Env var | Default | Consumed as |
|---|---|---|
| `POCKET_TTS_LANGUAGE` | `english` | `TTSModel.load_model(language=…)` |
| `POCKET_TTS_TEMP` | `1.2` | sampling temperature |
| `POCKET_TTS_LSD_DECODE_STEPS` | `5` | flow refinement steps per frame |
| `POCKET_TTS_EOS_THRESHOLD` | `-4.0` | logits EOS threshold |
| `POCKET_TTS_NOISE_CLAMP` | unset | trunc-normal bound on flow noise |
| `POCKET_TTS_FRAMES_AFTER_EOS` | `4` | **post-hoc trim only — see §2.7** |
| `POCKET_TTS_QUANTIZE` | `0` | int8 |

then calls `pocket_tts_runtime.load_pocket_tts_model(...)` (`pocket_tts_runtime.py:70-136`),
builds the default voice state from `profile.ref_audio`
(`build_default_voice_state`, `pocket_tts_runtime.py:143-217`), and runs a synchronous
throwaway generation (`warm_up_pocket_tts`, `pocket_tts_runtime.py:556-591`) whose docstring
records a real production failure mode: the *first* inference after every load carried a
one-time cost that manifested as a silent, tracebackless crash on the user's first request.
**Any replacement backend must keep an equivalent load-time warm-up or explicitly prove it is
unnecessary.**

Hot reload: `model.py:1041-1127` (`apply_runtime_updates`) and `model.py:1150-1170` (revert).
Pocket knobs trigger a full model reload only when the active backend is `pocket_tts`
(`model.py:1084`).

### 2.4 Voice state (the cloning contract)

`get_pocket_tts_voice_state()` (`pocket_tts_runtime.py:279-408`) resolves, in order:

1. empty `voice_id` → in-memory `pocket_tts_default_voice_state`, else rebuild from `REF_AUDIO`.
2. `pocket:`-prefix stripped; `vd_*` prefix means "voice library voice".
3. In-memory cache `pocket_tts_voice_state_cache[resolved_id]`.
4. Disk cache `voice_library/.state_cache/<id>.safetensors`, staleness-checked against the
   voice's `wav_path` and `meta.json` mtimes (`pocket_tts_runtime.py:350-371`).
5. Built-in preset or `hf://` path via `model.get_state_for_audio_prompt(resolved_id)`.
6. Voice-library lookup → `get_state_for_audio_prompt(wav_path)` → cache + `export_model_state`.

Plus `set_default_voice_state_from_library()` (`pocket_tts_runtime.py:248-272`) — the
"Activate for API" hot-swap, persisted to `voice_library/.active_default`, restored on boot —
and `invalidate_voice_state()` (`:411-419`), called from `app.py:553-564` whenever a voice's
reference audio changes or the voice is deleted.

The underlying primitives are `TTSModel.get_state_for_audio_prompt()`,
`export_model_state()` / `import_model_state()` (safetensors round-trip of a KV-cache-bearing
state dict). **These three are the hardest things to replicate over an HTTP boundary** and are
the crux of the Phase 2 gate.

### 2.5 Generation

Batch: `generate_pocket_tts()` (`pocket_tts_runtime.py:474-516`) → `model.generate_audio(voice_state, text)`
→ normalize to 1-D → `_trim_post_eos_tail()` → return `(tensor, 24000)`.

Streaming: `generate_pocket_tts_stream()` (`:519-553`) yields float32 numpy chunks from
`model.generate_audio_stream()`; **no tail trim** (documented at `:530-532`).

Inside the upstream package (`pocket_tts/models/tts_model.py`), the pipeline is:

- `generate_audio_stream()` (`:545-631`) — resolves `frames_after_eos`, then
  `split_into_best_sentences()` chunks the text by sentence under `MAX_TOKEN_PER_CHUNK`, and
  generates **each chunk as an independent short-text generation with its own EOS**.
- `prepare_text_prompt()` (`:913-942`) — strips newlines, optionally `;`→`,`, uppercases the
  first char, appends `.` if the text ends alphanumeric, and returns
  `frames_after_eos_guess = 3` for ≤4 words else `1`; the caller adds `+2` (`:622`).
- `_autoregressive_generation()` (`:744-779`) — the real EOS logic:
  `if is_eos and eos_step is None: eos_step = step`, then
  `if eos_step is not None and generation_step >= eos_step + frames_after_eos: break`
  (`:761-764`). Note the `break` happens **before** the latent is enqueued.
- `noise_clamp` is applied in `pocket_tts/models/flow_lm.py:134-137`: when not `None`, the flow
  noise is drawn with `torch.nn.init.trunc_normal_(noise, mean=0, std=std, a=-clamp, b=+clamp)`
  instead of a plain normal. It is a **per-step sampling-distribution bound inside the flow
  matching loop** — it does not touch the waveform and cannot "cut off" audio directly; it
  changes what the model generates, including when it decides to emit EOS.
- Package defaults (`pocket_tts/default_parameters.py:4-5`): `DEFAULT_NOISE_CLAMP = None`,
  `DEFAULT_EOS_THRESHOLD = -4.0`.
- Codec frame rate is **12.5 fps** at 24 kHz (`pocket_tts/config/english.yaml`, `mimi.frame_rate: 12.5`)
  → 1920 samples/frame.
- `model_recommended_frames_after_eos` is a config field (`pocket_tts/utils/config.py:118`,
  default `None`). **Only `french_24l.yaml` sets it (`: 8`).** `english.yaml` does not, so the
  English pack falls through to the 3-or-5 heuristic above.

### 2.6 App-level contract (what an adapter must provide)

For `TTS_BACKEND == "pocket_tts"`, `model.py:1664-1745` does:

```
voice_state = get_pocket_tts_voice_state(model, voice_id, voice_clone_prompt, REF_AUDIO)
audio_tensor, sr = generate_pocket_tts(model, voice_state, text)
wav = _trim_silence(audio_tensor.cpu().numpy().ravel(), sr)     # model.py:1183-1208
wav = _apply_generation_prosody_repair(wav, sr, text, job, ...)  # model.py:1555+
wav, sr = _apply_output_style(wav, sr, job, resolved_style_preset)  # model.py:1518-1533
```

and `model.py:2210-2264` (`_run_generate_pocket_tts_stream`) does the streaming variant:
per-chunk `_apply_telepresence_eq(chunk, 24000)` then float32→int16 LE PCM bytes.

Health/status surface: `model.py:845-857` (`pocket_tts` block in `/health`) and
`model.py:933-956` (Runtime Config live values, including
`pocket_tts_voice_cloning_available` / `_message`). `app.py:433-478` gates `builtin_voice`
and Activate-for-API on `TTS_BACKEND == "pocket_tts"` — a new backend id must be added to
those checks or those features silently disappear.

**The contract, minimally:**

| # | Requirement |
|---|---|
| C1 | Load/unload/reload with the same hot-swap semantics, idle-unload compatible (`model.py:183-184`) |
| C2 | Build a reusable voice handle from an arbitrary local WAV path |
| C3 | Persist/restore that handle to disk (or make rebuild cheap enough that the `.state_cache` is unnecessary) |
| C4 | Batch generate → 1-D float32 mono @ 24 kHz + sample rate |
| C5 | Incremental generate → float32 chunk iterator, low first-chunk latency |
| C6 | Deterministic-ish seeding (`_apply_optional_seed`, `model.py:1656`) |
| C7 | Load-time warm-up |
| C8 | Surface a cloning-available boolean + human-readable reason for `/health` and Runtime Config |

### 2.7 Two findings from reading the current code

**(a) `POCKET_TTS_FRAMES_AFTER_EOS` does not do what its name and docs say.** Persona Forge
never passes `frames_after_eos` to `TTSModel.generate_audio()` (`pocket_tts_runtime.py:500` —
the call is `model.generate_audio(voice_state, text)`, two positional args). The value is
stored in the module global `pocket_tts_frames_after_eos` (`:63`, set at `:127-133`) and used
**only** by the post-hoc waveform trimmer `_trim_post_eos_tail()` (`:514`). Generation itself
therefore always uses the upstream fallback chain
`model_recommended_frames_after_eos` → `None` → the 1-or-3 heuristic `+2`, i.e. **3 or 5
frames (240-400 ms) for English**. `docs/ENV_REFERENCE.md:149` describes it as a trim knob, so
the docs are honest, but the load-time plumbing at `model.py:444` and the "advanced knobs for
use during generation" comment at `pocket_tts_runtime.py:126` imply otherwise. This matters a
lot for §6.

**(b) `POCKET_TTS_NOISE_CLAMP` is wired.** `docs/ENV_REFERENCE.md:150` says "logged; wiring
TBD", but `model.py:432-433` reads it and `pocket_tts_runtime.py:117-118` forwards it into
`TTSModel.load_model()`, which forwards to `flow_lm`. The doc line is stale.

Both are documentation/behavior mismatches worth correcting independent of this plan.

---

## 3. Upstream capability summary (llama.cpp b10369 / PR #26871)

### 3.1 What landed

- **`mtmd` gains a pocket-tts pipeline.** The model is driven through llama.cpp's multimodal
  layer rather than a bespoke TTS path. Explicit architectural note from the author: this moves
  "away from discrete audio codes to passing continuous `embd`", framed as groundwork for
  future models such as chatterbox.
- **SEANet decoder upsampling rewrite** — grouped transposed conv emulated as
  matmul + col2im. **-80% CUDA / -50% CPU per-frame generation time**, correlation 0.999994,
  "sample for sample" match. A French long-text run landed within 2% of the reference
  implementation's wall time (22.96 s vs 23.44 s) — read that as: llama.cpp is now
  *at parity or better* with the reference, on that measurement, before the CPU speedup is
  fully accounted for. **Treat all of these as upstream's numbers, not ours** — Phase 1 exists
  to reproduce them on our hardware.
- **API surface:** `mtmd_gen_inp` / `mtmd_gen_out` gain `seed`, `temp`, `feats`, `is_eos`
  fields; new `mtmd_gen_inp_default()` helper; `mtmd_helper_gen_audio_step_gen()` takes
  `out_stop`; `mtmd_helper_gen_audio` manages stop conditions for continuous-embedding
  pipelines (which skip conventional token sampling entirely). Per-model generation defaults
  (top-k, top-p, temperature).
- **New mmproj GGUF metadata keys:**
  - `clip.gen.audio.frames_after_eos` — trailing frame padding after end-of-speech, per
    language pack (French pack = 8, default = 3). *This is exactly
    `model_recommended_frames_after_eos` from the reference config, and it confirms the
    English default really is 3.*
  - `clip.gen.audio.pad_short_text` — space-padding for short prompts (English pack), i.e.
    `pad_with_spaces_for_short_inputs`.
  - `clip.gen.audio.model_variant` — added in a later commit in the same PR.
  - **Existing mmproj files must be reconverted** to carry these keys.
- **Conversion tooling:** `conversion/pockettts.py` in the llama.cpp tree, with per-language-pack
  settings (temperature, frame padding, text padding). Semicolon→comma punctuation mapping is
  applied universally even though the reference only does it for three packs — a small,
  known behavioral divergence from `pocket_tts`'s `remove_semicolons`.
- Also in the PR: `flow_temp` handling, chunking support, dead hparam cleanup, security fixes,
  lint, docs.

### 3.2 How you would call it

Via `tools/server` → the standard `llama-server` HTTP API. Release `b10369` publishes prebuilt
`llama-server` binaries for macOS, Linux (CPU / Vulkan / ROCm / **OpenVINO** / SYCL), Android,
and Windows (CPU / CUDA / Vulkan / OpenVINO / SYCL / ROCm).

**There is no Python package or official Python binding exposing this as of `b10369`.**
`llama-cpp-python` tracks the `llama.h` C API and has historically lagged `mtmd` features by
weeks-to-months; the new symbols are `mtmd_*`, not `llama_*`. Verify at spike time with:

```bash
pip download llama-cpp-python==<latest> --no-deps -d /tmp/lcp && \
  python - <<'EOF'
import zipfile,glob,re
for f in glob.glob('/tmp/lcp/*'):
    print(f)
EOF
# and grep the vendored headers for mtmd_helper_gen_audio / mtmd_gen_inp_default
```

Practical integration shape for Persona Forge: **spawn and supervise a `llama-server`
subprocess, talk to it over localhost HTTP.** This is a known-shape problem for this repo —
the post-merge-initiatives work already froze a "spawn the Flask dev server as a subprocess"
decision, so there is prior art for process supervision here.

### 3.3 Open questions the spike must answer

| # | Question | Why it matters | How to answer |
|---|---|---|---|
| Q1 | **Does it support arbitrary reference-audio voice conditioning?** | The whole voice library (C2). PR thread is silent. | Read `tools/mtmd/` + `conversion/pockettts.py` for a Mimi *encoder* path (cloning needs encode, not just decode); check whether `mtmd_gen_inp` accepts an audio/`feats` input; try passing a WAV. |
| Q2 | Is the cloning-capable checkpoint (`kyutai/pocket-tts`, gated) convertible, or only the ungated `pocket-tts-without-voice-cloning` weights? | Gating already bites us (`pocket_tts_runtime.py:202-211`) and prior work explored the ungated route (`docs/plans/20260713-pocket_tts_ungated_onnx.md`). | Run `conversion/pockettts.py` against both. |
| Q3 | Can a computed voice/prompt state be **cached and reused** across requests? | C3. Rebuilding a voice state per request would erase our `.state_cache` win. | Check for slot/prompt-cache reuse in `tools/server` for the mtmd audio path. |
| Q4 | What is the actual server endpoint + request/response schema for audio generation? | Whole adapter design. | `llama-server --help`, then `/props` and the server README in `b10369`. |
| Q5 | Streaming? Chunked/incremental audio out? | C5 and the Hermes `/v1/audio/speech` streaming path. | Inspect the server route; test with `curl -N`. |
| Q6 | Output format, sample rate, channel layout, float vs int16. | C4 and every downstream DSP assumption. | Compare a generated WAV's header against our 24 kHz mono float. |
| Q7 | Which of `temp` / `lsd_decode_steps` / `eos_threshold` / `noise_clamp` / `quantize` remain settable? | Runtime Config page has UI for all of them. | Cross-reference hardcoded C++ constants vs. `mtmd_gen_inp` fields. |
| Q8 | Seeding — is `mtmd_gen_inp.seed` honored end-to-end? | C6 / reproducibility. | Two runs, same seed, byte-compare. |
| Q9 | Multi-sentence chunking behavior vs. `split_into_best_sentences`. | Affects §6's clipping symptom and prosody at sentence joins. | Long-text A/B. |
| Q10 | Does the semicolon→comma universal mapping change English output vs. our current behavior? | Small but real text-normalization divergence. | Prompt containing `;`, A/B. |

---

## 4. Risk assessment

### 4.1 Bleeding-edge dependency risk — **high**

`b10369` is the *first* release containing this. The `mtmd` API is explicitly being reshaped
(`mtmd_gen_inp`/`mtmd_gen_out` gained four fields in this very PR) and the author states the
pocket-tts work is scaffolding for a different model family. Expect churn. Mitigations: pin an
exact llama.cpp tag; vendor the prebuilt binary rather than building from a moving `master`;
never make it the default until it has survived ≥2 upstream releases.

### 4.2 Hyperparameter control loss — **medium-high**

The author deliberately hardcoded most hyperparameters in C++ "to avoid single-use-case
model-specific GGUF metadata". Persona Forge exposes five pocket knobs as **live,
hot-reloadable Runtime Config fields** (`model.py:933-956`, `frontend/src/pages/RuntimeConfigPage.tsx`).
If `lsd_decode_steps`, `eos_threshold`, `noise_clamp`, and `quantize` have no llama.cpp
counterpart, either the UI must gray them out per-backend (there is precedent — see the
"Unused by the active pocket_tts backend" strings at `model.py:1000-1005`) or we accept a
capability regression. `frames_after_eos` and `pad_short_text` move from Python runtime args to
**mmproj build-time metadata**, meaning tuning them requires *reconverting the model*, not
restarting the app. That is a genuine downgrade in iteration speed for exactly the parameter
§6 needs to iterate on.

### 4.3 DSP / post-processing coupling — **low-medium**

`audio_style.py`'s `STYLE_PIPELINES` (`:356-441`) operate on `(np.ndarray, sr)` — `telepresence_eq`
(`_apply_telepresence_eq`, `:310`), `normalize_lufs` (`:47`), `limit_peak`, plus pause shaping and
time stretch. Nothing in that chain is torch- or pocket-specific; it already runs unchanged for
the pytorch and openvino backends. **So the chain itself is safe** provided the adapter honors
C4 (1-D float32 mono @ 24 kHz numpy-convertible). The real exposures are:

- `_trim_silence()` (`model.py:1183-1208`) and `_trim_post_eos_tail()` are tuned against the
  torch model's tail behavior. Different EOS padding from llama.cpp means these thresholds need
  re-validation, not blind reuse.
- The streaming path applies `_apply_telepresence_eq` **per chunk** (`model.py:2256`). If
  llama.cpp's chunk boundaries differ (different chunk sizes, or chunking at sentence rather
  than frame granularity), the per-chunk IIR filtering will produce different edge artifacts.
  Phase 6 must A/B this specifically.
- `_apply_generation_prosody_repair` uses the source text to locate boundaries; if llama.cpp
  normalizes text differently (Q10), boundary detection drifts.

### 4.4 Packaging and deployment — **medium-high**

Today: one Python process, model in-process, `idle_unload` frees memory by dropping references
(`model.py:183-184`). Under llama.cpp: a **second native process** to build/ship, launch,
health-check, restart on crash, port-allocate, and shut down cleanly — inside a container that
currently only runs gunicorn. Concretely this means: a new Dockerfile stage or a pinned binary
download, a supervisor in `pocket_tts`-equivalent load path, a readiness probe before
`warm_up`, port config (collision-safe), and making `idle_unload` mean "stop the subprocess".
Offsetting benefit: it removes `torch` + `torchaudio` (~2 GB of wheels, `pyproject.toml:15-16`)
from the runtime image *if and only if* nothing else needs them — but OmniVoice and the
optional qwen-tts extra do, so the saving is conditional and probably not realized near-term.

### 4.5 Platform strategy — **this is the strongest argument in favor**

Per the runtime-posture pivot, the project is moving away from OpenVINO-IR-specific tooling
toward backend-agnostic, cross-platform (including Apple Silicon) execution; the iGPU goal
wants accent design running on Intel Iris Xe without the OpenVINO export path. A single
`llama-server` binary that ships in CPU / Metal / Vulkan / SYCL / **OpenVINO** / CUDA / ROCm
flavors from the same release collapses that whole matrix into "pick a build". It would let
Persona Forge drop its bespoke IR export pipeline (`src/export/`, `scripts/export.py`) as the
*only* GPU story, and it would make the Iris Xe target reachable via the SYCL or Vulkan build
without writing any of it ourselves. **If Phase 2 comes back positive, this — not the 50% CPU
speedup — is the reason to do it.**

### 4.6 Quality/parity risk — **low-medium**

Correlation 0.999994 is reassuring but it is *upstream's* measurement on *their* prompts with
*their* voices. Our workload is cloned voices with modified prosody references, which is the
part of the distribution most likely to expose a divergence. Phase 1/2 must A/B on our own
reference WAVs, not a generic prompt.

### 4.7 Risk of *not* doing it — **low, and reversible**

Staying on `pocket-tts==2.1.0` costs nothing today. The pinned upstream keeps working. This
plan can be re-opened at any later llama.cpp release with strictly better information. There is
no forcing function.

---

## 5. Phased plan

Rules: Phases 0-2 touch **no** files under `src/`. Phase 2 is a hard gate requiring Nick.
Each phase gets its own commit and updates its own docs (standing rule). Re-grep every cited
line number at the start of each phase.

### Phase 0 — Baseline on the current backend (½ day, no code changes)

Goal: numbers to compare against. Without this, Phase 1's result is uninterpretable.

1. Assemble a fixed prompt set at `docs/screenshots/artifacts/llamacpp-spike/prompts.json`
   (artifacts dir is disposable/gitignored until a curation pass):
   - `short`: ≤4 words (exercises the `frames_after_eos_guess = 3` branch).
   - `sentence`: one ~15-word sentence.
   - `paragraph`: 4+ sentences, mixed punctuation, ≥1 semicolon (Q10).
   - `soft_ending`: a sentence that trails off quietly — **this is the §6 repro case**.
2. Pick 3 voices: the default `REF_AUDIO`, one plain `vd_*` library voice, and one
   prosody-modified `vd_*` voice (the one Nick reproduced the clipping bug with).
3. With `TTS_BACKEND=pocket_tts`, generate all 12 combinations. Record per run: wall time,
   audio duration, RTF (already logged — `model.py:1734`), output WAV, host CPU model, thread
   count. Use a fixed seed.
4. Also capture the **untrimmed** waveform for each: temporarily run with
   `POCKET_TTS_FRAMES_AFTER_EOS` high (e.g. `40`) and `SILENCE_TRIM=0` to get raw model output
   for the §6 analysis. This is env-only, no code change.
5. Write `docs/screenshots/artifacts/llamacpp-spike/baseline.md`.

Gate: baseline table exists with RTF per prompt×voice, plus raw and trimmed WAVs.

### Phase 1 — Upstream capability spike, part 1: does it run? (≤1 day, time-boxed)

Work entirely in a scratch dir outside the repo (e.g. `/tmp/llamacpp-spike/`).

1. Fetch `llama-server` for the host from the `b10369` release assets (or build the tag from
   source if a needed backend build isn't published). Record the exact asset name/sha.
2. Read, in the `b10369` tree: `conversion/pockettts.py`, `tools/mtmd/` (grep
   `mtmd_helper_gen_audio`, `mtmd_gen_inp_default`, `frames_after_eos`, `pad_short_text`), and
   the `tools/server` README/routes for the audio-generation endpoint. **Answer Q4, Q5, Q6, Q7,
   Q9 from source before touching a model.**
3. Obtain a converted pocket-tts GGUF + mmproj. Prefer an upstream-published conversion if one
   exists; otherwise run `conversion/pockettts.py` against the local
   `pocket_tts` English weights (they are already cached under HF cache from our container
   pulls). Answer Q2 while doing this.
4. Start `llama-server`, hit it with the Phase 0 `sentence` prompt using a **built-in** voice.
   Save the WAV.
5. Measure RTF on the same host as Phase 0. Compare. Record whether the -50% CPU claim
   reproduces for us.
6. Spot-check Q8 (seed determinism) and Q10 (semicolon handling).

Gate: an audible, correct WAV from `llama-server` + an RTF number comparable to Phase 0.
**If this cannot be reached inside the time box, stop and write it up as a no-go-for-now.**

### Phase 2 — Upstream capability spike, part 2: voice cloning + go/no-go (≤1 day, time-boxed)

This is the decision phase. Everything else is downstream of it.

1. **Q1, definitively.** Determine whether the mtmd pocket-tts pipeline can condition on an
   arbitrary user WAV. Specifically check whether the Mimi **encoder** (not just the SEANet
   decoder) is present in the converted mmproj and reachable from the server — cloning requires
   encoding the reference audio into the model state, which is a different code path from the
   decoder work PR #26871 optimized. If the conversion only carries the decoder + text model,
   the answer is no.
2. If yes: clone the same prosody-modified `vd_*` voice used in Phase 0 and A/B the output
   against the torch baseline — speaker similarity by ear, plus a spectral/correlation check.
3. Answer Q3 (can the resulting state be cached/reused across requests, or is it recomputed
   per call?) and measure the per-request cost if it is recomputed.
4. Re-run the `soft_ending` prompt and check whether the §6 clipping reproduces on llama.cpp
   (with `clip.gen.audio.frames_after_eos` at the default 3, and again with a reconverted
   mmproj at 8).
5. Append a **Findings** section to this document: answers to Q1-Q10, the RTF comparison table,
   subjective quality notes, and a recommendation of one of:
   - **A. Go** — proceed to Phase 3.
   - **B. Go, narrow** — adopt only for the built-in-voice / `/v1/audio/speech` streaming path,
     keep torch for the voice library. (Only viable if Q1 is no but the speed win is large.)
   - **C. No-go, revisit at release N** — file the blockers, close the branch.

**Gate: Nick's explicit decision.** Nothing below this line runs without it.

---

*Phases 3-8 are contingent on a Phase 2 "Go". They are specified at plan-level detail; whoever
executes Phase 3 should re-derive specifics from the Phase 2 findings, which will be more
current than anything written here.*

### Phase 3 — Model acquisition and conversion pipeline

1. `scripts/convert_pocket_tts_gguf.sh` — pinned llama.cpp tag, pinned source weights, explicit
   `frames_after_eos` / `pad_short_text` / `model_variant` values per language pack, emits
   GGUF + mmproj with recorded sha256s.
2. Decide artifact hosting: ship in the image (size?), download at first boot (gating? see
   `docs/plans/20260713-pocket_tts_ungated_onnx.md` §8.1 for the existing artifact-resolution-order
   thinking — reuse it, do not reinvent), or mount from the host data dir.
3. Document the reconversion procedure for changing `frames_after_eos`, since it is no longer a
   runtime knob (§4.2).
4. Integrity: sha256 verification + a clear failure mode when the artifact is missing/corrupt,
   matching the existing pocket artifact conventions.

Gate: a second machine can reproduce byte-identical artifacts from the script.

### Phase 4 — `llama_cpp_pocket_tts_runtime.py` adapter

New module `src/persona_forge/llama_cpp_pocket_tts_runtime.py`, **mirroring
`pocket_tts_runtime.py`'s public API function-for-function** so it is swappable behind the
existing dispatch:

| Existing | New |
|---|---|
| `load_pocket_tts_model()` | `load_llama_pocket_tts()` — start + health-check the server |
| `build_default_voice_state()` | same name/signature; returns an opaque voice handle |
| `get_pocket_tts_voice_state()` | same name/signature/resolution order incl. both cache tiers |
| `set_default_voice_state_from_library()` | same (`.active_default` semantics preserved) |
| `invalidate_voice_state()` | same |
| `generate_pocket_tts()` | same signature → `(1-D float32 tensor, 24000)` |
| `generate_pocket_tts_stream()` | same → float32 numpy chunk generator |
| `warm_up_pocket_tts()` | same (C7 — keep it, see `pocket_tts_runtime.py:556-591`) |
| `unload_pocket_tts()` | same → terminate + reap the subprocess |
| `pocket_tts_cloning_available` / `_status_message` | same module globals (C8) |

Plus, new and internal-only:

- `_LlamaServerProcess` — spawn (bind `127.0.0.1`, ephemeral or configured port), readiness
  poll with timeout, log passthrough with a `[llama_pocket_tts]` prefix matching the existing
  logging style, crash detection, idempotent terminate with SIGTERM→SIGKILL escalation, and an
  `atexit` reaper so tests and dev restarts don't leak processes.
- `_LlamaTtsClient` — a thin `requests`/`httpx` wrapper over the endpoint discovered in Phase 1
  Q4. **All HTTP lives here and nowhere else** — this is the single seam Phase 7's fakes target.

Constraints: keep the module importable without `torch` (mirroring the existing lazy-import
discipline at `pocket_tts_runtime.py:44-46`), and do not import `pocket_tts`.

Gate: unit tests (Phase 7 tier-1) pass against a fake HTTP server; module imports cleanly in an
env with neither `torch` nor `pocket_tts` installed.

### Phase 5 — Backend dispatch and lifecycle

New backend id: **`llama_pocket_tts`** (with a `llama-pocket-tts` hyphen alias in
`config.py:normalize_backend`). Do **not** overload the existing `pocket_tts` id — a distinct id
is what makes the fallback in Phase 8 free.

Touch points (all currently hardcode the three-backend tuple):

- `src/persona_forge/config.py:23-62` — alias normalization.
- `src/persona_forge/model.py:351-352` — valid-backend set.
- `src/persona_forge/model.py:424-468` — load branch; add an `elif` mirroring the pocket branch,
  reading `LLAMA_POCKET_TTS_*` env (`_BINARY`, `_MODEL`, `_MMPROJ`, `_PORT`, `_THREADS`,
  `_NGL`, `_TEMP`).
- `src/persona_forge/model.py:1664-1745` — generation branch; condition should become
  `if TTS_BACKEND in POCKET_BACKENDS:` with the runtime module selected by a small resolver,
  since the body is otherwise identical.
- `src/persona_forge/model.py:2210-2264` — streaming branch, same treatment.
- `src/persona_forge/model.py:845-857`, `:933-956` — `/health` + Runtime Config blocks.
- `src/persona_forge/model.py:1041-1127`, `:1150-1170` — reconfig/revert validation and the
  reload-trigger key set.
- `src/persona_forge/model.py:183-184` — idle unload.
- `src/persona_forge/app.py:433-478`, `:553-564`, `:731-766` — `builtin_voice` gating,
  invalidation hooks, Activate-for-API gating. **These currently compare `== "pocket_tts"`
  literally; every one must become a set membership test or the voice features vanish on the
  new backend.**
- `frontend/src/pages/RuntimeConfigPage.tsx` + `frontend/src/lib/api.ts` — new backend option,
  and per-backend enable/disable for knobs that don't exist on llama.cpp (§4.2).
- `Dockerfile` — binary acquisition; `compose.yml` / `.env.example` — new env vars, default
  unchanged (`pocket_tts`).

Gate: `TTS_BACKEND=llama_pocket_tts` boots, `/health` reports honestly, Speak tab produces
audio, and `TTS_BACKEND=pocket_tts` still behaves exactly as before (regression suite green).

### Phase 6 — Post-processing chain re-validation

1. Confirm the adapter's batch output satisfies C4 exactly (dtype, shape, range, sr) — assert it
   in the adapter, don't assume.
2. Re-tune or confirm `_trim_silence` (`model.py:1183-1208`) and the tail-trim behavior against
   llama.cpp's `frames_after_eos=3` output. Upstream's default padding differs from the torch
   fallback path; the thresholds are empirical and must be re-derived, not inherited.
3. A/B every `STYLE_PIPELINES` preset (`audio_style.py:356-441`) on both backends with the same
   input text+voice; compare LUFS, true peak, and spectra. Any preset that lands >1 LU or >1 dB
   off between backends is a finding.
4. Streaming: verify `_apply_telepresence_eq` per-chunk filtering doesn't introduce audible
   boundary artifacts at llama.cpp's chunk sizes (§4.3). If it does, buffer to a fixed chunk
   size in the adapter rather than changing the DSP.
5. Re-run `_apply_generation_prosody_repair` on the paragraph prompt; check boundary detection
   still aligns given any text-normalization divergence (Q10).

Gate: an artifacts-dir report with per-preset measurements on both backends.

### Phase 7 — Test coverage

**Tier 1 (`tests/tier1_unit/test_llama_cpp_pocket_tts_runtime.py`)** — mirror the structure of
`tests/tier1_unit/test_pocket_tts_runtime.py`, which already establishes the pattern of
injecting a fake backend module into `sys.modules` before import (see its module docstring and
the `pocket_tts_runtime` fixture at `:59-77`). Here the fake is an HTTP layer, not a module:
patch `_LlamaTtsClient`'s transport, or stand up a `pytest`-scoped `http.server` fixture.
Cover: process spawn args, readiness timeout, crash surfacing, voice-state resolution order
(all six branches from §2.4), both cache tiers + staleness, `invalidate_voice_state`,
`generate_*` shape/dtype/sr contract, streaming chunk iteration, warm-up, idempotent unload,
and the cloning-available flags.

**Tier 1, dispatch (`tests/tier1_unit/test_run_generate.py`)** — extend the existing
`test_pocket_primary_runtime_applies_default_and_honors_bypass` pattern (`:289-305`, which
monkeypatches a fake runtime module) with an equivalent for the new backend id, proving the
shared generation branch routes correctly and post-processing still applies.

**Tier 1, config** — extend `test_config.py` / `test_runtime_store.py` for the new backend id,
alias normalization, and reload-trigger key set.

**Tier 2 (`tests/tier2_backend/`)** — `/health` and Runtime Config payload shape with the new
backend selected (fake runtime, no real server).

**Tier 3 / integration** — a new marker (`requires_llama_server`, registered in `pyproject.toml`
alongside the existing `requires_torch` / `requires_model_weights` / `requires_openvino_ir`
markers and excluded from the default CI selector) covering a real end-to-end synthesis against
a real `llama-server`. Never runs in CI; documented as a manual pre-release gate.

Gate: default CI selector green; new markers documented in the test README.

### Phase 8 — Rollout, fallback, docs

1. **No hard cutover.** `TTS_BACKEND` default stays `pocket_tts` (`compose.yml:61`,
   `.env.example:20`). `llama_pocket_tts` is opt-in.
2. Ship behind opt-in for at least one release; dogfood on dockermisc1; validate on the Plexxie
   hardware host for the iGPU/SYCL angle (that host runs without Docker — keep Nick informed of
   actions taken there).
3. Fallback policy: if the subprocess fails to become ready at load, **fail loudly with a clear
   message** rather than silently falling back to torch — silent backend substitution would make
   the RTF and quality reports meaningless. Document the manual fallback as "set
   `TTS_BACKEND=pocket_tts` and restart".
4. Docs, per the docs-per-phase standing rule: `docs/ENV_REFERENCE.md` (new vars; also fix the
   two stale lines noted in §2.7 — `:149` and `:150`),
   `docs/architecture/pocket_tts_integration.md` (add a backend-comparison section),
   `README.md` backend table, `CHANGELOG` via release-please.
5. Promotion to default requires: ≥2 upstream llama.cpp releases of stability, cloning parity
   confirmed in production use, and Phase 6's DSP report showing no regressions.
6. On completion, rename and move this doc to `docs/dev/resolved/` per the resolved-plans
   convention.

---

## 6. Known issue: end-of-sentence clipping (independent of this pivot)

### 6.1 Symptom

User-reported, 2026-08-12: on the **Speak** tab, using a **prosody-modified reference voice**
through `TTS_BACKEND=pocket_tts`, the end of the **final sentence** is sometimes clipped. Not
every generation; correlated with modified-prosody reference voices.

### 6.2 Hypothesis 1 (primary, high confidence): `_trim_post_eos_tail`'s global relative energy threshold

`pocket_tts_runtime.py:426-471`. The trimmer:

```python
frame_samples = max(1, sr // 12)          # 2000 samples
frames  = x.unfold(0, frame_samples, frame_samples)
energies = (frames * frames).sum(dim=1).sqrt()
peak = energies.max().item()
thresh = peak * 0.03                       # 3% of the LOUDEST frame in the WHOLE clip
speech_mask = (energies >= thresh).nonzero(as_tuple=True)[0]
last_speech_frame = int(speech_mask[-1])
limit_sample = min(len(x), (last_speech_frame + frames_after_eos + 1) * frame_samples)
return x[:limit_sample]
```

`thresh` is **3% of the global peak frame energy**, i.e. about **-30 dB relative to the loudest
frame in the entire utterance**. Sentence-final decay — an unvoiced fricative release, a
breathy trail-off, a soft final syllable — routinely sits below -30 dBFS-relative. When it
does, `last_speech_frame` lands *before* the true end of speech, and the clip is cut at
`last_speech + 4` frames ≈ 333 ms later. If the real remaining speech is longer than that, or
if the sub-threshold region is longer than 4 frames, **audible speech is removed**.

This explains every facet of the report:

- **Why the final sentence.** The threshold is computed over the whole waveform. In multi-sentence
  text, one loud sentence raises `peak` for everyone; a quieter closing sentence can fall
  entirely under 3% of it. The trimmer then cuts back to the end of the *loud* sentence.
- **Why modified-prosody reference voices.** Prosody modification (pace/pitch/dynamics changes
  applied to the reference WAV) widens the cloned voice's dynamic range and softens
  utterance-final energy. That is precisely the condition that pushes final frames under a
  global relative gate.
- **Why intermittent.** It depends on the specific text's loudness contour, so it fires on some
  prompts and not others with the same voice.
- **Why "clipped" and not "cut short mid-word".** The cut lands 4 frames past the last
  *above-threshold* frame, so it typically removes a final consonant/release rather than a
  whole word.

Two supporting defects in the same function:

- **Frame size is wrong by 4%.** The code uses `sr // 12 = 2000` samples, but the Mimi codec
  runs at **12.5 fps** (`pocket_tts/config/english.yaml`, `mimi.frame_rate: 12.5`) → 1920
  samples. So "4 frames" of headroom is actually 8000 samples = 333 ms rather than 7680 = 320 ms,
  and the "frames" here don't align with codec frames at all. Cosmetic on its own; it means the
  knob's units are a fiction.
- **`frames_after_eos` never reaches the model.** Per §2.7(a), `POCKET_TTS_FRAMES_AFTER_EOS`
  only affects this trimmer. Generation always uses upstream's fallback: English has no
  `model_recommended_frames_after_eos`, so `prepare_text_prompt()` returns 1 (>4 words) or 3
  (≤4 words), `+2` → **3 or 5 frames of post-EOS generation** (~240-400 ms at 12.5 fps). So the
  model itself is *also* generating a fairly short tail — and the trimmer then cuts into it.
  Corroboration: upstream llama.cpp independently chose **8** for the French pack and made this
  a per-language mmproj key, and `french_24l.yaml` in our own installed package sets
  `model_recommended_frames_after_eos: 8`. 3 is thin.

Also note the stacking: after `_trim_post_eos_tail`, `model.py:1722` runs `_trim_silence`
(`model.py:1183-1208`) which applies a *second* relative gate (1% of sample peak, 30 ms pad).
That one is far gentler and is unlikely to be the primary cause, but it compounds.

### 6.3 Hypothesis 2 (secondary, lower confidence): premature EOS from `noise_clamp` / `eos_threshold`

`noise_clamp` does **not** touch the waveform. It bounds the flow-matching noise draw
(`pocket_tts/models/flow_lm.py:134-137`, `trunc_normal_` with `a=-clamp, b=+clamp`). A tight
clamp reduces per-step stochasticity, which can bias the model toward the mode — plausibly
including earlier EOS emission. Since `_autoregressive_generation` (`tts_model.py:761-764`)
hard-breaks at `eos_step + frames_after_eos`, an early EOS with only 3 padding frames truncates
the utterance **at the codec level** — no amount of trimmer tuning recovers it. Same mechanism
for a too-permissive `POCKET_TTS_EOS_THRESHOLD` (default `-4.0`).

**Discriminating test:** set `SILENCE_TRIM=0` and `POCKET_TTS_FRAMES_AFTER_EOS=40` (both
env-only, no code change) and regenerate the failing prompt.
- If the full sentence is present in the raw output → **Hypothesis 1**; the fix is in the trimmer.
- If it is still clipped → **Hypothesis 2**; the fix is in generation (raise EOS padding at the
  model call, and/or relax `noise_clamp` / `eos_threshold`).

Phase 0.4 above already captures exactly these artifacts, so run Phase 0 first.

### 6.4 Near-term fix — **shipped** in [#145](https://github.com/nmorgowicz-org/persona-forge/pull/145) (2026-08-12, released in 1.0.2)

This did not wait on the llama.cpp decision. Discriminating-test result: Hypothesis 1
confirmed. The fix landed in `pocket_tts_runtime.py` as items 1-4 and 6 below (item 5 —
forwarding `frames_after_eos` into generation itself — was deliberately deferred; see the note
at the end of this list):

1. **Make the threshold absolute-ish and much lower.** Replace `peak * 0.03` (-30 dB) with the
   max of an absolute floor (e.g. `1e-3` RMS ≈ -60 dBFS) and a far gentler relative term
   (e.g. `peak * 0.002`, -54 dB). Speech decay lives well above -60 dBFS; room tone and codec
   noise live below it.
2. **Compute the threshold over a trailing window, not the whole clip**, so a loud early
   sentence cannot gate a quiet final one. E.g. use the peak of the last N seconds, or use the
   *median* of above-floor frames rather than the max.
3. **Fix the frame size** to `round(sr / 12.5)` = 1920 so the knob's stated units are true, and
   correct `pocket_tts_runtime.py:61`'s "1 frame ≈ 1/12 s" comment.
4. **Raise the default** `frames_after_eos` from 4 to 8, matching upstream's French pack and
   llama.cpp's per-pack tuning precedent. Cheap: 8 frames of tail is ~640 ms of *silence* at
   worst, and `_trim_silence` cleans that up downstream anyway.
5. **Deferred: actually pass it to the model.** Adding a `frames_after_eos` argument to
   `generate_pocket_tts()` and forwarding it to `model.generate_audio(voice_state, text,
   frames_after_eos=...)` (the parameter exists — `tts_model.py:482`) is the only fix that
   would address Hypothesis 2's codec-level truncation, and would make
   `POCKET_TTS_FRAMES_AFTER_EOS` mean what its name says. Not shipped in #145 — it changes
   generation behavior for every user and needs its own A/B. Still open; a candidate for a
   follow-up if the trimmer-side fix alone turns out insufficient in the field.
6. Update `docs/ENV_REFERENCE.md:149` (semantics) and `:150` (`POCKET_TTS_NOISE_CLAMP` is
   wired, not "TBD" — §2.7(b)). **Done.**

Regression coverage: `tests/tier1_unit/test_pocket_tts_runtime.py::TestTrimPostEosTail` — a
synthetic two-burst waveform (loud burst, silence, quiet burst) asserts the quiet burst
survives; a second test asserts true trailing silence is still trimmed. **Done.**

### 6.5 Relationship to the pivot

- §6.4 has shipped regardless of Phase 2's outcome, as recommended: the torch backend remains
  the default (and will remain the fallback for at least a full release cycle if Phase 2 is a
  go — Phase 8.1), so the trimmer-side fix benefits users today independent of this plan.
- On llama.cpp, the equivalent knob is the mmproj key `clip.gen.audio.frames_after_eos`
  (default 3, French pack 8) plus `clip.gen.audio.pad_short_text`. If Phase 2 is a go, the bug
  must be **re-validated** there, not assumed fixed — and note that tuning it requires
  *reconverting the mmproj* rather than setting an env var (§4.2). Persona Forge's own
  `_trim_post_eos_tail` / `_trim_silence` post-processing runs regardless of backend, so #145's
  trimmer-side fix (items 1-3) benefits both backends.
- Phase 0.4's baseline-capture step should now compare against the **post-#145** trimmer
  behavior, not the original buggy one — re-derive the `soft_ending` repro case against current
  `main` before assuming it still reproduces at the same severity.

---

## 7. References

- llama.cpp release `b10369` — https://github.com/ggml-org/llama.cpp/releases/tag/b10369 (commit `6e62ba5`)
- PR `ggml-org/llama.cpp#26871` "mtmd: support pocket-tts" — https://github.com/ggml-org/llama.cpp/pull/26871
- `src/persona_forge/pocket_tts_runtime.py` — current adapter
- `src/persona_forge/model.py:424-468, 845-857, 933-956, 1041-1170, 1183-1208, 1518-1533, 1664-1745, 2210-2264`
- `src/persona_forge/audio_style.py:310-441` — `STYLE_PIPELINES`
- `src/persona_forge/app.py:433-478, 553-564, 731-766`
- `tests/tier1_unit/test_pocket_tts_runtime.py`, `tests/tier1_unit/test_run_generate.py:289-305`
- `docs/architecture/pocket_tts_integration.md`, `docs/ENV_REFERENCE.md:146-151`
- `docs/plans/20260713-pocket_tts_ungated_onnx.md` — prior artifact-resolution + parity-validation
  methodology; reuse rather than reinvent
- `docs/plans/20260811-hermes_tts_streaming.md` — the streaming contract the adapter must keep
- Upstream package under audit: `.venv/lib/python3.13/site-packages/pocket_tts/` (`pocket-tts==2.1.0`)

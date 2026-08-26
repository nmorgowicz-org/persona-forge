# Boundary-Aware Prosody Alignment and Repair

Designed: 2026-07-12
Implemented and validated: 2026-07-13
Status: Complete
Supersedes: v2.0 "Prosody Boundary Awareness & Forced Alignment" draft (local-model)
Owner: Nick M

---

## 1. Executive Summary

The previous prosody system could not handle **blended speech** — audio where sentences run
together with no audible/visible gap (e.g. *"She's right, no worries. We'll sort it out
later."* spoken as one breath). Every old prosody path depended on finding silence gaps to
use as "handles"; when there was no gap, punctuation-driven pauses were silently dropped.

The implemented solution is **not** "VAD vs forced alignment" as a global choice. It is a
**tiered pipeline**:

1. **Triage** — a cheap, transcript-aware waveform check decides whether a clip *needs* the
   heavy pass. Clean, well-gapped audio keeps using today's fast energy-based path.
2. **Align (only when needed)** — for blended clips, run **forced alignment** against the
   transcript we already store to get frame-accurate word/sentence boundaries.
3. **Alignment-directed pause edits** — map transcript punctuation to aligned words, choose
   safe cut points, and emit the final ordered silence/fade edits directly. Precise mode does
   not feed manufactured gaps back through proportional matching, so it cannot reintroduce
   the drift it is designed to remove.

Because we **already store the transcript** (`meta.sample_text`, the "REFERENCE TEXT" box in
the Voice Library), we do **not** need ASR/Whisper. We need *pure forced alignment given
audio + known text*, which is lighter, faster, and more accurate than WhisperX.

### Implemented decisions (see §3)
- **Aligner:** ONNX MMS CTC forced alignment with project-owned normalization and Viterbi,
  run via **`onnxruntime`**. The upstream `ctc-forced-aligner` package informed the design
  but is not a serving dependency because its pinned dependency chain is incompatible with
  Python 3.13.
  The portable **CPU execution provider** is the baseline — it runs on any CPU (Intel/AMD
  x86-64, ARM64, **Apple Silicon**). OpenVINO EP (Intel) and CoreML EP (Apple) are *optional*
  accelerators, never load-bearing. No PyTorch in the serving path. Default MMS model's
  CC-BY-NC license is acceptable (personal/research use).
- **Runtime posture:** backend-agnostic. Earlier OpenVINO-specific assumptions are
  explicitly relaxed — nothing in this plan depends on OpenVINO being present.
- **UX:** Auto-triage + auto-fix, with a manual **Processing mode: Natural / Precise**
  override and a badge indicating when alignment was used.
- **Surfaces:** Voice Library (cloning prep), Stitch Studio, OmniVoice segments.
- **Generation / OpenAI output:** complete-file routes reuse the same engine behind an
  explicit opt-in and strict latency budget; streaming rejects repair.

---

## 2. Problem Statement & Root-Cause Validation

### 2.1 The original failure, in code

The old path was *gap-dependent* end to end. Two functions embodied it:

- **`get_prosody_adjusted_wav`** (`src/persona_forge/voice_library.py:81`) — loads the master,
  calls `detect_pause_intervals`, filters to `interior` gaps, and at
  `voice_library.py:115`:
  ```python
  if not interior:
      return wav, sr        # ← blended speech exits here, UNCHANGED
  ```
- **`_shape_pauses`** (`src/persona_forge/audio_style.py:218`) — same dependency:
  ```python
  non_silent = librosa.effects.split(wav, top_db=30)
  if len(non_silent) <= 1:
      return wav, 1.0       # ← one continuous block → no-op
  ```

Both roads lead through **`detect_pause_intervals`** (`audio_style.py:62`), which is just
`librosa.effects.split(top_db=30)` — pure energy thresholding. No gap ⇒ no handle ⇒ the
period after *"no worries"* is invisible to the system.

### 2.2 The secondary defect: proportional drift

`get_pause_targets` (`audio_style.py:156`) maps each punctuation mark to the nearest gap by
**character-position proportion vs. time proportion**, gated by a 5% window
(`audio_style.py:209`). This assumes a *uniform speech rate* across the clip (false in
practice) and **silently drops** any mark whose proportional position has no gap nearby.
This is the "pause drift" — it is real and it is structural, not a tuning bug.

### 2.3 What is solid and should be reused

- **`src/persona_forge/audio_post.py`** — clean, numpy-only DSP. Equal-power crossfades,
  ordered region-edit application (`apply_region_edits`, `audio_post.py:233`) that mirrors
  the frontend, compressor/limiter/normalize. **This is our surgical-insertion toolkit.**
- **Region-edit engine** — `insert_silence` / `remove_range` / `apply_region_fade` already
  exist and are validated. Surgical micro-gap insertion is expressible as a generated
  `insert_silence` edit list.
- **Reference storage** — `_voice_dir`, `original.wav` master, prosody variants
  (`create_prosody_variant`, `voice_library.py:168`), `set_active_variant`, `family_id`,
  and `meta.sample_text` (the transcript). The variant model is a good fit for caching
  aligned/repaired outputs without destroying the master.

### 2.4 Implemented DSP order

- **Generation:** trim silence → optional bounded output prosody repair → explicit style
  preset or the default house chain. `postprocess: false` preserves the historical trim-only
  behavior and does not disable an explicitly requested repair.
- **`/v1/audio/speech`:** uses the same complete-file generation path and returns repair
  outcome metadata in `X-Prosody-Repair-*` headers.
- **Reference preparation:** `/voices/<id>/adjust-pauses`, `preview-prosody`, region edits,
  Stitch Studio, and OmniVoice all converge on the canonical resolved boundary plan and
  renderer.

### 2.5 The strategic implication

Because cloned/generated output *inherits* prosody from the reference, **a clean, correctly
paced reference is worth more than any output-side repair.** The plan therefore invests
first in reference-side triage+alignment (Library/Stitch/OmniVoice), then delivers output
repair as the required final extension of the same engine.

---

## 3. Decisions Log (aligned with nick, 2026-07-12)

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | Aligner footprint | **Pinned MMS INT8 ONNX + project-owned CTC alignment**, via `onnxruntime` (portable CPU EP baseline; optional providers require separate validation) | Runs without a PyTorch aligner path; the upstream package was incompatible with Python 3.13, so its algorithms were adapted behind the same backend-agnostic contract |
| D7 | Runtime posture | **Backend-agnostic** (not OpenVINO-specific) | Recent decisions trend cross-platform; don't re-lock to OpenVINO |
| D8 | Default output DSP | **Conservative "house" preset** (normalize + peak limit, on by default when no `style_preset`) | Safe polish improves bare requests independently of alignment; `postprocess: false` preserves trim-only behavior; reserve true-peak/dBTP wording for an oversampled implementation |
| D2 | Model license | **CC-BY-NC default MMS OK** | Personal/research use, not commercially shipped |
| D3 | Trigger UX | **Auto-triage + manual override** | Silent fast path; escalate only when blended; user can force Natural/Precise |
| D4 | Surfaces | **Voice Library, Stitch Studio, OmniVoice** | Reference-prep surfaces; Stitch seams are known → prevents later Library rework |
| D5 | hermes profile | **Batch/offline rendering** | Per-request aligner *tolerable*, but still not on any live turn |
| D6 | Output/OpenAI surface | **Implemented for complete-file routes** | Reuses the engine behind an opt-in flag + latency budget, with graceful fallback to un-repaired audio when the budget expires |

---

## 4. Target Architecture

```
                         ┌─────────────────────────────────────────────┐
   reference audio  ───► │  TRIAGE (cheap, transcript-aware)           │
   + transcript          │  gaps_detected vs boundaries_expected       │
                         │  → decide: NATURAL | PRECISE                 │
                         └───────────────┬─────────────────────────────┘
                                         │
                      NATURAL ◄──────────┴──────────► PRECISE
                         │                               │
              (today's energy path)           ┌─────────▼──────────┐
              detect_pause_intervals          │  FORCED ALIGNMENT  │  (ONNX MMS, cached)
              get_pause_targets                │  audio + transcript│
                         │                     │  → word/sentence   │
                         │                     │    boundaries      │
                         │                     └─────────┬──────────┘
                         │                               │
                         │                     ┌─────────▼──────────────┐
                         │                     │ DIRECT PAUSE-EDIT PLAN │
                         │                     │ punctuation → aligned │
                         │                     │ word → safe cut →     │
                         │                     │ silence + micro-fades │
                         │                     └─────────┬──────────────┘
                         │                               │
                         └───────────────┬───────────────┘
                                         ▼
                          SHARED REGION-EDIT RENDERER
                          Natural: existing proportional shaping
                          Precise: alignment-directed ordered edits
                                         ▼
                              normalize / limit / write variant
```

Natural mode retains today's energy-based `get_pause_targets` / `_shape_pauses` behavior.
Precise mode uses alignment to build the **final ordered pause-edit plan directly**. It must
not manufacture gaps and then ask `get_pause_targets` to rediscover their punctuation by
character/time proportion: inserted duration would shift later proportions and preserve the
structural drift bug. Both modes converge on the shared region-edit renderer, keeping the DSP
blast radius small while making Precise mapping deterministic.

---

## 5. Component Design

### 5.1 Triage — "does this clip need the heavy pass?"

Implemented in `src/persona_forge/prosody_triage.py`.

**Signal:** compare *acoustic evidence* to *linguistic expectation* as a cheap heuristic.

```
boundaries_expected = count of sentence-ending + strong-clause punctuation in transcript
                      (['.', '!', '?', '…'] and optionally ',')
gaps_detected       = interior gaps from detect_pause_intervals() with dur ≥ MIN_GAP_MS
coverage            = gaps_detected / max(1, boundaries_expected)
```

Decision:
- `coverage ≥ COVERAGE_OK` (e.g. 0.8) → **NATURAL** (fast path; today's behavior).
- `coverage < COVERAGE_OK` → **PRECISE** (blended; escalate to alignment).
- Degenerate cases (no transcript, coverage undefined) → NATURAL with a "no transcript"
  note surfaced to the UI (alignment needs text).

**Secondary signals** (refine, don't gate): median gap duration, speech-rate variance
across the clip (high variance ⇒ proportional mapping unreliable ⇒ prefer PRECISE), SNR
(from `reference_analysis.calculate_snr` — low SNR degrades CTC, flag it).

**Output:** a `TriageResult` — `{mode, coverage, boundaries_expected, gaps_detected,
reasons[]}` — persisted so the UI can explain *why* Precise was chosen and the manual
override can flip it.

Gap count does not prove that a detected breath corresponds to a particular punctuation mark:
unrelated breaths can mask missing sentence gaps. Triage is therefore a measured classifier,
not a correctness oracle. Auto remains the default, but its threshold must be calibrated on a
labeled fixture matrix and its false-negative/false-positive rates recorded. Natural and
Precise remain available as deterministic manual overrides.

### 5.2 Forced alignment engine

Implemented in `src/persona_forge/forced_alignment.py`.

- **Model:** immutable-pinned MMS-300M INT8 ONNX from
  `onnx-community/mms-300m-1130-forced-aligner-ONNX`.
- **Alignment code:** project-owned transcript normalization, `<star>` targets, CTC Viterbi,
  confidence scoring, and punctuation ownership. The upstream `ctc-forced-aligner` source
  informed these algorithms but is not imported at runtime.
- **Runtime:** **`onnxruntime`** with `CPUExecutionProvider` as the portable baseline.
  `ALIGNER_PROVIDERS` permits explicitly validated alternatives; none is assumed available.
  No PyTorch model path is imported by the serving aligner.
- **Interface:**
  ```python
  def align(wav: np.ndarray, sr: int, transcript: str, *,
            granularity: str = "word", language: str = "en") -> list[Boundary]
  # Boundary = {"text": str, "start": float, "end": float, "score": float, "kind": str}
  ```
- **Preprocessing for alignment only** (never mutates the saved master): downmix, resample
  to 16 kHz, and normalize the emission input.
- **Model loading:** lazy singleton on first Precise request, followed by configurable idle
  unload through the serialized alignment job manager.

**Boundary derivation:** normalize the transcript while retaining source character offsets;
align spoken words; then attach punctuation to the preceding aligned word. Repeated words,
abbreviations, decimals, quotes, ellipses, and divergence cases have deterministic fixtures.
Punctuation itself is not assumed to produce an acoustic token.

**Divergence handling:** if the transcript and audio disagree (user edited text but not
audio), CTC scores drop. Per-boundary `score < CONF_MIN` (e.g. 0.6) ⇒ mark that boundary
"uncertain" and fall back to a local VAD search around the expected position rather than
cutting blindly.

### 5.3 Surgical micro-gap insertion (anti-click)

Implemented in `audio_post.py` (co-located with the DSP it depends on):

```python
plan = plan_boundary_pauses(wav, sr, pause_edits)
repaired = apply_resolved_boundary_pause_plan(wav, sr, plan)
```

For each punctuation-owned aligned boundary, emit the final target-duration edit directly:
1. **Safe-cut selection** — search around the aligned word boundary for a low-energy point;
   use zero-cross proximity as a secondary preference, not the sole criterion. Phase 0/3
   compares windows and policies against hand-marked truth rather than locking ±2 ms early.
2. **Micro-fade** — 2 ms cosine ramp-down before the cut, 2 ms ramp-up after (reuse the
   equal-power curve already in `apply_fades`).
3. **Insert or resize silence** — emit an alignment-owned pause edit at the cut for the final
   target duration. Do not pass it back through `get_pause_targets`.
4. **Shared contract** — the backend returns resolved cut position, duration, provenance,
   origin, and rendered-preview coordinates. The frontend displays those server-owned
   markers without recomputation, keeping preview and saved render sample-equivalent.

This transforms blended speech into correctly segmented speech **without a perceptible
click**. The alignment-owned edit already carries the preset's final target (for example,
Storyteller `sentence_end = 1000 ms`); no second mapping or expansion pass occurs.

> Note: today's `_shape_pauses` inserts raw `np.zeros` when *replacing* an already-silent
> gap — fine there. The anti-click work is only required for the new *cut-into-voiced-audio*
> path; keep the two paths distinct.

### 5.4 Data model & caching

Alignment is expensive-once and reusable only while every semantic input matches. Cache raw
word alignment separately from derived pause edits. The cache identity must include the
master audio, transcript, language, model/tokenizer revision, preprocessing contract, and
alignment schema version:

```json
{
  "alignment": {
    "engine": "mms-onnx-v1",
    "audio_sha256": "…",
    "transcript_sha256": "…",
    "language": "en",
    "model_id": "onnx-community/mms-300m-1130-forced-aligner-ONNX",
    "model_revision": "<immutable revision>",
    "preprocess_version": 1,
    "schema_version": 1,
    "sample_rate": 16000,
    "granularity": "word",
    "boundaries": [
      {"text": "worries", "start": 3.812, "end": 4.104, "score": 0.94, "kind": "sentence_split"}
    ]
  },
  "triage": {"mode": "precise", "coverage": 0.4, "boundaries_expected": 5, "gaps_detected": 2}
}
```

- Invalidate when any cache-identity field differs. In particular, editing `sample_text`
  invalidates alignment even if the audio is unchanged. Resolve and hash the actual source
  master used by the voice/variant rather than assuming every edit rewrites `original.wav`.
- Repaired audio is stored as a **prosody variant** (existing mechanism), never overwriting
  `original.wav`. The manual override + undo (`/voices/<id>/undo-reference-edit`,
  `app.py:474`) continue to work.

### 5.5 API surface

- `POST /voices/<id>/triage` → returns `TriageResult` (cheap, sync).
- `POST /voices/<id>/align` → runs alignment, caches to `meta.json`. **Async job** (returns
  `job_id`; poll for completion) because it can take 1–5 s. Extract a small generic bounded
  background-job contract or add an alignment-specific manager; generation `_JobState` is
  not directly reusable because its progress, cancellation, and lifecycle are frame-generation
  specific. Serialize alignment against conflicting model loads/reconfiguration and large
  VoiceDesign/OmniVoice work. Define lazy-load, idle-unload, cancellation, and `LOW_RAM_MODE`
  behavior explicitly.
- Extend `POST /voices/<id>/adjust-pauses` (`app.py:645`) with a `mode` param
  (`natural|precise|auto`, default `auto`): `auto` runs triage, escalates to alignment-directed
  when blended, else today's path. Backwards compatible.
- Fallback chain inside `adjust-pauses`:
  1. valid cached alignment → direct alignment-owned pause-edit plan → render
  2. no cache + PRECISE → align (sync-with-budget or reuse async result) → direct plan → render
  3. alignment fails / low conf → VAD-assisted local safe-cut search → explicit edit → render
  4. final fallback → today's energy path (never worse than status quo)

### 5.6 Frontend UX

Surface: `frontend/src/pages/VoiceLibraryPage.tsx` (the fingerprint + "Adjust prosody"
panel in the screenshot), reusing `RegionEditor.tsx` for manual edits.

- **Processing mode** control in the Adjust-prosody panel: **Natural** (energy) / **Precise**
  (forced alignment) / **Auto** (default — triage decides).
- **Boundary badge** on the analysis strip: when Precise ran, show "Aligned · N boundaries"
  and let the user reveal the detected boundaries over the waveform. When a boundary was
  *manufactured* (surgical), mark it distinctly from a natural gap.
- **Latency masking:** align is async — show "Finding linguistic boundaries…" progress
  (reuse existing job-progress polling) so a 1–5 s pass never blocks the UI.
- **Explainability:** if triage chose Precise, tooltip shows "2 gaps detected, 5 sentence
  boundaries expected → blended speech." If no transcript, show why alignment is disabled.

> **Landed (2026-07-13):** Processing-mode control, latency masking, the **Aligned · N
> boundaries** badge (sentence/clause breakdown in tooltip), and explainability text are live
> in `VoiceLibraryPage.tsx`. The badge count comes straight from the alignment record; the
> *reveal-over-the-waveform* and *manufactured-vs-natural* halves of the boundary badge are
> deferred to §5.6.1 because they need the resolved edit plan, which the render endpoints do
> not yet return.

### 5.6.1 Boundary overlay & shared edit-plan contract (Phase 3.5 fast-follow)

The boundary badge answers *how many* boundaries were found; the overlay answers *where they
are and what happened to each*. It is the highest-value refinement of the Library surface
because it makes the surgical pass legible: the user sees the exact cut the renderer chose and
whether a gap was **natural** (already silent, preserved) or **manufactured** (cut into voiced
audio + padded to the preset target).

**Blocking dependency — surface the edit plan (backend).** §5.3 step 4 already defines the
shared region-edit schema (resolved cut position, duration, snap provenance, fade semantics);
today it lives only inside `apply_boundary_pause_plan` and never crosses the wire.

- `GET /voices/<id>/preview-prosody` returns a `plan` array alongside `audio_base64`/`metrics`:
  each entry `{ at_ms, cut_sample, cut_ms, insert_ms, target_ms, existing_ms, provenance,
  origin }` where `provenance ∈ {zero_cross, energy_min, boundary}` and `origin ∈ {alignment,
  vad, energy}`. This is the same list `plan_boundary_pauses` already computes — expose it,
  don't recompute it, so overlay and saved render stay sample-equivalent by construction.
- `insert_ms > 0` ⇒ **manufactured**; `insert_ms == 0` (target already satisfied by an
  existing gap) ⇒ **natural**. The frontend derives the marker distinction from `insert_ms`,
  never re-implements the DSP.

**Overlay (frontend, `RegionEditor.tsx` + `Waveform.tsx`).**
- Read-only markers first (per Open Question #3): a vertical tick at each `cut_sample`, tinted
  by `origin` (alignment vs VAD-directed vs energy fallback) and shaped by manufactured-vs-
  natural; hover shows `target_ms`, `insert_ms`, and `provenance`.
- Render on the **preview** waveform (the adjusted audio the user auditions), with cut samples
  mapped through the same sample-rate the plan carries — no client-side gap math.
- Editable handles (drag a boundary, nudge a target) are a fast-follow *after* read-only ships,
  reusing RegionEditor's existing region-drag affordances and posting back through the same
  edit-plan schema.

**Reuse note:** the `preview-prosody` `plan` payload is the same contract Stitch (§6.2),
OmniVoice (§6.3), and generation repair (§6.4) will each surface per-segment, so building it
here pays down those phases too.

---

## 6. Surface Integration

### 6.1 Voice Library (primary — Phase 2/3)
The screenshot surface. Triage on analysis; auto-fix on adjust; variant caching; manual
override + RegionEditor for hand-tuning. This is where the feature is proven.

### 6.2 Stitch Studio (Phase 4)
Seams between segments are **known at stitch time** — we don't even need alignment there for
the *joins*: `concat_with_padding` (`audio_post.py:289`) already injects controlled,
anti-clicked silence per gap. What Stitch adds:
- Apply triage/alignment to **each source segment's own internal** blended speech before
  joining (so a segment that is itself two blended sentences gets fixed).
- Because Stitch controls the seams, prepping a voice *there* can indeed reduce Library
  rework (nick's hypothesis — confirmed viable): a clip assembled from clean, correctly
  paced segments needs no Library-side surgery.
- `StitchTimeline.tsx` already has region-edit lanes; add per-gap target-pause and a
  "normalize pacing across segments" action driven by the same targets engine.

### 6.3 OmniVoice segments (Phase 4)
Per-segment prosody/pause shaping during audition. `omnivoice_engine.py` already stitches
via `stitch_segments` with `postprocess_output` controlling its own silence/normalize
(`omnivoice_engine.py:196`). Add triage+alignment-directed repair per segment so a chosen
take that is internally blended can be repaired before it becomes a saved reference.

> **Landed (2026-07-13):** `prosody_repair.repair_segment_audio` is the shared in-memory
> segment engine: Auto triages each clip, Precise forces alignment, and both use the same
> alignment → VAD-safe-cut fallback and canonical resolved pause plan as Voice Library.
> Stitch-plan clips carry their transcript and independent `off|auto|precise` repair mode;
> repair runs before trim/region DSP and before `stitch_segments`, for both preview and save.
> Unchanged clips are cached by audio/transcript/target identity so timeline rerenders do not
> repeat alignment. The standalone Stitch Studio and OmniVoice quick-stitch/save paths both
> opt new clips into Auto. `POST /omnivoice/stitch/pacing-targets` resolves known seams from
> the canonical prosody target table, and StitchTimeline's **Normalize pacing** action applies
> those per-gap targets while enabling Auto repair. Existing payloads remain backward-
> compatible because omitted repair modes resolve to off server-side.

### 6.4 Generation / OpenAI output (Phase 6 — required delivery)
- **Not** on any live conversational turn. hermes is batch/offline (D5), so an opt-in
  per-request aligner is *tolerable*, but it must be explicit and budgeted.
- Reuse the identical triage+alignment-directed edit engine, applied to the generated wav using the
  **input text** (which the request already carries) as the alignment transcript.
- Gate behind a request flag (e.g. `"prosody_repair": true` alongside `style_preset`) plus a
  server latency budget that aborts to the un-repaired output if alignment overruns. A budget
  fallback is an operational guarantee, not a deferral mechanism: the endpoint plumbing,
  repair attempt, result metadata, and fallback behavior are all required Phase 6 scope.
- Strategic note (§2.5): expect modest ROI vs. fixing the reference; this exists for the
  cases where the reference is fixed but a specific long generation still blends.

---

### 6.5 Default output DSP — "house" preset (independent quick win)

Independent of alignment; shippable immediately. Today a request with no `style_preset`
(every bare hermes call) gets only `_trim_silence` (`model.py:1428`) — no loudness, no
peak safety. Add a conservative, always-beneficial default chain.

- **New preset `"default"`** in `STYLE_PIPELINES` (`audio_style.py:313`), distinct from
  `"off"`. Core steps (transparent, safe on a clone):
  1. `_normalize_lufs` to a conversational target (~−16 LUFS; tune per playback context).
  2. Peak limiting at −1 dB. The existing `limit_peak` is a sample-peak limiter; call the
     result dBFS/sample-peak safety unless Phase Q adds oversampled inter-sample measurement
     and limiting sufficient to substantiate a −1 dBTP/true-peak claim.
  - *Optional, milder, off by default:* ~80 Hz high-pass (rumble) + gentle compression
    (`ratio ≤ 2`) for consistency. Opinionated → opt-in, because heavy dynamics/EQ can
    shift perceived voice character in a cloning pipeline.
- **Wiring:** in `_run_generate` (`model.py:1429`), when `job.style_preset` is falsy, apply
  the `"default"` preset instead of skipping DSP. Honor the existing `postprocess` flag:
  `postprocess: false` (or an env kill-switch, e.g. `TTS_DEFAULT_DSP=off`) restores the
  raw-output behavior. **No pause-shaping in the default path** — that stays gated behind
  explicit presets and the triage engine.
- **Applies to** `/generate` and `/v1/audio/speech` uniformly, so hermes benefits with zero
  request changes.

**Gate:** bare hermes output is loudness-normalized and peak-safe with no audible artifacts
and no perceptible change to voice identity across `/generate`, `/generate/async`, and
`/v1/audio/speech`, all supported backends, and WAV/MP3 response paths. `postprocess: false`
yields sample-equivalent prior trim-only PCM; require byte identity only where the same
deterministic encoding path makes that a valid invariant.

## 7. Phases & Gates

Each phase has an exit gate that must pass before the next begins.

### Phase Q — Default output DSP (quick win, parallel/independent)
Ship the `"default"` house preset (§6.5). No dependency on triage or alignment; can land
before or alongside Phase 0.
- **Gate:** §6.5 gate (loudness-normalized, peak-safe, identity-preserving; `postprocess:
  false` = sample-equivalent prior trim-only PCM, with byte identity only on deterministic
  encoding paths).

> **Complete (2026-07-12):** omitted `style_preset` selects the conservative default
> normalize/limit chain, `postprocess: false` remains the request-level bypass, and
> `TTS_DEFAULT_DSP=off` disables only the implicit default.

### Phase 0 — Spike & footprint validation
- The spike evaluated the upstream `ctc-forced-aligner` logic and ONNX artifact on portable
  CPU EP in a dev container. It proved tokenizer/normalization compatibility,
  output names, blank/`<star>` behavior, score semantics, immutable revision pinning, and that
  no PyTorch model path is imported. Align the screenshot clip; compare safe-cut policies;
  measure cold/warm latency, peak RSS, retained idle RSS, and unload behavior on the target
  16-core Intel CPU. Optional providers remain unclaimed until validated on their platforms.
- **Gate:** aligner runs offline on portable CPU, boundaries for *"…no worries. We'll sort…"*
  land within ±50 ms of hand-marked truth; package/model/license/provisioning contracts and
  runtime footprint are documented and acceptable. The upstream package install failed on
  Python 3.13, so the shipped backend-agnostic path uses the ONNX model plus project-owned
  normalization and CTC Viterbi without reducing product scope.

> **Complete (2026-07-12):** the pinned MMS INT8 ONNX model, CPU execution provider,
> vocabulary, `<star>` handling, custom CTC Viterbi, revision identity, and no-Torch serving
> path were proven. Reproducible evidence is in `docs/spikes/phase0_alignment/`.

### Phase 1 — Triage (no alignment yet)
- Build `prosody_triage.py`; wire `TriageResult` into `analyze_reference` output and the
  fingerprint UI; expose the Natural/Precise/Auto control (Precise disabled until Phase 2).
- **Gate:** calibrate and record false-negative/false-positive rates on a labeled matrix:
  clean gaps; missing gaps plus unrelated breaths; abbreviations; decimals; ellipses; quoted
  punctuation; short sentences; commas/clauses; noisy/accented speech; mismatched and missing
  transcripts. Blended clips meet the agreed detection threshold without unacceptable clean-
  clip escalation. Synthetic tests remain necessary but are not sufficient alone.

> **Complete (2026-07-13):** transcript-aware triage, Natural/Precise/Auto selection,
> explainability metadata, the labeled punctuation/noise/accent matrix, and clean fast-path
> regression coverage are implemented and green.

### Phase 2 — Alignment engine
- Build `forced_alignment.py`; async `/voices/<id>/align`; `meta.json` cache + hash
  invalidation.
- **Gate:** normalized source offsets and word/punctuation ownership are deterministic;
  cache identity covers audio, transcript, language, immutable model/tokenizer revision,
  preprocessing, and schema; audio or transcript edits invalidate it; confidence-based
  divergence fallback is proven on deliberately mismatched and repeated-word transcripts;
  alignment jobs serialize safely and obey cancellation/idle-unload/LOW_RAM rules.

> **Complete (2026-07-13):** `forced_alignment.py`, serialized asynchronous voice alignment,
> immutable cache identity/invalidation, confidence fallback, cancellation, provisioning,
> and idle unload are implemented and validated.

### Phase 3 — Surgical insertion + Voice Library end-to-end
- Build the canonical boundary-pause planner/renderer; wire the `adjust-pauses` `mode=auto`
  fallback chain;
  anti-click validated; variant caching; manual override + RegionEditor. Precise mode maps
  punctuation directly to aligned-word edits and never re-enters proportional gap mapping.
- **Gate (the headline test):** a Storyteller preset injects ~1000 ms pauses at the periods
  in the screenshot clip (0 ms original silence) with **no audible click**, and the fast
  path for clean clips is unchanged. Frontend preview and backend saved render are sample-
  equivalent for the shared edit contract. Listening test + click-detection assertion.

> **Backend status (2026-07-13):** `audio_post.resolve_safe_cut` / `plan_boundary_pauses` /
> `apply_boundary_pause_plan` land the anti-click surgical insertion (energy-min + zero-cross
> snap, 2 ms equal-power micro-fades). `voice_library.build_alignment_pause_edits` maps
> punctuation-owned aligned boundaries to preset targets (sentence_end/comma, existing-gap
> resized), and `get_alignment_directed_wav` runs the §5.5 chain (cached alignment → align →
> plan → render) behind `get_prosody_adjusted_wav(mode=...)`. `adjust-pauses` +
> `preview-prosody` accept `mode=natural|precise|auto` (default `auto`). Click-detection
> assertion is green (`test_no_click_at_seams`). The pure-VAD fallback (step 3) now lands via
> `build_vad_pause_edits` / `get_vad_directed_wav` — proportional punctuation placement +
> VAD-safe anti-click cut — wired into the auto/precise chain (alignment → VAD → energy).
>
> **Frontend status (2026-07-13):** §5.6 UX landed in `VoiceLibraryPage.tsx`. The
> Processing-mode control (Natural/Precise/Auto) is fully wired — Precise is enabled when the
> clip has a transcript (disabled with a reason otherwise) and `mode` is threaded to both
> `preview-prosody` and `adjust-pauses`. When the resolved mode aligns (explicit Precise, or
> Auto + triage=precise), the card kicks off the async `/align` job, masks the 1–5 s latency
> with a "Finding linguistic boundaries…" state (polled + cancel-on-unmount), then shows an
> **Aligned · N boundaries** badge (sentence vs clause breakdown in tooltip) and falls to a
> "safe fallback" note on job failure. Explainability text renders the triage rationale
> ("N gaps detected, M sentence boundaries expected → blended speech") or the no-transcript
> reason. `frontend/src/lib/api.ts` gained `ProsodyMode`, alignment types, and
> `startVoiceAlignment` / `getVoiceAlignmentStatus` / `cancelVoiceAlignment`. The boundary
> overlay and manufactured-vs-natural edit-plan contract described here were subsequently
> completed in Phase 3.5 below.

### Phase 3.5 — Boundary overlay & edit-plan contract (Library fast-follow)
Highest-value refinement of the Phase 3 surface (§5.6.1). Surface the resolved edit plan from
`preview-prosody` (the list `plan_boundary_pauses` already computes — `cut_sample`, `cut_ms`,
`insert_ms`, `target_ms`, `existing_ms`, `provenance`, `origin`), then render read-only
boundary markers over the preview waveform in `RegionEditor.tsx`, tinted by `origin` and
distinguishing manufactured (`insert_ms > 0`) from natural (`insert_ms == 0`) gaps.
- **Gate:** for the screenshot clip under Storyteller, every rendered cut has a marker at the
  exact `cut_sample` the saved render used (overlay ↔ audio sample-equivalent); manufactured
  vs natural is visually distinct; no client-side gap recomputation. Editable handles are an
  explicit fast-follow, not part of this gate.

> **Landed (2026-07-13):** `preview-prosody` now returns the canonical resolved plan plus
> preview `sample_rate` / `sample_count`. `cut_sample` is expressed in rendered-preview
> coordinates with all prior server-side insertions already folded in, and the same plan is
> applied by the backend renderer. Voice Library renders read-only RegionEditor markers from
> those samples directly: origin controls color, while diamond/solid and circle/dashed markers
> distinguish manufactured from natural gaps. Hover text exposes target, inserted duration,
> snap provenance, and the exact sample. Tests cover running-offset coordinates and PCM-
> equivalent preview/saved output. **Phase 3 and Phase 3.5 are complete.**

### Phase 4 — Stitch Studio + OmniVoice
- Per-segment triage/alignment-directed edits; StitchTimeline per-gap targets; OmniVoice
  per-segment repair.
- **Gate:** a stitched clip from blended segments needs no Library-side surgery.

> **Complete (2026-07-13):** the shared segment repair contract is wired through Stitch
> preview/save and OmniVoice chosen-take flows; per-gap targets and per-clip repair controls
> are exposed in StitchTimeline. Tests prove clean Auto clips remain sample-equivalent,
> alignment failure falls back to VAD safe cuts, and a blended Storyteller segment receives
> its exact internal 1000 ms sentence pause in the stitched output. **Phase 4 is complete.**

### Phase 5 — Hardening
- Perf budget enforcement, error surfaces, docs, `pytest` + frontend build, dev-container
  verification.
- **Gate:** full test suite green; latency < 5 s p95 on target CPU; no regression on the
  energy fast path.

> **Complete (2026-07-13):** alignment jobs now expose per-job duration/budget status and a
> bounded runtime p50/p95 window through `/alignment/performance` and `/health`; the Voice
> Library warns on a slow successful alignment without discarding its usable result. Compose
> passes the aligner provider, latency budget, and idle-unload controls into the serving
> container. `scripts/benchmark_aligner.py` is the fail-closed real-model gate. On
> `docker-agent` (Intel i7-1360P, 8 allocated CPU threads), the exact 11.16 s Aussie screenshot
> reference ran through pinned MMS INT8 ONNX / CPU EP at warm p50 **3.511 s** and p95
> **4.136 s** over 10 measured iterations (cold session load 5.106 s; peak benchmark RSS
> 958.4 MiB), passing the strict `< 5 s` gate. The complete fake lane, frontend build,
> Compose config, live dev-container health/alignment, and clean Auto fast-path invariants are
> green. **Phase 5 is complete.**

### Phase 6 — Generation/output repair (required)
- Request-flag plumbing on `/generate` + `/v1/audio/speech`; latency-budgeted opt-in;
  reuse engine. Include async generation paths and response/progress metadata indicating
  repaired, unnecessary, failed, or budget-fallback outcome.
- **Gate:** opt-in repair never fires on un-flagged requests; budget abort returns
  un-repaired audio cleanly; flagged requests attempt repair on every supported generation
  path; successful repair uses the same canonical boundary/edit renderer as reference audio.

> **Complete (2026-07-13):** complete-file generation now accepts the strict boolean
> `prosody_repair` opt-in on `/generate`, `/generate/with_metrics`, `/v1/audio/speech`, and
> `/generate/async`; streaming rejects it because emitted PCM cannot be repaired
> retroactively. Every request records `not_requested`, `repaired`, `unnecessary`, `failed`,
> or `budget_fallback` through raw-audio headers or structured JSON/progress metadata. The
> five-second server deadline runs the existing `repair_segment_audio` engine with
> cancellation checks, so successful edits use the canonical boundary planner/renderer and
> late ONNX results are neither rendered nor cached. On `docker-agent`, an unflagged
> same-seed Pocket request returned `not_requested`; its cold flagged counterpart returned
> `budget_fallback` at **5.000339 s**, and both WAV files were byte-identical at SHA-256
> `6a1423df520946cc613c3fdd8ae021d99f98a57368f83039c2c659a2320e0bbe`. Warm native,
> OpenAI-compatible, and async requests all returned usable audio and the expected
> `unnecessary` metadata for a naturally well-gapped clip. Focused, fake-only, Torch,
> frontend, repository, and Compose gates are green. **Phase 6 is complete.**

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Upstream aligner package is incompatible | Resolved: keep the validated pinned ONNX artifact and project-owned normalization/CTC Viterbi; no upstream package or PyTorch aligner dependency |
| Aligner footprint too heavy on dev container | Phase 0 measures cold/warm latency, peak/idle RSS, and unload behavior; ONNX/int8 + optional accelerator EP; smaller compatible model if needed |
| Transcript ↔ audio divergence | `<star>` token + per-boundary confidence; low-conf → VAD-assisted local search, never blind cut |
| Audible clicks from cutting voiced audio | Low-energy safe-cut selection with zero-cross proximity + micro-fades; automated click-detection test in Phase 3 gate |
| Low-SNR references degrade CTC | Surface the SNR warning; confidence-gate boundaries and use VAD-safe fallback; keep the master untouched |
| Gap counts hide missing boundaries or over-triage clean audio | Treat triage as a calibrated classifier; labeled matrix records false-negative/false-positive rates; user retains Natural/Precise override |
| Fast-path regression | Fallback chain always terminates in the legacy energy path; snapshot tests protect current behavior |
| Non-English / accented refs (e.g. the Aussie sample) | MMS is multilingual (158 langs); pass language; `<star>` absorbs accent-driven mismatch |

---

## 9. Dependencies & Footprint

- **Runtime dependency:** `onnxruntime`; no PyTorch aligner path and no
  `ctc-forced-aligner` package dependency. Project-owned normalization, tokenization, CTC
  Viterbi, and boundary derivation live in `forced_alignment.py`. CPU EP is load-bearing;
  optional OpenVINO/CoreML providers require platform-specific validation.
- **Model asset:** pinned MMS-300M forced-aligner INT8 ONNX (~302 MB), provisioned through
  the existing Hugging Face cache and lazy-loaded on first Precise use.
- **License:** default MMS model is CC-BY-NC 4.0 — acceptable per D2. If the project later
  goes commercial, replace it with a permissively licensed aligner behind the same internal
  `align()` contract. Do not assume a one-line model-id swap: vocabulary, normalization,
  language coverage, blank/star tokens, outputs, and score calibration require a new gate.

---

## 10. Resolved implementation choices

1. Triage counts sentence-ending punctuation by default; clause/comma behavior remains a
   tunable rather than increasing default escalation.
2. The aligner loads lazily and unloads after the configured idle interval. This preserves
   the validated low-memory posture while exposing cold starts in operational telemetry.
3. RegionEditor exposes read-only boundary markers from the server-resolved plan. Editable
   handles remain a separate enhancement and are not required by this implementation.

---

## 11. Acceptance criteria

All criteria below are satisfied by the phase evidence in §7.

- **Blended repair:** Storyteller injects target pauses at periods in a 0-gap clip; ±50 ms
  of target duration; no audible click.
- **Zero drift:** punctuation maps to the correct linguistic boundary within ±20 ms,
  independent of original gaps; Precise mode never uses proportional gap remapping.
- **No fast-path regression:** clean, well-gapped clips behave exactly as today and incur no
  alignment cost.
- **Latency:** PRECISE pass < 5 s p95 on a 16-core Intel CPU; NATURAL pass unchanged.
- **Explainability:** the UI always shows why a mode was chosen and which pauses were
  manufactured vs. natural.
- **Surface completeness:** Voice Library, Stitch Studio, OmniVoice, and opt-in generation
  repair all use the same canonical boundary/edit contract and pass their phase gates.

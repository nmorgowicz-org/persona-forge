# Prosody Re-Architecture: Boundary-Aware Pause Handling

Date: 2026-07-12
Status: Proposed (aligned with nick — decisions locked in §3)
Priority: High
Supersedes: v2.0 "Prosody Boundary Awareness & Forced Alignment" draft (local-model)
Owner: Nick M

---

## 1. Executive Summary

Our prosody system cannot handle **blended speech** — audio where sentences run together
with no audible/visible gap (e.g. *"She's right, no worries. We'll sort it out later."*
spoken as one breath). Every prosody path today depends on finding silence gaps to use as
"handles"; when there is no gap, punctuation-driven pauses are silently dropped.

The fix is **not** "VAD vs forced alignment" as a global choice. It is a **tiered pipeline**:

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

### Locked decisions (see §3)
- **Aligner:** ONNX MMS CTC forced-aligner (`ctc-forced-aligner`) is the preferred candidate,
  subject to the mandatory Phase 0 feasibility gate, run via **`onnxruntime`**.
  The portable **CPU execution provider** is the baseline — it runs on any CPU (Intel/AMD
  x86-64, ARM64, **Apple Silicon**). OpenVINO EP (Intel) and CoreML EP (Apple) are *optional*
  accelerators, never load-bearing. No PyTorch in the serving path. Default MMS model's
  CC-BY-NC license is acceptable (personal/research use).
- **Runtime posture:** backend-agnostic. Earlier OpenVINO-specific assumptions are
  explicitly relaxed — nothing in this plan depends on OpenVINO being present.
- **UX:** Auto-triage + auto-fix, with a manual **Processing mode: Natural / Precise**
  override and a badge indicating when alignment was used.
- **Surfaces (build now):** Voice Library (cloning prep), Stitch Studio, OmniVoice segments.
- **Generation / OpenAI output:** a **required delivery phase** (Phase 6). It reuses the same
  engine, stays opt-in, and uses a strict latency budget so it never blocks a live turn.

---

## 2. Problem Statement & Root-Cause Validation

### 2.1 The failure, in code

The system is *gap-dependent* end to end. Two functions embody it:

- **`get_prosody_adjusted_wav`** (`src/qwen3_tts/voice_library.py:81`) — loads the master,
  calls `detect_pause_intervals`, filters to `interior` gaps, and at
  `voice_library.py:115`:
  ```python
  if not interior:
      return wav, sr        # ← blended speech exits here, UNCHANGED
  ```
- **`_shape_pauses`** (`src/qwen3_tts/audio_style.py:218`) — same dependency:
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

- **`src/qwen3_tts/audio_post.py`** — clean, numpy-only DSP. Equal-power crossfades,
  ordered region-edit application (`apply_region_edits`, `audio_post.py:233`) that mirrors
  the frontend, compressor/limiter/normalize. **This is our surgical-insertion toolkit.**
- **Region-edit engine** — `insert_silence` / `remove_range` / `apply_region_fade` already
  exist and are validated. Surgical micro-gap insertion is expressible as a generated
  `insert_silence` edit list.
- **Reference storage** — `_voice_dir`, `original.wav` master, prosody variants
  (`create_prosody_variant`, `voice_library.py:168`), `set_active_variant`, `family_id`,
  and `meta.sample_text` (the transcript). The variant model is a good fit for caching
  aligned/repaired outputs without destroying the master.

### 2.4 Where DSP actually runs today (important, from validation)

- **Generation path** (`_run_generate`, `model.py:1354`): `apply_style_preset` runs **only
  if a `style_preset` is passed** (`model.py:1429`). Otherwise the sole processing is
  `_trim_silence` (`model.py:1428`).
- **`/v1/audio/speech`** (`app.py:1759`) forwards `style_preset=data.get("style_preset")`
  (`app.py:1797`) — which is `None` for a bare hermes request. **So today, the OpenAI
  endpoint applies no prosodic DSP at all** — output prosody is entirely the reference +
  the clone. This is why fixing the *reference* is the highest-leverage lever (see §2.5).
- **Reference edits** are already wired: `/voices/<id>/adjust-pauses` (`app.py:645`),
  `/voices/<id>/region-edits` (`app.py:670`), `normalize`, `trim-silence`, plus
  `apply_reference_region_edits` (`voice_library.py:714`).

### 2.5 The strategic implication

Because cloned/generated output *inherits* prosody from the reference, **a clean, correctly
paced reference is worth more than any output-side repair.** The plan therefore invests
first in reference-side triage+alignment (Library/Stitch/OmniVoice), then delivers output
repair as the required final extension of the same engine.

---

## 3. Decisions Log (aligned with nick, 2026-07-12)

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | Aligner footprint | **ONNX MMS CTC aligner preferred, subject to the mandatory Phase 0 feasibility gate**, via `onnxruntime` (portable CPU EP baseline; OpenVINO/CoreML optional) | Target posture runs on any CPU incl. Apple Silicon with no torch serving path; Phase 0 must prove the selected package/export/provider combination before implementation locks to it |
| D7 | Runtime posture | **Backend-agnostic** (not OpenVINO-specific) | Recent decisions trend cross-platform; don't re-lock to OpenVINO |
| D8 | Default output DSP | **Add a conservative "house" preset** (normalize + peak limit, on by default when no `style_preset`) | Bare hermes requests get only `_trim_silence` today; safe polish improves all output, independent of alignment; reserve true-peak/dBTP wording for an oversampled implementation |
| D2 | Model license | **CC-BY-NC default MMS OK** | Personal/research use, not commercially shipped |
| D3 | Trigger UX | **Auto-triage + manual override** | Silent fast path; escalate only when blended; user can force Natural/Precise |
| D4 | Surfaces (build) | **Voice Library, Stitch Studio, OmniVoice** | Reference-prep surfaces; Stitch seams are known → prevents later Library rework |
| D5 | hermes profile | **Batch/offline rendering** | Per-request aligner *tolerable*, but still not on any live turn |
| D6 | Output/OpenAI surface | **Build in Phase 6** | Reuse engine behind an opt-in flag + latency budget; required scope, with graceful fallback to un-repaired audio when the budget expires |

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

New module: `src/qwen3_tts/prosody_triage.py`.

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

New module: `src/qwen3_tts/forced_alignment.py`.

- **Preferred candidate (pending the Phase 0 feasibility gate):** `ctc-forced-aligner`
  with MMS-300M. It advertises sentence/word/char granularity,
  `<star>` token for transcript-vs-audio divergence, structured JSON output, ~5× less
  memory than torchaudio's (deprecated) `forced_align`.
- **Runtime candidate:** ONNX model via the already-present **`onnxruntime`** dependency
  (`onnx-community/mms-300m-1130-forced-aligner-ONNX`).
  **Baseline = portable CPU execution provider** — runs on Intel/AMD x86-64, ARM64, and
  Apple Silicon with no code change. Optional accelerators selected at load time if present:
  **OpenVINO EP** (Intel) and **CoreML EP** (Apple). Provider selection is a single
  config point; the CPU EP is always the guaranteed fallback. No PyTorch in the serving path.
  Phase 0 must prove that the package's normalization/tokenization/alignment logic can be
  used with this ONNX export without importing a PyTorch model path; verify output names,
  blank/`<star>` tokens, score semantics, provider packaging, and immutable model revision.
- **Interface:**
  ```python
  def align(wav: np.ndarray, sr: int, transcript: str,
            granularity: str = "word") -> list[Boundary]
  # Boundary = {"text": str, "start": float, "end": float, "score": float, "kind": str}
  ```
- **Preprocessing for alignment only** (never mutates the saved master): resample to the
  model's expected rate, optional light spectral-subtraction *for the emission pass only*
  when SNR is low.
- **Model loading:** lazy singleton, loaded on first PRECISE request; guarded by the same
  startup pattern as the TTS model. Warm-load option at boot behind an env flag.

**Boundary derivation:** normalize the transcript while retaining source character offsets;
align spoken words; then attach punctuation to the preceding aligned word (or an explicitly
defined neighboring word for leading punctuation). Repeated words, abbreviations, decimals,
quotes, ellipses, and non-verbal tags must have deterministic fixtures. Punctuation itself is
not assumed to produce an acoustic token.

**Divergence handling:** if the transcript and audio disagree (user edited text but not
audio), CTC scores drop. Per-boundary `score < CONF_MIN` (e.g. 0.6) ⇒ mark that boundary
"uncertain" and fall back to a local VAD search around the expected position rather than
cutting blindly.

### 5.3 Surgical micro-gap insertion (anti-click)

New in `audio_post.py` (co-located with the DSP it depends on):

```python
def apply_boundary_pause_plan(wav, sr, pause_edits, *,
                              search_ms=2.0, fade_ms=2.0) -> np.ndarray
```

For each punctuation-owned aligned boundary, emit the final target-duration edit directly:
1. **Safe-cut selection** — search around the aligned word boundary for a low-energy point;
   use zero-cross proximity as a secondary preference, not the sole criterion. Phase 0/3
   compares windows and policies against hand-marked truth rather than locking ±2 ms early.
2. **Micro-fade** — 2 ms cosine ramp-down before the cut, 2 ms ramp-up after (reuse the
   equal-power curve already in `apply_fades`).
3. **Insert or resize silence** — emit an alignment-owned pause edit at the cut for the final
   target duration. Do not pass it back through `get_pause_targets`.
4. **Shared contract** — extend the region-edit schema with the resolved cut position,
   duration, snap provenance, and fade semantics. Implement it identically in frontend and
   backend so waveform preview and saved render are sample-equivalent.

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

### Phase 0 — Spike & footprint validation
- Prototype the preferred `ctc-forced-aligner` + ONNX export first on portable CPU EP, then
  optional OpenVINO EP, in a dev container. Prove tokenizer/normalization compatibility,
  output names, blank/`<star>` behavior, score semantics, immutable revision pinning, and that
  no PyTorch model path is imported. Align the screenshot clip; compare safe-cut policies;
  measure cold/warm latency, peak RSS, retained idle RSS, and unload behavior on the target
  16-core Intel CPU. Validate provider/package behavior on every supported platform before
  claiming optional acceleration there.
- **Gate:** aligner runs offline on portable CPU, boundaries for *"…no worries. We'll sort…"*
  land within ±50 ms of hand-marked truth; package/model/license/provisioning contracts and
  runtime footprint are documented and acceptable. If the preferred candidate fails, choose
  another backend-agnostic ONNX CTC aligner without reducing any product surface or phase.

### Phase 1 — Triage (no alignment yet)
- Build `prosody_triage.py`; wire `TriageResult` into `analyze_reference` output and the
  fingerprint UI; expose the Natural/Precise/Auto control (Precise disabled until Phase 2).
- **Gate:** calibrate and record false-negative/false-positive rates on a labeled matrix:
  clean gaps; missing gaps plus unrelated breaths; abbreviations; decimals; ellipses; quoted
  punctuation; short sentences; commas/clauses; noisy/accented speech; mismatched and missing
  transcripts. Blended clips meet the agreed detection threshold without unacceptable clean-
  clip escalation. Synthetic tests remain necessary but are not sufficient alone.

### Phase 2 — Alignment engine
- Build `forced_alignment.py`; async `/voices/<id>/align`; `meta.json` cache + hash
  invalidation.
- **Gate:** normalized source offsets and word/punctuation ownership are deterministic;
  cache identity covers audio, transcript, language, immutable model/tokenizer revision,
  preprocessing, and schema; audio or transcript edits invalidate it; confidence-based
  divergence fallback is proven on deliberately mismatched and repeated-word transcripts;
  alignment jobs serialize safely and obey cancellation/idle-unload/LOW_RAM rules.

### Phase 3 — Surgical insertion + Voice Library end-to-end
- Build `apply_boundary_pause_plan`; wire `adjust-pauses` `mode=auto` fallback chain;
  anti-click validated; variant caching; manual override + RegionEditor. Precise mode maps
  punctuation directly to aligned-word edits and never re-enters proportional gap mapping.
- **Gate (the headline test):** a Storyteller preset injects ~1000 ms pauses at the periods
  in the screenshot clip (0 ms original silence) with **no audible click**, and the fast
  path for clean clips is unchanged. Frontend preview and backend saved render are sample-
  equivalent for the shared edit contract. Listening test + click-detection assertion.

### Phase 4 — Stitch Studio + OmniVoice
- Per-segment triage/alignment-directed edits; StitchTimeline per-gap targets; OmniVoice
  per-segment repair.
- **Gate:** a stitched clip from blended segments needs no Library-side surgery.

### Phase 5 — Hardening
- Perf budget enforcement, error surfaces, docs, `pytest` + frontend build, dev-container
  verification.
- **Gate:** full test suite green; latency < 5 s p95 on target CPU; no regression on the
  energy fast path.

### Phase 6 — Generation/output repair (required)
- Request-flag plumbing on `/generate` + `/v1/audio/speech`; latency-budgeted opt-in;
  reuse engine. Include async generation paths and response/progress metadata indicating
  repaired, unnecessary, failed, or budget-fallback outcome.
- **Gate:** opt-in repair never fires on un-flagged requests; budget abort returns
  un-repaired audio cleanly; flagged requests attempt repair on every supported generation
  path; successful repair uses the same canonical boundary/edit renderer as reference audio.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Preferred aligner/package/export combination is incompatible | Phase 0 proves tokenizer, outputs, scores, providers, and no-torch serving path before lock-in; select another backend-agnostic ONNX CTC aligner without reducing scope if it fails |
| Aligner footprint too heavy on dev container | Phase 0 measures cold/warm latency, peak/idle RSS, and unload behavior; ONNX/int8 + optional accelerator EP; smaller compatible model if needed |
| Transcript ↔ audio divergence | `<star>` token + per-boundary confidence; low-conf → VAD-assisted local search, never blind cut |
| Audible clicks from cutting voiced audio | Low-energy safe-cut selection with zero-cross proximity + micro-fades; automated click-detection test in Phase 3 gate |
| Low-SNR references degrade CTC | Spectral subtraction *for emission pass only*; surface SNR warning; keep master untouched |
| Gap counts hide missing boundaries or over-triage clean audio | Treat triage as a calibrated classifier; labeled matrix records false-negative/false-positive rates; user retains Natural/Precise override |
| Fast-path regression | Fallback chain always terminates in today's energy path; snapshot tests on current behavior |
| Non-English / accented refs (e.g. the Aussie sample) | MMS is multilingual (158 langs); pass language; `<star>` absorbs accent-driven mismatch |

---

## 9. Dependencies & Footprint

- **Existing runtime dep:** `onnxruntime` is already installed. The candidate new dependency
  is `ctc-forced-aligner`, used only if Phase 0 proves its normalization/tokenization/alignment
  logic can drive the selected ONNX model without importing a PyTorch model path. No PyTorch
  is added to the serving path. CPU EP is load-bearing; optional OpenVINO/CoreML provider
  availability and wheel compatibility must be detected and validated per platform rather
  than assumed additive.
- **Model asset:** MMS-300M forced-aligner ONNX (~300 MB–1 GB). Ship via the existing
  model-provisioning path; lazy-load on first PRECISE use.
- **License:** default MMS model is CC-BY-NC 4.0 — acceptable per D2. If the project later
  goes commercial, replace it with a permissively licensed aligner behind the same internal
  `align()` contract. Do not assume a one-line model-id swap: vocabulary, normalization,
  language coverage, blank/star tokens, outputs, and score calibration require a new gate.

---

## 10. Open Questions (non-blocking; resolve during build)

1. Should `,` count toward `boundaries_expected` in triage, or only sentence-enders? (Start
   with sentence-enders; make comma weighting a tunable.)
2. Warm-load the aligner at boot (faster first Precise, higher idle RAM) or purely lazy?
   (Default lazy; env flag for warm.)
3. Do we expose detected boundaries as *editable* handles in RegionEditor, or read-only
   overlays first? (Read-only in Phase 3; editable is a fast-follow.)

---

## 11. Success Criteria

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

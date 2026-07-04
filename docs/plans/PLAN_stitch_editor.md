# Plan: VST-style Stitch Editor for Persona Forge / OmniVoice

Status (2026-07-04): Part A ("Persona Forge polish" items, see bottom
section) is **done and deployed to dockermisc1**. Part B (the stitch editor
itself, backend + frontend, steps 1-7 below) is in progress: **step 1
(`audio_post.py` primitives: `trim`, `apply_fades`, `concat_with_padding`,
extended `stitch_segments` kwargs) is done** — implemented, unit-tested
(34/34 passing in `tests/test_audio_post.py`, including an explicit
default-kwargs-match-original-output parity test), not yet deployed. Steps
2-7 (API wiring, frontend timeline) not yet started. Serves as both the
implementation plan and the handoff doc for this feature.

## Context / motivation

Persona Forge's OmniVoice workflow lets a user generate multiple candidate
takes per text segment, pick one take per segment, then hit a single
"Stitch all" button to concatenate the picks into one clip and optionally
save it to the voice library. That one-click stitch has zero editing
control: no reordering, no way to trim generated padding, no way to insert
silence between clips, and no way to tune fades/compression/normalization —
even though the DSP primitives to do most of this already exist in
`audio_post.py`, unused beyond their hardcoded defaults.

The user wants an intermediate "VST-style" timeline/editor step between
"select takes" and "commit stitch," modeled on how a DAW/VST plugin shows and
lets you manipulate clips on a timeline: reorder clips, trim/pad clip edges,
add silence between clips, and control fades/compression before committing
to a final stitch or library save.

This is meaningful multi-file surface area (backend DSP + API + a new
frontend timeline component), so it's scoped here and delivered in
independently-shippable increments rather than one large change.

## Current state (grounding — read this before changing anything)

- **`src/qwen3_tts/audio_post.py`** already has all the DSP primitives needed
  — `compress()`, `normalize_rms()`, `limit_peak()`, `crossfade_concat()`,
  `stitch_segments()` (the orchestrator) — all pure numpy, all
  keyword-configurable. But `stitch_segments()`'s defaults
  (`segment_target_dbfs=-20.0`, `final_target_dbfs=-18.0`,
  `crossfade_ms=100.0`, `final_ceiling_db=-1.0`) are baked in with **no
  override path anywhere in the stack**. `crossfade_concat()` always
  crossfades between clips — there is no padding/silence-insertion mode, and
  no per-clip trim or fade capability at all today.
- **`src/qwen3_tts/omnivoice_engine.py`**: `stitch_selected(selected:
  list[tuple[wav, sr]])` (~line 456) takes a flat list of `(wav, sr)` tuples,
  validates a single common sample rate, and calls
  `audio_post.stitch_segments(wavs, sr)` with no options.
- **`src/qwen3_tts/app.py`**:
  - `POST /omnivoice/stitch` (~line 752, `omnivoice_stitch()`) resolves
    clips via `_resolve_omnivoice_clips` (~line 664) — either `segment_ids`
    (persisted, via `segment_library.py`) or `selections` (ephemeral
    `candidate_id`s in the in-memory `_omnivoice_candidates` cache, NOT
    persisted across restarts) — then calls `stitch_selected` and returns
    raw WAV bytes. Preview-only, no persistence.
  - `POST /omnivoice/save` (~line 773, `omnivoice_save()`) does the same
    resolution + stitch, then calls `voice_library.save_voice(wav_bytes,
    description=instruct, sample_text=..., language=..., selections={engine,
    accent_id, instruct, segments, segment_ids, candidate_ids})`. Response:
    `{voice_id, sample_rate, audio_base64}`.
  - Neither endpoint accepts any per-clip or DSP override today.
- **`src/qwen3_tts/voice_library.py`**: `save_voice(wav_bytes, *,
  description, sample_text, language, seed=None, selections=None)` — disk
  layout `/voices/<voice_id>/{reference.wav,meta.json}`. `selections` is
  already a free-form `dict[str, Any] | None` stored verbatim in
  `meta.json` — no schema migration needed to add new keys to it.
- **`src/qwen3_tts/segment_library.py`**: persisted single takes at
  `/segments/<segment_id>/{clip.wav,meta.json}`; distinct from the
  ephemeral per-audition `_omnivoice_candidates` cache.
- **Frontend `frontend/src/store.ts`**: `ovSegmentRack: SegmentRackRow[]`
  holds `{segmentId, text, candidates, selectedTakeIndex}` — one row per
  segment, `candidates` only ever carry `candidate_id`s (ephemeral), not
  `segment_id`s, since they come straight from an audition run.
- **Frontend `PersonaForgePanel.tsx`**: `handleStitch` (~line 1240) builds a
  flat, ordered `candidateIds` array from `segmentRack` and calls
  `stitchOmniVoice(candidateIds)` (`frontend/src/lib/api.ts` ~line 309,
  POSTs to `/omnivoice/stitch`, returns a `Blob`) → sets `ovStitchedUrl`/
  `ovStitchedBlob`, rendered via `<AudioPlayer src blob />`. `handleSave`
  (~line 1286) does the analogous thing for `/omnivoice/save`.
- **Frontend `Waveform.tsx`**: not canvas/SVG — renders one `motion.div` bar
  per peak value in a flex row, has its own time-axis tick computation and a
  `progress` playhead prop. Always single-clip today (one `Waveform` per
  `AudioPlayer` per candidate/take). **No multi-clip timeline component
  exists.**
- **Frontend `frontend/src/lib/waveform.ts`**: `computePeaks(blob,
  buckets?)` decodes audio client-side via a shared `AudioContext`, mono
  peak-only, returns a normalized peaks array.

## Design

### 1. Backend: "stitch plan" data shape

A JSON-serializable dict, not a new persisted entity — travels in request
bodies and gets embedded verbatim in `voice_library` meta.json for
reproducibility. Clip refs still resolve through the existing
segment-library/ephemeral-cache mechanism; no third clip-storage layer.

```
StitchPlanClip:
  ref: { segment_id: str } | { candidate_id: str }   # exactly one
  trim_start_ms: float = 0.0
  trim_end_ms: float = 0.0
  fade_in_ms: float = 0.0
  fade_out_ms: float = 0.0

StitchPlan:
  clips: list[StitchPlanClip]        # order = timeline order
  padding_ms: list[float]            # len == len(clips) - 1; silence AFTER clip i (0 = crossfade, as today)
  crossfade_ms: float = 100.0        # used where padding_ms[i] == 0
  segment_target_dbfs: float = -20.0
  final_target_dbfs: float = -18.0
  final_ceiling_db: float = -1.0
  compress: { threshold_db, ratio, attack_ms, release_ms } | null   # null = skip compression
```

Example wire payload:

```json
{
  "clips": [
    {"segment_id": "seg_abc123", "trim_start_ms": 0, "trim_end_ms": 40, "fade_in_ms": 10, "fade_out_ms": 30},
    {"candidate_id": "cand_xyz", "trim_start_ms": 15, "trim_end_ms": 0, "fade_in_ms": 20, "fade_out_ms": 20}
  ],
  "padding_ms": [120],
  "crossfade_ms": 100,
  "segment_target_dbfs": -20,
  "final_target_dbfs": -18,
  "final_ceiling_db": -1,
  "compress": {"threshold_db": -24, "ratio": 2.5, "attack_ms": 5, "release_ms": 80}
}
```

### 2. Backend API: additive, not breaking

Both `/omnivoice/stitch` and `/omnivoice/save` accept **either**:
- the current flat shape (`segment_ids`/`selections`) — unchanged behavior, or
- a new `stitch_plan` key.

At the top of each handler: if `data.get("stitch_plan")` is present, parse
and take the new code path; otherwise fall through to today's
`_resolve_omnivoice_clips` + `stitch_selected(selected)` unchanged. The old
flat list is logically just a `StitchPlan` with all-default per-clip values
and all-zero `padding_ms` (crossfade throughout) — the new path can
eventually subsume the old one once proven, without maintaining two
permanently-diverging implementations.

New helper, parallel to `_resolve_omnivoice_clips`:

```python
def _resolve_stitch_plan(data: dict[str, Any]) -> StitchPlan | None:
    """Validate + resolve a stitch_plan payload's clip refs into (wav, sr)
    tuples, reusing the same segment_id/candidate_id resolution as
    _resolve_omnivoice_clips."""
```

Factor a `_resolve_one_clip_ref(ref: dict) -> tuple[wav, sr] | None` out of
`_resolve_omnivoice_clips` so both the flat-list and stitch-plan paths share
one ref-resolution implementation.

### 3. `audio_post.py` changes

Pure additions — no existing signature changes, zero risk to current callers:

```python
def trim(audio, sr, start_ms=0.0, end_ms=0.0) -> np.ndarray:
    """Cut start_ms off the head and end_ms off the tail. Clamped to never
    produce negative-length output; also clamp at the API boundary
    (defense in depth)."""

def apply_fades(audio, sr, fade_in_ms=0.0, fade_out_ms=0.0) -> np.ndarray:
    """Per-clip user-controlled fade at the clip's own head/tail — distinct
    from crossfade_concat's join-fades, applied before any joining."""

def silence(sr, duration_ms) -> np.ndarray:
    """np.zeros helper for inter-clip padding."""

def concat_with_padding(segments, sr, *, padding_ms=None, crossfade_ms=100.0) -> np.ndarray:
    """Join segments; for gap i, if padding_ms[i] > 0 insert that much
    silence with a short fade into/out of the silence (to avoid a click —
    NOT a hard butt join), else crossfade per crossfade_ms exactly as
    crossfade_concat does today. Supersedes crossfade_concat for the new
    code path; crossfade_concat itself stays untouched and is reused/shared
    for the padding_ms[i] == 0 case via a common fade-curve helper."""
```

Extend `stitch_segments(...)` with new optional kwargs, all defaulting to
preserve current behavior exactly: `padding_ms=None`, `trims=None`,
`fades=None`, `compress_params=None`.

Per-segment order of operations (matches the module's existing documented
rationale — dynamics processing before touching seams): trim → compress (if
enabled) → normalize_rms to `segment_target_dbfs` → apply_fades → feed into
`concat_with_padding` → limit_peak → normalize_rms(final) → limit_peak.

`omnivoice_engine.stitch_selected` gets a new optional `plan=` kwarg;
`plan=None` behaves byte-identical to today.

### 4. `voice_library` reproducibility

No changes to `voice_library.py` itself. In `/omnivoice/save`, when a
`stitch_plan` was used, store it verbatim:

```python
selections={
    "engine": "omnivoice",
    "accent_id": accent_id,
    "instruct": instruct,
    "segments": segments,
    "segment_ids": data.get("segment_ids"),
    "candidate_ids": data.get("selections"),
    "stitch_plan": data.get("stitch_plan"),   # None if legacy flat path used
}
```

**Caveat to flag in the UI eventually**: only `segment_id`-based plans are
durably re-editable later — `candidate_id`s live only in the ephemeral
in-memory cache and are gone after a server restart/eviction. If "reopen a
saved voice in the editor" becomes a real near-term goal, the editor should
nudge/require locking clips into the segment library first.

### 5. Frontend store additions (`frontend/src/store.ts`)

```ts
export interface StitchPlanClip {
  clipId: string             // client-generated, for React keys/DnD; not sent to server
  ref: { segmentId: string } | { candidateId: string }
  text: string
  sourceAudioBase64: string  // reused from in-memory candidate/segment payload, no extra fetch
  sampleRate: number
  trimStartMs: number
  trimEndMs: number
  fadeInMs: number
  fadeOutMs: number
}

export interface StitchPlanDsp {
  segmentTargetDbfs: number   // default -20
  finalTargetDbfs: number     // default -18
  finalCeilingDb: number      // default -1
  crossfadeMs: number         // default 100
  compressEnabled: boolean    // default true
  compressThresholdDb: number // default -24
  compressRatio: number       // default 2.5
}

// new store fields:
// ovStitchPlanClips: StitchPlanClip[]
// ovStitchPlanPaddingMs: number[]      // length clips.length - 1
// ovStitchPlanDsp: StitchPlanDsp
// ovStitchEditorOpen: boolean
// ovStitchPreviewUrl: string | null    // live re-rendered preview, distinct from ovStitchedUrl (committed result)
// ovStitchPreviewBlob: Blob | null
// ovIsRenderingPreview: boolean
```

Actions: `setOvStitchPlanClips`, `reorderOvStitchPlanClip(from, to)`,
`updateOvStitchPlanClip(clipId, patch)`, `removeOvStitchPlanClip(clipId)`,
`setOvStitchPlanPaddingAt(gapIndex, ms)`, `setOvStitchPlanDsp(patch)`,
`setOvStitchEditorOpen(v)`.

Keep `ovStitchedUrl`/`ovStitchedBlob`/`ovSavedVoiceId` as-is — those remain
"the final committed stitched result." The new `ovStitchPreview*` fields are
for the editor's live re-render-on-change preview, kept separate so mid-edit
state never clobbers an already-saved/committed result.

### 6. Entry point: segment rack → stitch editor

The "Stitch all" button becomes/gains an "Open stitch editor" affordance
that:
1. Validates every row has a selected take (same check `handleStitch` does today).
2. Builds `ovStitchPlanClips` from `segmentRack` in row order — one
   `StitchPlanClip` per row, `ref = {candidateId: ...}` (rack rows only ever
   carry `candidate_id`s today), all trim/fade params zeroed.
3. Sets `ovStitchPlanPaddingMs` to an all-zero array (defaults to today's
   all-crossfade behavior).
4. Sets `ovStitchEditorOpen = true`.

Keep a "quick stitch with defaults" path for users who don't want the extra
step — this is additive, not a forced replacement of the one-click flow.

Stretch goal (not v1): an "add from segment library" affordance to insert
`segment_id`-based clips (from `ovLibrary`/`SegmentMeta[]`) into the
timeline alongside ephemeral rack candidates.

### 7. New component: `frontend/src/components/StitchTimeline.tsx`

Reuses `waveform.ts::computePeaks` (decode each clip's `audioBase64` once,
memoize per `clipId`) and `Waveform.tsx`'s visual language (bar rendering,
palette, center track line), but needs new layout capability:

- **Proportional horizontal layout**: clips laid out left-to-right sized by
  (post-trim) duration relative to total timeline duration — a real
  timeline ruler, not stacked single-clip players.
- **Padding gaps**: visually distinct (hatched/empty) segment between
  clips, width proportional to `padding_ms[i]`, with a +/- stepper.
- **Trim handles**: draggable or +/- numeric steppers at each clip's edges;
  visually crop the peak bars by slicing the already-computed `peaks` array
  (cheap, no re-decode) — this is a *visual* approximation only, see the
  server-authoritative-playback tradeoff below.
- **Fade overlays**: small triangular gradient at each clip's head/tail
  scaled to `fadeInMs`/`fadeOutMs`.
- **Reorder**: up/down buttons in v1 (simple, keyboard-accessible, no new
  dependency); `framer-motion`'s `Reorder.Group`/`Reorder.Item` as a
  fast-follow (framer-motion is already a dependency, avoids adding a DnD
  library).
- **Numeric inputs alongside any drag handles** for trim/fade/padding, since
  drag-based ms precision is unreliable at typical panel widths.

Component boundary:
```
<StitchTimeline
  clips={ovStitchPlanClips}
  paddingMs={ovStitchPlanPaddingMs}
  onReorder={...}
  onUpdateClip={...}
  onUpdatePadding={...}
  onRemoveClip={...}
  totalDurationSec={...}
/>
```
Internally renders one `<StitchTimelineClip>` per clip and one
`<StitchTimelineGap>` per inter-clip padding slot.

### 8. DSP controls panel

Compact panel (matches the existing `ovShowAdvanced` disclosure pattern):
segment/final target level sliders, final ceiling, crossfade length (used
where gap padding is 0), compression on/off + threshold/ratio. Leave
attack/release at DSP defaults for v1 — exposing 6 knobs is more surface
than useful; threshold + ratio + on/off covers the ask without overwhelming
the UI.

### 9. Live preview

New `frontend/src/lib/api.ts` function:

```ts
export interface StitchPlanPayload {
  clips: { segmentId?: string; candidateId?: string; trimStartMs, trimEndMs, fadeInMs, fadeOutMs }[]
  paddingMs: number[]
  crossfadeMs, segmentTargetDbfs, finalTargetDbfs, finalCeilingDb: number
  compress: { thresholdDb, ratio, attackMs, releaseMs } | null
}
export async function renderStitchPlan(plan: StitchPlanPayload): Promise<Blob> {
  // POST /omnivoice/stitch with { stitch_plan: {...} } — same endpoint, new payload shape, no new route
}
```

Debounce param-change → re-render (400-600ms after the last edit). While a
render is in flight, keep showing the last-good preview audio (don't blank
it) with a "preview stale" indicator. **Server is the source of truth for
actual audio** — trim/fade/compression are only ever visually approximated
client-side (peak-array slicing), never re-implemented in JS, to avoid a
second DSP implementation drifting from `audio_post.py`.

### 10. `handleStitch`/`handleSave` changes

- `handleStitch` becomes the "Render/commit" action inside the editor:
  builds `StitchPlanPayload` from store state, calls `renderStitchPlan`,
  sets `ovStitchedUrl`/`ovStitchedBlob` (the committed result).
- `handleSave` does the same plus passes `stitch_plan` in the
  `/omnivoice/save` body (new field on `OmniVoiceSaveParams`/`saveOmniVoice`).

## Delivery order (each step independently shippable/testable)

1. **`audio_post.py` primitives only** — `trim`, `apply_fades`,
   `concat_with_padding`, extended `stitch_segments` kwargs. No API wired
   yet; unit-testable in isolation; zero risk to running endpoints.
2. **`/omnivoice/stitch` accepts `stitch_plan`** — `_resolve_stitch_plan`,
   widened `stitch_selected(plan=...)`. Curl-testable against a live
   audition before any frontend work exists.
3. **`/omnivoice/save` gets the same treatment** — persists `stitch_plan`
   into `voice_library` meta. Small, mechanical, low risk once step 2 is proven.
4. **Frontend v1: reorder-only editor** — `StitchTimeline` with up/down
   reorder buttons only, no trim/fade/padding/preview yet (reuse existing
   "render on click" flow). Store additions limited to `ovStitchPlanClips` +
   reorder action. Already a real visual win using `Waveform`'s bar
   rendering.
5. **Frontend v2: trim + padding** — trim handles/steppers, padding gap
   controls, debounced live preview via `renderStitchPlan`.
6. **Frontend v3: fades + DSP controls** — fade-in/out per clip,
   compression/normalization panel.
7. **Polish (fast-follow)**: drag-and-drop reorder via `Reorder.Group`,
   "insert from segment library," reopen-a-saved-plan for re-editing.

## Risks / tradeoffs (surfaced up front, decide during implementation, not deferred)

- **`audio_post.compress()` is a per-sample Python loop (not vectorized)** —
  repeated re-renders on every slider tick could be slow for longer clips.
  The debounce window is a mitigation, not a fix; profile during step 5/6 if
  it feels sluggish. A possible optimization (skip compression in preview
  renders when compression params haven't changed) adds pipeline-staging
  complexity — probably not worth it for v1 given clip lengths here are
  seconds, not minutes.
- **Padding-as-silence needs a small fade into/out of the silence itself**
  (separate from user-set clip fades) to avoid a click at the silence
  boundary — decide the exact curve during step 1 implementation, not left
  to the UI layer to work around later.
- **Client-side preview is visual-only, not audio-accurate until a server
  render completes.** Explicit decision: the timeline visually approximates
  trim/padding by slicing/resizing already-computed peak data, but playback
  always reflects the last-rendered server audio. Needs a clear
  "unrendered changes" indicator so users aren't confused when playback
  doesn't yet match a fresh drag/edit.
- **`candidate_id`-based stitch plans can't be faithfully reopened** once
  the ephemeral cache is gone (server restart/eviction) — only
  `segment_id`-based (locked-in) plans are durably re-editable. Decide
  later whether the rack→editor entry point should nudge/require locking
  clips into the segment library first, once "reopen a saved voice" is an
  actual near-term goal.
- **Two parallel stitch code paths (flat list vs. `stitch_plan`) will exist
  in `app.py` for as long as the flat path is kept for backward
  compatibility.** Fine indefinitely if it's also kept as a stable "quick
  stitch" API for any future non-editor caller (e.g. a CLI/script) — just
  don't let it linger as accidental dead code once the frontend fully
  migrates to always sending a `stitch_plan`.

## Related, smaller work bundled in the same session (Persona Forge polish)

Tracked separately/informally, not part of this doc's scope, but landed
alongside it. **All four items DONE and deployed to dockermisc1 as of
2026-07-04** (implemented, `tsc --noEmit` + `npm run build` clean,
`py_compile` clean on backend changes):
- ✅ Moved the "Autoplay takes" toggle out of the segments-only-visible
  header into the always-visible advanced-options panel
  (`PersonaForgePanel.tsx`), so it can be set before generation starts.
- ✅ Waveform x-axis now always shows the clip's exact total duration at the
  far right, even if the last evenly-spaced tick fell short of it
  (`Waveform.tsx`); last label right-aligns instead of overflowing.
- ✅ Added a live-adjustable ASR match-score confidence threshold: new
  `min_match_score` optional param threaded through
  `omnivoice_engine.run_omnivoice_job` (overrides the word-count-based
  short/long thresholds when provided; the 0.6 hard sanity floor is
  unaffected) → `/omnivoice/audition` request body → new
  `ovMinMatchScore` store field → a slider (with an "Auto" pill to clear
  the override) in the advanced-options panel, alongside the existing
  per-candidate debug button (`TakeDebugButton` in `PersonaForgePanel.tsx`,
  left as-is).
- ✅ Segment text is now click-to-edit directly (not just via the pencil
  icon) in `SegmentRackRow`.

Not yet deployed to dockermisc1 — pending explicit go-ahead to push.

## Verification

- Step 1: `python3 -m py_compile src/qwen3_tts/audio_post.py`; extend or add
  unit tests for `audio_post` if a test file exists for it.
- Steps 2-3: `curl -X POST http://<host>:8318/omnivoice/stitch -d
  '{"stitch_plan": {...}}'` against real `candidate_id`s from a live
  audition run, before touching the frontend.
- Steps 4-6: `npx tsc --noEmit` + `npm run build` in `frontend/`, then
  manual browser test — build a multi-clip stitch, reorder, trim, add
  padding, adjust fades/compression, confirm live preview updates and final
  save persists a reproducible `stitch_plan`.
- Deploy per the standard dev-test loop (`docs/DEV_TEST_LOOP.md`): commit +
  push, `git pull` on dockermisc1, `npm run build` there for frontend
  changes, `docker restart qwen3-tts` for backend changes — only after
  explicit user confirmation to deploy.

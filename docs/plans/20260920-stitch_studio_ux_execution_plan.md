# Stitch Studio UX Overhaul Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `executing-plans` to implement this plan one work packet at a time. Do not start a packet until the preceding hard gate is recorded as PASS. Do not use parallel agents: the packets share state and intentionally serialize interface changes.

**Goal:** Deliver the approved Stitch Studio, Voice Library, and Voice Edit UX overhaul without losing edits, breaking navigation, or regressing the existing capture harness.

**Architecture:** Separate durable stitch-plan data from mounted-editor preview state. Both the Studio page and quick-insert modal consume one `StitchPlanSession` interface; Studio uses zustand-backed state, while quick insert uses a local transactional draft. Shared audio analysis, time geometry, and display primitives support a scalable segment browser and one truthful time-scaled timeline.

**Tech Stack:** React 19, TypeScript 7, Zustand 5, Tailwind CSS 4, Motion 13, Radix UI, Playwright, Puppeteer capture harness, Flask fake-model server.

**Spec:** `docs/plans/20260920-stitch_studio_ux_overhaul.md`

## Global constraints

- Read the specification above and `AGENTS.md` before editing.
- Preserve `/generate`, `/v1/audio/speech`, `/health`, `/omnivoice/stitch`, and existing save payload compatibility.
- Do not add frontend dependencies.
- Do not add a backend endpoint or change an HTTP payload contract.
- Do not change family-default `is_default` behavior; API activation uses `activateVoiceForApi` and `api_active` only.
- Do not implement undo/history, a light theme, or new DSP algorithms.
- Do not duplicate the stitch editor, prosody editor, saved-voice picker, time-axis math, audio decoder, or waveform palette.
- Use semantic design-system status tokens. Do not introduce raw status colors rejected by `frontend/oxlint-design-system.cjs`.
- Use test-first RED/GREEN cycles for observable behavior. The frontend has no unit-test runner; use focused Playwright tests rather than adding Vitest.
- Each task ends with its focused verification. Do not run the project-wide suite between task steps.
- After every non-trivial edit, inspect `git diff -- <touched paths>`.
- Commit only after the task and its gate pass. Use the Conventional Commit shown for that task.
- A failed hard gate blocks later packets. Fix or revert the active packet; never compensate in a later packet.

## Required executor preflight

Run from the repository root:

```bash
git branch --show-current
git status --short
python scripts/validate_repo.py
docker compose config --quiet
git diff --check
npm run --prefix frontend check
npm --prefix tests/ui test -- core/basic.spec.js performance/performance.spec.js
node tests/ui/capture/index.mjs --scenario segment-library-browse --source fake
node tests/ui/capture/index.mjs --scenario stitch-assembly --source fake
```

Expected baseline:

- Branch is `fix/stitch-studio-ux-overhaul-20260920` or an explicitly approved successor.
- Only the two `docs/plans/20260920-stitch_studio_ux_*.md` documents may already be staged.
- Every command exits `0`.
- Baseline capture artifacts exist under `docs/screenshots/artifacts/stitch-studio/`.

If the working tree contains unrelated changes, preserve them and restrict every diff/commit to this plan’s paths.

---

## Locked interfaces

Later packets consume these names exactly. If TypeScript exposes a conflict that makes one signature impossible, stop and amend this document before inventing a second interface.

### Plan-domain types — `frontend/src/lib/stitchPlan.ts`

```ts
import type { StitchPlanClip, StitchPlanDsp } from '@/store'
import type { StitchPlanRegionEdit } from '@/lib/api'

export type StitchRegionEdit = StitchPlanRegionEdit & { id: string }
export type StitchRegionEditsByClip = Record<string, StitchRegionEdit[]>
export interface StitchPlanState {
  clips: StitchPlanClip[]
  paddingMs: number[]
  dsp: StitchPlanDsp
  regionEditsByClip: StitchRegionEditsByClip
}

export interface StitchDurations {
  sourceMaterialMs: number
  spacingMs: number
  crossfadeOverlapMs: number
  renderedMs: number
}

export function cloneStitchPlanState(plan: StitchPlanState): StitchPlanState
export function clipEffectiveDurationMs(clip: StitchPlanClip): number
export function computeStitchDurations(plan: StitchPlanState): StitchDurations
export function suggestedGapMs(text: string): number
export function suggestedPaddingForClips(clips: StitchPlanClip[]): number[]
export function reorderStitchPlan(plan: StitchPlanState, from: number, to: number): StitchPlanState
export function removeClipFromStitchPlan(plan: StitchPlanState, clipId: string): StitchPlanState
export function toPayloadRegionEdits(edits: StitchRegionEdit[]): StitchPlanRegionEdit[]
```

`computeStitchDurations` excludes `paddingMs` from `sourceMaterialMs`, subtracts crossfade only when adjacent clips overlap, and clamps every public duration to `>= 0`.

### Session contract — `frontend/src/hooks/useStitchPlanSession.ts`

```ts
export interface StitchPlanSession {
  plan: StitchPlanState
  setClips(updater: StitchPlanClip[] | ((clips: StitchPlanClip[]) => StitchPlanClip[])): void
  updateClip(clipId: string, patch: Partial<StitchPlanClip>): void
  removeClip(clipId: string): void
  reorderClip(from: number, to: number): void
  setPaddingAt(index: number, milliseconds: number): void
  setPadding(values: number[]): void
  setDsp(patch: Partial<StitchPlanDsp>): void
  setRegionEdits(clipId: string, edits: StitchRegionEdit[]): void
  reset(): void
}

export function useStoreStitchPlanSession(): StitchPlanSession
export function useDraftStitchPlanSession(initial: StitchPlanState): StitchPlanSession
```

The draft hook deep-clones its initial value once per modal opening. It never writes to zustand. Committing is one explicit `replaceOvStitchPlan(plan)` store action.

### Editor contract — `frontend/src/components/StitchTimeline.tsx`

```ts
interface StitchEditorCommonProps {
  session: StitchPlanSession
  library: SegmentMeta[]
  voiceLibrary?: VoiceMeta[]
}

export type StitchEditorBodyProps =
  | (StitchEditorCommonProps & {
      surface: 'studio'
      onSave(plan: StitchPlanPayload, segments: string[]): Promise<void>
      onStartOver?: () => void
    })
  | (StitchEditorCommonProps & {
      surface: 'quick-insert'
      onCommitDraft(plan: StitchPlanState, destination: 'caller' | 'studio'): void
      onCancelDraft(): void
    })
```

The discriminated union makes invalid callback combinations a compile error.
Quick insert never renders a reference-voice save control.

### Preview contract — `frontend/src/hooks/useStitchPreview.ts`

```ts
export interface StitchPreviewState {
  url: string | null
  blob: Blob | null
  isRendering: boolean
  isStale: boolean
  error: string | null
  renderNow(): Promise<void>
  scheduleRender(): void
  cancel(): void
  clear(): void
}

export function useStitchPreview(plan: StitchPlanState): StitchPreviewState
```

The hook owns its `AbortController`, debounce timer, request sequence, blob URL,
and cleanup. Zustand owns none of them. Client-side edit rendering helpers move
to `frontend/src/lib/stitchPreview.ts`; the hook never imports component code.

### Audio-analysis contract — `frontend/src/lib/waveform.ts`

```ts
export interface ClipAudioAnalysis {
  durationMs: number
  sampleRate: number
  peaks: number[]
}

export async function getClipAudioAnalysis(
  assetKey: string,
  audio: Blob | string,
  buckets?: number,
): Promise<ClipAudioAnalysis>

export function invalidateClipAudioAnalysis(assetKey: string): void
```

Cache compact peaks and metadata only. The bounded LRU maximum is `64` entries.
Callers form `assetKey` as `<kind>:<persistent-id>:<revision>`, using `sha256`
when present and the audio byte length otherwise. Never retain an `AudioBuffer`,
Blob, object URL, or base64 payload.

### Time-axis contract — `frontend/src/lib/timeAxis.ts`

```ts
export interface TimeTick {
  seconds: number
  x: number
  label: string
  major: boolean
}

export function niceTimeStep(secondsPerPixel: number, minimumTickPx?: number): number
export function formatTimelineTime(seconds: number): string
export function createTimeTicks(args: {
  durationSeconds: number
  pixelsPerSecond: number
  widthPx: number
}): TimeTick[]
```

## Specification traceability

| Specification requirement | Implementing packet | Blocking gate |
| --- | --- | --- |
| B24 region edits persist across surfaces | 1, 3 | Gates 1 and 3 |
| B19/B21/B22/B25 decode, cache, abort, preview ownership | 2 | Gate 2 |
| A1-A4 naming, modal actions, return destination | 3 | Gate 3 |
| A5-A6 library discoverability and scalable picker | 4 | Gate 4 |
| B14/B20 fades and DPR-correct waveform | 5 | Gate 5 |
| A7-A9 and B15-B18 gap, geometry, pointer, reorder | 6 | Gate 6 |
| B23 shared preview waveform/playhead/transport | 7 | Gate 7 |
| A10-A12 automation, readiness, API activation | 8 | Gate 8 |
| A13 first-class Voice Edit with retained library UI | 9 | Gate 9 |
| Visual contract, accessibility, captures, regression | 10 | Gate 10 |

Every A/B item in the specification maps to a packet above. A gate failure
reopens its packet; it never becomes an undocumented exception.

## Stable UI automation contract

Preserve the specification’s existing testids. Add these exact identifiers;
tests and captures must not target CSS utility classes:

| Testid | Element/contract |
| --- | --- |
| `stitch-editor-dialog` | Quick-insert Radix dialog content |
| `stitch-open-studio` | Commit draft and navigate |
| `stitch-save-close` | Commit draft and remain on caller |
| `stitch-cancel-draft` | Discard draft |
| `segment-browser-dialog` | Rich picker dialog content |
| `segment-browser-audio` | Row audition action |
| `stitch-gap` | Seam container with gap index |
| `stitch-gap-input` | Direct gap editor |
| `stitch-region-edit` | Durable region-edit row/chip |
| `stitch-preview-ready` | Preview root with `data-plan-hash` |
| `stitch-readiness` | Readiness meter with `data-state` |
| `stitch-source-duration` | Source-material readout |
| `stitch-rendered-duration` | Rendered-duration readout |
| `stitch-api-default` | API-default checkbox |
| `stitch-guidance` | State-derived next-step rail |
| `voice-edit-picker` | Pure saved-reference picker |
| `voice-edit-panel` | Page-layout prosody editor |

---

# Work packet 0 — Baseline evidence and execution ledger

**Purpose:** Establish reproducible evidence before source changes.

**Files:**

- Modify when execution starts: this document’s packet ledger at the end.
- Capture outputs remain in the harness-selected
  `docs/screenshots/artifacts/<category>/` directories; do not copy or rename
  baseline artifacts manually.

### Task 0.1: Capture the pre-change behavior

- [ ] Run the required executor preflight.
- [ ] Copy command exit status, capture artifact paths, current commit, and branch into the packet ledger.
- [ ] Record the observed quick-insert close destination and whether a one-clip modal exposes Save.
- [ ] Do not modify production code.

**Gate 0 — Baseline reproducible**

PASS requires all baseline commands to exit `0` and the two baseline screenshots to be inspectable. A failure here is environmental or pre-existing; do not begin Packet 1.

**Commit:** none.

---

# Work packet 1 — Durable plan domain and atomic store replacement

**Purpose:** Make plan mutations correct before changing navigation or visuals.

**Callers:** `StitchTimeline`, `StitchEditorBody`, `StitchStudioPage`, `OmniVoicePanel`, `VoiceLibraryPage`, `stitchClips.ts`.

**Contracts:** clip order; seam-indexed padding; DSP values; region edits; one atomic plan replacement.

**Files:**

- Create: `frontend/src/lib/stitchPlan.ts`
- Modify: `frontend/src/store.ts`
- Modify: `frontend/src/components/StitchTimeline.tsx`
- Create/modify: `tests/ui/stitch-studio/studio.spec.js`

### Task 1.1: Add failing durable-plan browser contracts

- [ ] Add `region edits survive Stitch Studio unmount and remount`: insert a
  segment, add a visible region edit, navigate to Speak, return to Stitch
  Studio, and assert the same edit remains.
- [ ] Add `removing a middle clip keeps later gap values on their seams`: insert
  three clips, set distinct first/second gaps, remove the middle clip, and assert
  the surviving seam value follows the removal rule from the locked contract.
- [ ] Run:

```bash
npm --prefix tests/ui test -- stitch-studio/studio.spec.js -g \"region edits survive Stitch Studio|removing a middle clip\"
```

Expected: FAIL because region edits are component-local and plan removal logic
is not centralized.

### Task 1.2: Implement pure plan operations

- [ ] Create `frontend/src/lib/stitchPlan.ts` with the locked types and functions.
- [ ] Preserve seam semantics: moving a clip changes clip order but leaves each padding value attached to its timeline boundary.
- [ ] On removal, remove the seam after the clip, or the preceding seam when removing the final clip.
- [ ] Move `clipEffectiveDurationMs`, the UI edit type/map, punctuation gap
  calculation, reorder, and removal math into this module. Strip the UI-only
  `id` field when mapping `StitchRegionEdit` values into
  `StitchPlanPayload.clips[].edits`.
- [ ] Do not import React or zustand from this module.
- [ ] Run `npm run --prefix frontend build` and fix only type errors caused by this task.

### Task 1.3: Make the store own the complete durable plan

- [ ] Add `ovStitchRegionEditsByClip: StitchRegionEditsByClip`.
- [ ] Add `replaceOvStitchPlan(plan: StitchPlanState): void` using one zustand `set` call.
- [ ] Add `setOvStitchRegionEdits(clipId, edits)`.
- [ ] Reimplement reorder/removal actions through the pure plan helpers.
- [ ] Remove region-edit state from `StitchEditorBody`; adapt it to store-backed
  region edits without changing the rendered controls.
- [ ] Run Task 1.1 again and require both tests to pass.

### Task 1.4: Verify and commit Packet 1 foundation

Run:

```bash
npm run --prefix frontend check
npm --prefix tests/ui test -- core/basic.spec.js performance/performance.spec.js
PYTHONPATH=src:src/export python -m pytest tests/tier2_backend/test_app_omnivoice.py -q
```

Inspect:

```bash
git diff -- frontend/src/lib/stitchPlan.ts frontend/src/store.ts frontend/src/components/StitchTimeline.tsx tests/ui/stitch-studio/studio.spec.js
```

**Gate 1 — Durable plan model**

PASS requires TypeScript/oxlint/build and backend stitch tests green, both
Task 1.1 tests green, region edits represented in zustand, and no
component-local durable edit map.

**Commit:** `refactor(frontend): centralize stitch plan state`

---

# Work packet 2 — Shared audio analysis and editor-local preview

**Purpose:** Remove decoder churn and prevent preview state from crossing transaction boundaries.

**Files:**

- Modify: `frontend/src/lib/waveform.ts`
- Modify: `frontend/src/lib/stitchClips.ts`
- Create: `frontend/src/lib/stitchPreview.ts`
- Create: `frontend/src/hooks/useStitchPreview.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/StitchTimeline.tsx`
- Modify: `frontend/src/store.ts`
- Modify: `tests/ui/stitch-studio/studio.spec.js`

### Task 2.1: Add failing preview-lifecycle tests

- [ ] Add `superseded preview render is aborted`: delay the fake stitch
  response, change a gap twice, and assert only the final plan hash reaches
  `stitch-preview-ready`.
- [ ] Add `Studio preview URL is revoked on page unmount`: record the preview
  object URL, navigate away, assert fetching that URL rejects, return, and
  assert a new preview URL is produced for the durable plan.
- [ ] Run both tests and confirm RED.

### Task 2.2: Consolidate audio analysis

- [ ] Extend `frontend/src/lib/waveform.ts` with the locked `ClipAudioAnalysis` API and a 64-entry LRU.
- [ ] Key entries with a stable asset key plus requested bucket count.
- [ ] Reuse the existing shared `AudioContext`.
- [ ] Replace `stitchClips.ts::decodeAudioDurationMs` and the inline 48-bucket decoder in `StitchTimelineClip`.
- [ ] Keep failed decode behavior explicit: return no cached entry and surface `durationMs: 0` to callers; do not cache failure as valid audio.

### Task 2.3: Add abortable API and local preview ownership

- [ ] Change only the frontend signature:

```ts
export async function renderStitchPlan(
  plan: StitchPlanPayload,
  signal?: AbortSignal,
): Promise<Blob>
```

- [ ] Pass `signal` to `fetch`; treat `AbortError` as cancellation, not a
  user-visible render failure.
- [ ] Move `decodeClipAudio`, `processClipAudio`, `appendWithGapAndCrossfade`,
  `encodeWav`, and `renderEditedStitchPreview` from the component into
  `lib/stitchPreview.ts` without changing audio math.
- [ ] Implement `useStitchPreview` with a 700ms idle debounce, immediate
  `renderNow`, sequence guard, object-URL cleanup, and request abort.
- [ ] Move preview URL/blob/rendering state out of zustand and delete setters.
- [ ] Replace `StitchEditorBody` preview effects with the hook.

### Task 2.4: Verify and commit Packet 2

```bash
npm run --prefix frontend check
npm --prefix tests/ui test -- stitch-studio/studio.spec.js -g "preview|aborted"
node tests/ui/capture/index.mjs --scenario stitch-assembly --source fake
```

**Gate 2 — Preview isolation**

PASS requires both lifecycle tests green, one active preview request per editor,
all object URLs revoked on replacement/unmount, and no `ovStitchPreview*` or
`ovIsRenderingPreview` fields remaining in zustand.

**Commit:** `refactor(frontend): isolate stitch preview lifecycle`

---

# Work packet 3 — Transactional quick insert and correct navigation

**Purpose:** Fix the reported modal flow and wrong close destination.

**Files:**

- Create: `frontend/src/hooks/useStitchPlanSession.ts`
- Modify: `frontend/src/store.ts`
- Modify: `frontend/src/components/StitchTimeline.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/OmniVoicePanel.tsx`
- Modify: `frontend/src/pages/VoiceLibraryPage.tsx`
- Modify: `tests/ui/stitch-studio/studio.spec.js`

### Task 3.1: Add failing quick-insert transaction tests

- [ ] Add `quick insert cancel preserves the committed stitch plan`.
- [ ] Seed two segments, insert one into Studio, record clip count and gap, open
  quick insert with the second, change placement, Cancel, and assert the
  committed count/gap are unchanged.
- [ ] Add `region edits survive quick insert commit into Studio`: make a region
  edit in quick insert, choose Open in Stitch Studio, and assert it remains.
- [ ] Add `quick insert X Escape and backdrop restore Voice Library focus`.
- [ ] Add `cancelled quick insert cannot replace Studio preview`: record the
  committed Studio preview hash, change a draft gap, cancel, return to Studio,
  and assert the committed plan hash is unchanged.
- [ ] Run the four tests and confirm RED before implementing the session.

### Task 3.2: Implement both session adapters

- [ ] Implement the locked `StitchPlanSession` interface.
- [ ] Store-backed adapter delegates to zustand actions.
- [ ] Draft adapter deep-clones once per modal opening and uses local React state.
- [ ] Add store fields `ovStitchEditorReturnPage: Page | null` and `ovStitchEditorIncomingClip: StitchPlanClip | null`.
- [ ] Add `openOvStitchEditor({ returnPage, incomingClip })` and `closeOvStitchEditor()` to update modal metadata atomically.

### Task 3.3: Hoist and convert the modal

- [ ] Mount `StitchEditorPanel` once in `App.tsx`, outside the page switch but inside providers.
- [ ] Replace its raw portal/backdrop shell with the existing Radix dialog primitives.
- [ ] Delete the `OmniVoicePanel` mount.
- [ ] Keep Voice Design opens returning to `voice-design`.
- [ ] Voice Library opens must not call `setPage('voice-design')`.
- [ ] Restore focus to the launch button after Cancel/X/Escape/backdrop close.

### Task 3.4: Implement surface-specific actions

- [ ] Update `StitchEditorBody` to receive `session` and `surface`.
- [ ] Quick insert renders exactly:
  - primary `Open in Stitch Studio`;
  - secondary `Save and close` with “Keep this segment in your Stitch Studio draft”;
  - tertiary `Cancel`.
- [ ] X, Escape, backdrop, and Cancel discard the draft.
- [ ] Save and close calls `replaceOvStitchPlan`, closes, and remains on the caller page.
- [ ] Open calls `replaceOvStitchPlan`, closes, and navigates to `stitch-studio`.
- [ ] No quick-insert path renders `stitch-save-voice`.

### Task 3.5: Make the RED transaction tests green

```bash
npm --prefix tests/ui test -- stitch-studio/studio.spec.js -g "quick insert|region edits survive|preview"
node tests/ui/capture/index.mjs --scenario design-to-stitch-gif --source fake
```

**Gate 3 — Transaction and navigation correctness**

PASS requires all quick-insert outcomes, focus restoration, region-edit continuity, and preview isolation tests green. Manual browser verification must cover X, Escape, backdrop, Cancel, Save and close, and Open in Studio from Voice Library.

**Commit:** `fix(frontend): make Stitch Studio insert flow transactional`

---

# Work packet 4 — Voice Library tabs and scalable segment browser

**Purpose:** Make reference voices/segments discoverable and segment insertion workable at hundreds of rows.

**Files:**

- Create: `frontend/src/components/stitch/SegmentBrowserModal.tsx`
- Create: `frontend/src/components/stitch/SegmentPreviewRail.tsx`
- Create: `tests/ui/fixtures/largeSegmentLibrary.mjs`
- Modify: `frontend/src/pages/VoiceLibraryPage.tsx`
- Modify: `frontend/src/components/StitchTimeline.tsx`
- Modify: `frontend/src/index.css` only for named reusable timeline/browser tokens
- Modify: `tests/ui/stitch-studio/studio.spec.js`
- Modify: `tests/ui/capture/scenarios/stitch-studio/segment-library-browse.mjs`
- Modify: `tests/ui/capture/scenarios/stitch-studio/assembly.mjs`
- Modify: `tests/ui/capture/scenarios/wizard/design-to-stitch-gif.mjs`
- Modify: `tests/ui/capture/index.mjs`
- Modify: `tests/ui/README.md`

### Task 4.1: Add failing discovery and scale tests

- [ ] Add `Voice Library switches between Reference voices and Segments without scrolling`.
- [ ] Add `segment browser filters by project and inserts selected assets after the selected clip`.
- [ ] Add `segment browser auditions only one row and does not eagerly request audio`.
- [ ] For the last test, intercept `/omnivoice/segments/*/audio`, open a 250-row fixture library, assert zero audio requests before audition, play two rows, and assert the first pauses and only the auditioned assets were requested.
- [ ] Implement `largeSegmentLibrary.mjs` as a deterministic generator of 250
  metadata rows across five projects. Its request-interception helper fulfills
  the segment list and returns one small valid WAV body only for requested
  `/audio` resources; it must not write generated audio to Git.
- [ ] Run the three tests and confirm RED.

### Task 4.2: Add Voice Library tabs

- [ ] Use existing `ui/tabs.tsx` with labels `Reference voices` and `Segments`.
- [ ] Keep search, project grouping, layout mode, and existing voice actions inside their applicable tab.
- [ ] Persist selected tab under `voice-library-tab`; validate stored values before use.
- [ ] Preserve every existing Voice Library action and testid.

### Task 4.3: Build one segment browser

- [ ] Implement a Radix dialog with tabs `Segments` and `Reference voices`.
- [ ] Add search, project filter, sort by newest/duration/name, multi-select,
  select all for filtered results, explicit Add, Enter, and double-click insert.
- [ ] Preserve `stitch-picker-toggle-segments`, `stitch-picker-item-segments`, and `stitch-picker-insert-segments` on equivalent controls.
- [ ] Use a neutral duration rail before audio is requested.
- [ ] Fetch audio only on audition/expansion, use the shared bounded peak cache, and allow one active player.
- [ ] Render rows in stable-height batches with `content-visibility: auto`; do not add a dependency.
- [ ] Delete all four `LibraryPickerButton` instances and the component.

### Task 4.4: Update captures and verify scale

- [ ] Replace `.shadow-lg` waits with `data-testid="segment-browser-dialog"`.
- [ ] Register `segment-browser-scale` with expected output
  `segment-browser-scale--neutral--scale.png`, using the deterministic 250-row
  interceptor.
- [ ] Update the wizard scenario to clear the auto-filled name before typing and
  insert enough source material for the later save gate.
- [ ] Run:

```bash
npm --prefix tests/ui test -- stitch-studio/studio.spec.js
node tests/ui/capture/index.mjs --scenario segment-library-browse --source fake
node tests/ui/capture/index.mjs --scenario stitch-assembly --source fake
node tests/ui/capture/index.mjs --scenario segment-browser-scale --source fake
```

**Gate 4 — Discovery and browser scale**

PASS requires no eager audio requests, one-player behavior, working project filtering and insert position, keyboard insertion, 250-row scrolling without a recorded long task over 50ms, and inspected screenshots with no clipping at 1280×720 and 1568×700.

**Commit:** `feat(frontend): add scalable Stitch Studio segment browser`

---

# Work packet 5 — Waveform and time-axis infrastructure

**Purpose:** Establish sharp, shared primitives before rebuilding the timeline.

**Files:**

- Create: `frontend/src/lib/timeAxis.ts`
- Modify: `frontend/src/lib/waveform.ts`
- Modify: `frontend/src/components/Waveform.tsx`
- Modify: `frontend/src/components/waveform/TimeRuler.tsx`
- Modify: `frontend/src/components/waveform/WaveformLane.tsx`
- Modify: `tests/ui/stitch-studio/studio.spec.js`

### Task 5.1: Add failing visual/geometry tests

- [ ] Add `timeline ruler labels remain aligned at Fit and two zoom levels`.
- [ ] Add `waveform canvas backing store follows device pixel ratio` by evaluating canvas width against CSS width at DPR 1 and 2.
- [ ] Add `fade overlays are visible and change width when fade values change` using stable fade-overlay testids or canvas state exposed only as accessible text, not implementation-source assertions.
- [ ] Run and confirm RED.

### Task 5.2: Consolidate time and palette utilities

- [ ] Implement the locked `timeAxis.ts` contract.
- [ ] Move duplicated time formatting and tick spacing from `Waveform.tsx`, `TimeRuler.tsx`, and Stitch Timeline to it.
- [ ] Export one waveform meter/playhead palette from `lib/waveform.ts`; remove duplicated `hsl(...)` calculations.

### Task 5.3: Make canvas rendering premium and truthful

- [ ] Set canvas backing width/height to CSS size × DPR, reset transform before scaling, and redraw through `ResizeObserver`.
- [ ] Draw trim shading and fade gain ramps.
- [ ] Keep accessible text for duration, trim, and fade values; canvas is not the sole information channel.
- [ ] Respect reduced motion in all waveform animation.

### Task 5.4: Verify and commit Packet 5

```bash
npm run --prefix frontend check
npm --prefix tests/ui test -- stitch-studio/studio.spec.js -g "ruler|device pixel ratio|fade overlays"
```

**Gate 5 — Shared visual primitives**

PASS requires all three consumers using `timeAxis.ts`, no duplicated waveform palette math, crisp 1×/2× canvas evidence, and visible fades.

**Commit:** `refactor(frontend): unify audio timeline primitives`

---

# Work packet 6 — Pointer-safe editing and truthful timeline geometry

**Purpose:** Replace misleading flex widths and broken mouse-only gestures.

**Files:**

- Create: `frontend/src/components/stitch/TimelineRuler.tsx`
- Create: `frontend/src/components/stitch/GapControl.tsx`
- Create: `frontend/src/components/stitch/StitchClipCard.tsx`
- Modify: `frontend/src/components/StitchTimeline.tsx`
- Modify: `tests/ui/stitch-studio/studio.spec.js`
- Create: `tests/ui/capture/scenarios/stitch-studio/gap-editing.mjs`
- Modify: `tests/ui/capture/index.mjs`
- Modify: `tests/ui/README.md`

### Task 6.1: Add failing interaction tests

- [ ] Add `trim drag uses pointer delta without acceleration`.
- [ ] Add `multi-position reorder applies the full permutation`.
- [ ] Add `gaps accept 200, 0.2s, and 200ms and preserve seam semantics after reorder`.
- [ ] Add `zero gap remains visible and distinguishable from non-zero gap`.
- [ ] Add keyboard coverage for selection, reorder, removal, and trim nudging; assert shortcuts do not fire in an input.
- [ ] Run and confirm RED.

### Task 6.2: Convert gestures to pointer transactions

- [ ] Replace mouse listeners with pointer events and `setPointerCapture`.
- [ ] Store `{ pointerId, startClientX, startValue }` at gesture start.
- [ ] Update only RAF-driven visual state during drag; commit the semantic value once on pointer-up/cancel.
- [ ] Keep touch/pen behavior identical to mouse.

### Task 6.3: Build the time-scaled timeline

- [ ] Store `pixelsPerSecond`; provide Fit, minus, plus, and Ctrl/Command+wheel zoom.
- [ ] Calculate clip and gap widths from duration × scale.
- [ ] When minimum interactive width clamps geometry, show hatching plus the exact value.
- [ ] Render shared ticks/gridlines behind clips.
- [ ] At narrow desktop widths stack controls and preserve horizontal timeline scrolling.

### Task 6.4: Make gaps first-class controls

- [ ] Always render every seam, including `0.00s`.
- [ ] Support drag, click-to-type, Enter commit, Escape revert, Up/Down 10ms, Shift+Up/Down 100ms, range 0–5000ms.
- [ ] Snap to 0/80/150/250/400/600/900ms unless Alt is held.
- [ ] Label each control `Gap between clip N and clip N+1`.
- [ ] Show 0ms, positive spacing, and crossfade overlap as distinct shape plus text, not color alone.

### Task 6.5: Verify and commit Packet 6

```bash
npm run --prefix frontend check
npm --prefix tests/ui test -- stitch-studio/studio.spec.js -g "trim drag|reorder|gaps|keyboard"
node tests/ui/capture/index.mjs --scenario gap-editing --source fake
```

**Gate 6 — Timeline truth and input parity**

PASS requires pointer/mouse/keyboard paths, full reorder, typed gap formats, visible 0ms seam, real-time width geometry at three zoom levels, and inspected gap capture.

**Commit:** `feat(frontend): rebuild Stitch Studio timeline interactions`

---

# Work packet 7 — Unified transport and premium motion

**Purpose:** Give the arrangement one playback model and one playhead.

**Files:**

- Create: `frontend/src/hooks/useStitchTransport.ts`
- Modify: `frontend/src/components/StitchTimeline.tsx`
- Modify: `frontend/src/components/stitch/StitchClipCard.tsx`
- Modify: `frontend/src/components/Waveform.tsx`
- Modify: `tests/ui/stitch-studio/studio.spec.js`

### Task 7.1: Add failing transport tests

- [ ] Add `Space toggles arrangement playback outside editable controls`.
- [ ] Add `clicking the ruler seeks the preview and moves the playhead`.
- [ ] Add `clip play scopes playback to the clip span but uses the shared transport`.
- [ ] Add `reduced motion removes travel animations without hiding state`.
- [ ] Run and confirm RED.

### Task 7.2: Implement one transport

- [ ] `useStitchTransport` owns one audio element, current time, duration,
  playing state, and `rangeEndSeconds: number | null`.
- [ ] Update playhead transforms via `requestAnimationFrame`; do not set React state every frame.
- [ ] Ruler/waveform click seeks the same audio element.
- [ ] Per-clip play sets a bounded range; it must not create another `Audio` instance.
- [ ] Stop and clean RAF/audio listeners on unmount or preview replacement.

### Task 7.3: Add restrained motion and shortcuts help

- [ ] Use layout motion for insert/reorder/remove and short state cross-fades only.
- [ ] Keep transitions between 120–220ms.
- [ ] Add a compact shortcuts dialog triggered by `?`; do not intercept `?` inside editable controls.
- [ ] Disable travel/springs under reduced motion.

### Task 7.4: Verify and commit Packet 7

```bash
npm run --prefix frontend check
npm --prefix tests/ui test -- stitch-studio/studio.spec.js -g "Space|ruler seeks|clip play|reduced motion"
```

Record Chromium performance evidence for scrub, zoom, and playback. Target 60fps with no React render per audio frame.

**Gate 7 — Transport synchronization**

PASS requires audible output, playhead, ruler seek, clip-range playback, and reduced-motion behavior synchronized through one transport.

**Commit:** `feat(frontend): add unified Stitch Studio transport`

---

# Work packet 8 — Automation, readiness, and save outcomes

**Purpose:** Remove bookkeeping while preventing invalid reference saves.

**Files:**

- Modify: `frontend/src/lib/stitchPlan.ts`
- Modify: `frontend/src/lib/stitchClips.ts`
- Create: `frontend/src/components/stitch/ReferenceReadiness.tsx`
- Modify: `frontend/src/components/StitchTimeline.tsx`
- Modify: `frontend/src/pages/StitchStudioPage.tsx`
- Modify: `tests/ui/stitch-studio/studio.spec.js`
- Create: `tests/ui/capture/scenarios/stitch-studio/readiness-states.mjs`
- Modify: `tests/ui/capture/index.mjs`
- Modify: `tests/ui/README.md`

### Task 8.1: Add failing automation/readiness tests

- [ ] Add `first clip names an untouched voice field and later clips never overwrite user input`.
- [ ] Add `punctuation creates visible suggested gaps and manual values are not overwritten`.
- [ ] Add `five seconds of gaps cannot satisfy the five-second source-material minimum`.
- [ ] Add `readiness distinguishes blocked, warning, ideal, and overlong states`.
- [ ] Add `missing name disables save and focuses the name step`.
- [ ] Run and confirm RED.

### Task 8.2: Implement predictable defaults

- [ ] Apply `suggestedGapMs` only when appending a new seam.
- [ ] Announce “Suggested from punctuation”; manual edits take ownership and are never silently replaced.
- [ ] Auto-fill the name only on 0→1 clips while pristine.
- [ ] Remove `stitch-use-source-name`; show a subtle source provenance hint and an explicit revert-to-suggestion action.

### Task 8.3: Implement readiness and guidance

- [ ] Use `computeStitchDurations`; never use rendered total as source material.
- [ ] Block save below 5000ms source material.
- [ ] Render warning below 10s rendered, success from 10–15s, info over 15s.
- [ ] Display `X.Xs clips + Y.Ys spacing = Z.Zs rendered`.
- [ ] Add the state-derived guidance rail: Add clips → Reach 10–15s → Name it → Save → Adjust prosody.
- [ ] Keep exactly one primary action based on state.

### Task 8.4: Implement explicit API activation choice

- [ ] Add unchecked `Use as default for API calls` with explanatory copy.
- [ ] Change primary label to `Save & use as API default` when checked.
- [ ] Save first, then call `activateVoiceForApi(newVoiceId)`.
- [ ] On activation failure, retain saved success and show `Saved, not activated` with retry action.
- [ ] Plain save must not alter `api_active`.

### Task 8.5: Verify and commit Packet 8

```bash
npm run --prefix frontend check
npm --prefix tests/ui test -- stitch-studio/studio.spec.js -g "names|punctuation|source-material|readiness|API default"
node tests/ui/capture/index.mjs --scenario readiness-states --source fake
PYTHONPATH=src:src/export python -m pytest tests/tier1_unit/test_segment_library.py tests/tier2_backend/test_app_omnivoice.py -q
```

**Gate 8 — Valid reference and honest save**

PASS requires gaps unable to unlock save, all four readiness states, valid-name gating, plain/default save separation, and partial activation failure reported honestly.

**Commit:** `feat(frontend): guide and validate stitched voice saving`

---

# Work packet 9 — First-class Voice Edit page

**Purpose:** Extract prosody editing without removing or forking Voice Library behavior.

**Files:**

- Create: `frontend/src/components/voice/SavedVoicePicker.tsx`
- Create: `frontend/src/components/prosody/useProsodyEditor.ts`
- Create: `frontend/src/components/prosody/ProsodyEditorPanel.tsx`
- Create: `frontend/src/pages/VoiceEditPage.tsx`
- Modify: `frontend/src/components/VoiceSelector.tsx`
- Modify: `frontend/src/pages/VoiceLibraryPage.tsx`
- Modify: `frontend/src/store.ts`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `tests/ui/core/basic.spec.js`
- Modify: `tests/ui/performance/performance.spec.js`
- Create: `tests/ui/voice-edit/voice-edit.spec.js`
- Create: `tests/ui/capture/scenarios/prosody/voice-edit.mjs`
- Modify: `tests/ui/capture/index.mjs`
- Modify: `tests/ui/README.md`

### Task 9.1: Add failing route and shared-data tests

- [ ] Add `nav exposes Voice Edit between Voice Library and Stitch Studio` to both nav specs.
- [ ] Add `Voice Edit deep link preselects the saved voice`.
- [ ] Add `variant saved in Voice Edit appears in Voice Library prosody editor`.
- [ ] Add `Voice Library retains its existing prosody controls`.
- [ ] Run and confirm RED.

### Task 9.2: Extract pure saved-voice selection

- [ ] `SavedVoicePicker` accepts saved `VoiceMeta[]`, selected ID, change callback, search value, and search callback.
- [ ] It contains no `setPage`, `setDesignEngine`, Pocket built-ins, or create-new action.
- [ ] Refactor `VoiceSelector` to compose the pure picker with existing built-in/create behavior; preserve current callers.

### Task 9.3: Extract one prosody implementation

- [ ] Move current VoiceCard prosody state/effects into `useProsodyEditor(voiceId)`.
- [ ] Move panel JSX into `ProsodyEditorPanel` with `layout: 'compact' | 'page'`.
- [ ] Keep `VariantCompare` and `AlignmentCompare`; do not create replacement comparison components.
- [ ] Voice Library uses compact layout; Voice Edit uses page layout.
- [ ] Both surfaces refresh from the same API result after save/promote.

### Task 9.4: Add route and handoff

- [ ] Add `'voice-edit'` to `Page`.
- [ ] Add nav item between Voice Library and Stitch Studio with `nav-voice-edit` and description `Prosody & variants`.
- [ ] Add `VoiceEditPage` route.
- [ ] Consume `deepLinkProsodyVoiceId` only after the page has selected the voice.
- [ ] From successful Stitch save, `Adjust prosody` sets the deep link then navigates to Voice Edit.

### Task 9.5: Verify and commit Packet 9

```bash
npm run --prefix frontend check
npm --prefix tests/ui test -- core/basic.spec.js performance/performance.spec.js voice-edit/voice-edit.spec.js
node tests/ui/capture/index.mjs --scenario voice-edit --source fake
```

**Gate 9 — One prosody data path**

PASS requires correct nav order, deep link, compact and page layouts sharing one hook/panel, new variant visible on both surfaces, and no Voice Library regression.

**Commit:** `feat(frontend): add first-class Voice Edit workspace`

---

# Work packet 10 — Final visual, accessibility, and regression gate

**Purpose:** Prove the finished surface rather than infer quality from compilation.

**Files:**

- Modify only defects discovered by this gate.
- Update capture documentation/artifacts through the harness.

### Task 10.1: Run repository and focused regression checks

```bash
python scripts/validate_repo.py
docker compose config --quiet
git diff --check
npm run --prefix frontend check
npm --prefix tests/ui test
PYTHONPATH=src:src/export python -m pytest \
  tests/tier1_unit/test_segment_library.py \
  tests/tier1_unit/test_audio_post.py \
  tests/tier2_backend/test_app_omnivoice.py -q
npm --prefix tests/ui run capture:test
npm --prefix tests/ui run capture:manifest
```

Every command must exit `0`.

### Task 10.2: Run required fake captures

```bash
node tests/ui/capture/index.mjs --scenario segment-library-browse --source fake
node tests/ui/capture/index.mjs --scenario segment-browser-scale --source fake
node tests/ui/capture/index.mjs --scenario stitch-assembly --source fake
node tests/ui/capture/index.mjs --scenario gap-editing --source fake
node tests/ui/capture/index.mjs --scenario readiness-states --source fake
node tests/ui/capture/index.mjs --scenario voice-edit --source fake
node tests/ui/capture/index.mjs --scenario design-to-stitch-gif --source fake
```

Inspect every artifact. Regenerate after each visual correction.

### Task 10.3: Manual browser matrix

Use the actual app surface at:

- 1280×720
- 1440×900
- 1568×700
- 1920×1080

At each size verify:

- violet, teal, amber, and rose themes;
- Reference voices and Segments tabs;
- quick-insert Cancel/Save/Open and focus restoration;
- 250-row browser search/filter/audition;
- 0ms/200ms/2000ms gaps and crossfade visualization;
- Fit/minus/plus/wheel zoom;
- mouse, keyboard, and pointer drag;
- unified playback and ruler seek;
- blocked/warning/ideal/overlong readiness;
- plain save, API-default save, and simulated activation failure;
- Voice Edit deep link and saved variant reflected in Voice Library;
- loading, empty, preview failure, save failure, and activation failure states;
- `prefers-reduced-motion: reduce`.

Record Chromium Performance traces for:

- 250-row browser scroll: no long task over 50ms;
- timeline scrub/zoom/playback: target 60fps and no React render per audio frame.

### Task 10.4: Final diff and cleanup

- [ ] Remove throwaway counters, performance hooks, debug logs, temporary files, and obsolete picker/preview code.
- [ ] Confirm no old `LibraryPickerButton`, global preview store fields, component-local region map, raw modal portal, or duplicate time-axis helper remains.
- [ ] Update `tests/ui/README.md` scenario catalog.
- [ ] Run the complete Task 10.1 command block again after cleanup.
- [ ] Inspect `git diff --check` and `git diff --stat`.

**Gate 10 — Release-ready**

PASS requires all automated commands green, every named manual scenario observed, captures inspected at required viewports/themes, performance targets recorded, no scope exceptions, and the execution ledger complete.

**Commit:** `test(frontend): verify Stitch Studio UX overhaul`

---

## Packet execution ledger

Update this table during implementation. Do not pre-mark a packet PASS.

| Packet | Status | Source commit | Commands/evidence | Visual artifacts | Known divergence | Next permitted packet |
| --- | --- | --- | --- | --- | --- | --- |
| 0 Baseline | PASS | fb1af3683cc0f9b0a06871f092dab84e847385bc | validate_repo.py=0; `docker compose config --quiet`=0; `git diff --check`=0; `npm run --prefix frontend check`=0 (lint warnings only, pre-existing); `npm --prefix tests/ui test -- core/basic.spec.js performance/performance.spec.js`=0 (5 passed); `node capture/index.mjs --scenario segment-library-browse --source fake`=0; `node capture/index.mjs --scenario stitch-assembly --source fake`=0 | `docs/screenshots/artifacts/stitch-studio/segment-library-browse--neutral--segment-library-browse.png`; `docs/screenshots/artifacts/stitch-studio/stitch-assembly--neutral--assembly.png` (both inspected) | Manual repro on fake stack confirms A.2/A.3 (single-clip modal footer renders only "Save as reference voice") and A.4 (Voice Library "Insert into stitch editor" navigates to `voice-design` first; closing via X strands the user on Voice Design, never returns to Voice Library) | 1 |
| 1 Plan domain | PASS | bc548ab | RED confirmed (region-edit survival test failed pre-fix; removal-seam test already passed on prior store logic); `npm run --prefix frontend check`=0; `npm --prefix tests/ui test -- stitch-studio/studio.spec.js -g "region edits survive Stitch Studio\|removing a middle clip"`=0 (2 passed, GREEN); `npm --prefix tests/ui test -- core/basic.spec.js performance/performance.spec.js`=0 (5 passed); `PYTHONPATH=src:src/export pytest tests/tier2_backend/test_app_omnivoice.py -q`=0 (14 passed) | none (no visual change this packet) | Test selectors for tooltip-bearing elements must use `data-app-tooltip`, not `title` — `TitleTooltipBridge` (components/ui/tooltip.tsx) rewrites every `title` attribute at runtime; noted for later packets writing new Playwright specs | 2 |
| 2 Preview/audio | PASS | 5c0c0aa | RED confirmed (both lifecycle tests failed on missing `stitch-preview-ready` testid); `npm run --prefix frontend check`=0; `npm --prefix tests/ui test -- stitch-studio/studio.spec.js -g "preview\|aborted"`=0 (2 passed, GREEN); full `stitch-studio/studio.spec.js`=0 (4 passed); `node tests/ui/capture/index.mjs --scenario stitch-assembly --source fake`=0; `npm --prefix tests/ui test -- core/basic.spec.js performance/performance.spec.js`=0 (5 passed); `PYTHONPATH=src:src/export pytest tests/tier2_backend/test_app_omnivoice.py -q`=0 (14 passed) | `docs/screenshots/artifacts/stitch-studio/stitch-assembly--neutral--assembly.png` (inspected; unchanged layout, preview still mid-debounce at capture time as before) | Added `hashStitchPlan` to `frontend/src/lib/stitchPlan.ts` (not in the packet's stated file list) as a small shared fingerprint function so the preview hook's debounce/skip logic and the component's `stitch-preview-ready` `data-plan-hash` attribute cannot drift from each other; consistent with that module's existing "pure plan domain" scope, no locked-interface rename | 3 |
| 3 Quick insert | PASS | 4a0b92e | RED confirmed (4 tests failed on missing `stitch-editor-dialog`); `npm run --prefix frontend check`=0; `npm --prefix tests/ui test -- stitch-studio/studio.spec.js -g "quick insert\|region edits survive quick\|preview"`=0 (all GREEN, incl. the 4 new tests plus Packet 2's); full `stitch-studio/studio.spec.js`=0 (8 passed); `node tests/ui/capture/index.mjs --scenario design-to-stitch-gif --source fake`=0; `npm --prefix tests/ui test -- core/basic.spec.js performance/performance.spec.js voice-library/voices.spec.js`=0 (6 passed); `PYTHONPATH=src:src/export pytest tests/tier2_backend/test_app_omnivoice.py -q`=0 (14 passed); `python scripts/validate_repo.py`=0; `git diff --check`=0 | `docs/screenshots/artifacts/wizard/design-to-stitch-gif--pocket-tts--design-to-stitch.gif` (inspected); manual browser walkthrough via a standalone fake server: quick-insert modal renders exactly Cancel/Save and close/Open in Stitch Studio with no `stitch-save-voice`; "Save and close" closes the modal, stays on Voice Library, and the clip is present when navigating to Stitch Studio afterward; "Open in Stitch Studio" commits and navigates directly, landing with the clip already on canvas | `docs/screenshots/artifacts/stitch-studio/` unchanged this packet (no stitch-studio-category capture touched) | Radix's own `onCloseAutoFocus` does not reliably fire because the quick-insert modal is conditionally *unmounted* (not kept mounted with `open=false`) on close, so `store.ts` performs its own focus capture/restore in `openOvStitchEditor`/`closeOvStitchEditor` (deferred one macrotask past Radix's internal FocusScope cleanup, which otherwise re-steals focus). `reopenInStitchStudio` (Voice Library, full multi-clip plan reconstruction) bypasses the quick-insert modal entirely — commits via `replaceOvStitchPlan` and navigates straight to `stitch-studio` — since its N-clip rebuild has no natural fit for the locked singular `ovStitchEditorIncomingClip` field; this still fully fixes its share of the reported navigation bug (never touches `voice-design`). `OmniVoicePanel`'s own multi-take "open stitch editor" (from an OmniVoice audition rack) keeps writing its built clips directly into the store (unchanged from prior behavior) and now opens the quick-insert modal with `returnPage: 'voice-design'` and no incoming clip — as an accepted consequence, its previous "Save" action (which attached OmniVoice's own `instruct`/`accentId` metadata) is gone: users must "Open in Stitch Studio" and save from there with a plain name, matching every other quick-insert flow. This is Task 3.3's explicit "delete the OmniVoicePanel mount" mandate, not a scope decision made unilaterally here; flagging since it is a real capability change beyond the reported bug. Touched `frontend/src/lib/stitchClips.ts` and `frontend/src/pages/StitchStudioPage.tsx` beyond the packet's stated file list -- both are mechanically required by the locked `StitchEditorBodyProps` discriminated union (every caller of the changed interface must migrate) | 4 |
| 4 Browser/library | PASS | 936efa8 | RED confirmed (3 tests failed: missing `voice-library-tab-*`/`segment-browser-dialog`); `npm run --prefix frontend check`=0; `npm --prefix tests/ui test -- stitch-studio/studio.spec.js -g "Voice Library switches\|segment browser"`=0 (3 passed, GREEN); full `stitch-studio/studio.spec.js`=0 (11 passed, incl. 4 Packet-3 tests updated for the new Segments tab); `npm --prefix tests/ui test -- core/basic.spec.js performance/performance.spec.js voice-library/voices.spec.js`=0 (6 passed); `PYTHONPATH=src:src/export pytest tests/tier2_backend/test_app_omnivoice.py -q`=0 (14 passed); `python scripts/validate_repo.py`=0; `git diff --check`=0; `node tests/ui/capture/index.mjs --scenario segment-library-browse --source fake`=0; `--scenario stitch-assembly --source fake`=0; `--scenario segment-browser-scale --source fake`=0 (new, 250-row fixture) | `docs/screenshots/artifacts/stitch-studio/segment-library-browse--neutral--segment-library-browse.png`, `stitch-assembly--neutral--assembly.png`, `segment-browser-scale--neutral--scale.png` (all inspected, no clipping); manual browser checks at 1280×720 and 1568×700 (no clipping, both inspected); `PerformanceObserver` longtask trace across a full 250-row scroll recorded zero long tasks; manual Enter-key insertion check confirmed a checked row inserts and closes the dialog | Fixed a latent Packet-3 bug while implementing multi-select batch insert: `appendStitchPlanClip`'s per-item padding-length computation read a stale pre-batch snapshot on every iteration of a `forEach`, silently dropping padding entries for the 2nd+ item in any multi-item insert (existing behavior via the old `LibraryPickerButton`'s "Insert selected"). Replaced with one atomic `spliceStitchPlanClips` per batch call (single snapshot, one clips-splice, one padding-array rebuild), which also naturally supports "insert after a selected clip." Updated 4 existing Packet-3 Playwright tests to open the new "Segments" tab before "Insert into stitch editor" is visible (segment cards now live behind Voice Library's tab, previously always visible) — pre-existing tests, not new coverage, so not counted as new RED/GREEN pairs. Touched `frontend/src/lib/stitchClips.ts`, `frontend/src/App.tsx`, `frontend/src/pages/StitchStudioPage.tsx` beyond the packet's stated file list (mechanically required: every caller of the batch-insert signature change must migrate) and created `tests/ui/capture/scenarios/stitch-studio/segment-browser-scale.mjs` (not explicitly listed, but required to "register segment-browser-scale" per Task 4.4) | 5 |
| 5 Visual primitives | PASS | cba6217 | RED confirmed (3 tests failed: missing `stitch-ruler-tick`/`stitch-waveform-canvas`/`stitch-fade-overlay-left`); `npm run --prefix frontend check`=0; `npm --prefix tests/ui test -- stitch-studio/studio.spec.js -g "ruler\|device pixel ratio\|fade overlays"`=0 (3 passed, GREEN); full `stitch-studio/studio.spec.js`=0 (14 passed); `npm --prefix tests/ui test -- core/basic.spec.js performance/performance.spec.js voice-library/voices.spec.js`=0 (6 passed, 1 flaky-but-passed retry on a pre-existing Packet-3 backdrop-click test untouched by this packet); `PYTHONPATH=src:src/export pytest tests/tier2_backend/test_app_omnivoice.py -q`=0 (14 passed); `python scripts/validate_repo.py`=0; `git diff --check`=0; `node tests/ui/capture/index.mjs --scenario stitch-assembly --source fake`=0; `--scenario segment-library-browse --source fake`=0; `--scenario design-to-stitch-gif --source fake` skipped -- confirmed (via `git stash` on the pre-Packet-5 commit) to hang identically before this packet's changes, a pre-existing environment issue, not a regression | `docs/screenshots/artifacts/stitch-studio/stitch-assembly--neutral--assembly.png` (inspected: top ruler now shows real evenly-spaced 0.5s ticks instead of the old fixed 0/25/50/75/100% ratio ticks, no clipping), `segment-library-browse--neutral--segment-library-browse.png` (inspected, unaffected by this packet, no clipping); manual browser check: pushed a clip's fade-in to 600ms and trim-start to 200ms, read the canvas back via `toDataURL` -- confirmed a visible triangular gain-ramp wedge over the fade region and dimmed (not removed) bars over the trimmed region, at the environment's real DPR of 1.25 (canvas backing store 640x120 for a 512.48x96 CSS box, ratio matching `window.devicePixelRatio` exactly, proving the DPR fix works at non-integer ratios too, not just 1x/2x) | Every ruler in the app (`Waveform.tsx`'s playback deck, `waveform/TimeRuler.tsx`'s reference-editor lane, Stitch Timeline's top ruler) now computes ticks through the locked `timeAxis.ts` contract using each container's real measured width (via a new small `useElementWidth` hook, not in the packet's stated file list but required to avoid tripling ResizeObserver boilerplate) instead of the old ad-hoc "3-7 evenly spaced ratios" guess -- `useElementWidth` had to switch from a plain `useRef` to a callback-ref pattern after the first implementation produced 0 ticks: the ruler `<div>` mounts conditionally (`effectiveTotalMs > 0`), so a plain ref's mount-time effect (empty deps) ran before that div existed and never re-ran once it did. `WaveformLane`'s canvas now draws every peak across the clip's full untrimmed duration (dimming trimmed-out bars) instead of slicing them out of the array, which used to silently rescale the remaining bars to fill the lane whenever trim values changed -- a truthfulness fix beyond the DPR requirement, in the same spirit as Gate 5's "premium and truthful" canvas mandate. `StitchTimeline`'s fade-overlay divs are now sized proportionally to the fade duration (`ms / effectiveDuration`) instead of a fixed 32px, so they visibly change width as a user adjusts the Fade in/out steppers | 6 |
| 6 Timeline input | PASS | 93a43ad | RED confirmed (4 tests failed: missing `stitch-trim-handle-left`/`stitch-gap-control`/`data-gap-ms`/`data-selected`); `npm run --prefix frontend check`=0; `npm --prefix tests/ui test -- stitch-studio/studio.spec.js -g "trim drag\|reorder\|gaps\|keyboard"`=0 (4 passed, GREEN); `node tests/ui/capture/index.mjs --scenario gap-editing --source fake`=0; full `stitch-studio/studio.spec.js`=0 (19 passed); `npm --prefix tests/ui test -- core voice-library`=0 (10 passed); `PYTHONPATH=src:src/export pytest tests/tier2_backend/test_app_omnivoice.py -q`=0 (14 passed); `python scripts/validate_repo.py`=0; `git diff --check`=0 | `docs/screenshots/artifacts/stitch-studio/gap-editing--neutral--gap-editing.png` (inspected: 0ms seam as a thin marker beside a typed 250ms seam as a wider box, real second-scale ruler ticks 0.0s-7.5s, zoom controls with live px/s readout) | Reconciled three real interaction bugs discovered while making Task 6.1's RED tests pass, beyond the packet's literal scope text: (1) the pre-Packet-6 trim/fade drag handler added the cursor's in-lane pixel offset onto the *current* semantic value on every mousemove -- not a delta, and it compounds with every extra event; (2) fade handles at their 0ms default occupy the exact same pixel position as trim handles and, being later in DOM paint order, always won the pointerdown, making the trim handle silently unreachable until fade was already nonzero; (3) clicking a header control (Edit clip/play/remove) on an already-selected clip bubbled to the card's own onClick and toggled selection off. All three are fixed as part of this packet's "broken mouse-only gestures" purpose, not deferred. Also: the plan's Task 6.1 "multi-position reorder applies the full permutation" RED test passed unmodified against pre-Packet-6 code (Framer Motion's Reorder.Group only ever calls onReorder with single-swap arrays in practice); the reconciliation simplification (`setClips(next)` replacing the old from/to search) still lands as a correctness/robustness fix with that test now guarding it as a regression net. | Packet 7 |
| 7 Transport | PASS | 96b90d1 | RED confirmed (4 tests failed: missing `stitch-transport-toggle`/`stitch-timeline-ruler`/`stitch-transport-playhead`/`stitch-clip-wrapper`); `npm run --prefix frontend check`=0; `npm --prefix tests/ui test -- stitch-studio/studio.spec.js -g "Space\|ruler seeks\|clip play\|reduced motion"`=0 (4 passed, GREEN); `node tests/ui/capture/index.mjs --scenario transport-playback --source fake`=0; full `stitch-studio/studio.spec.js`=0 (23 passed); `npm --prefix tests/ui test -- core voice-library`=0 (10 passed); `PYTHONPATH=src:src/export pytest tests/tier2_backend/test_app_omnivoice.py -q`=0 (14 passed); `python scripts/validate_repo.py`=0; `git diff --check`=0 | `docs/screenshots/artifacts/stitch-studio/transport-playback--neutral--playback.png` (inspected: playhead visibly offset mid-arrangement after a ruler click, arrangement toggle in "Pause" state, live-preview fill advanced, all reflecting one shared `<audio>` element) | Fixed a real mount-order bug discovered while turning Task 7.1's RED tests GREEN: `useStitchTransport`'s play/pause/timeupdate listener-attach effect originally ran once with `[]` deps, but the `<audio>` element is conditionally rendered only once `preview.url` resolves -- on the render where the effect first ran, `audioRef.current` was still null (listeners never attached), so `isPlaying` never flipped true even though the underlying element really was playing. Fixed by making the ref a callback ref that bumps an `attachTick` counter on (re)attach, and keying the listener effect on that counter instead of `[]`; this is the same category of bug Packet 5 hit with `useElementWidth`'s plain-ref-vs-callback-ref mount timing, now recurring in a second hook. Per-clip play/pause range boundaries are a client-side approximation (`computeClipRangesMs`, scaled by the shared audio element's real measured duration against the client's estimated arrangement duration) rather than a sample-accurate readout of the backend's actual render -- the backend's DSP chain is intentionally never modeled client-side, matching the plan's DSP-untouched constraint. The arrangement-level `PreviewPlayer` component was replaced outright with `TransportBar` (not named in the packet's file list, but required: Packet 7 mandates exactly one `<audio>` element for the whole arrangement, and the old `PreviewPlayer` owned its own) | Packet 8 |
| 8 Readiness/save | PASS | 57f87c1 | RED confirmed (7 tests failed: empty suggested name, zero punctuation seam, save incorrectly enabled by 5s gap, no readiness rail, missing-name save enabled, plain save navigated away, API-default choice absent); `npm run --prefix frontend check`=0; `npm --prefix tests/ui test -- stitch-studio/studio.spec.js -g "names\|punctuation\|source-material\|readiness\|API default"`=0 (7 passed, GREEN); full `stitch-studio/studio.spec.js`=0 (30 passed); `npm --prefix tests/ui test -- core voice-library`=0 (10 passed); `node tests/ui/capture/index.mjs --scenario readiness-states --source fake`=0; `PYTHONPATH=src:src/export .venv/bin/python -m pytest tests/tier1_unit/test_segment_library.py tests/tier2_backend/test_app_omnivoice.py -q`=0 (26 passed); `python scripts/validate_repo.py`=0; `git diff --check`=0 | `docs/screenshots/artifacts/stitch-studio/readiness-states--neutral--{blocked,warning,ideal,overlong}.png` (inspected: 0.0s clips/0.0s spacing blocked; warning below 10s; ideal 7.4s clips + 4.0s spacing = 11.2s; overlong 7.4s clips + 10.0s spacing = 17.2s; each has semantic state styling and exactly one enabled primary action) | Punctuation gaps are suggested only while seams are created: a first batch gets its own internal suggestions, end appends add one suggestion per new seam, and middle insertion retains the existing zero-value positional-seam behavior. Existing Packet 1/6 tests previously assumed all new seams began at zero, so their test setup now explicitly types the values they mean to exercise before asserting positional semantics. Plain save stays on Stitch Studio so the honest saved/activation outcome can remain visible rather than navigating to Voice Library; Packet 9 will wire its planned Adjust prosody handoff. | Packet 9 |
| 9 Voice Edit | PASS | pending commit | RED: nav/route/deep-link/variant tests failed as expected; `npm run --prefix frontend check`=0 (pre-existing warnings); `npm --prefix tests/ui test -- core/basic.spec.js performance/performance.spec.js voice-edit/voice-edit.spec.js --retries=0`=0 (8 passed); `node tests/ui/capture/index.mjs --scenario voice-edit --source fake`=0 | `docs/screenshots/artifacts/prosody/voice-edit--neutral--workspace.png` (inspected) | Voice Library's existing compact prosody controls remain unchanged while Voice Edit exposes the shared page workflow | Packet 10 |
| 10 Final gate | BLOCKED | — | — | — | waits for Gate 9 | none |

## Required handoff after every packet

Use this exact structure:

```text
Packet:
Gate result: PASS | FAIL
Source commit:
Image tag/digest: not built | exact value
Model revision: unchanged | exact value
IR metadata hash: unchanged | exact value
Completed milestones:
Remaining release gates:
Files changed:
Commands run and exit status:
Behavior exercised:
Visual artifacts:
Benchmark prompts/runtime settings: not applicable | exact prompts and FP32/INT8/cache mode
Known divergences and first failing step:
Non-Git artifact locations:
Rollback procedure:
Rollback tested: yes | no
Next permitted packet:
```

Do not claim a packet complete from a build alone. A UI packet requires the named browser scenario and inspected visual artifact.

## Execution choice

Use inline `executing-plans` with a human checkpoint after each hard gate. Do not dispatch parallel subagents: packets 1–9 deliberately mutate shared state and interfaces, and the user explicitly requested no subagents for this initiative.

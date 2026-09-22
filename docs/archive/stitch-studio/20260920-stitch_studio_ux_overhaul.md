# Stitch Studio UX Overhaul: Segment Flow, Timeline Craft, Voice Edit

Date: 2026-09-20
Status: **COMPLETE** — fully implemented; review-fix pass complete (2026-09-21)
Branch: `fix/stitch-studio-ux-overhaul-20260920`

Fixes the chain of UX/naming/navigation bugs in how voice segments flow
**OmniVoice → Voice Library → Stitch Studio → reference voice → prosody**, and
raises the Stitch Studio timeline to the visual/interaction quality of a
professional audio tool. Scoped as a fix + polish pass: every item traces to a
reproduced problem from the 2026-09-20 walkthrough or to a concrete divergence
found in the code during planning.

Three governing goals, in priority order:

1. **Correctness of flow** — the user can never be dumped on the wrong page, and
   can never be invited to save a reference voice that is too short to work.
2. **Automate and simplify** — the app should pre-decide everything it can
   (name, gaps, next step) so the user makes taste decisions, not bookkeeping
   decisions.
3. **Premium craft** — timeline, gaps, waveforms, and transport must read like a
   modern DAW/VST, not like a form with audio in it.

---

## Central finding: the premium look already exists; Stitch Studio diverged

This is the most important grounding fact for whoever implements this. The app
**already has** a high-craft audio UI language — it is just not used by the
Stitch Studio timeline. Building "new fancy visuals" from scratch here would be
the wrong move; the job is to bring the timeline onto the existing primitives
and then push those primitives further.

| Capability | Already exists | Stitch Studio currently does instead |
| --- | --- | --- |
| DAW-style waveform with meter palette (cyan→magenta by level), glowing amber playhead + head dot, click-to-seek, drag-to-select region, spring-in bars, `isActive` idle pulse, bottom time axis | `frontend/src/components/Waveform.tsx` (`barColor`, `PLAYHEAD_COLOR`, motion springs) | `waveform/WaveformLane.tsx`: flat canvas bars, **no playhead**, no seek, no selection, no animation |
| Shared `AudioContext` + duration-scaled peak buckets (24–120 buckets by duration) | `frontend/src/lib/waveform.ts` (`computePeaks`) | `StitchTimeline.tsx` line ~288-320: its own inline decoder, **`new AudioContext()` per clip per mount**, hardcoded 48 buckets |
| "Nice step" time-ruler tick generator with edge-clamped labels | `frontend/src/components/waveform/TimeRuler.tsx` (`niceStep`) | `StitchTimeline.tsx` line ~1206-1222: 5 hardcoded fractions (0/.25/.5/.75/1) of total |
| Region select + gain/mute/fade editing over a waveform | `waveform/RegionEditor.tsx`, `waveform/regionAudio.ts` | already reused (good — keep) |
| Design tokens, brand CTA, status pills, lint guard | `frontend/src/index.css` (`--brand-from/to/glow`, `--surface-1`, `.btn-brand`, `.status-badge`/`.status-tone-*`), `docs/dev/DESIGN_SYSTEM.md`, `frontend/oxlint-design-system.cjs` | partially; several hand-rolled `cyan-500/xx` borders and raw `hsl()` values in `StitchTimeline.tsx` |

Consequences to respect:

- **Three** tick/axis implementations exist (`Waveform.tsx`, `TimeRuler.tsx`,
  inline in `StitchTimeline.tsx`). **Two** waveform renderers (DOM/motion bars
  vs. canvas). **Four+** audio-decode paths (`lib/waveform.ts`,
  `StitchTimeline.tsx` inline, `stitchClips.ts` duration probe,
  `VariantCompare.tsx`, `AlignmentCompare.tsx`, `RegionEditor.tsx`). Polish
  applied on top of that divergence will not hold. Consolidation is Phase 0 and
  is not optional.
- **No new audio-UI dependency.** Stack is React 19 / Tailwind 4 / `motion` 13 /
  `radix-ui` / `lucide-react` / zustand (`frontend/package.json`). Do **not** add
  wavesurfer.js, tone.js, konva, or a charting lib — everything below is
  achievable with canvas + CSS + `motion`, and the existing components prove it.
- `docs/dev/DESIGN_SYSTEM.md` is binding. Status meaning uses semantic tokens
  (`text-warning`, `bg-success/10`, …) and `oxlint` rejects raw status palette
  classes. The waveform meter palette is explicitly *allowed* as categorical
  color ("audio-edit lane accents") — keep it, but route it through one shared
  place rather than re-deriving `hsl(190 + peak*140 …)` in three files.

---

## Codebase grounding (read this first)

Build on what exists. Do not create a second "arrange clips" implementation —
one already exists and is shared by both surfaces.

| Concern | Existing code | Reuse / extend, do not replace |
| --- | --- | --- |
| Shared stitch plan state | `frontend/src/store.ts` (`ovStitchPlanClips`, `ovStitchPlanPaddingMs`, `ovStitchPlanDsp`, `ovStitchEditorOpen`, `ovSavedVoiceId`, `deepLinkProsodyVoiceId`) | Global zustand state is page-agnostic, so clips survive navigation. It is not yet a complete transaction model: region edits are component-local and preview blobs are over-globalized (B24/B25). Phase 0 corrects those boundaries. |
| Shared "arrange" UI | `StitchTimeline.tsx`: `StitchEditorBody` (internals), `StitchEditorPanel` (portal modal shell), `StitchEditorInline` (plain page shell) | One body, two shells. Footer/behavior changes belong in `StitchEditorBody`, parameterized. |
| Insert-into-timeline logic | `frontend/src/lib/stitchClips.ts`: `createStitchClipFromSegment`, `createStitchClipFromVoice`, `insertSegmentIntoStitchTimeline`, `insertVoiceIntoStitchTimeline`, `appendStitchPlanClip`, `suggestedStitchVoiceName` | Already shared by `OmniVoicePanel` and `VoiceLibraryPage`. Extend, do not fork. |
| Real Stitch Studio page | `frontend/src/pages/StitchStudioPage.tsx` (route `page === 'stitch-studio'`, nav testid `nav-stitch-studio`) | The actual destination the user wants to land on. Already renders `StitchEditorInline` + name field + delivery variant + save. |
| Voice Library entry points | `VoiceLibraryPage.tsx`: `insertSegmentIntoStitchEditor` (~1782), `reopenInStitchStudio` (~1830) | **Root cause of the navigation bug**: both `setPage('voice-design')` + `setDesignEngine('omnivoice')` + `setOvStitchEditorOpen(true)`. Neither ever navigates to `stitch-studio`. |
| Modal mount point | `OmniVoicePanel.tsx` ~2444 `{stitchEditorOpen && <StitchEditorPanel …/>}`, where `stitchEditorOpen = s.ovStitchEditorOpen` | The flag is **already global**; only its render site is trapped inside the Voice Design page. Hoist the render, not the flag. |
| Gap control | `StitchTimeline.tsx` `GapControl` (~714), `MsStepper` (~747) | `paddingMs <= 0` renders only a thin dashed `+`; value is a non-editable `<span>`; `step={10}`, `max={3000}`. Exactly the reported complaints, confirmed in code. |
| Library picker | `StitchTimeline.tsx` `LibraryPickerButton` (~777-998), instantiated **4×** (segments/voices × empty-state/populated-state) | Text-only checkbox list, no audio, no waveform, no project grouping. Replaced in Phase 2 — but see the **testid contract** below before deleting. |
| Per-voice prosody editor | `VoiceLibraryPage.tsx` inside `VoiceCard`: state ~855-914, popover JSX ~1440-1650 (variant entries, target-marker sliders, preview, "save as new variant", "save & promote to primary") | A full prosody surface trapped in a card popover. **Extract**, don't reimplement, so the new page and the popover share one implementation. |
| API-serving default | backend `voice_library.set_active_default_voice_id` / `get_active_default_voice_id`, `model.activate_default_voice_from_library`, `pocket_tts_runtime.set_default_voice_state_from_library`; frontend `activateVoiceForApi`, `voice.api_active` | This is the flag that drives no-voice-id TTS. **Distinct** from `is_default` / "Set family default" (`voice_library.set_default_variant`), which only picks a variant within a family. The new save option uses `activateVoiceForApi`. |
| Segment/voice data | `lib/api.ts` `SegmentMeta` / `VoiceMeta`, `listOmniVoiceSegments`, `getSegmentAudioBase64`, `listVoices` | List metadata includes project, tags, duration, and language but intentionally omits segment audio. Filter/sort use metadata; audition lazily fetches one asset through the existing audio endpoint. No server endpoint change is required. |
| Motion / reduced motion | `motion` v13 (`motion/react`), local `useReducedMotion` helper at `StitchTimeline.tsx` ~22 | Reuse the helper; every new animation must degrade under `prefers-reduced-motion`. |
| UI capture + E2E | `tests/ui/` (`core/basic.spec.js`, `performance/performance.spec.js`, `capture/scenarios/stitch-studio/{assembly,segment-library-browse}.mjs`, `capture/scenarios/wizard/design-to-stitch-gif.mjs`), `tests/ui/README.md` | These drive the product screenshots/GIFs and **depend on exact testids and even on a `.shadow-lg` popover class**. See the testid contract section. |

---

## Problem inventory

### A. Reported by the user (walkthrough, 2026-09-20)

1. **"Stitch editor" ≠ "Stitch Studio".** `VoiceLibraryPage.tsx` renders
   `"+ Insert into stitch editor"`; the shared editor header says
   `"ARRANGE YOUR REFERENCE CLIP"`; the page says "Stitch Studio". One feature,
   three names. → one name everywhere.
2. **Single-clip modal presents an arrange canvas with nothing to arrange, and
   its only CTA is "Save as reference voice".** `StitchEditorBody`'s footer
   (~1691-1705) unconditionally renders exactly that one button regardless of
   clip count or entry point, and offers no way to accept the segment and go
   edit it properly. → contextual footer (Decision A).
3. **Saving must be impossible with too little audio.** Same root cause: no
   clip-count or duration gate anywhere, reachable from a modal whose whole
   purpose is "you just added one 2.6s clip." → remove save from the
   quick-insert surface entirely, and add a real readiness gate on the studio
   surface (Phase 5).
4. **X always returns to Voice Design.** Confirmed: both Voice Library handlers
   navigate to `voice-design` *before* opening the modal, so there is no prior
   page left to return to. → stop navigating on open; track a return page
   (Decision B).
5. **No obvious way to add more segments inside Stitch Studio.** The pickers do
   exist (4 `LibraryPickerButton` instances) but read as afterthoughts:
   text-weight, no icon, clustered with "Auto-pace". → one promoted primary
   action (Phase 2/5).
6. **The picker cannot scale.** Text-only checkbox list; no audio, no waveform,
   no duration, no project grouping; unusable at hundreds of segments. → rich
   `SegmentBrowserModal` (Phase 2).
7. **The default gap is invisible.** `GapControl` renders only a dashed `+` at
   `paddingMs <= 0`, so "no gap" and "I haven't touched this seam" look
   identical, and adding a gap appears to grow space from nothing. → gaps are
   always-visible first-class objects with large seconds readouts (Phase 3).
8. **Gap editing is unusable.** Non-editable `<span>`, `−`/`+` only, `step=10`
   (so 1080ms took ~108 clicks), and `max=3000` silently caps at 3s. →
   click-to-edit + drag-the-seam + keyboard nudge + honest range (Phase 3).
9. **Can't tell how long anything is or where it sits.** Clip flex-basis is
   `Math.max(300, effectiveDurationMs)` and gap flex-basis `Math.max(1,
   paddingMs)` with `minWidth` floors, so short clips/gaps occupy width
   unrelated to their duration while the ruler claims linear time. The ruler is
   5 fixed fractions, not a time axis. → true px/sec scale + real gridlines +
   zoom (Phase 3).
10. **"Use source name" is a tiny unexplained link** (`StitchStudioPage.tsx`
    ~110-119, 10px text). → auto-fill on first insert, drop the link (Phase 4).
11. **No answer to "what do I do next?"** Name, delivery variant, arrange,
    auto-pace, add segments, DSP, live preview and save all carry equal visual
    weight. → explicit guidance rail + action hierarchy (Phase 5).
12. **Save can't also mark the voice as the API default**, though
    `activateVoiceForApi` already exists as a separate Voice Library action. →
    explicit save option, not a hidden menu (Phase 6).
13. **Prosody has no first-class home** — only a card popover. → new "Voice
    Edit" page, shared implementation (Phase 7).

### B. Found in code during this planning pass (not reported, same blast radius)

- **B14. Fades are never drawn.** `WaveformLane` accepts `fadeInMs`/`fadeOutMs`,
  lists them in its effect deps, and never renders them. Users adjust fades
  (drag handles exist) with zero visual feedback.
- **B15. Trim/fade drag drifts.** `StitchTimelineClip.handleMouseMove` computes
  `clip.trimStartMs + offsetX * msPerPx` on *every* mousemove — the pointer's
  absolute offset is added to the already-updated trim, so the handle
  accelerates away from the cursor. Needs a drag-start anchor
  (`{ startValue, startClientX }`) and delta math.
- **B16. Mouse-only interaction.** Trim, fade, and region selection use
  `onMouseDown` / `window.addEventListener('mousemove')` — no pointer events, so
  no pen/touch support and no pointer capture (drags break when the cursor
  leaves the lane).
- **B17. Reorder applies only the first differing index.**
  `StitchTimeline.handleReorder` finds the first mismatch, calls `reorderClip`,
  then `break`s; it also builds an unused `newIndices` array. Multi-step drags
  land wrong.
- **B18. Reorder does not move gaps.** `store.reorderOvStitchPlanClip` reorders
  clips only; `ovStitchPlanPaddingMs` stays seam-indexed. Defensible (gaps *are*
  seam properties) but currently invisible, so it reads as corruption.
  Decision: keep seam semantics and make them visible — after Phase 3 every gap
  shows its value, so a reorder's effect is legible instead of mysterious. Name
  the seam in its tooltip ("gap between clip 2 and clip 3").
- **B19. AudioContext churn.** Each clip mount does `new AudioContext()` +
  decode + `ctx.close()`; `stitchClips.decodeAudioDurationMs` opens and closes
  another one per insert. This creates avoidable resource churn and inconsistent
  browser lifecycle behavior. `lib/waveform.ts` already provides a shared
  context — adopt it.
- **B20. Canvas is not DPR-scaled.** `WaveformLane` sets `canvas.width =
  canvas.clientWidth`, so every waveform is soft on any HiDPI display. This one
  detail alone reads as "not a premium tool".
- **B21. Preview render spam.** `StitchEditorBody` re-renders the whole stitch
  server-side on a 500ms debounce keyed on a JSON hash; a click-to-edit gap
  field or a seam drag will fire many full renders. Needs drag-aware debouncing
  (commit on gesture end) and request abort — `renderSeqRef` already guards
  *application* of stale responses, but not their *cost*.
- **B22. Peaks are duration-blind.** A fixed 48 buckets means a 0.8s clip and a
  12s clip get the same 48 bars; `lib/waveform.ts`'s `bucketsForDuration`
  (24-120) already does this correctly.
- **B23. Live preview has no waveform at all** — `PreviewPlayer` is a play
  button and a bare track, while `Waveform.tsx` (playhead, seek, axis) sits
  unused two directories away.
- **B24. Region edits are transient component state.** `regionEditsByClip`
  lives inside `StitchEditorBody`, while trims/fades live on store clips. Opening
  the same plan in a new surface loses gain/mute/delete/insert-silence edits even
  though the preview showed them. Moving from quick-insert to Studio must not
  discard work.
- **B25. Preview state crosses transaction boundaries.** Preview URL/blob and
  rendering status live globally in zustand. A quick-insert draft can replace
  the Studio preview, then Cancel, leaving a preview for a plan that was never
  committed. Object-URL ownership and revocation are also harder to reason about.

---

## Architecture decisions (locked)

### A. Contextual footer for the shared editor body

`StitchEditorBody` takes a surface mode (`'studio' | 'quick-insert'`) and a
`StitchPlanSession` adapter instead of reading/writing the live store directly.
The adapter exposes clips, padding, DSP, **region edits**, and plan-editing
actions. Region edits become part of the plan domain model rather than
component-local state.

- **`studio`** uses a store-backed session. Every edit is live and durable for
  the current app session.
- **`quick-insert`** uses a local draft initialized from the current store plan
  plus the incoming clip. Opening the modal does **not** mutate the live plan.
  Its three actions are:
  - **"Open in Stitch Studio"** (primary) — atomically commit the draft to the
    store, navigate to `stitch-studio`, close.
  - **"Save and close"** — atomically commit the draft, remain on the calling
    page, close. Supporting text must say "Keep this segment in your Stitch
    Studio draft" because "save" here does not create a reference voice.
  - **"Cancel"** — discard the local draft and close. No rollback is needed and
    unrelated store changes cannot be overwritten.
  - The arrange canvas stays available in this mode (correct for 2+ clips and
    harmless for one). The footer and destination change; editing capability
    does not.

This transactional boundary is REQUIRED. The prior snapshot-and-rollback idea
mutated the live global plan before confirmation, leaked uncommitted edits to
other surfaces, and could overwrite unrelated state on Cancel.

Rendered preview URL/blob, playback position, stale/error state, and in-flight
request belong to the mounted editor session, keyed by plan hash. They are not
durable plan data and MUST move out of global zustand. Revoke object URLs on
replacement/unmount. A committed draft causes Studio to render its own preview.

### B. Global modal mount + return-page tracking

- `store.ts`: add `ovStitchEditorReturnPage: Page | null` and a setter. Do
  **not** add a global plan snapshot; the quick-insert draft belongs to the
  modal session.
- `App.tsx`: render `<StitchEditorPanel>` once at app root, gated on
  `ovStitchEditorOpen`, as a sibling of the page switch.
- `OmniVoicePanel.tsx`: delete its own `<StitchEditorPanel>` render; its
  audition-flow open sets `returnPage = 'voice-design'`.
- `VoiceLibraryPage.tsx`: both handlers stop calling `setPage('voice-design')`,
  pass the incoming clip into the quick-insert session, and set
  `returnPage = 'voice-library'`.
- X, backdrop click, Escape, and Cancel discard the quick-insert draft and
  return focus to the exact launch control on the calling page.
- "Save and close" commits then returns; "Open in Stitch Studio" commits then
  navigates.
- Use the existing Radix dialog primitive for focus trap, Escape handling,
  accessible title/description, focus restoration, and scroll locking rather
  than maintaining those behaviors manually in a raw portal.

### C. One `SegmentBrowserModal`

One component replacing **all four** `LibraryPickerButton` instantiations; the
picker component is then deleted (no parallel implementation left behind).

- Radix `dialog` (already a dependency and used elsewhere) — a real modal, not
  a popover, so it can be large enough to browse.
- Tabs: **Segments** / **Reference voices** (`ui/tabs.tsx` exists).
- Rows: play/pause, duration, transcript, project chip, selection state, and an
  audio-preview rail. List metadata intentionally omits audio, so an unloaded
  row shows a truthful neutral duration rail — never a fake waveform. On first
  audition/expansion, fetch that asset through `getSegmentAudioBase64`, compute
  a static DPR-correct canvas thumbnail, and promote the auditioning row to the
  interactive waveform with playhead. Do not mount motion bars for every row.
- Large-list behavior: one active audio element, bounded cached peaks,
  `content-visibility: auto` for off-screen cards, incremental rendering in
  bounded batches, and stable row heights. Never prefetch audio for all rows.
  If the measured library misses the performance budget, add dependency-free
  windowing before shipping; user-reported jank is not the acceptance gate.
- Filters: text search, project filter (segments carry `project_id`/
  `project_name` — mirror Voice Library's existing language), asset-type tab,
  and sort by newest/duration/name. Filter state stays local to the open modal.
- Multi-select + "Insert selected (N)" preserves today's select-all, checkbox,
  and bulk-insert behavior. If a timeline clip is selected, offer "insert after
  selected" instead of always appending.
- Fast path: each row has an explicit **Add** action and `Enter` equivalent.
  Double-click MAY also add and close, but is never the only discoverable path.
- Not used by the Voice-Library single-segment entry point — that already knows
  its segment.

### D. Timeline rendering model

The timeline stops being a flex row of min-width cards and becomes a
**time-scaled arrangement**:

- One source of truth: `pxPerSecond` (zoom), with **Fit** / **−** / **+**
  controls and `Ctrl/⌘+wheel` zoom. Clip width = `durationMs * pxPerSecond`,
  gap width = `paddingMs * pxPerSecond`, both honest at all zooms.
- A **minimum interactive width** still exists (a 40ms clip cannot be a 1px
  target), but when a clip or gap is width-clamped it renders an explicit
  hatched edge and exact value instead of silently lying. At default zoom a
  10-15s reference fits the workspace without clamping.
- Ruler/gridlines come from **one** shared tick module (promote
  `waveform/TimeRuler.tsx`'s `niceStep` into `lib/timeAxis.ts`, consumed by
  `TimeRuler`, `Waveform.tsx`, and the timeline) — gridlines behind lanes,
  labels above, ticks aligned to real time.
- One **transport**: a single playhead that sweeps the whole arrangement during
  live-preview playback (including across gaps), click-anywhere-to-seek, `Space`
  = play/pause. Per-clip play buttons drive the same transport, scoped to that
  clip's span, rather than spawning independent `Audio` elements per clip.
- Desktop-first responsive contract: at narrower widths the inspector/controls
  stack above the timeline while the time-scaled lane remains horizontally
  scrollable. Do not squeeze controls, collapse seconds labels, or reduce
  pointer targets to force everything into one viewport.

---

## Phased plan

Phases are ordered so each one lands on a foundation that the next needs.
Phases 0 and 1 together form the first independently shippable slice.

### Phase 0 — Consolidation foundation (prerequisite for all visual work)

Files: `store.ts`, `lib/waveform.ts`, new `lib/timeAxis.ts`,
`waveform/WaveformLane.tsx`, `waveform/TimeRuler.tsx`,
`components/Waveform.tsx`, `StitchTimeline.tsx`, `lib/stitchClips.ts`.

1. Extend `lib/waveform.ts` into the single audio-analysis entry point:
   `getClipAudio(assetKey, blobOrBase64)` → `{ peaks, durationMs, sampleRate }`,
   using the existing shared `AudioContext`. Cache only compact peak envelopes
   and metadata — never decoded `AudioBuffer`, Blob, object URL, or base64.
   Use a bounded LRU with explicit invalidation when an asset is replaced; key
   by stable asset identity plus revision/content fingerprint, not ephemeral
   `clipId`. Optional bucket density supports timeline zoom. Keep
   `bucketsForDuration`; add a min/max envelope for wide lanes.
2. Replace the inline decoder in `StitchTimelineClip` (~288-320) and the
   AudioContext probe in `stitchClips.decodeAudioDurationMs` with it. Net effect:
   one context, one decode per distinct audio, no per-mount churn (fixes B19,
   B22).
3. `waveform/WaveformLane.tsx`: DPR-correct sizing — set the backing store to
   `clientWidth × devicePixelRatio` and `ctx.scale(dpr, dpr)` — plus a
   `ResizeObserver` redraw, and **draw the fades** as gain-ramp overlays with
   trim shading (fixes B14, B20). Route its bar color through the one shared
   meter-palette function extracted from `Waveform.tsx`'s `barColor`
   (categorical color, permitted by `DESIGN_SYSTEM.md` §2 — but defined once).
4. New `lib/timeAxis.ts`: `niceStep`, `formatTime`, `ticksFor({durationSec,
   pxPerSecond, widthPx})`. Rewire `TimeRuler`, `Waveform.tsx`, and the
   timeline's inline 5-fraction ruler to it (removes the third tick
   implementation).
5. Convert trim/fade/selection gestures in `StitchTimelineClip` to **pointer
   events with `setPointerCapture`**, and fix the drag math with a drag-start
   anchor (fixes B15, B16).
6. Fix `handleReorder` to apply the full permutation (or drive `Reorder.Group`
   from a single `setClips(next)` rather than index-by-index moves) and delete
   the unused `newIndices` (fixes B17).
7. Promote region edits into the stitch plan/session model: define the shared
   region-edit type outside `StitchTimeline.tsx`, store edits by clip, include
   them in draft clone/commit and payload serialization, and remove
   `StitchEditorBody`'s private `regionEditsByClip` state (fixes B24).
8. Move preview URL/blob, rendering, stale/error, playback, and request lifecycle
   out of zustand into an editor-local `useStitchPreview(planHash)` hook. Revoke
   every replaced/unmounted object URL and abort superseded requests (fixes B25).
9. Verification: existing capture scenarios still pass unchanged; waveforms are
   crisp at 1× and 2× DPR; handles track 1:1 under pointer capture; repeated
   open/close cycles do not grow the LRU or leak object URLs; a 6-clip timeline
   uses the shared decode context; region edits survive quick-insert → Studio;
   Cancel leaves both the committed plan and Studio preview unchanged.

### Phase 1 — Navigation, naming, and the quick-insert contract

Files: `store.ts`, `App.tsx`, `OmniVoicePanel.tsx`, `VoiceLibraryPage.tsx`,
`StitchTimeline.tsx`.

1. Store: `ovStitchEditorReturnPage` + setter. Introduce the
   `StitchPlanSession` interface and local/store-backed adapters; do not add a
   global rollback snapshot.
2. `App.tsx`: hoist `<StitchEditorPanel>` to app root per Decision B.
3. `OmniVoicePanel.tsx`: remove its render; set the return page when opening.
4. `VoiceLibraryPage.tsx`: both handlers stop navigating to `voice-design`;
   create a local quick-insert draft from the live plan plus incoming clip, set
   return page `voice-library`, and rename user-visible copy to "Stitch Studio"
   (`"+ Insert into Stitch Studio"`; `"Open in Stitch Studio"` is already right).
5. `StitchTimeline.tsx`: consume `StitchPlanSession`, implement Decision A's
   three-action footer, and commit/discard atomically. Rename the shared header
   to "Stitch Studio" with a contextual subtitle such as
   `Arranging 2 clips · 4.2s` so the modal and the page never disagree.
6. Also fix the **Voice Library discoverability** complaint that the segments
   list is a long scroll under the voices list: add a segments/voices
   **tab or sticky section switcher** at the top of Voice Library (user:
   "we need tabs to be able to quickly see reference voices vs segments"). Reuse
   `ui/tabs.tsx`; preserve the existing search, project grouping, and layout-mode
   toggle inside each tab; persist the selected tab in `localStorage` next to the
   existing `voice-library-layout` key.
7. Verification (manual, dev stack): insert one segment from Voice Library →
   modal shows 1 clip, **no save button anywhere** → X → back on Voice Library.
   Repeat → "Open in Stitch Studio" → real Stitch Studio page with the clip on
   canvas. Repeat → "Save and close" → still on Voice Library, clip present when
   you navigate to Stitch Studio later. Repeat → "Cancel" → clip count
   unchanged from before the modal opened.

### Phase 2 — `SegmentBrowserModal`

Files: new `components/SegmentBrowserModal.tsx`, `StitchTimeline.tsx`,
`tests/ui/capture/scenarios/stitch-studio/*`, `tests/ui/capture/scenarios/wizard/design-to-stitch-gif.mjs`.

1. Build per Decision C.
2. Replace all four `LibraryPickerButton` instantiations with one promoted
   "Add segments" primary-weight button (plus the empty-state call to action);
   delete `LibraryPickerButton`.
3. **Honor the testid contract** (below): keep `stitch-picker-toggle-segments`,
   `stitch-picker-item-segments`, `stitch-picker-insert-segments` as the
   corresponding new elements' testids, or update all three capture scenarios in
   the same commit. The `.shadow-lg` visibility probe in
   `assembly.mjs`/`segment-library-browse.mjs`/`design-to-stitch-gif.mjs` must be
   replaced with a stable testid-based wait — a class-name probe against a new
   dialog will silently hang for 5s and then fail.
4. Update `tests/ui/README.md`'s `segment-library-browse` description to the new
   modal.
5. Verification: `segment-library-browse` and `stitch-assembly` captures produce
   the new modal; only one row can play at a time; static thumbnails stay crisp;
   project filter narrows; Enter/Add and optional double-click both insert;
   "Insert selected (2)" appends both clips with Phase 4's suggested gaps. Test
   with at least 250 fixture rows and confirm scrolling remains responsive.

### Phase 3 — Timeline craft: scale, gaps, transport

Files: `StitchTimeline.tsx` (`StitchTimeline`, `GapControl`, `MsStepper`,
`StitchTimelineClip`), `lib/timeAxis.ts`, `waveform/WaveformLane.tsx`,
`index.css` (new tokens only if needed).

1. **Time-scaled arrangement** per Decision D: `pxPerSecond` state, Fit/−/+
   controls, `Ctrl/⌘+wheel` zoom, gridlines from `lib/timeAxis.ts`, clamped-width
   affordance instead of silent lying (fixes A9).
2. **Gap as a first-class object** (fixes A7, A8):
   - Always rendered, including at 0ms, as a seam marker with a **large,
     tabular-nums seconds readout** (`0.00s` / `0.20s` / `1.08s`) sized for low
     vision — no 10px text in this control, ever.
   - **Drag the seam** left/right to change the gap, with a live readout and a
     magnetic snap set (0 / 80 / 150 / 250 / 400 / 600 / 900ms) that can be
     bypassed with `Alt`.
   - **Click the number to type it** (`<input>` accepting `200`, `0.2s`, or
     `200ms`; Enter commits, Escape reverts), `↑/↓` nudge 10ms, `Shift+↑/↓`
     100ms, and a sane range (0-5000ms, replacing the silent 3000ms cap).
   - Tooltip names the seam ("gap between clip 2 and clip 3") so reorder
     semantics (B18) are legible.
   - Distinct visual states: **0ms = butt-joined** (tight seam glyph, muted),
     **>0 = open gap** (brand-tinted, width-true), **crossfade active** (DSP
     `crossfadeMs` > 0 overlaps the seam — show it, since it currently only
     exists as a number in the DSP panel).
3. **One transport with a real playhead** (fixes B23 in part, plus the
   "can't tell where I am" complaint): arrangement-wide playhead sweeping clips
   and gaps, click-to-seek on the ruler/lanes, `Space` play/pause, per-clip play
   scoped to that clip's span. Playhead visual language comes from
   `Waveform.tsx` (`PLAYHEAD_COLOR` + glow + head dot) — extracted to the shared
   palette module so the timeline and every waveform agree.
4. **Keyboard model** (VST-grade table stakes, exposed through focused
   tooltips and a compact shortcuts dialog): `Space` play/pause, `←/→` select
   previous/next clip, `Alt+←/→` move selected clip, `Delete` remove selected
   clip, and `[`/`]` nudge trim. Shortcuts never fire while focus is in an
   input, textarea, select, or editable control. Undo is **not** in this plan:
   no history model exists, and a partial `Ctrl/⌘+Z` would be misleading.
5. **Motion polish** (all gated on the existing `useReducedMotion`):
   `motion` layout animation on insert/reorder/remove so clips slide rather than
   jump; gap width springs to its new value; new clips fade+rise in; the
   "changes pending" → "rendered" transition cross-fades instead of popping.
6. **Surface treatment**, using existing tokens only (`--surface-1`, `--brand-*`,
   semantic status tokens, `oklch` neutrals): lane background with a subtle
   inset/gradient like `Waveform.tsx`'s `from-black/30`, 1px hairline grid,
   clip cards with real elevation and a brand-tinted selected state, gap chips
   as `--brand-*` tinted pills. No new arbitrary hex/hsl outside the shared
   meter palette; `npm --prefix frontend run lint` must stay clean against
   `design-system/no-raw-status-colors`.
7. **Preview cost control** (fixes B21): commit-on-gesture-end for seam drags and
   numeric entry, raise the idle debounce, and `AbortController`-cancel the
   in-flight `renderStitchPlan` when a newer edit supersedes it. Extend
   `lib/api.ts::renderStitchPlan` to accept an optional `AbortSignal`; keep
   `renderSeqRef` as the defense against late non-abortable responses.
8. **Accessibility and performance acceptance**: all interactive targets are at
   least 44×44 CSS px unless part of a keyboard-accessible dense ruler; every
   icon action has an accessible name; focus is always visible; status changes
   use a polite live region; color is never the only state signal. During
   pointer drag, zoom and playback, avoid React state per animation frame —
   update canvas/transforms via RAF and commit semantic state at gesture end.
9. Verification: a 3-clip timeline with 0 / 200 / 2000ms gaps is instantly
   readable; values are legible without zooming; gaps support type, drag, and
   keyboard nudge; Fit frames a 12s arrangement; the playhead stays synchronized
   with audio; keyboard-only operation reaches every action; reduced motion
   removes transitions without breaking layout; sustained drag/zoom has no
   obvious frame drops in Chromium's performance panel.

### Phase 4 — Automation: smart defaults that remove bookkeeping

Files: `lib/stitchClips.ts`, `StitchStudioPage.tsx`, `StitchTimeline.tsx`.

1. **Visible suggested gaps on insert.** Gaps currently default to 0. Move the
   existing punctuation heuristic (`520ms` sentence-final, `260ms` clause,
   otherwise `90ms`) from `StitchTimeline.autoPace` into `lib/stitchClips.ts`
   and apply it when a clip is appended. Immediately expose the result in the
   always-visible gap control and announce "Suggested from punctuation"; never
   silently overwrite a gap after the user edits it. "Auto-pace" explicitly
   reapplies client suggestions; "Normalize pacing" remains the higher-fidelity
   server action. This is predictable automation, not hidden magic.
2. **Auto-name on first clip** (fixes A10): when `clips` goes 0 → 1 and the name
   field is untouched, fill it from `suggestedStitchVoiceName(clips[0])`
   immediately. Remove the "Use source name" link; keep the field editable and
   never overwrite a user edit or a later clip's name. Mark the field as
   auto-filled (subtle "from source" hint + a revert affordance) so provenance
   is explicit rather than mysterious.
3. **Actionable empty state**: replace "No clips in timeline" with a real
   zero-state — one primary "Add segments" (opens the Phase 2 browser) plus a
   one-line explanation of the 10-15s target.
4. Verification: insert a segment → name pre-filled, no click needed; insert a
   second → name unchanged and a non-zero, punctuation-appropriate gap already
   present and visible; edit the name, insert a third → name still yours.

### Phase 5 — Readiness, guidance, and action hierarchy

Files: `StitchTimeline.tsx` (`StitchEditorBody`), `StitchStudioPage.tsx`.

1. **Reference-readiness meter** — mechanically enforce the user's rule that a
   reference should not be saved from one tiny clip. Track two values:
   - **Source material** = sum of effective clip durations after trims, excluding
     inter-clip gaps. This drives the hard minimum.
   - **Rendered length** = source material + gaps, adjusted for crossfade. This
     drives the 10-15s target and the timeline ruler.
   States:
   - source material `< 5s` → save disabled, `status-tone-warning`: "Add ~Xs of
     clip audio." Inter-clip spacing must never satisfy the minimum. This is a
     duration proxy, not VAD-measured speech; label it honestly.
   - source material `≥ 5s`, rendered length `< 10s` → save enabled with warning:
     "Usable; 10-15s usually gives a stronger reference."
   - rendered length `10-15s` → `status-tone-success`: "Ideal reference length."
   - rendered length `> 15s` → `status-tone-info`: "Longer than recommended;
     trim unless the extra material adds useful range." This matches the existing
     `reference_analysis.py` warning boundary; do not invent a 20s threshold.
   Display both values, e.g. **8.7s clips + 1.1s spacing = 9.8s rendered**.
2. **Guidance rail** answering "what do I do next" (A11): a slim, non-modal
   step indicator — *Add clips → Reach 10-15s → Name it → Save as reference
   voice → Adjust prosody* — where the current step derives from clip count,
   source-material duration, rendered length, name validity, and
   `ovSavedVoiceId`. Each step is clickable where useful. No wizard and no
   blocking overlay; this replaces 12px muted instruction prose.
3. **Action hierarchy**: exactly one primary action at a time (`.btn-brand`) —
   "Add segments" below the source-material minimum, then "Save reference voice"
   once source duration and name are valid. A missing name disables save and
   focuses the name step; do not wait for a server error. Auto-pace, Normalize
   pacing, and zoom stay secondary; DSP controls and delivery variant remain
   disclosed. The footer shows both source and rendered duration using the same
   tabular time treatment as gaps.
4. **Live preview, first class** (fixes B23): replace `PreviewPlayer` with the
   real `Waveform`, fed by peaks from the editor-local rendered preview blob —
   playhead, click-to-seek, active pulse while rendering, and clear
   stale/failed states reusing today's status language.
5. Verification: with 2.6s of source audio, save is disabled and the meter says
   how much clip audio is missing; increasing only gaps never unlocks save; with
   a valid name, ≥5s source material, and 10-15s rendered length, save is primary
   and the meter reads ideal. The guidance rail follows real state; a gap edit
   updates the combined preview waveform after the debounce and seek stays in
   sync.

### Phase 6 — Save: reference voice, optionally the API default

Files: `StitchTimeline.tsx` (studio-mode footer), `StitchStudioPage.tsx`
(`handleSave`), existing `activateVoiceForApi`.

1. Place an explicit option beside the primary save action:
   **"Use as default for API calls"**, off by default, with supporting text
   explaining that requests without `voice_id` use this voice. When off, the
   primary label is **"Save reference voice"**. When on, it becomes
   **"Save & use as API default"** and, after save, calls
   `activateVoiceForApi(newVoiceId)`. Do not hide this consequential choice in a
   split-button dropdown. Studio mode only; quick-insert never saves a voice.
2. Surface the outcome honestly: on success, show the saved voice and what it
   means ("served by `/v1/audio/speech` when no voice is specified" for the
   activated path), with the Phase 7 "Adjust prosody" handoff as the obvious next
   step. Today's bare `Saved to voice library as <id>` line is the floor, not the
   ceiling.
3. Do **not** touch `is_default` / family-default. Different concept, already
   correct, out of scope.
4. Failure handling: if save succeeds and activation fails, report the voice as
   saved with a distinct activation error; never present partial success as a
   total save failure.
5. Verification: plain save leaves `api_active` untouched; opting into API
   default makes the new voice active; forced activation failure reports
   "saved, not activated."

### Phase 7 — Voice Edit page (prosody as a first-class surface)

Files: `store.ts` (`Page`), `AppShell.tsx` (`NAV_ITEMS`), `App.tsx`, new
`pages/VoiceEditPage.tsx`, new/refactored saved-voice picker and prosody units,
`VoiceLibraryPage.tsx`, `VoiceSelector.tsx`,
`tests/ui/core/basic.spec.js`, `tests/ui/performance/performance.spec.js`.

1. **Extract, don't duplicate**: pull the card-popover prosody implementation
   (state ~855-914; JSX ~1440-1650) into `useProsodyEditor(voiceId)` +
   `ProsodyEditorPanel`, consumed by both the existing popover (compact layout)
   and the new page (large waveform/markers, side-by-side variant list, A/B via
   existing `VariantCompare`/`AlignmentCompare`).
2. Extract a pure `SavedVoicePicker` (saved voices and family grouping only,
   no navigation side effects). Refactor `VoiceSelector` to compose it with the
   Pocket built-in and create/design affordances. Voice Edit uses the pure
   picker and honors `deepLinkProsodyVoiceId`.
3. Add `'voice-edit'` to `Page`; add **Voice Edit** between Voice Library and
   Stitch Studio (description: "Prosody & variants", testid
   `nav-voice-edit`); route it in `App.tsx`; add it to both nav test arrays.
4. Voice Library keeps full prosody functionality, per explicit instruction.
5. Verification: Voice Edit → select the Phase 6 voice → adjust marker →
   preview → save variant → confirm the same variant appears in Voice Library's
   popover (one data path, two surfaces).

---

## Visual and interaction acceptance contract

"Premium VST" is not a request for maximum decoration. It means precise
information hierarchy, instantaneous feedback, truthful time geometry, sharp
rendering, and controlled motion. These requirements are release gates:

1. **Three-layer visual grammar**
   - App chrome: quiet neutral surfaces; navigation and global state.
   - Work surface: inset timeline grid, ruler, clips, seams, playhead.
   - State accents: brand color for selection/commit, amber playhead, semantic
     success/warning/error. No competing neon borders on every control.
2. **Typography and numerics**
   - Geist Sans for labels; Geist Mono with `tabular-nums` for time, duration,
     gap, trim, and meter readouts.
   - Essential values are at least 14px; the primary gap/time readout is at
     least 16px. Metadata MAY be smaller but must meet contrast requirements.
3. **Motion**
   - Motion explains causality: insert, reorder, remove, render-state change.
     No perpetual decorative animation except active playback/rendering.
   - Typical UI transitions finish in 120-220ms; reduced-motion removes travel
     and springs while preserving state changes.
4. **Rendering and responsiveness**
   - Canvas is DPR-correct at 1×/2×; no blurry waveform or ruler text.
   - Dragging, scrubbing, zooming, and playhead motion target 60fps on the
     supported desktop Chromium surface. The 250-row browser scroll has no
     long task over 50ms in the recorded interaction. No React render per audio
     frame.
   - Verify 1280×720, 1440×900, 1568×700 (reported screenshots), and 1920×1080.
     At narrower desktop widths, controls stack; timeline remains scrollable.
5. **Accessibility**
   - WCAG 2.2 AA contrast for text and controls; focus-visible on every action;
     44px primary pointer targets; no hover-only action; no color-only meaning.
   - Modal focus trap/restore, named tabs, keyboard selection/reorder, live
     announcements for render/save/activation state, and text equivalents for
     waveform-only information.
6. **Perceptual QA**
   - Capture before/after screenshots at the four target viewports and inspect
     alignment, clipping, text truncation, contrast, focus, empty/loading/error
     states, and all four accent themes. Automated build success is not visual
     acceptance.

---

## Testid and capture contract (do not break the product screenshots)

`tests/ui` drives the README/marketing screenshots and GIFs. Identifiers are
load-bearing; any rename lands with its scenario update.

| Identifier | Used by | Plan impact |
| --- | --- | --- |
| `nav-stitch-studio`, `nav-voice-library`, `nav-speak`, `nav-voice-design`, `nav-integrations`, `nav-runtime` | `core/basic.spec.js`, `performance/performance.spec.js`, 3 capture scenarios | unchanged; add `nav-voice-edit` to both spec arrays |
| `stitch-picker-toggle-segments` | `assembly.mjs`, `segment-library-browse.mjs`, `design-to-stitch-gif.mjs` | becomes the new Add segments trigger, or update all three |
| `stitch-picker-item-segments`, `stitch-picker-insert-segments` | same three | map to the new modal row + insert action |
| `.shadow-lg` popover opacity probe | same three | replace with a stable dialog testid wait |
| `stitch-clip` | `assembly.mjs`, `design-to-stitch-gif.mjs` | keep on the clip card |
| `stitch-voice-name` | `design-to-stitch-gif.mjs` | keep; clear before typing because Phase 4 pre-fills it |
| `stitch-save-voice` | `design-to-stitch-gif.mjs` | keep on primary save; fixtures need ≥5s source material; gaps cannot unlock it |
| `stitch-use-source-name` | none found | safe to remove |
| `stitch-start-over`, `voice-card`, `voice-set-default` | specs/scenarios | unchanged |

Required new scenarios: gap editing with 0ms/non-zero seams, readiness at
blocked/warning/ideal states, the 250-row segment browser, and Voice Edit.
Register each in the capture manifest and `tests/ui/README.md`.

---

## Non-goals (explicit)

- **No server endpoint or payload-contract changes.** Existing endpoints cover
  activation, segment/voice listing, stitch render/save, and prosody variants.
  Adding an optional `AbortSignal` to the frontend `renderStitchPlan` wrapper is
  in scope and does not change the HTTP contract.
- **No new frontend dependencies** — no wavesurfer/tone/konva/chart/windowing
  libraries. If native `content-visibility` and batching miss the measured
  large-list budget, implement focused in-repo windowing.
- **No undo/history stack.** No history model exists; a half-undo is worse than
  none. "Start over" remains the escape hatch.
- **No changes to OmniVoice generation/audition** itself — only to how its
  output is inserted downstream.
- **No change to `is_default` / family-default variant logic.**
- **No DSP-algorithm changes** (crossfade/compression/targets keep their current
  math; Phase 3 only makes crossfade *visible*).
- **No light-theme work.** The app is `color-scheme: dark` with accent themes;
  new surfaces must respect the four accent themes but need not add a light mode.

## Risk notes

- **Phase 3 is the largest change** and touches the component that
  `OmniVoicePanel`, `StitchStudioPage`, and three capture scenarios all render.
  Land Phase 0 and Phase 1 first (independently shippable), then Phase 3 behind
  its own review so a visual regression is bisectable.
- `StitchTimeline.tsx` is already 1787 lines. Phases 0-3 should *reduce* it by
  moving audio/axis/palette concerns into `lib/` and the browser modal into its
  own file — if the file grows, the refactor was done wrong.
- `VoiceLibraryPage.tsx` (2542 lines) and `OmniVoicePanel.tsx` (2737 lines) are
  the other two hotspots; Phase 7's extraction should shrink the former.

## Verification plan (end to end, after all phases)

Manual walkthrough of the exact reported flow on the dev stack
(`scripts/dev-deploy.sh` on `docker-agent`, or local `persona-forge serve` +
`npm --prefix frontend run dev`; see `docs/dev/validation_checks.md`):

1. Voice Design → OmniVoice → generate and save several segments.
2. Voice Library → **Segments tab** → a segment's "Insert into Stitch Studio" →
   modal with no save action → X returns to Voice Library.
3. Same action → "Open in Stitch Studio" → real page, clip on canvas, **name
   already filled**, readiness meter says how much source material is missing,
   save disabled.
4. "Add segments" → rich browser → audition rows, filter by project → insert
   two more → clips land with visible punctuation suggestions. Repeat with 250
   fixture rows and confirm one-player behavior and responsive scrolling.
5. Gaps: read every value at a glance; type `0.35s`; drag a seam; `Shift+↑`
   nudge; confirm zoom Fit/±.
6. `Space` plays the arrangement; playhead sweeps clips and gaps; click-to-seek
   works; live-preview waveform re-renders after edits settle.
7. Confirm added silence cannot satisfy the 5s source-material gate. At ≥5s
   source material and 10-15s rendered length, the meter reads ideal and save
   becomes primary. Enable "Use as default for API calls", save, and confirm the
   API-active badge in Voice Library.
8. Follow the guidance rail's final step into **Voice Edit** → the just-saved
   voice is preselected → adjust prosody → save a variant → confirm it also
   appears in Voice Library's popover for that voice.
9. Re-run with `prefers-reduced-motion: reduce` and confirm no animation-dependent
   layout breaks.

Automated:

```bash
python scripts/validate_repo.py
docker compose config --quiet
git diff --check
npm run --prefix frontend check

# Existing browser contracts
npm --prefix tests/ui test

# Deterministic visual scenarios changed by this work
node tests/ui/capture/index.mjs --scenario segment-library-browse --source fake
node tests/ui/capture/index.mjs --scenario stitch-assembly --source fake
node tests/ui/capture/index.mjs --scenario design-to-stitch-gif --source fake

# Segment/stitch backend contract remains intact
PYTHONPATH=src:src/export python -m pytest \
  tests/tier1_unit/test_segment_library.py \
  tests/tier2_backend/test_app_omnivoice.py -q
```

Inspect generated screenshots/GIFs; their existence is not proof of visual
quality. Run the manual viewport/theme/accessibility matrix from the visual
acceptance contract. All scenario/testid changes land in the same commit as the
surface change that requires them.

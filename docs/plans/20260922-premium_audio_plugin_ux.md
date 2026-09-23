# Premium Audio-Plugin UX: Interaction Craft Pass

Date: 2026-09-22
Status: **PROPOSED** — planning doc only; not started, not part of PR #310
Branch: TBD (do not start from a review-heated branch; cut fresh when picked up)

## Goal statement

Persona Forge designs a voice for TTS. The owner's direction: the studio should
have the *first-class audio VST plugin feel of the most premium audio plugins* —
sharp interaction detail, instrument-grade direct manipulation, coherent
transport — not a generic web app with audio in it.

The last PR (#310) fixed correctness and artifact truth. This plan raises the
interaction model itself.

Grounding evidence: an independent code survey (2026-09-22, `history://PluginUXScout`)
read the whole frontend against premium audio-industry conventions
(FabFilter/iZotope/UAD-class plugins, Pro Tools/Ableton interaction grammar).
Every idea below names the files it would touch and a one-sentence acceptance
criterion. Governing constraints from the 2026-09-20 overhaul carry forward:
**no light theme, no new frontend deps, no backend endpoint/payload contract
changes, no DSP algorithm changes, no undo/history** (§5 flags one deliberate
exception to consider).

---

## Central finding: the premium foundation already exists; what's missing is *consistency* and *reachability*

The studio already has credible audio-editor DNA. The gap is not a visual
rewrite — it is that the pro-audio primitives live on some surfaces and not
others.

| Premium convention | Where it already exists | Where it is missing |
| --- | --- | --- |
| One shared arrangement transport, RAF playhead, bounded clip audition | `frontend/src/hooks/useStitchTransport.ts:1-160` | `AudioDeck.tsx:72-140` and `AlignmentCompare.tsx:200-249` each own separate local playback models |
| Time-scaled timeline with zoom, ruler, click-to-seek | `StitchTimeline.tsx:227-247, 377-462`; `TimelineRuler.tsx:1-113` | Wheel zoom does not preserve the point under the cursor; no hover time guide on the ruler |
| Pointer-captured trim/fade gestures, monotonic snapping ladders | `StitchClipCard.tsx:185-302`; `GapControl.tsx:1-15, 88-145` | Numeric values themselves (`MsStepper` `StitchClipCard.tsx:20-42`, `SliderField` `StitchTimeline.tsx:535-560`, `AudioDeck` speed `AudioDeck.tsx:18-39`) are click-only — not drag-scrubbable |
| Loop regions with brace/repeat semantics | `AudioDeck.tsx:85-140`; `AlignmentCompare.tsx:353-374` | Stitch Studio arrangement has no loop brace; only per-clip `playRange` |
| Visible keymap / keyboard-first operation | `StitchTimeline.tsx:259-311, 895-920` (`?` dialog) | Installed only while the timeline is mounted; AudioDeck has no keyboard binding; no global layer |
| Right-click context menus | — | No `onContextMenu` anywhere in the frontend |
| Undo/redo history | backend voice-reference undo (`api.ts:140-142, 458-461`) | No editor/plan history (`store.ts:419-703`) |
| Per-clip metering / analysis inspector | `LevelMeter`, `SpectralAccent` (used in `AudioDeck.tsx:252-255`) | Timeline clips draw static peaks only (`waveform/WaveformLane.tsx:15-78`) |

---

## 1. Small hunks (each ~point-PR size, ranked by solo-dev UX ROI)

### S1 — Plugin-style drag-scrub numbers (highest ROI)

**Acceptance:** every visible numeric audio control — trim, fade, gap,
region bounds, DSP sliders, playback speed, OmniVoice duration — supports
click-to-type **plus** horizontal drag-to-adjust; Shift = fine increments,
Alt bypasses snapping where relevant. Live value readout while dragging,
without losing keyboard entry.

**Files:** `StitchClipCard.tsx` (`MsStepper`), `GapControl.tsx`,
`StitchTimeline.tsx` (`SliderField`), `AudioDeck.tsx` (speed), new
`hooks/useDragScrubValue.ts`; `OmniVoice/SegmentRackRow.tsx` (duration) only if
the shared interaction stays small.

**Grounding:** `MsStepper` is a non-editable `<span>` with ± buttons
(`StitchClipCard.tsx:20-42`); `SliderField` shows a formatted value beside a
native range input (`StitchTimeline.tsx:535-560`).

### S2 — Cursor-preserving zoom + hover time readout

**Acceptance:** Ctrl/Cmd-wheel zoom keeps the timeline time under the pointer
**fixed**; hovering ruler or lane shows a vertical guide with an exact time
label (reuse the proven pattern from `AlignmentCompare.tsx:481-493`); Fit
restores prior behavior.

**Files:** `StitchTimeline.tsx:227-247` (zoom handler), `TimelineRuler.tsx:71-86`
(seek math), optional shared coordinate helper in `lib/timeAxis.ts`.

### S3 — Pointer-safe waveform gestures everywhere

**Acceptance:** `Waveform.tsx` drag-selection migrates from mouse-only to
Pointer Events with pointer capture; exact hover time on all waveform
surfaces; modifier-held scrub gesture without breaking click-seek or
loop-region selection. Reduced-motion path unchanged.

**Files:** `Waveform.tsx:47-70, 96-100`; `AudioDeck.tsx:142-168` (already has
the fraction→time mapping state needed for scrub).

### S4 — Semantic consistency of numeric/edit affordances on the timeline

**Acceptance:** one units/tabs/tooltip grammar across trim/fade/gap values —
same units (`ms`/`s` both accepted, shown the same way), same tab order, same
focus ring, same direct-entry behavior; exact values exposed via accessible
text, not hatch/colour alone.

**Files:** `StitchClipCard.tsx:20-42`, `GapControl.tsx:14-35, 213-232`,
`TimelineRuler.tsx`, plus `frontend/src/index.css` **only** if a shared
focus/inspector class must come from existing design tokens.

---

## 2. Medium hunks (one PR each, after the S baseline)

### M1 — Timeline loop brace + loop-aware transport

Drag across the ruler to create a loop brace with draggable handles; Space
replays the active loop; the brace survives zoom/scroll and maps correctly
through `previewScale`.

**Files:** `StitchTimeline.tsx`, `TimelineRuler.tsx`, `useStitchTransport.ts`,
optional `hooks/useArrangementLoop.ts`. **Depends on** S2's coordinate
mapping.

### M2 — Right-click clip/seam context menu

Actions already supported by the domain, as thin wrappers over
`StitchPlanSession` and region-edit callbacks: play range, edit text,
duplicate/insert-after where safe, split selected region, mute/delete selected
region, remove clip, reset trim/fade, focus numeric editor. No new editor
implementations.

**Files:** `StitchTimeline.tsx`, `StitchClipCard.tsx`, `GapControl.tsx`, the
existing Radix context-menu primitive under `components/ui/` (add one only if
none exists). **Depends on** S1 for focusing values.

### M3 — Per-clip metering + compact analysis inspector

Selecting a clip exposes peak/RMS-from-existing-analysis, a live playback
meter wired to the shared transport range, and a compact spectrum/spectral
accent view from the cached analysis. No fake data before analysis resolves;
no new chart dependency.

**Files:** `StitchClipCard.tsx`, `waveform/WaveformLane.tsx`, `LevelMeter.tsx`,
`SpectralAccent.tsx`, `lib/waveform.ts` cache; optional
`components/stitch/ClipInspector.tsx`.

### M4 — One global command/shortcut layer

Global `?`/Cmd-K surface listing navigation, play/stop, focus search, open
Stitch Studio, and page-specific shortcuts; Space never steals focus from
editable controls; the same keymap is displayed in AudioDeck, Voice Edit, and
Stitch Studio.

**Files:** `App.tsx`, `AppShell.tsx`, `StitchTimeline.tsx`, `AudioDeck.tsx`,
`AlignmentCompare.tsx`, new `hooks/useGlobalShortcuts.ts`, new
`components/CommandPalette.tsx`. **Depends on** M1 if global Space should
control the arrangement.

### M5 — A/B snapshot strip for stitch plans

Capture the current plan as A, edit to B, switch without losing either, and
audition both previews with clearly labelled active state. Session-local;
uses existing stitch payloads; no backend change.

**Files:** `StitchStudioPage.tsx`, `useStitchPlanSession.ts`,
`useStitchPreview.ts`, new `components/stitch/StitchABBar.tsx`, possibly
`lib/stitchPlan.ts`.

---

## 3. Structural (larger, deliberate scope)

### T1 — Shared app-level audio transport coordinator

One coordinator owns page-wide transport state (active source, position,
loop/range, keyboard); Stitch Studio, AudioDeck, and AlignmentCompare opt in
and stop competing audio elements. Isolated candidate audition stays scoped and
must not interrupt an active generation job.

**Files:** new `audio/AudioTransportStore.ts` or `store.ts`, new
`hooks/useAudioTransport.ts`, `App.tsx`, `AppShell.tsx`,
`useStitchTransport.ts`, `AudioDeck.tsx`, `AlignmentCompare.tsx`.

**Why non-trivial:** each surface's playback contract differs (callback audio
ref + RAF in `useStitchTransport.ts:1-160`; hidden element in
`AudioDeck.tsx:178-207`; decode-and-play in
`AlignmentCompare.tsx:1-50, 200-249`). Requires explicit source-ownership /
cleanup / interruption semantics without changing server APIs.

### T2 — Editor undo/redo (deliberate exception to a standing non-goal)

Bounded, session-local past/future stacks of complete `StitchPlanState`
snapshots; Cmd/Ctrl-Z / Shift variant; visible buttons + history tooltip;
previews keyed by plan hash; quick-insert drafts stay isolated until commit;
one drag = one history entry; memory capped.

**Files:** new `hooks/useStitchHistory.ts` or `store.ts`,
`useStitchPlanSession.ts`, `StitchTimeline.tsx`, `useStitchPreview.ts`,
`lib/stitchPlan.ts`.

**Why it needs owner sign-off:** "Do not implement undo/history" was an
explicit constraint of the 2026-09-20 execution plan. With destructive
trim/delete/split gesturing, history is the one pro-tool convention most worth
re-elevating — but it must be accepted as a *deliberate architectural
exception*, not smuggled in.

### T3 — First-class track/automation lane view (frontend-only)

Collapsible inspector/lanes for clip-level gain/mute/fade and existing region
edits with automation-like handles, serializing exclusively through the
already-supported `StitchPlanPayload`/region-edit fields. Continuous curves
and new DSP explicitly excluded.

**Files:** `lib/stitchPlan.ts`, `useStitchPlanSession.ts`, `StitchTimeline.tsx`,
`StitchClipCard.tsx`, new `components/stitch/AutomationLane.tsx` or
`ClipInspector.tsx`, `lib/stitchPreview.ts`, `StitchStudioPage.tsx`.

**Why non-trivial:** the model is clip-centric plus discrete region edits
(`store.ts:52-78`), not a lane graph; needs coordinate mapping, selection
semantics, mutation coalescing, and proof that every edit stays representable
in the current payload.

---

## 4. Recommended next-PR scope (if the owner wants one follow-up)

Three things, in this order — none of them a visual restyle, global transport
rewrite, spectral-analysis project, or undo implementation. Each visibly
sharpens the interaction model while leaving the stable architecture intact:

1. **S1 — drag-scrubbable numbers** across `MsStepper`, `GapControl`,
   `SliderField` (AudioDeck speed and OmniVoice duration only if the shared
   hook stays small).
2. **S2 — cursor-preserving zoom + hover time readout**, reusing the proven
   hover-guide pattern from `AlignmentCompare`.
3. **M2 — right-click context menu** on clips/seams as thin wrappers over the
   existing session/region-edit callbacks.

If appetite allows a second PR in the same arc, **M1 (loop brace)** rides the
same coordinate-mapping work and completes the transport story.

---

## 5. Non-goals honored / conflicts flagged

- **No light theme** — honored; all suggestions use existing dark design
  tokens and the semantic status palette.
- **No new frontend dependencies** — honored; React, Motion, Radix, canvas,
  Pointer Events, and the existing analysis cache suffice.
- **No backend endpoint/payload contract changes** — honored by S1–S4, M1–M5,
  T1; T3 restricts itself to fields already in the stitch payload and region
  edits.
- **No DSP algorithm changes** — "spectrum/analysis inspector" means presenting
  already-decoded cached analysis, not a new processor.
- **INT8 statefulness / gunicorn worker rules** — untouched; nothing here
  touches backend model lifecycle.
- **No undo/history** — honored everywhere except T2, which is flagged as a
  candidate architectural exception requiring explicit owner approval, not a
  smuggled feature.
- **Premium direction** — from interaction latency, direct manipulation,
  hover/focus feedback, and coherent transport, not decorative gradients or an
  expanded palette.
- **Prior-plan reference** — the completed governing plan lives at
  `docs/archive/stitch-studio/20260920-stitch_studio_ux_overhaul.md` (+ its
  `_execution_plan.md`), not under `docs/plans/`; this doc follows their
  structure.

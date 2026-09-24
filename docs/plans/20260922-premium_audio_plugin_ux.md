# Premium Audio-Plugin UX: Interaction Craft Pass

Date: 2026-09-22
Status: **APPROVED FOR EXECUTION** — Phases 0–5 below are approved; M3–M5,
T1–T3, and all N-candidates are owner-gated and are decided **once, up front,
at Checkpoint 0** of the master runbook
(`docs/plans/20260923-premium_ux_execution.md`), recorded in the §7 ledger.
V1–V4 are superseded by the presentation plan (see §8 notes).

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
| One shared arrangement transport, RAF playhead, bounded clip audition | `frontend/src/hooks/useStitchTransport.ts:1-193` (full hook contract) | `AudioDeck.tsx:72-140` and `AlignmentCompare.tsx:200-249` each own separate local playback models |
| Time-scaled timeline with zoom, ruler, click-to-seek | `StitchTimeline.tsx:227-247, 377-462`; `TimelineRuler.tsx:1-113` | Wheel zoom does not preserve the point under the cursor; no hover time guide on the ruler |
| Pointer-captured trim/fade gestures, monotonic snapping ladders | `StitchClipCard.tsx:185-302`; `GapControl.tsx:1-15, 88-145` (**already implements the full drag-scrub pattern** — see S1) | The *other* numeric controls (`MsStepper` `StitchClipCard.tsx:26-67`, `SliderField` `StitchTimeline.tsx:527-552`, `AudioDeck.tsx:18-39` speed) don't use that pattern yet — click-only |
| Loop regions with brace/repeat semantics | `AudioDeck.tsx:85-140`; `AlignmentCompare.tsx:353-374` | Stitch Studio arrangement has no loop brace; only per-clip `playRange` |
| Visible keymap / keyboard-first operation | `StitchTimeline.tsx:261-311, 897-924` (`?` dialog) | Installed only while the timeline is mounted; `components/audio/AudioDeck.tsx` has no keyboard binding; no global layer |
| Right-click context menus | — | No `onContextMenu` anywhere in the frontend (verified globally 2026-09-23) |
| Undo/redo history | backend voice-reference undo (`api.ts:140-142, 458-461`) | No editor/plan history (`store.ts:52-92` type slice, `store.ts:322-340` ovStitch slice; 856 lines, zero undo/history symbols) |
| Per-clip metering / analysis inspector | `LevelMeter` exists as a component (`AudioDeck.tsx:253, 304`) — **but it is not a true meter**: level is a normalized peak lookup updated at ~4 Hz, peak is the file max, and `SpectralAccent` redraws peaks (with a synthetic sine fallback). Verified 2026-09-23; fixed by the presentation plan P2–P4 | Timeline clips draw static peaks only (`waveform/WaveformLane.tsx:15-78`); every waveform is normalized to its own max (`lib/waveform.ts:32-33`) |
| Double-click-to-reset on controls (plugin idiom) | — (only `SegmentBrowserModal.tsx:105` uses double-click, for row insert) | No numeric/slider control anywhere supports double-click-to-default |
| Scroll-wheel fine-adjust on numeric controls | timeline zoom (`StitchTimeline.tsx:233-240, 378`) | No value control reacts to wheel; `onWheel` exists only for timeline zoom |
| Determinate feedback for long operations / announcements | `Skeleton` component ships in `components/ui/` | Zero `aria-live`/`role="status"`/`role="progressbar"` anywhere in `frontend/src` (verified globally 2026-09-23); no toast/notification component exists |

---

## 1. Small hunks (each ~point-PR size, ranked by solo-dev UX ROI)

### S1 — Plugin-style drag-scrub numbers (highest ROI)

**Key fact the first draft got wrong:** `GapControl` **already implements** this
interaction pattern — pointer-drag anywhere on the control with
`setPointerCapture`, ladder snapping (`[0, 80, 150, 250, 400, 600, 900]`ms) with
Alt bypass, click-to-type accepting `200` / `0.2s` / `200ms` with
Enter/Escape/blur semantics, Shift-scaled keyboard increments
(`GapControl.tsx:1-14` documents it, `88-235` implements it). So S1 is not
invention; it is **generalization**.

**Acceptance:** every visible numeric audio control — trim, fade, gap ✓
(already), region bounds, DSP sliders, playback speed, OmniVoice duration —
supports click-to-type **plus** horizontal drag-to-adjust; Shift = fine
increments, Alt bypasses snapping where relevant. Live value readout while
dragging, without losing keyboard entry.

**Files:** extract `hooks/useDragScrubValue.ts` **from GapControl's existing
pattern** (not built fresh), then migrate `StitchClipCard.tsx` (`MsStepper`,
`StitchClipCard.tsx:26-67`), `StitchTimeline.tsx` (`SliderField`,
`StitchTimeline.tsx:527-552`), `AudioDeck.tsx:18-39` (speed);
`OmniVoice/SegmentRackRow.tsx` (duration) only if the shared interaction stays
small.

**Grounding:** `GapControl.tsx:88-235` is the reference implementation;
`SliderField` is a display-only formatted span beside a native `<input
type="range">` (`StitchTimeline.tsx:527-552`); `MsStepper` is a non-editable
`<span>` flanked by −/+ buttons (`StitchClipCard.tsx:46-66`).

### S2 — Cursor-preserving zoom + hover time readout

**Acceptance:** Ctrl/Cmd-wheel zoom keeps the timeline time under the pointer
**fixed**; hovering ruler or lane shows a vertical guide with an exact time
label (reuse the proven pattern from `AlignmentCompare.tsx:481-493`); Fit
restores prior behavior.

**Files:** `StitchTimeline.tsx:227-247` (zoom handler at 233-240),
`TimelineRuler.tsx:72-79` (seek math), optional shared coordinate helper in
`lib/timeAxis.ts`. The hover guide is **static** (no animation), so it is
reduced-motion-safe by construction; keep it consistent with the existing
`prefers-reduced-motion` pattern at `StitchTimeline.tsx:35`. Pointer Events
(like `GapControl`) so touch/pen work, not just mouse.

### S3 — Pointer-safe waveform gestures everywhere

**Acceptance:** `Waveform.tsx` drag-selection migrates from mouse-only to
Pointer Events with pointer capture; exact hover time on all waveform
surfaces; modifier-held scrub gesture without breaking click-seek or
loop-region selection. Reduced-motion path unchanged.

**Files:** `components/Waveform.tsx:47-70, 96-100` (the only mouse-only
surface; clip trim/fade gestures already use Pointer Events +
capture); `AudioDeck.tsx:142-168` (already has the fraction→time mapping
state needed for scrub).

### S4 — Semantic consistency of numeric/edit affordances on the timeline

**Acceptance:** one units/tabs/tooltip grammar across trim/fade/gap values —
same units (`ms`/`s` both accepted, shown the same way), same tab order, same
focus ring, same direct-entry behavior; exact values exposed via accessible
text, not hatch/colour alone.

**Files:** `StitchClipCard.tsx:26-67`, `GapControl.tsx:1-14, 213-232`,
`TimelineRuler.tsx`, plus `frontend/src/index.css` **only** if a shared
focus/inspector class must come from existing design tokens.

---

## 2. Execution discipline (mirrors the 2026-09-20 overhaul)

Execute one phase at a time. Do not start a phase until the previous gate is
recorded PASS. No parallel agents: phases share `StitchTimeline` state.
**RED-before-GREEN:** each phase writes its focused Playwright spec in
`tests/ui/` FIRST, runs it against unmodified code to see it fail for the
right reason, then implements. The frontend has **no unit-test runner**; do
not add one and do not reach for Vitest.

**Preflight (every phase):**
`git branch --show-current && git status --short && python scripts/validate_repo.py && npm run --prefix frontend check` — all exit 0.

- **Phase 0 — Baseline evidence.** Run preflight; run
  `node tests/ui/capture/index.mjs --scenario stitch-assembly --source fake`;
  record branch commit, artifact paths, current zoom/scrub/context-menu
  behavior in a packet ledger appended to this doc. No production edits.
  **Gate 0:** all commands exit 0, baseline capture inspectable.
- **Phase 1 — S1 drag-scrub.** RED: Playwright spec asserting drag-scrub,
  Shift-fine, and click-to-type on `MsStepper`/`SliderField`/AudioDeck speed —
  and asserting GapControl does **not** regress. GREEN: extract
  `hooks/useDragScrubValue.ts` from GapControl's pattern; migrate the other
  controls to it. **Gate 1:** RED spec green; GapControl behavior unchanged;
  preflight clean. Commit: `feat(ui): drag-scrubbable numeric controls`.
- **Phase 2 — S2 cursor-anchored zoom + hover guide.** RED: spec asserting the
  timeline time under the pointer is invariant across Ctrl-wheel zoom, and
  hover on ruler/lane renders a guide with exact time. GREEN: anchor math in
  `onWheelZoom` (`StitchTimeline.tsx:233-240`); hover guide reusing the
  `AlignmentCompare.tsx:478-493` pattern. **Gate 2:** spec green; zoom/fit/
  scroll regression check; capture refresh.
- **Phase 3 — S3+S4 pointer-safe Waveform + semantic numeric grammar.** RED:
  Waveform drag-select via synthetic Pointer Events (pointer capture); units/
  tab-order assertions on trim/fade/gap. GREEN: migrate
  `components/Waveform.tsx:47-70, 96-100` to Pointer Events; unify units/
  focus-ring/tab order. **Gate 3:** spec green; existing `tests/ui` specs pass.
- **Phase 4 — M1 loop brace** (depends on Gate 2's coordinate mapping). RED:
  drag-on-ruler creates brace; Space replays the loop; brace survives zoom.
  GREEN: `StitchTimeline` + `TimelineRuler` + `useStitchTransport`. **Gate 4:**
  spec green; per-clip `playRange` unregressed.
- **Phase 5 — M2 context menu** (depends on Gate 1). RED: right-click on
  clip/seam shows the menu; each action invokes the existing session/
  region-edit callback. GREEN: add `components/ui/context-menu.tsx` wrapping
  the already-installed unified `radix-ui` package (`ContextMenu` export is
  present; no dependency change); wire actions to `StitchPlanSession` +
  region-edit callbacks. **Gate 5:** spec green; a keyboard-only path to the
  same actions exists.
- **Phase 6+ — decided at runbook CP0a (2026-09-23):** accepted N1 + N2
  (fold into Phase 1), N6 (folds into Phase 4), N5 (folds into Phase 5), and
  structural items as numbered phases: **Phase 6 T2 undo/redo** (owner's
  selection is the recorded architectural sign-off for the no-undo
  exception, §6), **Phase 7 M4 command palette**, **Phase 8 M5 A/B plan
  snapshots**, **Phase 9 T1 shared transport**, and **Phase 10 M3 clip
  inspector** (runs after presentation P4 — see runbook §2). **T3 deferred.**
  Each keeps the same RED-before-GREEN gate; commit titles: `feat(ui): stitch
  editor undo/redo`, `feat(ui): global command palette`, `feat(ui): A/B plan
  snapshots`, `feat(ui): shared audio transport coordinator`, `feat(ui): clip
  analysis inspector`.

A failed gate reopens its phase; never compensate in a later phase. One
Conventional Commit per phase (titles pre-assigned above). The whole arc
(this plan + the presentation plan) ships as **one PR**, opened at the
presentation plan's P12; its override block carries one entry per phase.

---

## 3. Medium hunks (one PR each, after the S baseline)

### M1 — Timeline loop brace + loop-aware transport (approved as Phase 4; rides Gate 2's coordinate mapping)

Drag across the ruler to create a loop brace with draggable handles; Space
replays the active loop; the brace survives zoom/scroll and maps correctly
through `previewScale`.

**Files:** `StitchTimeline.tsx`, `TimelineRuler.tsx`, `useStitchTransport.ts`,
optional `hooks/useArrangementLoop.ts`. **Depends on** S2's coordinate
mapping.

### M2 — Right-click clip/seam context menu (approved as Phase 5)

Actions already supported by the domain, as thin wrappers over
`StitchPlanSession` and region-edit callbacks: play range, edit text,
duplicate/insert-after where safe, split selected region, mute/delete selected
region, remove clip, reset trim/fade, focus numeric editor. No new editor
implementations.

**Files:** `StitchTimeline.tsx`, `StitchClipCard.tsx`, `GapControl.tsx`. There
is **no** context-menu primitive in `components/ui/` today — M2 must create
`frontend/src/components/ui/context-menu.tsx` wrapping the **already-installed
unified `radix-ui` package**, which exports `ContextMenu` (pattern used by
`components/ui/tooltip.tsx:3`). Zero dependency changes — the no-new-deps
constraint holds. **Depends on** S1 for focusing values.

### M3 — Per-clip metering + compact analysis inspector (owner-gated)

Selecting a clip exposes peak/RMS-from-existing-analysis, a live playback
meter wired to the shared transport range, and a compact spectrum/spectral
accent view from the cached analysis. No fake data before analysis resolves;
no new chart dependency.

**Files:** `StitchClipCard.tsx`, `waveform/WaveformLane.tsx`, `LevelMeter.tsx`,
`SpectralAccent.tsx`, `lib/waveform.ts` cache; optional
`components/stitch/ClipInspector.tsx`.
**Depends on (if accepted):** presentation plan P2 (absolute RMS/peak
envelope) and P4 (meter) — schedule after those land; do not build a second
analysis path.

### M4 — One global command/shortcut layer (owner-gated)

Global `?`/Cmd-K surface listing navigation, play/stop, focus search, open
Stitch Studio, and page-specific shortcuts; Space never steals focus from
editable controls; the same keymap is displayed in AudioDeck, Voice Edit, and
Stitch Studio.

**Files:** `App.tsx`, `AppShell.tsx`, `StitchTimeline.tsx`, `AudioDeck.tsx`,
`AlignmentCompare.tsx`, new `hooks/useGlobalShortcuts.ts`, new
`components/CommandPalette.tsx`. **Depends on** M1 if global Space should
control the arrangement.

### M5 — A/B snapshot strip for stitch plans (candidate, owner-gated)

Capture the current plan as A, edit to B, switch without losing either, and
audition both previews with clearly labelled active state. Session-local;
uses existing stitch payloads; no backend change.

**Files:** `StitchStudioPage.tsx`, `useStitchPlanSession.ts`,
`useStitchPreview.ts`, new `components/stitch/StitchABBar.tsx`;
`lib/stitchPlan.ts` only if the snapshot type needs a home.

**Status:** candidate idea — no acceptance signal from the owner yet; give it
an explicit acceptance note before cutting a phase for it.

---

## 4. Structural (larger, deliberate scope)

### T1 — Shared app-level audio transport coordinator (owner-gated)

One coordinator owns page-wide transport state (active source, position,
loop/range, keyboard); Stitch Studio, AudioDeck, and AlignmentCompare opt in
and stop competing audio elements. Isolated candidate audition stays scoped and
must not interrupt an active generation job. This changes playback semantics
across three surfaces at once, so it carries the same "deliberate exception
requiring explicit owner approval" framing as T2 — it is a candidate, not
committed scope.

**Files:** new `audio/AudioTransportStore.ts` or `store.ts`, new
`hooks/useAudioTransport.ts`, `App.tsx`, `AppShell.tsx`,
`useStitchTransport.ts`, `AudioDeck.tsx`, `AlignmentCompare.tsx`.

**Why non-trivial:** each surface's playback contract differs (callback audio
ref + RAF in `useStitchTransport.ts:1-193`; hidden element in
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

### T3 — First-class track/automation lane view (frontend-only; candidate)

Collapsible inspector/lanes for clip-level gain/mute/fade and existing region
edits with automation-like handles, serializing exclusively through the
already-supported `StitchPlanPayload`/region-edit fields. Continuous curves
and new DSP explicitly excluded. Whether every existing edit is representable
in the current payload **is the open question** this phase must answer before
any implementation — treat this as conditional until that proof exists.

**Files:** `lib/stitchPlan.ts`, `useStitchPlanSession.ts`, `StitchTimeline.tsx`,
`StitchClipCard.tsx`, new `components/stitch/AutomationLane.tsx` or
`ClipInspector.tsx`, `lib/stitchPreview.ts`, `StitchStudioPage.tsx`.

**Why non-trivial:** the model is clip-centric plus discrete region edits
(`store.ts:52-78`), not a lane graph; needs coordinate mapping, selection
semantics, mutation coalescing, and proof that every edit stays representable
in the current payload.

---

## 5. Recommended next-PR scope (if the owner wants one follow-up)

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

## 6. Non-goals honored / conflicts flagged

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

---

## 7. Phase ledger (appended during execution)

| Phase | Gate result | Commit | Notes |
| --- | --- | --- | --- |
| 0 baseline | PASS 2026-09-23 | b7180f1 | Suite 68/68 on `--source fake`; 11 capture scenarios saved as the before-set. Zoom was button-only + unanchored Ctrl-wheel; no context menu; drag-scrub only in GapControl. |
| 1 S1 drag-scrub + N1 + N2 | PASS 2026-09-23 | 9f6d4cc | `useDragScrubValue` extracted from GapControl (zero-change refactor), then MsStepper / SpeedStepper / SliderField migrated: drag-scrub, click-to-type, double-click reset, opt-in wheel. drag-scrub.spec 5/5; full suite 73/73. |
| 2 S2 zoom+hover | PASS 2026-09-23 | 783d9d5 | Cursor-anchored zoom (layout-effect scroll correction) + imperative hover time guide. zoom-hover.spec 3/3; full suite 76/76. |
| 3 S3+S4 waveform+grammar | PASS 2026-09-23 | b427c4d | Waveform moved to Pointer Events with capture (drag survives leaving the control; release outside still commits); one ms display/parse grammar across trim/fade/gap; one tab stop per control with the shared house focus ring. waveform-pointer.spec 3/3; full suite 79/79. |
| 3b S3 completion (hover readout + scrub) | PASS 2026-09-23 | 6479ec4 | S3's acceptance prose taken on by owner decision: one `formatHoverTime` + one `useHoverTimeGuide` across all five waveform surfaces (deck, clip lane, prosody variant lanes, prosody region editor, voice-edit compare; the stitch ruler adopted it and dropped its bespoke guide), plus Alt-drag scrub on the deck. waveform-pointer.spec 6/6; full suite 82/82. Readout precision is 10 ms everywhere (owner decision after asking about tenths): `formatHoverTime(seconds)` takes no scale argument, renders `1.23s` below 10s and `0:12.34` past it; ruler tick labels keep their own coarser `formatTimelineTime`. Follow-up refactor a1cc047 (lane scale measured at hover time, not observed). |
| 4 M1 loop brace + N6 | PASS 2026-09-23 | fb077c7 | Drag across the ruler sets an arrangement loop (brace + two edge handles), stored in seconds so zoom/scroll cannot move it; wrap runs in the transport's rAF tick and is skipped while a clip range owns its own end; Space starts from the brace when the playhead is parked outside. N6: `lib/playbackFocus.ts` claim/release registry wired into the stitch transport, every deck, the prosody A/B compare, and the voice-edit lane compare. loop-brace.spec 3/3 + exclusive-audition.spec 2/2; suite 86 passed / 1 flaky (pre-existing). |
| 4b clip range readiness fix | PASS 2026-09-23 | a756e31 | The per-clip range button no longer offers playback before the transport can play it: `playRange` refuses a sub-50ms range and the card waits for a known transport duration and clip duration. New range-readiness.spec; suite 89/89. |
| 4c N6 completion (segment audition + variant preview) | PASS 2026-09-23 | a72c891 | The last two audio owners joined the playback-focus registry: the segment browser's row audition and the prosody variant preview. N6's acceptance — "starting any player pauses whichever other player was sounding" — now holds for every owner in the app. Spec 4/4; suite 90 passed / 1 flaky (pre-existing). |
| 4d preview continuity fix | PASS 2026-09-23 | d480bf6 | A preview re-render (a real plan change: gap suggestion or an analysis-driven trim clamp) replaced the transport's src and stopped playback at zero. The transport now carries position as a duration fraction and resumes, including an active clip range. preview-continuity.spec 2/2; suite 93/93. |
| 5 M2 context menu + N5 | PASS 2026-09-23 | 320f672 | Clip/seam/segment-row right-click menus over the already-installed radix-ui ContextMenu (no dependency change). Keyboard parity implemented in the trigger (macOS Chromium never synthesizes `contextmenu` from Shift+F10). Primary-button guards for scrub/selection/trim drags. context-menu.spec 5/5; suite 98/98; captures pixel-identical. |
| 6 T2 undo/redo | PASS 2026-09-23 | d58af05 | Store-driven recording over the four plan slices; cap-100 snapshot stacks; atomic restore; 800ms same-control coalescing (wheel bursts are the case that needs it -- every drag already commits once on release); Cmd/Ctrl+Z behind the editable-target guard; controls survive an empty plan; drafts isolated until commit. undo.spec 7/7; suite 105/105. |
| 7 M4 command palette | PASS 2026-09-23 | 1dbdaed | Shared registry feeds the Cmd/Ctrl+K palette and the `?` keymap; stitch keymap moved in unchanged, its dialog replaced by the global keymap (old rows preserved and asserted); single editable-target guard in the dispatcher; deck commands + compare keys registered (compare keeps focus-scoped dispatch via `when`); header Search button. 5/5 new, studio 42 + core/basic 3 green, suite 110/110 no flakes. Flake fix in e32d9f6. |
| 8 M5 A/B snapshots | PASS 2026-09-23 | 1837929 | Module-state snapshots (session-local, never persisted), one-undoable-entry switching via `replaceOvStitchPlan`, per-slot preview + registry-mediated audition (N6), labelled active slot. ab-snapshots 5/5 (RED verified by stash+rebuild), studio 42 + undo 7 green, suite 114 passed / 1 pre-existing flake. |
| 9 T1 shared transport | PASS 2026-09-23 | dc56730 | Coordinator owns no element/clock: register(kind,label) + claim + report(position) from each surface's own tick; sr-only readout in AppShell written imperatively per frame. Seven owners migrated (card named three; the other three imported the same registry). transport.spec 4/4 (RED verified by stash+rebuild), suite 118 passed / 1 pre-existing flake, captures 0.000% changed px vs a pre-A-9 build. Fake-tier limit (fixed in 23087a1): the tier's async jobs were born completed, so the profile's documented 3-5s window did not exist; the fixture now provides it and the spec asserts the card's actual claim (job still running when playback starts, then finishes uncancelled). |
| N3 + N4 (absorbed into B-P9) | PASS 2026-09-24 | b44bcad | N3's acceptance ("one announcement surface; generation, save and promote route through it") and N4's gate-in ("prove the progress value exists") both landed in presentation P9 — see R §7 `B-P9`. **The proof N4 asked for is that the value was not real:** the fake reported a flat 25% for every running job, so no client could tell a determinate readout from a painted-on one; fixed at the source, then read off the job's own frames. |
| 10 M3 clip inspector | | | after presentation P4 |

**Owner decisions (CP0a, 2026-09-23):** N1, N2, N5, N6 accepted; N3/N4
absorbed by presentation P9; M3, M4, M5, T1, T2 accepted (T2 = recorded
architectural sign-off for the no-undo exception); T3 deferred — revisit
after merge.

---

## 8. Second-pass candidates (owner-gated; added 2026-09-23 self-review re-research)

Evidence for this section came from two passes the first draft never did:
direct code verification (every claim below names the file/line that proves
it) **plus visual review of the four published README screenshots
(`speak-generate--pocket-tts--after-generate.png`,
`stitch-assembly--neutral--assembly.png`,
`hero-voice-design--neutral--panel.png`,
`prosody/voice-edit--neutral--prosody-ab.png`) against the same
FabFilter/iZotope reference frame.** The screenshots surfaced a different
class of gap than the interaction survey: not broken gestures, but
*prototype residue presented as product* (lab-notebook copy, placeholder
version tags, unlabeled dropdowns) and *coarse rendering the interaction
work will sit on top of* (block-bar waveforms). Those are visual-hygiene and
render-quality items — they are small, safe, and they raise the ceiling every
approved phase lands on.

All zero-dep, no-restyle, no backend change. Each is a candidate until you
accept it; none modify Phases 0–5.

### N1 — Double-click-to-reset on the drag-scrub hook (upgrade S1 for free)

The canonical knob/slider reset gesture (double-click restores the parameter's
default) does not exist anywhere in the app today. If accepted **before Gate
1**, it folds into `useDragScrubValue.ts` for free instead of being retrofitted
per-control later. The reset value is a property of each control (MsStepper
default gap, SliderField neutral value, AudioDeck 1.0× speed), never a guess.

**Acceptance:** double-clicking any drag-scrub control restores its defined
default and announces it; GapControl spec asserts non-regression.
**Files:** `hooks/useDragScrubValue.ts` + each migrated control's default.
**Depends on:** S1. **Size:** tiny if folded into Phase 1; small otherwise.

### N2 — Scroll-wheel fine-adjust on numeric controls

Plugin convention: hovering a knob/slider and scrolling nudges the value with
modifier-key fine adjustment. Today `onWheel` exists only for timeline zoom
(`StitchTimeline.tsx:378`); GapControl's own pattern has no wheel path, so the
S1 hook should accept an optional wheel handler per control (opt-in where it
doesn't fight existing scroll containers like the timeline).

**Acceptance:** wheeling over an S1-migrated control nudges value in fine
steps; timeline zoom and page scroll behavior unchanged.
**Files:** `hooks/useDragScrubValue.ts` (+ control sockets opt-in).
**Depends on:** S1. **Risk:** must not hijack wheel inside scrollable
containers — per-control opt-in, never global.

### N3 — One tiny announcement/toast utility (feedback for async wins)

Verified: zero `aria-live`/`role="status"`/`role="progressbar"` occurrences in
`frontend/src`, and no toast/notification component in `components/ui/` despite
`Skeleton` shipping there. Async completions (generation done, save succeeded,
clipboard copy, promote success) currently give no ambient confirmation;
assistive tech gets nothing either. A single non-dependency-built utility —
a small fixed-position toast stack + an `aria-live="polite"` region — closes
both the accessibility gap and the "did it work?" gap with one primitive.

**Acceptance:** the utility is the only announcement surface; generation,
save, and promote paths route a confirmation through it; the region is
programmatically detectable (`role="status"`).
**Files:** new `components/ui/toast.tsx` (or `announcer.tsx`), wired at ~5
call sites (`prosody` variant save/promote, generate, copy, stitch save).
No new deps. **Size:** small; biggest value for the least engineering in §8.

### N4 — Determinate progress for long GPU/model operations

Today `Skeleton` exists but nothing renders `role="progressbar"`. Model loads,
export jobs, and batch renders report nothing but indeterminate shimmer —
a premium instrument shows its ETA. Backend already reports per-job progress
(`fake_model_server.py` mirrors `get_fake_job_progress`; check which surfaces
can show a determinate bar). Phase must first prove the progress source; the
UI hunk is a `components/ui/progress.tsx` wrapper reusing the unified
`radix-ui` `Progress` export if the value source proves out.

**Acceptance:** every operation the backend can measure shows determinate
progress; indeterminate shimmer remains only where the backend can't measure.
**Files:** `components/ui/progress.tsx` + the generation/model-load surfaces.
**Gate-in:** conditional — proof the progress value exists before GREEN.

### N5 — Segment-browser gesture parity (context-menu gentle extension)

`SegmentBrowserModal.tsx:105` is the **only** double-click surface in the app
(row insert). Once M2 ships `components/ui/context-menu.tsx`, the same
primitive is a natural fit for the segment browser row menu (insert, audition,
preview, copy id) — a one-PR polish on an already-approved primitive rather
than a new invention.

**Acceptance:** right-click on a segment row offers the existing actions as
thin wrappers over current handlers; keyboard parity retained.
**Files:** `components/stitch/SegmentBrowserModal.tsx`, reusing M2's context
menu. **Depends on:** Gate 5.

### N6 — Exclusive audition (one sound at a time)

Verified 2026-09-23: five independent `<audio>` owners
(`StitchTimeline.tsx` ×2, `VariantCompare.tsx`, `AudioDeck.tsx`,
`AlignmentCompare.tsx`) plus AlignmentCompare's decode-and-play can sound
simultaneously; starting one never stops another (no coordination symbol
exists). Every plugin host and DAW browser auditions exclusively. This is
the minimal, safe subset of T1: no shared transport state, only a
"playback focus" registry — each player registers a `pause()` callback; any
player starting pauses the others. Isolated candidate audition still must
not interrupt an active generation job (no job coupling at all).

**Acceptance:** starting any player pauses whichever other player was
sounding (Playwright: start deck A, start deck B, assert A paused); no
player's own contract changes.
**Files:** new `lib/playbackFocus.ts`; one register/claim call in each of
the five owners. **Size:** small. **Slot:** Phase 4. **T1 (accepted,
Phase 9) grows this registry into the full coordinator** rather than
replacing it, so N6 is not throwaway work.

---

### V1 — Waveform render quality → **superseded by presentation plan P2**

Kept for provenance. The presentation plan's code audit (A3–A5) found the
problem is deeper than resolution: per-file normalization, a 120-bucket cap,
and per-bar DOM animation. P2 replaces this item; do not execute V1.

The screenshot pass made this the highest-leverage **visual** item in the
plan: every lane today renders the same coarse single-sided block bars
(Speak player, Stitch clips, A/B lanes). Underneath, the data is already
good — `lib/waveform.ts` decodes real peaks via `peaksFromBuffer`
(`lib/waveform.ts:17-32`) with persistent per-clip caching (`45-51`) and an
existing played/unplayed color grammar (`waveformBarColor`,
`lib/waveform.ts:118-125`: cyan/teal base, magenta push, `played` variant).
What is missing is resolution and shape: density-scaled bucketing, a
mirrored (center-line symmetric) silhouette, and a distinct played-region
tint so the playhead reads as position-on-sound, not a yellow line floating
over bars.

**Acceptance:** at typical lane widths every lane renders mirrored,
density-scaled peaks with a visible played-region treatment; no new color —
only the existing `waveformBarColor` grammar at higher fidelity; cache keys
unchanged (`<kind>:<persistent-id>:<revision>`).
**Files:** `lib/waveform.ts` (`peaksFromBuffer`, `waveformBarColor`),
lane renderers that consume peaks (Speak deck, `StitchClipCard`,
`WaveformLane.tsx`, A/B lanes). Canvas vs DOM is the executor's call —
whichever preserves the existing cache contract.
**Size:** medium-small; render-only, zero domain change.

### V2 — Prototype-residue copy sweep → **superseded by presentation plan P6 (info view) + P10**

The Voice Design screenshot shows engineering notebook copy shipped as
product: `"High pitch" trends tinnier in testing — "moderate" is usually the
safer default` and `there's no "warm" or "sweet" here (that's
VoiceDesign-only)` (`components/OmniVoice/AccentChipPanel.tsx:104-125`),
plus `v0.0.0-fake` chrome in published screenshots. The tinny-pitch warning
is genuine product knowledge — it should **survive as design**, not die as
copy: e.g. a "safe default" marker on the Moderate chip, or a one-line hint
that only appears when High/Very-high is selected, instead of a paragraph
the user reads before they have made any choice.

**Acceptance:** no sentence in shipped UI explains the engineering process
(`testing`, backend-name internals); every genuine warning is preserved as
contextual, state-dependent guidance; published screenshots re-captured.
**Files:** `components/OmniVoice/AccentChipPanel.tsx:95-127`,
`VoiceDesignPanel`, `EngineSelector`, AppShell version/footer copy.
**Size:** small; copy-only, zero behavior change. Pairs naturally with
Phase 0 (re-capture baseline while the camera is out).

### V3 — Labeled-control grammar → **superseded by presentation plan P8**

The Speak screenshot shows the pattern that reads most "generic web form":
`Default voice`, `English`, `Off` — dropdowns whose label names the current
*value*, not the *parameter*, so a first-time user cannot tell what the third
one even controls. Plugin convention (and S4's own grammar instinct) is
small-caps parameter labels sitting above the control: VOICE / LANGUAGE /
the `Off` control's actual function (prosody repair? post-processing?),
each with an inline `title`/tooltip.
**Acceptance:** every select on the Speak page carries a visible
parameter label (`<label>` or labelled group), the `Off` control names its
function, and icon-only buttons reuse the existing `tooltip=` pattern from
`AudioDeck.tsx:255`.
**Files:** `pages/SpeakPage.tsx` (controls row), then the same grammar on
Voice Design / Voice Edit selects as a follow-up.
**Size:** small; markup-only. Natural companion to S4's units/tabs/tooltip
grammar — accept together if appetite allows.

### V4 — Capture verdicts → **superseded by runbook §3 + presentation plan P10/P11**

Every phase gate now names its capture scenario (runbook §3); publishing
happens once, in presentation P11 — the "re-shoot after Phase 5" below is
dropped to avoid three re-shoots.

The capture harness already produces before/after pairs for scenarios
(`stitch-assembly`, `prosody-adjustment`, `voice-edit`, `speak-generate`,
`hero-*`, `readiness-states`). The 2026-09-20 plan proved the mechanism
(receipts with hashes), but no phase currently **requires the visual verdict**:
before/after pair inspected, differences attributable to the hunk, no
regression (no layout shift, no truncated labels, no residue). Make each
phase's gate include its capture diff as an artifact, and re-shoot the
eight README screenshots once at the end of Phase 5 — the README is the
product's storefront, and every craft hunk should be visible in it.
**Acceptance:** §2 gates each name their capture scenario; README
screenshots re-shot post-Phase-5.
**Files:** `tests/ui/capture/` scenarios (existing) + §2 gate text.
**Size:** process-only; zero production code.

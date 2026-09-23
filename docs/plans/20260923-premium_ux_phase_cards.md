# Premium UX — Phase Cards (executor instructions)

Date: 2026-09-23
Status: **READY.** Execute top to bottom, one card per session, and **STOP at
every gate**. The protocol, stop conditions, standard commands, and gate
report template are in `docs/plans/20260923-premium_ux_execution.md` §0 —
read that first, every session.

Abbreviations: **A** = `docs/plans/20260922-premium_audio_plugin_ux.md`
(interaction), **B** = `docs/plans/20260923-luminous_instrument_redesign.md`
(presentation), **R** = the runbook. Paths without a prefix are under
`frontend/src/`. Line numbers were taken at commit `abfe76e`. If code has
moved, locate the symbol by name; if it is gone, apply stop condition 1.

Every card ends with the same close-out; it is written out once here:

> **Close-out (every card).** (1) Run the Verify steps; all must pass.
> (2) Fill this phase's row in R §7 and in the owning plan's ledger (A §7 or
> B "Phase ledger") with gate result, commit hash, and a one-line summary.
> (3) Commit with the card's title (one gate commit per phase; intermediate
> commits use the same title with `(part N)`), then
> `git push origin feat/premium-audio-plugin-ux-20260923`. (4) Send the gate
> report (R §0 template) and **STOP**. Do not open the next card.

Test-writing conventions (all cards): specs live under `tests/ui/<area>/`,
use `@playwright/test` with `page.getByTestId(...)`, and follow the helper
style in `tests/ui/stitch-studio/studio.spec.js` (e.g. `insertNSegments`).
When a control needs a test id, add a kebab-case `data-testid` — adding one
is always allowed in files the card lists. To inject exact audio, route the
request with `page.route(...).fulfill({ contentType: 'audio/wav', body })`,
as `tests/ui/fixtures/largeSegmentLibrary.mjs` does.

---

## A-0 — Baseline evidence (no production edits)

**Read:** R §0–§3; A §2 "Phase 0".

**Allowed files:** R §7 and A §7 ledgers only.

**Steps:**

1. Preflight (R §0). All exit 0.
2. Build, then run the full UI suite once and record the result as the
   baseline: `npm run --prefix frontend build && cd tests/ui && npx playwright test`.
   Pre-existing failures are **recorded, not fixed** (list them in the gate
   report). If more than 3 fail, STOP.
3. Capture the published "before" set with `--source fake`, one scenario at
   a time: `speak-generate`, `hero-voice-design`, `prosody-adjustment`,
   `stitch-assembly`, `voice-edit`, `readiness-states`, `omnivoice-audition`,
   `omnivoice-audition-gif`, `design-to-stitch-gif`, `gap-editing`,
   `transport-playback`, `segment-browser-scale`. A scenario that fails on
   the fake source is recorded as such; do not fix it.
4. Copy the whole artifacts tree to the durable baseline:
   `mkdir -p docs/screenshots/artifacts/_gates/A-0 && cp -R docs/screenshots/artifacts/* docs/screenshots/artifacts/_gates/A-0/`
   (`docs/screenshots/artifacts/` is gitignored, so this stays local; B-P12's
   PR "before" images come from here).
5. In the ledger notes record: commit hash, suite pass/fail counts, any
   scenario that failed, and current zoom/scrub/context-menu behavior in one
   sentence each (A §2 Phase 0).

**Commit:** `docs(plans): record A-0 baseline evidence`

**Gate:** preflight clean; baseline suite result and captures recorded. STOP.

> For every later card, "save before" means:
> `mkdir -p docs/screenshots/artifacts/_gates/<card> && cp -R docs/screenshots/artifacts/<category> docs/screenshots/artifacts/_gates/<card>/before`
> run **before** editing any file.

---

## A-1 — Drag-scrub numbers + double-click reset + wheel adjust (S1, N1, N2)

**Read:** A §1 "S1", A §8 "N1" and "N2", A §2 "Phase 1".

**Allowed files:** new `hooks/useDragScrubValue.ts`;
`components/stitch/GapControl.tsx` (reference implementation, lines 88–235);
`components/stitch/StitchClipCard.tsx` (`MsStepper`, line 29);
`components/StitchTimeline.tsx` (`SliderField`, line 529);
`components/audio/AudioDeck.tsx` (`SpeedStepper`, line 13); new
`tests/ui/stitch-studio/drag-scrub.spec.js`; ledgers.

**Save before:** `gap-editing`, `stitch-assembly` (category `stitch-studio`).

**RED** — `tests/ui/stitch-studio/drag-scrub.spec.js`, one `test()` each:

1. Horizontal pointer drag (+40 px) on a trim `MsStepper` increases its
   value; the same drag with Shift held changes it by less.
2. Click the value, type `0.2s`, press Enter → it reads `200 ms`. Escape
   cancels the edit.
3. Double-click restores the control's default (N1).
4. Mouse wheel over the control nudges it (N2); wheel over the timeline
   still zooms (the existing zoom behavior is unchanged).
5. Deck speed (add `data-testid="deck-speed"` to `SpeedStepper`): drag
   changes the rate; double-click returns to `1.0×`.

Build, run: all five fail on unmodified code for "feature missing" reasons.

**GREEN:**
1. Extract `useDragScrubValue` **from GapControl's existing code** (pointer
   capture, ladder snapping with Alt bypass, click-to-type with
   Enter/Escape/blur, Shift fine steps). Add options `defaultValue`
   (double-click reset) and `wheel` (opt-in, fine step with Shift).
2. Refactor `GapControl` onto the hook with **zero behavior change**; run
   `studio.spec.js` now — the gap tests must still pass before continuing.
3. Migrate `MsStepper`, `SliderField`, `SpeedStepper`. Default values: gap →
   GapControl's current default; trim/fade → 0 ms; speed → 1.0; DSP sliders
   → the value a new plan starts with (find it in `store.ts`). If a default
   is not findable, stop condition 1.
4. Wheel stays opt-in per control; never register it on the timeline.

**Verify:** build; `drag-scrub.spec.js` green; `studio.spec.js` green;
captures `gap-editing` + `stitch-assembly` after, compared with before.

**Commit:** `feat(ui): drag-scrubbable numeric controls`

---

## A-2 — Cursor-anchored zoom + hover time guide (S2)

**Read:** A §1 "S2", A §2 "Phase 2".

**Allowed files:** `components/StitchTimeline.tsx` (`onWheelZoom`, line 233);
`components/stitch/TimelineRuler.tsx`; `lib/timeAxis.ts`; new
`tests/ui/stitch-studio/zoom-hover.spec.js`; ledgers.

**Save before:** `stitch-assembly`, `transport-playback`.

**RED:**

1. Ctrl-wheel zoom at a pointer x: the timeline time under the pointer is
   the same before and after zoom (± 1 px of ruler mapping).
2. Hovering the ruler or a lane shows `data-testid="timeline-hover-guide"`
   with an exact time label; moving the pointer updates it; leaving hides it.
3. `stitch-zoom-fit` still restores fit.

**GREEN:** anchor math in `onWheelZoom` (keep the time at pointer invariant
by adjusting scroll after the scale change). Hover guide reuses the pattern
at `components/waveform/AlignmentCompare.tsx:478-493`; Pointer Events; no
animation (static guide is reduced-motion-safe).

**Verify:** build; new spec + `studio.spec.js` green; captures compared.

**Commit:** `feat(ui): cursor-anchored zoom and hover time guide`

---

## A-3 — Pointer-safe waveform + one numeric grammar (S3, S4)

**Read:** A §1 "S3" and "S4", A §2 "Phase 3".

**Allowed files:** `components/Waveform.tsx` (mouse handlers, lines 47–100);
`components/audio/AudioDeck.tsx`; `components/stitch/StitchClipCard.tsx`;
`components/stitch/GapControl.tsx`; `components/stitch/TimelineRuler.tsx`;
`index.css` only for a shared focus class; new
`tests/ui/generate/waveform-pointer.spec.js`; ledgers.

**Save before:** `speak-generate`, `gap-editing`.

**RED:**

1. On the Speak result deck, a synthetic **pointer** drag (`page.mouse` is
   fine; the handler must be `onPointer*` with `setPointerCapture`) selects a
   region; a click without movement still seeks.
2. Trim, fade, and gap values all display units the same way (`ms`, or `s`
   at ≥ 1000 ms) and accept both `ms` and `s` input.
3. Tab order walks trim → fade → gap in DOM order; every one shows the same
   focus ring class.

**GREEN:** migrate `Waveform.tsx` from `onMouse*` to Pointer Events with
capture; unify display/parse formatting in one helper used by all three
controls (keep it in `hooks/useDragScrubValue.ts` or `lib/timeAxis.ts`).

**Verify:** build; new spec + `studio.spec.js` + `generate/generate.spec.js`
green; perf budget n/a (no new animation); captures compared.

**Commit:** `feat(ui): pointer-safe waveform and numeric grammar`

---

## A-4 — Loop brace + exclusive audition (M1, N6)

**Read:** A §3 "M1", A §8 "N6", A §2 "Phase 4".

**Allowed files:** `components/StitchTimeline.tsx`;
`components/stitch/TimelineRuler.tsx`; `hooks/useStitchTransport.ts`;
optional new `hooks/useArrangementLoop.ts`; new `lib/playbackFocus.ts`;
the five audio owners (`StitchTimeline.tsx`, `VariantCompare.tsx`,
`components/audio/AudioDeck.tsx`, `components/waveform/AlignmentCompare.tsx`);
new `tests/ui/stitch-studio/loop-brace.spec.js` and
`tests/ui/core/exclusive-audition.spec.js`; ledgers.

**Save before:** `transport-playback`.

**RED:**

1. Drag across the ruler creates `data-testid="loop-brace"` with two
   handles; Space plays and the transport time wraps back to the brace start
   (poll `stitch-transport-audio` currentTime).
2. Zooming keeps the brace on the same times.
3. The per-clip range play button still plays only its clip.
4. Exclusive audition: start the Speak deck, then start a second player
   (e.g. a Voice Library row deck) → the first reports paused.

**GREEN:** loop brace per A M1 on top of A-2's coordinate mapping.
`lib/playbackFocus.ts`: `claim(id, pause)` pauses the previous claimant;
`release(id)` on unmount. One claim/release call per owner, no other
behavior change.

**Verify:** build; both new specs + `studio.spec.js` + `voice-edit.spec.js`
green; capture compared.

**Commit:** `feat(ui): arrangement loop brace and exclusive audition`

---

## A-5 — Context menus on clips, seams, and segment rows (M2, N5)

**Read:** A §3 "M2", A §8 "N5", A §2 "Phase 5".

**Allowed files:** new `components/ui/context-menu.tsx` (wraps the

**already installed** unified `radix-ui` package's `ContextMenu`, following
`components/ui/tooltip.tsx:3`); `components/StitchTimeline.tsx`;
`components/stitch/StitchClipCard.tsx`; `components/stitch/GapControl.tsx`;
`components/stitch/SegmentBrowserModal.tsx`; new
`tests/ui/stitch-studio/context-menu.spec.js`; ledgers.

**Save before:** `stitch-assembly`, `segment-library-browse`.

**RED:**

1. Right-click a clip → menu with: play range, edit text, reset trim/fade,
   remove clip, focus numeric editor. Choosing "remove clip" removes it.
2. Right-click a seam → gap actions; choosing one changes the gap.
3. Right-click a segment-browser row → insert / audition / copy id; insert
   adds the clip.
4. Keyboard parity: every menu action is reachable without a pointer
   (Shift+F10 or the context-menu key on the focused item opens the menu).

**GREEN:** thin wrappers over existing `StitchPlanSession` / region-edit /
browser handlers only. No new editor behavior. `package.json` must not change.

**Verify:** build; new spec + `studio.spec.js` green; `git diff --stat
frontend/package.json` empty; captures compared.

**Commit:** `feat(ui): clip, seam, and segment context menus`

---

## A-6 — Stitch editor undo/redo (T2; owner sign-off recorded at CP0a)

**Read:** A §4 "T2" and §6 (the no-undo exception is **approved**).

**Allowed files:** new `hooks/useStitchHistory.ts`;
`hooks/useStitchPlanSession.ts`; `components/StitchTimeline.tsx`;
`hooks/useStitchPreview.ts`; `lib/stitchPlan.ts`; `store.ts` only if the
session state lives there; new `tests/ui/stitch-studio/undo.spec.js`;
ledgers.

**Save before:** `stitch-assembly`.

**RED:**

1. Remove a clip, press Cmd/Ctrl+Z → clip returns; Shift+Cmd/Ctrl+Z → gone
   again.
2. One trim drag = one history entry (one undo restores the pre-drag value).
3. Undo while typing in a text field does **not** undo the plan (focus
   guard).
4. Visible undo/redo buttons (`data-testid="stitch-undo"` /
   `"stitch-redo"`) with disabled state at the ends of history.
5. Quick-insert drafts do not enter history until committed.

**GREEN:** bounded (cap 100) past/future stacks of full `StitchPlanState`
snapshots; drag gestures push once on pointerup; previews stay keyed by plan
hash (no preview cache change).

**Verify:** build; new spec + `studio.spec.js` green; capture compared.

**Commit:** `feat(ui): stitch editor undo/redo`

---

## A-7 — Global command palette (M4)

**Read:** A §3 "M4".

**Allowed files:** `App.tsx`; `components/AppShell.tsx`; new
`hooks/useGlobalShortcuts.ts`; new `components/CommandPalette.tsx`;
`components/StitchTimeline.tsx` (move its keymap into the shared registry,
same keys); `components/audio/AudioDeck.tsx`;
`components/waveform/AlignmentCompare.tsx`; new
`tests/ui/core/command-palette.spec.js`; ledgers.

**RED:**

1. Cmd/Ctrl+K opens `data-testid="command-palette"`; typing "stitch" and
   Enter navigates to Stitch Studio.
2. `?` opens the keymap; it lists the same shortcuts the old Stitch dialog
   listed (`stitch-shortcuts-dialog` content is preserved).
3. Space inside a text input types a space (never toggles playback).

**GREEN:** one shortcut registry; pages register their keys; the palette and
`?` both read it. Built on existing `components/ui/dialog.tsx`.

**Verify:** build; new spec + `studio.spec.js` + `core/basic.spec.js` green.

**Commit:** `feat(ui): global command palette`

---

## A-8 — A/B plan snapshots (M5)

**Read:** A §3 "M5".

**Allowed files:** `pages/StitchStudioPage.tsx`;
`hooks/useStitchPlanSession.ts`; `hooks/useStitchPreview.ts`; new
`components/stitch/StitchABBar.tsx`; `lib/stitchPlan.ts` only for a snapshot
type; new `tests/ui/stitch-studio/ab-snapshots.spec.js`; ledgers.

**RED:** capture A (`data-testid="stitch-ab-capture-a"`), change a gap,
capture B, switch to A → the gap shows A's value; switch to B → B's; the
active slot is labelled; both previews audition. Snapshots are
session-local (a reload clears them) and are not written to the backend.

**GREEN:** per A M5; switching A/B is one undoable history entry (A-6).

**Verify:** build; new spec + `studio.spec.js` + `undo.spec.js` green.

**Commit:** `feat(ui): A/B plan snapshots`

---

## A-9 — Shared audio transport coordinator (T1)

**Read:** A §4 "T1"; the N6 registry you built in A-4.

**Allowed files:** grow `lib/playbackFocus.ts` into the coordinator (or new
`audio/AudioTransportStore.ts` that absorbs it); new
`hooks/useAudioTransport.ts`; `hooks/useStitchTransport.ts`;
`components/audio/AudioDeck.tsx`; `components/waveform/AlignmentCompare.tsx`;
`VariantCompare.tsx`; `App.tsx`/`AppShell.tsx` for the provider; new
`tests/ui/core/transport.spec.js`; ledgers.

**RED:**

1. The coordinator exposes the active source id and position
   (`data-testid="transport-active-source"` in a dev-hidden or sr-only
   element is acceptable for the test).
2. Stitch arrangement, a Speak deck, and a Voice Edit A/B lane all register;
   starting any one pauses the others (A-4 test keeps passing).
3. Starting candidate audition while a generation job runs does not cancel
   or pause the job.

**GREEN:** move ownership, not behavior: each surface keeps its own playback
contract (A §4 T1 "Why non-trivial") and only reports/claims through the
coordinator. No server API change.

**Verify:** build; new spec + **full UI suite** green (compare with the A-0
baseline; no new failures); captures `transport-playback`, `voice-edit`
compared.

**Commit:** `feat(ui): shared audio transport coordinator`

---

## CP1 — Feel review (owner-only; STOP)

**Executor:** build; run the full UI suite; list any failures versus the A-0
baseline; write a 10-line "how to try it" for the owner (drag-scrub, wheel,
double-click reset, zoom, hover guide, loop brace, context menus, undo,
Cmd-K, A/B, one-sound-at-a-time). Fill the R §7 CP1 row as
`awaiting owner`. STOP.

**Owner:** tries the build; replies "proceed", or names an A-card to reopen.

---

## B-P1 — Obsidian material, signal, and motion tokens

**Read:** B "Doctrines", B "P1" (exact values), R §0.

**Allowed files:** `index.css`; new `lib/signal.ts`; new `lib/motion.ts`;
`lib/waveform.ts` (`waveformBarColor`, `WAVEFORM_PLAYHEAD_COLOR` delegate to
`lib/signal.ts`); `docs/dev/DESIGN_SYSTEM.md`; new
`tests/ui/core/tokens.spec.js`; ledgers.

**Save before:** `speak-generate`, `stitch-assembly`, `hero-voice-design`,
`voice-edit`.

**RED:**

1. `getComputedStyle(document.documentElement).getPropertyValue('--background')`
   under `.dark` equals the Obsidian value from
   `tests/ui/capture/lookdev/obsidian.css`.
2. For each theme in `violet, teal, amber, rose` (set `data-theme` on
   `<html>`), `.btn-brand`'s computed `background-image` contains the
   theme's `--primary` color (D3 follow accent).
3. `.panel-1`, `.well`, `.glow-active`, `.readout`, `.micro-label` classes
   exist (an element given each class has a non-default computed style).

**GREEN:** exactly as B P1 lists. Copy Obsidian values verbatim; implement
`lib/signal.ts` with the S-c constants and `heat()` exactly as specified;
`waveformBarColor` delegates to `signalColor`. Do not copy
`tests/ui/capture/lookdev/common.css`'s class-hijacking selectors.
`DESIGN_SYSTEM.md` gets a "Materials, signal, motion" section.

**Verify:** `npm run --prefix frontend check` (includes the oxlint color
guard); new spec + full UI suite (no new failures vs A-0); captures
compared — neutrals match the Obsidian board shots in
`docs/screenshots/artifacts/lookdev/`; waveform colors are the S-c hybrid.

**Commit:** `feat(ui): luminous material, signal, and motion token layer`

---

## B-P2 — True-scale hi-res waveform renderer + RAF playhead

**Read:** B audit A2–A5, B "P2", B "Performance budget" (Non-goals section).

**Allowed files:** `lib/waveform.ts`; new
`components/waveform/WaveformCanvas.tsx`; new `hooks/useMediaClock.ts`;
`components/Waveform.tsx`; `components/waveform/WaveformLane.tsx`; every
consumer listed in B P2 Acceptance; new `tests/ui/fixtures/signalFixtures.mjs`
(WAV generator: `sineWav({ hz, dbfs, seconds })`, `impulseWav({ dbfs })`);
new `tests/ui/fixtures/longtasks.mjs` (`collectLongTasks(page, fn)` using a
`PerformanceObserver` for `longtask`); new
`tests/ui/stitch-studio/waveform-truth.spec.js`; ledgers.

**Save before:** `speak-generate`, `stitch-assembly`, `voice-edit`,
`segment-browser-scale`.

**RED:**

1. Stitch timeline with two injected clips (−6 dBFS and −24 dBFS sines, via
   `page.route` on the segment audio URL): the quieter clip's drawn waveform
   height (read the canvas: tallest non-background pixel column) is < 25% of
   the louder one's.
2. During playback, sample the playhead x twice with `requestAnimationFrame`
   less than 50 ms apart: the values differ (display-rate, not ~4 Hz).
3. `collectLongTasks` during 3 s of Stitch playback returns 0 entries >
   50 ms.
4. No element with `Array(64).fill(0.15)`-style placeholder: while decoding,
   `data-testid="waveform-skeleton"` is shown instead.

**GREEN:** B P2 exactly: min/max/RMS pyramid in absolute units stored

**additively** in the analysis cache (key format unchanged; `peaks` kept);
density from lane width × DPR; two-tone silhouette with
`signalColor(heat(...))` per B P2; shared vertical scale in multi-clip views;
single-clip views auto-fit and show `−x dBFS` peak readout; playhead drawn in
the same canvas from `useMediaClock` (no React state per frame); delete the
per-bar `motion.div` rendering.

**Verify:** build; new spec + full UI suite (no new failures); perf budget
met; captures compared — waveforms match the P0 signal board's S-c row.

**Commit:** `feat(ui): true-scale hi-res waveform renderer with RAF playhead`

---

## B-P3 — Spectrogram view

**Read:** B audit A6, B "P3", B P1 "Signal constants" (`SPECTRO_STOPS`, dB
window).

**Allowed files:** new `lib/stft.worker.ts`; new `lib/spectrogram.ts`; new
`components/waveform/SpectrogramCanvas.tsx`;
`components/audio/AudioDeck.tsx`; `VariantCompare.tsx` / Voice Edit lane
component; delete `components/audio/SpectralAccent.tsx` and its usages;
`tests/ui/fixtures/signalFixtures.mjs`; new
`tests/ui/generate/spectrogram.spec.js`; ledgers.

**Save before:** `speak-generate`, `voice-edit`.

**RED:**

1. Inject a 1 kHz −12 dBFS sine as the Speak result (route `/generate`, or
   the async job result request SpeakPage uses). Toggle
   `data-testid="view-spectrum"`. In `data-testid="spectrogram-canvas"`,
   the brightest row in the middle column maps to 1 kHz ± 1/12 octave using
   f = 50·(12000/50)^(1 − y/(H−1)).
2. The Wave/Spectrum choice survives navigating away and back (session).
3. `collectLongTasks` while the spectrogram computes returns 0 entries > 50 ms
   (STFT is in the worker).
4. `SpectralAccent` no longer exists (`grep` in the spec is not needed; the
   file is deleted and the build passes).

**GREEN:** B P3: Hann 1024 / hop 256 radix-2 FFT in a module worker
(`new Worker(new URL('./stft.worker.ts', import.meta.url), { type: 'module' })`),
log-frequency 50 Hz–12 kHz, `SPECTRO_STOPS` colormap, dB window −72…−12,
additive cache key `spectrogram:<kind>:<id>:<revision>`, hover readout
`time · Hz · dB`, shared media-clock playhead.

**Verify:** build; new spec + full suite (no new failures); perf budget met;
captures compared.

**Commit:** `feat(ui): spectrogram view for decoded clips`

---

## B-P4 — Instrument transport strip + true dBFS metering + LUFS

**Read:** B audit A1–A2, B "P4".

**Allowed files:** `components/audio/AudioDeck.tsx`; `MiniAudioDeck.tsx`;
`LevelMeter.tsx` (rebuild on canvas); `components/AudioPlayer.tsx`;
`components/OmniVoice/ClipPlayer.tsx`; `lib/signal.ts`; the P3 worker (add
loudness); `tests/ui/fixtures/signalFixtures.mjs`; new
`tests/ui/generate/metering.spec.js`; ledgers.

**Save before:** `speak-generate`, `omnivoice-audition`, `voice-edit`.

**RED** (inject fixtures as the Speak result):

1. −6 dBFS peak sine → `data-testid="deck-peak-readout"` reads `-6.0` ± 0.1.
2. Mono 997 Hz sine at −20 dBFS peak → `data-testid="deck-lufs-readout"`
   reads `-23.0` ± 0.1 LUFS (B P4 explains the math).
3. A full-scale sample → `data-testid="deck-clip-led"` has
   `data-state="on"`; clicking it sets `off`.
4. During playback the meter (`role="meter"`) `aria-valuenow` changes
   between two RAF samples.
5. Every deck instance (Speak, Voice Library row via `MiniAudioDeck`,
   OmniVoice candidate, Voice Design result) renders
   `data-testid="transport-strip"` with play/restart/loop buttons ≥ 32 px.

**GREEN:** B P4 exactly (−60…0 dBFS scale, ticks, instant attack, ~20 dB /
1.5 s fall, 1.5 s peak hold, clip latch; BS.1770-4 LUFS offline in the
worker). Reduced motion: no ballistic easing, still true level.

**Verify:** build; new spec + full suite; perf budget; captures compared.

**Commit:** `feat(ui): instrument transport strip with true dBFS metering`

---

## A-10 — Clip analysis inspector (M3)

**Read:** A §3 "M3".

**Allowed files:** new `components/stitch/ClipInspector.tsx`;
`components/stitch/StitchClipCard.tsx`; `components/StitchTimeline.tsx`;
reuse (do not duplicate) `lib/waveform.ts` envelope, `lib/spectrogram.ts`,
`LevelMeter.tsx`; new `tests/ui/stitch-studio/clip-inspector.spec.js`;
ledgers.

**RED:** selecting a clip opens `data-testid="clip-inspector"` with peak and
RMS dBFS matching the injected fixture (± 0.1), a live meter during that
clip's playback, and a mini spectrum; before analysis resolves it shows a
skeleton, never numbers.

**GREEN:** presentation of existing analysis only — no second analysis path.

**Verify:** build; new spec + `studio.spec.js`; perf budget.

**Commit:** `feat(ui): clip analysis inspector`

---

## B-P5 — Knob and fader instrument controls

**Read:** B "P5".

**Allowed files:** new `components/ui/knob.tsx`, `components/ui/fader.tsx`;
`components/StitchTimeline.tsx` (DSP row); `components/audio/AudioDeck.tsx`
(speed); `hooks/useDragScrubValue.ts` (vertical-drag option only); new
`tests/ui/stitch-studio/knob.spec.js`; ledgers.

**Save before:** `stitch-assembly`, `speak-generate`.

**RED:** the A-1 contract, re-run against the knob: vertical drag changes the
value, Shift is finer, double-click resets, wheel nudges, click-to-type
works, arrow keys step, `role="slider"` with `aria-valuenow`; the value
bubble (`data-testid="knob-bubble"`) is visible while dragging.

**GREEN:** SVG arc knob (track, accent value arc, pointer) on
`useDragScrubValue`; fader sibling; replace the DSP sliders and deck speed
in their existing slots — trim/fade/gap stay numeric fields.

**Verify:** build; new spec + `drag-scrub.spec.js` + `studio.spec.js`;
captures show no layout shift around the replaced controls.

**Commit:** `feat(ui): knob and fader instrument controls`

---

## B-P6 — Chrome depth, header grammar, info strip, brand mark

**Read:** B "P6", B audit A10–A11.

**Allowed files:** `components/AppShell.tsx`; `SwapBanner.tsx`,
`HealthStatusBanner.tsx`, `UpdateAvailableBanner.tsx`;
`components/ui/ActivityStatusBar.tsx`; page header markup in `pages/*.tsx`;
components adding `data-help` strings; radius-class migration across
`components/**` (class names only); `frontend/public/favicon.svg`;
`src/persona_forge/static/favicon.svg`;
`assets/brand/exports/persona-forge-mark.svg`; `assets/brand/README.md`; new
`tests/ui/core/chrome.spec.js`; ledgers.

**Save before:** `health`, `home`, `hero-voice-design`, `stitch-assembly`.

**RED:**

1. `frontend/public/favicon.svg` is byte-identical to
   `assets/brand/concepts/persona-forge/mark-final/mark-small.svg` (read both
   files in the spec with `fs`).
2. The sidebar header renders an `<img>` whose src ends in `favicon.svg`
   (no `AudioLines` icon).
3. Hovering a control with `data-help` puts that text into
   `data-testid="info-strip"` in the status bar, announced via
   `role="status"`.
4. The three banners share one component shape (same root test id pattern
   `data-testid="app-banner"` + `data-tone`).

**GREEN:** B P6. Brand wiring is copy-only (B P6 "Brand mark" lists every
file). Move A V2's high-pitch warning into `data-help`.

**Verify:** build; new spec + full suite; `python scripts/validate_repo.py`;
captures at all four themes compared.

**Commit:** `feat(ui): chrome depth, header grammar, info strip, and brand mark`

---

## B-P7 — Motion as feedback

**Read:** B "P7".

**Allowed files:** page shells; `components/StitchTimeline.tsx` (reorder);
dialog/menu primitives in `components/ui/`; transport buttons; `lib/motion.ts`
(consume only); new `tests/ui/core/motion.spec.js`; ledgers.

**RED:**

1. Reorder animates: after a keyboard reorder, the moved clip's
   `getBoundingClientRect().x` sampled one frame later is between its old
   and new positions.
2. With `page.emulateMedia({ reducedMotion: 'reduce' })` the same reorder
   lands in its final position on the first frame.
3. Dialogs/menus mount with an enter transition (`data-state` open plus a
   non-`none` computed `transition` or motion style).
4. `collectLongTasks` during a reorder: 0 entries > 50 ms.

**GREEN:** B P7 using only `lib/motion.ts` tokens; animate
`transform`/`opacity` only.

**Verify:** build; new spec + full suite; perf budget; captures compared.

**Commit:** `feat(ui): motion-as-feedback system`

---

## B-P8 — Readout typography + labeled controls

**Read:** B "P8"; A §8 "V3" (superseded text, still useful context).

**Allowed files:** `pages/SpeakPage.tsx`; Voice Design / Voice Edit select
markup; components rendering time/level readouts (class changes only); new
`tests/ui/core/readouts.spec.js`; ledgers.

**RED:** every `select`/combobox on Speak, Voice Design, and Voice Edit has an
accessible name matching a visible `.micro-label` (VOICE, LANGUAGE, and the
`Off` control's real function — find what it controls in `SpeakPage.tsx`);
gap readouts include a unit (`520 ms`, never bare `520`); time/level
readouts have `font-variant-numeric: tabular-nums`.

**GREEN:** B P8.

**Verify:** build; new spec + full suite; captures compared.

**Commit:** `feat(ui): instrument readout typography`

---

## B-P9 — Crafted async states + startup splash

**Read:** B "P9"; A §8 "N3", "N4".

**Allowed files:** new `components/ui/toast.tsx` (or `announcer.tsx`); new
`components/ui/progress.tsx` (wraps installed `radix-ui` `Progress`);
per-surface empty/working/error markup; startup state component; new
`tests/ui/core/async-states.spec.js`; ledgers.

**RED:**

1. A save/promote/generate success produces text in one
   `role="status"` region.
2. Speak generation shows `role="progressbar"` with changing
   `aria-valuenow` (fake server `slow_async` mode, see the top of
   `tests/ui/fixtures/fake_model_server.py`).
3. Empty Stitch Studio / empty library show a designed empty state with one
   next-action button (`data-testid="empty-state-action"`).
4. The initial-load 503 window shows `data-testid="startup-state"` with the
   ring + spark mark.

**GREEN:** B P9 (splash per B P9 using `mark-final/mark.svg` and the Option E
social JPEG, which must be copied into `frontend/public/` or imported; ask
if unsure where static assets belong — stop condition 1).

**Verify:** build; new spec + full suite; captures compared.

**Commit:** `feat(ui): crafted async states`

---

## B-P10 — Residue sweep + scorecard verdict

**Read:** B "P10"; R §5 scorecard; A §8 "V2".

**Allowed files:** copy strings in components (no behavior); R §5 scorecard
cells; ledgers.

**Steps:** remove engineering-process copy (e.g.
`OmniVoice/AccentChipPanel.tsx` lab notes — their genuine warnings already
moved to `data-help` in B-P6); re-run every capture from the A-0 list plus
`lookdev-board`'s Obsidian shots for comparison; fill every R §5 scorecard
cell PASS / FAIL / N/A-with-reason, each citing a capture file.

**Gate:** no FAIL cells. A FAIL reopens the owning phase (stop condition 5 if
you cannot fix it inside this card's allowed files).

**Commit:** `feat(ui): residue sweep and craft verdict`

---

## CP2 — Craft review (owner-only; STOP)

**Executor:** send the owner the filled scorecard and the captures folder;
fill the R §7 CP2 row as `awaiting owner`. STOP.

**Owner:** approves, or names phases to reopen; approves B-P11 scope.

---

## B-P11 — Reference docs, walkthroughs, published media

**Read:** B "P11"; `docs/README.md` doc map; `tests/ui/README.md`.

**Allowed files:** `README.md`; `docs/architecture/*.md`; `docs/HOW_TO_RUN.md`;
`docs/README.md`; `docs/screenshots/**` (published images only);
`tests/ui/capture/scenarios/**` (dwell/selector fixes and the one new signal
GIF scenario, registered in `tests/ui/capture/index.mjs`); ledgers.

**Steps:**

1. Re-run every published scenario (`--source fake` unless the scenario
   requires otherwise) and copy the regenerated files over the published
   ones in `docs/screenshots/` (same filenames README already embeds).
2. Add the signal GIF scenario (meter + playhead + spectrogram toggle during
   playback) and embed it in README.
3. Add the Option E social JPEG as README's top banner; tell the owner to
   set it as the GitHub social preview (repo settings — not an executor
   action).
4. Add captioned screenshots per flow to the docs B P11 lists; add a
   controls reference (knob/fader gestures, keymap, meter scale) to
   `docs/architecture/FRONTEND_OVERVIEW.md`.
5. Walk every touched doc against the running build and fix drift.

**Verify:** `python scripts/validate_repo.py`; capture self-test (R §0);
every image README embeds exists and was regenerated this phase
(`git log -1 --format=%h -- <file>` equals this phase's commit).

**Commit:** `docs: refresh reference docs, walkthroughs, and published media`

---

## B-P12 — Archive plans and open the PR

**Read:** R §6; AGENTS.md "Commit and PR conventions".

**Allowed files:** `docs/plans/*` (move only); new
`docs/archive/luminous-instrument/`; ledgers.

**Steps:**

1. All ledgers complete (A §7, B "Phase ledger", R §7).
2. `git mv` A, B, R, and this file into `docs/archive/luminous-instrument/`;
   fix any links to them (`grep -rn "20260923-premium_ux\|20260922-premium_audio\|20260923-luminous" docs README.md`).
3. Preflight + `git diff --check`; commit; push.
4. Draft the PR title and body (Conventional Commit title; Release Please
   override block with one line per phase commit; scorecard; before/after
   index from `_gates/A-0` vs published). **Show the draft to the owner and
   STOP** — the owner approves before `gh pr create` is run.

**Commit:** `chore: archive luminous-instrument planning docs`

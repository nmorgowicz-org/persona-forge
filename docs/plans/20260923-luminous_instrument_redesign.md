# Luminous Instrument — Presentation Overhaul

Date: 2026-09-23
Status: **PROPOSED** — planning doc only; no phase starts without owner
acceptance. Approved execution order is §5.
Branch: `feat/premium-audio-plugin-ux-20260923` (same branch as the interaction
plan; this doc is its visual sibling, sequenced **after** Phases 0–5 land).

## Goal statement

The interaction plan (`20260922-premium_audio_plugin_ux.md`) fixes how the app
*behaves*. This plan fixes how it *reads*: Persona Forge should look like a
precision audio instrument — FabFilter-clean, dark, luminous — not a competent
dark-mode web form with audio in it. Same layout and IA everywhere; the change
is the presentation system sitting on top of it.

Owner direction (2026-09-23): **new visual system, same layout** ·
**FabFilter-clean aesthetic** · **confident motion design**.

Surveyed against FabFilter/Valhalla/UAD-class surfaces plus our own README
screenshots. The delta between our UI and theirs is six concrete things:

1. **Light, not paint.** Premium plugin surfaces are dark *so that signal
   glows against them* — playheads, meters, active states emit light.
   Our dark surfaces are matte: waveforms are flat bars, playheads are thin
   yellow lines, active states are fill swaps. Nothing emits.
2. **Meters everywhere signal exists.** Every surface that plays audio in a
   premium plugin shows level. Our Speak deck has one LEVEL readout; Stitch
   clips, audition takes, and library rows play audio with no metering at all.
3. **One elevation language.** Premium surfaces read depth instantly: chrome
   → panel → well → readout. Our cards are all one flat charcoal with the
   same radius and border; hierarchy comes only from color, never depth.
4. **Numeric readouts are instruments.** Tabular figures, unit styling,
   parameter labels above values, exact timecodes. Our readouts mix fonts,
   hide units (`GAP 520`), and label dropdowns with current values.
5. **Motion is feedback.** Premium plugins animate state, not decoration:
   playheads sweep, meters fall ballistically, active controls breathe on
   hover, views transition. Our motion today is hover-lift on one stepper and
   spring taps on chips — the transport itself barely moves.
6. **No prototype residue.** Lab-notebook copy, `v0.0.0-fake` chrome, and
   unlabeled controls in *published screenshots*. Premium means the
   storefront is finished.

## Non-goals / constraints (carry forward)

- Same layout and IA on every page. No page restructuring, no new routes.
- No new frontend dependencies. `motion/react` (^13.1.0, already installed)
  covers the motion system; canvas + WebAudio cover metering/rendering.
- No light theme. Dark-only, all four accent themes (`violet`/`teal`/`amber`/
  `rose`) keep working — the glow system keys off `--primary` and
  `--brand-*`, never hardcoded hues.
- No backend contract changes, no DSP changes, no undo/history.
- Design-system rules in `docs/dev/DESIGN_SYSTEM.md` stay binding: semantic
  status tokens only, `.btn-brand` for CTAs, the oxlint
  `no-raw-status-colors` guard keeps passing.
- Reduced motion: every animation ships with a `prefers-reduced-motion` path
  (static end-state, no sweep). Matches the existing
  `StitchTimeline.tsx:35` pattern.

## Workstreams (each ~one PR, ordered)

### P1 — Glow + elevation token layer (the foundation everything sits on)

New presentation tokens in `frontend/src/index.css`, consumed as utilities:

- `--glow-primary` / `.glow-active`: box-shadow + text-shadow treatment for
  active controls, selected chips, playheads, live meters — keyed off
  `--primary` so all four themes glow in their own accent.
- `.panel-1 / .panel-2 / .well`: three elevation steps (chrome → card →
  inset readout well) via layered shadow + border treatments. Replaces the
  current single-flat-card look without touching layout.
- `.hairline`: 1px dividers with theme-aware alpha for section separation
  inside cards (today: ad-hoc `border-border/80` everywhere).
- `.readout`: tabular-nums + mono + unit styling for every time/level value.

**Acceptance:** tokens render identically under all four accent themes;
`npm --prefix frontend run lint` clean; no component restyle yet — this phase
only adds the tokens plus a `DESIGN_SYSTEM.md` section documenting them.
**Files:** `frontend/src/index.css`, `docs/dev/DESIGN_SYSTEM.md`.
Commit: `feat(ui): luminous elevation and glow token layer`.

### P2 — Waveform render quality (mirrored, hi-res, played-region tint)

Every lane today renders coarse single-sided block bars (visible in all four
README screenshots). The data layer is already good — real decoded peaks
(`lib/waveform.ts:17-40`), persistent per-clip LRU caching (`43-60`,
`<kind>:<persistent-id>:<revision>` keys), existing played/unplayed color
grammar (`waveformBarColor`, `115-124`). Missing: density-scaled bucketing,
mirrored center-line silhouette, played-region tint so the playhead reads as
position-on-sound.

**Acceptance:** at typical lane widths every consumer (Speak deck,
`StitchClipCard`, `WaveformLane.tsx`, A/B lanes) renders mirrored,
density-scaled peaks with a visible played treatment; only the existing
`waveformBarColor` grammar, at higher fidelity; cache keys unchanged
(`<kind>:<persistent-id>:<revision>`).
**Files:** `lib/waveform.ts` + lane renderers. Canvas vs DOM is executor's
call; render cost measured before/after on the segment-browser-scale
scenario — no main-thread regression.
Commit: `feat(ui): hi-res mirrored waveform rendering`.

### P3 — Transport chrome (AudioDeck + MiniAudioDeck + clip audition)

The Speak screenshot shows the problem: LEVEL + speed + download icons tiny,
crowded, low hit-target, while Generate sits small against a large empty
textarea. Elevate the deck into an instrument strip: grouped transport
cluster (play/restart/loop) at proper touch targets, prominent level meter
with peak-hold reusing P1 glow, labeled speed control (feeds S1/V3 grammar),
download + seed actions in a consistent trailing cluster.

**Acceptance:** every deck instance (Speak, library rows via MiniAudioDeck,
clip audition) uses the same strip; hit targets ≥ 32px; meter shows
peak-hold; no layout change to surrounding pages.
**Files:** `components/audio/AudioDeck.tsx`, `MiniAudioDeck.tsx`,
`components/AudioPlayer.tsx`.
Commit: `feat(ui): instrument-grade transport strip`.

### P4 — App chrome depth (sidebar, headers, banners, status)

Same IA, higher craft: sidebar active item gets the P1 glow treatment
instead of a flat fill; section headers across pages converge on one
micro-label style (uppercase, tracked, muted — already half-present);
the banner stack (`SwapBanner`, `HealthStatusBanner`,
`UpdateAvailableBanner`) converges on `.status-badge` tones instead of three
bespoke looks; `ActivityStatusBar` becomes the single ambient-status surface.

**Acceptance:** one header grammar, one banner grammar, one status surface;
screenshots of shell before/after at all four themes.
**Files:** `components/AppShell.tsx`, banner components,
`components/ui/ActivityStatusBar.tsx`.
Commit: `feat(ui): chrome depth and banner convergence`.

### P5 — Motion as feedback (motion/react system)

Confident but functional: view/section enter transitions, `AnimatePresence`
on dialogs/menus/popovers, `layout` animation on clip reorder (today reorder
jumps), spring tap states extended from chips to transport buttons, meter
needles with ballistic fall, playhead sweep already exists — give it glow
(P1) so motion reads as light. Every animation checks
`prefers-reduced-motion` and renders its end-state statically.

**Acceptance:** reorder animates, dialogs/menus transition, meters fall
ballistically, reduced-motion path verified per surface (or forced via
emulation in the spec).
**Files:** page shells, `StitchTimeline.tsx` (reorder), dialog/menu
primitives, deck meters.
Commit: `feat(ui): motion-as-feedback system`.

### P6 — Readout typography + labeled controls (Speak first)

`tabular-nums` + `.readout` on every time/level value; dropdowns get
small-caps parameter labels above the control (VOICE / LANGUAGE / the `Off`
control's actual function) instead of value-as-label; icon buttons reuse the
existing `tooltip=` pattern from `AudioDeck.tsx:255`. Extends the interaction
plan's S4/V3 grammar into the visual layer.

**Acceptance:** no unlabeled select on Speak; every numeric readout tabular;
units always visible (`GAP 520` → `520 ms`).
**Files:** `pages/SpeakPage.tsx`, then Voice Design / Voice Edit selects.
Commit: `feat(ui): instrument readout typography`.

### P7 — Empty / loading / error states with craft

Segment Library `(3)` with no clips, empty script box, `Generating
preview...` with no meter — premium instruments never show a void. Crafted
empty states with a next action, determinate progress where the backend
reports it (Speak already polls `getGenerateJobProgress` with `progress_pct`
- ETA — surface it as a real progress readout, not just a bar width),
`role="status"`/`progressbar` semantics folded in (covers N3/N4 of the
interaction plan — accept those here instead of there).

**Acceptance:** every async surface has designed empty → working →
done/error states; progress determinate wherever the backend measures.
**Files:** per-surface, plus shared `components/ui/` primitives as needed.
Commit: `feat(ui): crafted async states`.

### P8 — Storefront re-shoot + residue sweep

Re-capture all eight README screenshots post-P1–P7; sweep prototype residue
(V2 of the interaction plan: `AccentChipPanel.tsx:104-125` lab copy as
contextual guidance, `v0.0.0-fake` chrome, placeholder voice names) so the
published product reads finished.

**Acceptance:** README screenshots re-shot, residue checklist closed,
receipts green.
Commit: `feat(ui): storefront re-shoot and residue sweep`.

### P9 — Reference docs, walkthroughs, and full media refresh

Docs must describe the product that P1–P8 built, not the one from September.
Concretely:

- **Re-take everything published:** all 8 README PNGs
  (`speak-generate`, `hero-voice-design`, `prosody-adjustment`,
  `stitch-assembly`, `voice-edit` workspace, `readiness-states`,
  `voice-edit` prosody-ab, `omnivoice-audition` candidates) **plus** both
  README GIFs (`omnivoice-audition-gif`, `design-to-stitch-gif`) via the
  existing capture scenarios (`tests/ui/capture/scenarios/`,
  `audition-gif.mjs` + `design-to-stitch-gif.mjs` already script dwell
  times so beats stay readable). P8's re-shoot covers the craft deltas;
  P9 re-verifies every file README.md references and closes any stale
  frame.
- **Illustrate the reference docs:** add screenshots to feature
  documentation where a picture replaces a paragraph —
  `docs/architecture/PERSONA_FORGE_STUDIO.md`,
  `docs/architecture/VOICE_DESIGN.md`,
  `docs/architecture/OMNIVOICE_REFERENCE.md`,
  `docs/architecture/STUDIO_LIBRARIES.md`, and the user-facing walkthrough
  surfaces (`docs/HOW_TO_RUN.md`, `docs/README.md`) get a captioned
  screenshot per major flow (Speak → Voice Design → Audition → Stitch →
  Voice Edit). New images live under `docs/screenshots/` beside the
  existing set; every added image gets a one-line caption tying it to the
  feature text.
- **Capability audit:** walk each reference doc against the shipped UI and
  fix drift — new drag-scrub/zoom/loop/context-menu behavior (interaction
  plan Phases 1–5), new glow/meter/motion/readout behavior (this plan
  P1–P7), current engine/backend names, current routes and nav labels.
  Delete or rewrite anything describing pre-overhaul behavior.
- **Walkthrough check:** the end-to-end user path (clone/design → audition
  → stitch → edit → generate over API) must read start-to-finish across
  the docs without gaps; add a short guided walkthrough section where the
  chain currently jumps between pages unexplained.

**Acceptance:** `python scripts/validate_repo.py` clean; every image
README.md and the touched reference docs embed resolves to a file
regenerated in P8/P9 (no stale frames); a reviewer can follow the
walkthrough cold.
**Files:** `README.md`, `docs/architecture/*.md`, `docs/HOW_TO_RUN.md`,
`docs/README.md`, `docs/screenshots/**`, `tests/ui/capture/scenarios/**`
(only if a scenario needs a dwell/selector fix to re-capture cleanly).
Commit: `docs: refresh reference docs, walkthroughs, and published media`.

### P10 — Archive planning docs and open the PR

The last step before review, not after merge:

1. Confirm both plans' ledgers are complete (interaction plan §7,
   this plan's Phase ledger) — every phase PASS with its commit.
2. Move both planning docs out of the active set following the
   established convention (`docs/archive/<topic>/`, cf.
   `docs/archive/stitch-studio/20260920-stitch_studio_ux_overhaul.md`):
   `docs/plans/20260922-premium_audio_plugin_ux.md` and this file go to
   `docs/archive/luminous-instrument/` (new folder), updated in place
   with final commit hashes. Active `docs/plans/` is left clean.
3. Final preflight (`validate_repo.py`, frontend `check` + `lint`,
   `git diff --check`), then open the PR with the Release Please override
   block per repo PR conventions (AGENTS.md) — one `feat(ui):` entry per
   craft phase so the changelog tells the whole story.

**Acceptance:** `docs/plans/` contains no file for this work; archive
copies are final; PR body carries the override block and the capture
before/after index.
Commit: `chore: archive luminous-instrument planning docs`.

## Execution discipline (§2 of the interaction plan applies verbatim)

One phase at a time, previous gate PASS before next starts. RED-before-GREEN
with focused Playwright specs; preflight identical
(`git branch --show-current && git status --short &&
python scripts/validate_repo.py && npm run --prefix frontend check`).
Each phase names its capture scenario in its gate; before/after pairs
inspected, differences attributable to the hunk, no regressions (no layout
shift, no truncated labels). Per-phase Conventional Commits pre-assigned
above. Sequencing: **after interaction-plan Phases 0–5** (the glow/meter
work lands on top of the drag-scrub/zoom/context-menu behavior, not under
it). P1 must go first within this doc — everything else consumes its tokens.

## Phase ledger

| Phase | Gate result | Commit | Notes |
| --- | --- | --- | --- |
| P1 tokens | | | |
| P2 waveforms | | | |
| P3 transport | | | |
| P4 chrome | | | |
| P5 motion | | | |
| P6 readouts | | | |
| P7 async states | | | |
| P8 storefront | | | |
| P9 docs + media | | | |
| P10 archive + PR | | | |

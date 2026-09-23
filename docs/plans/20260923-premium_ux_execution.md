# Premium UX Execution — Master Runbook

Date: 2026-09-23 (revised same day: CP0a and CP0b closed; executor protocol
and phase cards added)
Status: **READY TO EXECUTE.** Every owner decision is closed (§4, §7). Next
step: phase card **A-0** in `docs/plans/20260923-premium_ux_phase_cards.md`.
This file is process only: order, decisions, gates, scorecard, executor
protocol. Design content lives in the two planning docs; step-by-step
instructions live in the phase cards.

## 0. Executor protocol (binding for every agent that executes a card)

This arc is designed to be executed by a mid-tier model (e.g. Sonnet) one
phase per session, with the owner reviewing at every gate.

**One card per session.** Start a session by reading this §0, the §7 ledger
(to find the first row without a PASS), and that phase's card. Do not start a
second card in the same session.

**STOP at every gate.** After the gate report is written, the ledger row
filled, and the phase commit pushed: stop and hand control back to the owner
with the gate report. Do not begin the next card until the owner replies
"proceed" (or equivalent). Checkpoint cards (CP1, CP2) are owner-only; the
executor prepares the listed materials and stops.

**STOP and ask immediately (do not improvise) if:**
1. A step is ambiguous or the code does not match what the card/plan
   describes (file moved, symbol renamed, line numbers far off).
2. A change would touch a file not in the card's "Allowed files" list.
3. A change would add/upgrade a dependency, touch backend Python, change an
   HTTP payload, or change what the user *hears* (DSP).
4. The RED spec passes against unmodified code (the test is wrong or the
   feature exists), or fails for a reason other than the missing feature.
5. Any gate check still fails after **two** honest fix attempts.
6. The performance budget fails, or a capture shows a regression the card
   did not predict.
7. `git push` is blocked by a guard or protection rule — never bypass.

When stopping early, write the ledger row as `BLOCKED — <reason>` and report.

**Hard rules.** No new frontend dependencies. No unit-test runner (no
Vitest/Jest). No `--no-verify`, no force-push, no history rewrite. Never
delete or weaken an existing test to make a gate pass. Follow
`AGENTS.md` and `docs/dev/DESIGN_SYSTEM.md`. Commit titles are the
pre-assigned ones on the card (≤ 72 characters; the local hook rejects longer).

**Standard commands** (run from the repo root unless noted):

| Purpose | Command |
| --- | --- |
| Preflight | `git branch --show-current && git status --short && python scripts/validate_repo.py && npm run --prefix frontend check` |
| Build (required before any Playwright run; specs run against `frontend/dist`) | `npm run --prefix frontend build` |
| One spec file | `cd tests/ui && npx playwright test <path/to/file.spec.js>` |
| One test by name | `cd tests/ui && npx playwright test <file> -g "<test name>"` |
| Capture scenario | `node tests/ui/capture/index.mjs --scenario <key> --source fake` |
| Save a "before" capture (before editing; gitignored, stays local) | `mkdir -p docs/screenshots/artifacts/_gates/<card> && cp -R docs/screenshots/artifacts/<category> docs/screenshots/artifacts/_gates/<card>/before` |
| Capture harness self-test | `cd tests/ui && node --test capture/*.test.mjs && node capture/cli-manifest.mjs --strict` |
| Final diff hygiene | `git diff --check` |

**Gate report** (paste into the ledger Notes as a one-line summary, and send
in full to the owner):

```text
Phase: <id> — <title>
Commit: <hash>  (pushed: yes/no)
RED: <spec file> — failed before GREEN because: <reason>
GREEN: <spec file> — <n> passed
Neighbour specs: <files> — <n> passed / <n> failed
Capture: <scenario> — before: docs/screenshots/artifacts/_gates/<card>/before, after: docs/screenshots/artifacts/<category>
Visual verdict: <what changed, and confirmation nothing else did>
Perf budget: <n/a | longtasks > 50 ms: <n>>
Deviations from the card: <none | list>
Open questions for the owner: <none | list>
```

**Visual verdict.** Open the before and after PNGs (image viewer / read
tool) and describe what changed. If you cannot attribute a difference to
this phase's hunk, that is stop condition 6.

## 1. The two plans

| # | Doc | Layer | Phases |
| --- | --- | --- | --- |
| A | `docs/plans/20260922-premium_audio_plugin_ux.md` | Interaction — how the app **behaves** | Phases 0–10 (see §2); T3 deferred; V1–V4 superseded by B |
| B | `docs/plans/20260923-luminous_instrument_redesign.md` | Presentation + signal display — how it **reads** and how its **sound is shown** | P0 done; P1–P12 |
| C | `docs/plans/20260923-premium_ux_phase_cards.md` | **Executor instructions** — one card per phase, in run order | Execute cards top to bottom |

An executor reads §0 (above), then the next unfinished card in C. The card
says exactly which sections of A and B to read for that phase.

**The one idea that ties them together:** premium feel comes from *truth first,
then craft*. A makes the controls behave like instruments; B makes the signal
honest (true meters, display-rate playhead, true-scale waveforms, real
spectrogram) and then makes everything emit light. Craft on top of untrue
signal still reads as a toy — which is why B's P2–P4 sit before its polish
phases.

## 2. Run order

Strictly sequential, one branch, one PR at the end. No parallel agents: every
phase touches shared timeline / shell / token / media-clock state.

```text
CP0a decisions (closed) → B-P0 look-dev + brand board → CP0b: D1, D7, D9 picked
  → A-0 baseline (all 8 README scenarios + both GIFs captured as the "before" set)
  → A-1 S1 drag-scrub + N1 double-click reset + N2 wheel adjust
  → A-2 S2 zoom + hover guide
  → A-3 S3+S4 pointer waveform + numeric grammar
  → A-4 M1 loop brace + N6 exclusive audition (playback-focus registry)
  → A-5 M2 context menu + N5 segment-browser menu
  → A-6 T2 undo/redo → A-7 M4 command palette → A-8 M5 A/B plan snapshots
  → A-9 T1 shared transport (grows N6's registry into the coordinator)
  → CP1 feel review
  → B-P1 tokens → B-P2 waveform renderer → B-P3 spectrogram → B-P4 transport + metering + LUFS
  → A-10 M3 clip inspector (consumes P2 envelope, P3 spectrum, P4 meter)
  → B-P5 knob/fader → B-P6 chrome + info strip + brand mark → B-P7 motion → B-P8 readouts → B-P9 async states
  → B-P10 residue sweep + scorecard verdict
  → CP2 craft review
  → B-P11 docs + media → B-P12 archive + PR
```

- **Why T1 lands before B-P2:** B-P2's media clock and B-P4's meters read
  playback position; building them on the final transport owner avoids
  re-plumbing every deck twice.
- **T3 (automation lanes): deferred** at CP0a — not selected; recorded, not
  dropped. Revisit after the PR merges.
- Rejected or deferred items are recorded in §7 as `deferred — <reason>`,
  never silently dropped.

## 3. Per-phase loop (every phase, no exceptions)

1. **Preflight** (all exit 0):
   `git branch --show-current && git status --short && python scripts/validate_repo.py && npm run --prefix frontend check`
2. **RED:** write the focused Playwright spec in `tests/ui/` FIRST; run it
   against unmodified code; confirm it fails for the right reason. (No unit
   runner — do not add Vitest.)
3. **GREEN:** implement per the planning doc's Files/Acceptance lines.
4. **Verify:**
   - RED spec green; neighbouring specs pass (`studio.spec.js`,
     `voice-edit.spec.js`, `voice-design.spec.js` where touched).
   - Capture before/after pair for the phase's named scenario, inspected:
     differences attributable to the hunk, no layout shift, no truncated
     labels, no residue.
   - **Performance budget** (every phase that renders signal or motion — B-P2
     onward and A-3): during playback on `segment-browser-scale` and
     `stitch-assembly`, zero `longtask` entries > 50 ms (PerformanceObserver
     inside the spec) and no React commit per animation frame on deck/lane
     components.
   - Reduced-motion path verified by emulation for any new animation.
5. **Record:** §7 ledger row (gate + commit hash); commit with the
   pre-assigned Conventional Commit title from the planning doc.
6. **Gate rule:** a failed gate reopens its phase. Never compensate later.

## 4. Checkpoints

### CP0 — Decide everything up front (before A-0)

The owner answers the decision register once; execution then runs without
stalls. Owner receives: the B-P0 look-dev board, this register, and the A §8
candidate list.

| ID | Decision | Options | Recommendation | **Owner answer (2026-09-23)** |
| --- | --- | --- | --- | --- |
| D1 | Look | L1 Graphite / L2 Obsidian / L3 Machined / L4 Forge | Pick from the board | **L2 Obsidian** (CP0b) — token values in `tests/ui/capture/lookdev/obsidian.css` |
| D2 | Knob/fader controls in DSP + speed slots (B-P5) | accept / reject | Accept | **Accepted** |
| D3 | CTA color | derive from theme accent / keep signature cyan | Derive from accent | **Follow the accent** |
| D4 | Spectrogram view (B-P3) | accept / reject | Accept | **Accepted** |
| D5 | Integrated loudness (LUFS) in B-P4 | accept / defer | Appetite call | **Accepted** — ships in B-P4 |
| D6 | Info strip in the status bar (B-P6) | accept / reject | Accept | **Accepted** |
| D7 | Brand identity | interim ring + spark / Signal Crucible | Signal Crucible | **Signal Crucible selected** after native Codex hero exploration. Public assets live under `assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/`; legacy concepts stay local and ignored. B-P6 wires the SVG set after its small-size optical gate |
| D8 | Single look vs selectable skins | one look + 4 accents / 3 skins × 4 accents | One look | **One look + 4 accents** |
| D9 | Signal palette | S-a current / S-b brand / S-c hybrid | Hybrid | **S-c hybrid** (CP0b): blue → violet → hot magenta → near-white, amber playhead, color by dBFS; exact values in B P1 "Signal constants" |
| N1–N6 | A §8 interaction candidates | accept / reject each | Accept N1, N2, N6 | **Accepted N1, N2, N5, N6**; N3/N4 absorbed by B-P9 |
| M3–M5, T1–T3 | A §3–§4 structural items | accept / defer each | T2 needs architectural sign-off | **Accepted M3, M4, M5, T1, T2** (T2 selection = recorded architectural sign-off for the no-undo exception); **T3 deferred** |

**CP0 closed 2026-09-23.** Precondition for A-0: working tree clean and the
branch pushed.

### CP1 — Feel review (after A-9)

Owner uses the build: drag-scrub, zoom, loop, menus, exclusive audition.
Behavior issues reopen their A-phase before any B-phase starts (B styles what
A builds).

### CP2 — Craft review (after B-P10)

Owner reviews the §5 scorecard with its captures. Every cell PASS or N/A with
a reason; any FAIL reopens the owning phase. Approves P11's docs/media scope.

## 5. Premium scorecard (the definition of done for "feels like a 2026 plugin")

Scored at CP2 from B-P10 captures and re-checked at P12. Each cell: PASS /
FAIL / N/A-with-reason. Owning phase in brackets.

| Criterion | Speak | Voice Design (Qwen) | Voice Design (OmniVoice) | Voice Library | Stitch Studio | Voice Edit | Shell |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Honest signal** — no fake/placeholder data drawn as audio [B-P2/P3] | | | | | | | N/A |
| **True metering** where audio plays, dBFS, peak-hold [B-P4] | | | | | | | N/A |
| **Display-rate playhead** — no stepping [B-P2] | | | | | | | N/A |
| **True-scale multi-clip waveforms** — loudness differences visible [B-P2] | N/A | N/A | | N/A | | | N/A |
| **Emits light** — active/playing/focused states glow [B-P1/P6/P7] | | | | | | | |
| **Depth** — chrome/panel/well readable at a glance [B-P1/P6] | | | | | | | |
| **Instrument controls** — drag, Shift-fine, wheel, double-click reset, typed entry, value bubble [A-1, B-P5] | | | | | | | N/A |
| **Readouts** — tabular, units always visible [B-P8] | | | | | | | |
| **One audition at a time** [A N6] | | | | | | | N/A |
| **Keyboard parity** for every pointer action [A-5, A M4] | | | | | | | |
| **Designed async states** — empty/working/done/error [B-P9] | | | | | | | |
| **Motion with a reduced-motion path** [B-P7] | | | | | | | |
| **No residue** — no lab copy, no fake versions, labeled controls [B-P8/P10] | | | | | | | |
| **Performance budget met** [§3] | | | | | | | |

## 6. Finish (B-P12, last step before review)

1. All three ledgers complete (A §7, B phase ledger, §7 below); every CP0
   decision recorded.
2. Move A, B, **this runbook**, the phase cards, and
   `20260923-native_codex_hero_generation_handoff.md` to
   `docs/archive/luminous-instrument/` (convention:
   `docs/archive/stitch-studio/`), stamped with final hashes. Active
   `docs/plans/` is left clean.
3. Final preflight + `git diff --check`; open the **one** PR with the
   Release Please override block (AGENTS.md) — one entry per phase commit
   (`feat(ui):` per craft phase, `docs:` for P11, `test(ui):` for P0) — so
   the changelog tells the whole story. PR body carries the scorecard and the
   capture before/after index (A-0 "before" set vs P11 "after" set).
4. **Version bump = MAJOR (owner addendum 2026-09-23).** This arc bundles a
   semi-rebrand (Signal Crucible identity, D7) with a large UI/UX overhaul,
   so the release must land as Y.0.0. Release Please mechanics (AGENTS.md
   "Version bump rules", squash-merge, one PR = one evaluated commit):
   - Because the PR body carries a `BEGIN_COMMIT_OVERRIDE` block, Release
     Please evaluates **the block's entries, not the PR title**, for both
     the changelog and the version bump (the override fully replaces the
     commit history it would otherwise read — including the squash title).
     So the breaking marker must live **inside the block**:
     - First override entry: `feat(ui)!: luminous instrument redesign and
       Signal Crucible rebrand` — the `!` after the scope is the breaking
       marker; the remaining craft phases follow as plain `feat(ui):`
       entries.
     - Belt-and-braces: end the block with a `BREAKING CHANGE: <summary>`
       footer paragraph (blank line before it, as a conventional-commit
       footer). Either signal alone triggers major; both cost nothing.
     - Do NOT put `!` on the other override entries.
   - The PR title itself should still be a valid Conventional Commit
     (`feat(ui): …` or `feat(ui)!: …` — the local hook validates it), but it
     is not what Release Please reads once the override block is present.
   - **Most reliable final check:** when Release Please opens its release
     PR, the executor verifies the proposed version is Y.0.0 before it is
     merged; if it is not, add a `Release-As: Y.0.0` trailer to the release
     PR (or hand to the owner). `Release-As` is checked before any
     breaking/feat heuristic, so it forces the exact version regardless.
   - Executors do not invent Y: it is current major + 1, read from the
     latest release tag/changelog at B-P12 time.

## 7. Ledger (appended during execution)

| Step | Plan | Gate / decision | Commit | Notes |
| --- | --- | --- | --- | --- |
| CP0a D2 knob/fader | B | accepted 2026-09-23 | — | |
| CP0a D3 CTA color | B | follow accent 2026-09-23 | — | |
| CP0a D4 spectrogram | B | accepted 2026-09-23 | — | |
| CP0a D5 LUFS | B | accepted 2026-09-23 | — | ships in B-P4 |
| CP0a D6 info strip | B | accepted 2026-09-23 | — | |
| CP0a D8 skins | B | one look + 4 accents 2026-09-23 | — | |
| CP0a N1–N6 | A | N1, N2, N5, N6 accepted; N3/N4 → B-P9 | — | |
| CP0a M3–M5, T1–T3 | A | M3, M4, M5, T1, T2 accepted; T3 deferred | — | T2 = architectural sign-off |
| CP0b D1 look | B | **Obsidian** 2026-09-23 | — | lookdev-board |
| CP0b D7 brand identity | B | **Signal Crucible**; lightning-centered identity rejected 2026-09-23 | — | selected finalist under `hero-v2/finalists/signal-crucible/` |
| CP0b D9 signal palette | B | **S-c hybrid** 2026-09-23 | — | lookdev-board signal board |
| B-P0 look-dev + brand board | B | PASS 2026-09-23 | abfe76e | + CP0b refinement commit 7fc9f4e (Signal Crucible) |
| Owner addendum: release version | R | **MAJOR (Y.0.0)** decided 2026-09-23 | — | semi-rebrand + UX overhaul; `feat(ui)!:` first override entry + `BREAKING CHANGE:` footer; verify release PR proposes Y.0.0, else `Release-As:` — §6 step 4 |
| A-0 baseline | A | PASS 2026-09-23 | a542cc3 | Suite: 68 passed / 0 failed (2.1m, Chromium+fake model). All 11 scenarios captured on `--source fake` (speak-generate, hero-voice-design, prosody-adjustment, stitch-assembly, voice-edit, readiness-states, omnivoice-audition, omnivoice-audition-gif, design-to-stitch-gif, gap-editing, transport-playback, segment-browser-scale); before set in `docs/screenshots/artifacts/_gates/A-0/` (gitignored, local). Baseline behavior: zoom is button-only (×1.25 steps + Fit) plus existing Ctrl/Cmd-wheel at fixed 1.1× — no cursor anchoring (`StitchTimeline.tsx:230-240`); drag-scrub exists only in GapControl; no context menu anywhere in the frontend |
| A-1 S1 drag-scrub + N1 + N2 | A | PASS 2026-09-23 | 9f6d4cc | `useDragScrubValue.ts` extracted from GapControl (zero-change refactor: studio.spec 42/42 after); MsStepper/SliderField/SpeedStepper migrated with drag-scrub, click-to-type (0.2s→200ms), N1 double-click reset (trim/fade→0, speed→1.0, gap→suggested, DSP→plan-start values), N2 opt-in wheel nudge (never on timeline); `deck-speed` testid added. drag-scrub.spec.js 5/5 (RED confirmed: 5/5 failed on missing feature pre-GREEN). Full suite 73/73. Captures: assembly identical (2px raster noise); gap-editing delta proven to be pre-existing capture raster nondeterminism (37k px between two same-code runs). Stepper scrub uses native capture-phase pointerdown + stopPropagation so it never triggers the Reorder.Item card drag (framer listener is native bubble-phase, React delegation cannot block it) |
| A-2 S2 zoom + hover | A | PASS 2026-09-23 | 783d9d5 | Cursor-anchored Ctrl/Cmd-wheel zoom (anchor + scroll correction in a layout effect, clamped against expected content width since Framer layout anims lag scrollWidth); hover time guide `timeline-hover-guide` written imperatively (never React state, ruler-playhead discipline) so pointer movement cannot re-render the timeline mid-gesture; wheel listener is native non-passive (React onWheel is passive — preventDefault was a silent no-op). zoom-hover.spec.js 3/3 (RED confirmed: anchor drift 21.8px, guide absent). Full suite 76/76. Captures: transport identical (70px noise), assembly 36k-px delta = the same capture raster nondeterminism proven in A-1 (luminance ±3–18, no structure). Two mid-phase regressions found and fixed: (1) hover guide via React state re-rendered the timeline on every pointermove and killed in-flight stepper/trim drags; (2) empty-deps effect bound the wheel listener before the timeline mounted (scroll div only exists once clips are inserted) — both fixed by attaching listeners from the scroll container's ref callback |
| A-3 S3+S4 | A | PASS 2026-09-23 | b427c4d | Waveform drag-selection migrated to Pointer Events + `setPointerCapture` (mouse handlers removed): leaving the control mid-drag no longer ends the gesture, release outside it still commits, `pointercancel` cancels. `onMouseLeave`-ends-the-drag was the RED failure. One ms grammar for trim/fade/gap: `formatMsValue` (lib/timeAxis.ts) shows whole ms below 1s and s at/above it next to the bare number, matching the existing `parseGapText` input grammar (bare, ms, s); each control is one tab stop (focusable root + arrow keys, −/+ out of the tab order) with one shared house focus ring constant. waveform-pointer.spec.js 3/3 (RED: 9/9 failed — no `deck-waveform` surface, no unit elements, no tab stops). Full suite 79/79. Test 1 verified discriminating: with `setPointerCapture` removed the drag test fails. Captures: speak-generate delta = the fake source's per-run random seed (two same-code runs differ by the same 396px in the same bbox as the 312px before/after delta; the seed text itself differs in the shot); gap-editing delta is exactly the added `ms` unit labels |
| A-4 M1 loop brace + N6 | A | | | |
| A-5 M2 context menu + N5 | A | | | |
| A-6 T2 undo/redo | A | | | |
| A-7 M4 command palette | A | | | |
| A-8 M5 A/B plan snapshots | A | | | |
| A-9 T1 shared transport | A | | | |
| CP1 feel review | — | | | |
| B-P1 tokens | B | | | |
| B-P2 waveform renderer | B | | | |
| B-P3 spectrogram | B | | | |
| B-P4 transport + metering + LUFS | B | | | |
| A-10 M3 clip inspector | A | | | |
| B-P5 knob/fader | B | | | |
| B-P6 chrome + info strip + brand mark | B | | | |
| B-P7 motion | B | | | |
| B-P8 readouts | B | | | |
| B-P9 async states | B | | | |
| B-P10 residue + verdict | B | | | |
| CP2 craft review | — | | | |
| B-P11 docs + media | B | | | |
| B-P12 archive + PR | — | | | |

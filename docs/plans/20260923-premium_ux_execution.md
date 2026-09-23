# Premium UX Execution — Master Runbook

Date: 2026-09-23 (revised same day: Checkpoint 0, decision register, premium
scorecard, performance budget, single-PR shape)
Status: **PROPOSED** — no phase starts until the owner closes Checkpoint 0.
This file is process only: order, decisions, gates, scorecard, commands. All
design content lives in the two planning docs.

## 1. The two plans

| # | Doc | Layer | Phases |
| --- | --- | --- | --- |
| A | `docs/plans/20260922-premium_audio_plugin_ux.md` | Interaction — how the app **behaves** | 0–5 approved; M3–M5, T1–T3, N1–N6 owner-gated; V1–V4 superseded by B |
| B | `docs/plans/20260923-luminous_instrument_redesign.md` | Presentation + signal display — how it **reads** and how its **sound is shown** | P0–P12, all PROPOSED |

Read A, then B (including B's "Baseline truth audit" A1–A11 and its
doctrines), before Checkpoint 0.

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
CP0 decisions ─ B-P0 look-dev board ─ D1..D7 recorded
  → A-0 baseline (all 8 README scenarios + both GIFs captured as the "before" set)
  → A-1 S1 drag-scrub (+N1 reset, +N2 wheel if accepted)
  → A-2 S2 zoom + hover guide
  → A-3 S3+S4 pointer waveform + numeric grammar
  → A-4 M1 loop brace (+N6 exclusive audition if accepted)
  → A-5 M2 context menu (+N5 segment-browser menu if accepted)
  → [accepted structural items, in this order: T2 undo → M4 command layer → M5 A/B → T1]
  → CP1 feel review
  → B-P1 tokens → B-P2 waveform renderer → B-P3 spectrogram → B-P4 transport + metering
  → [M3 clip inspector, if accepted — consumes P2 envelope + P4 meter]
  → B-P5 knob/fader → B-P6 chrome → B-P7 motion → B-P8 readouts → B-P9 async states
  → B-P10 residue sweep + scorecard verdict
  → CP2 craft review
  → B-P11 docs + media → B-P12 archive + PR
```

- T3 (automation lanes) is not slotted: if accepted at CP0, its own "is every
  edit representable in the payload" proof runs first and it is placed after
  B-P4 by a CP1 note.
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

| ID | Decision | Options | Recommendation (why) |
| --- | --- | --- | --- |
| D1 | Look | L1 Graphite / L2 Obsidian / L3 Machined / named hybrid (B-P0 board) | Pick from the board, not from prose |
| D2 | Knob/fader controls in DSP + speed slots (B-P5) | accept / reject | **Accept** — the single most "plugin" affordance; built on A's S1 hook, so near-free after A-1 |
| D3 | CTA brand color | derive from theme accent / keep signature cyan | **Derive from accent** — today's fixed cyan clashes with rose/amber themes (B audit A9); signal palette stays fixed either way |
| D4 | Spectrogram view (B-P3) | accept / reject | **Accept** — the hero visualization for a *voice* tool; replaces a fake component |
| D5 | Integrated loudness (LUFS) readout in B-P4 | accept / defer | Accept if API users target loudness specs; else defer (peak + RMS dBFS ship regardless) |
| D6 | Info view in the status bar (B-P6) | accept / reject | **Accept** — also resolves A V2's warnings as design, not paragraphs |
| D7 | Custom brand glyph + wordmark (B-P6) | owner supplies / approve a drafted SVG / keep stock icon | Owner's taste; blocks nothing if deferred |
| N1–N6 | A §8 interaction candidates | accept / reject each | **Accept N1, N2, N6** (fold into A-1/A-4 at near-zero cost); N3/N4 are absorbed by B-P9 automatically; N5 accept if appetite |
| M3–M5, T1–T3 | A §3–§4 structural items | accept / defer each | T2 needs the §6 architectural sign-off; the rest are appetite calls |

**Precondition at CP0:** working tree clean and the branch pushed (a one-off
local guard block on `096d424` cleared on retry at `339e9bf`; if it recurs,
stop and ask rather than bypassing the guard).

### CP1 — Feel review (after A-5 + accepted structural items)

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
2. Move A, B, **and this runbook** to `docs/archive/luminous-instrument/`
   (convention: `docs/archive/stitch-studio/`), stamped with final hashes.
   Active `docs/plans/` left clean.
3. Final preflight + `git diff --check`; open the **one** PR with the
   Release Please override block (AGENTS.md) — one entry per phase commit
   (`feat(ui):` per craft phase, `docs:` for P11, `test(ui):` for P0) — so
   the changelog tells the whole story. PR body carries the scorecard and the
   capture before/after index (A-0 "before" set vs P11 "after" set).

## 7. Ledger (appended during execution)

| Step | Plan | Gate / decision | Commit | Notes |
| --- | --- | --- | --- | --- |
| CP0 D1 look | B | | | |
| CP0 D2 knob/fader | B | | | |
| CP0 D3 CTA color | B | | | |
| CP0 D4 spectrogram | B | | | |
| CP0 D5 LUFS | B | | | |
| CP0 D6 info view | B | | | |
| CP0 D7 brand mark | B | | | |
| CP0 N1–N6 | A | | | |
| CP0 M3–M5, T1–T3 | A | | | |
| B-P0 look-dev | B | | | |
| A-0 baseline | A | | | |
| A-1 S1 drag-scrub | A | | | |
| A-2 S2 zoom + hover | A | | | |
| A-3 S3+S4 | A | | | |
| A-4 M1 loop brace | A | | | |
| A-5 M2 context menu | A | | | |
| Accepted structural items | A | | | |
| CP1 feel review | — | | | |
| B-P1 tokens | B | | | |
| B-P2 waveform renderer | B | | | |
| B-P3 spectrogram | B | | | |
| B-P4 transport + metering | B | | | |
| M3 clip inspector (if accepted) | A | | | |
| B-P5 knob/fader | B | | | |
| B-P6 chrome | B | | | |
| B-P7 motion | B | | | |
| B-P8 readouts | B | | | |
| B-P9 async states | B | | | |
| B-P10 residue + verdict | B | | | |
| CP2 craft review | — | | | |
| B-P11 docs + media | B | | | |
| B-P12 archive + PR | — | | | |

# Premium UX Execution — Master Runbook

Date: 2026-09-23
Status: **PROPOSED** — no phase starts until the owner accepts the two
planning docs this runbook drives. This file is process only: it contains no
design decisions, only order, gates, and commands. All design content lives in
the two planning docs below.

## The two plans

| # | Doc | Layer | Phases |
| --- | --- | --- | --- |
| A | `docs/plans/20260922-premium_audio_plugin_ux.md` | Interaction — how the app **behaves** | 0–5 approved; M3–M5, T1–T3, N-/V-candidates owner-gated (§6–§8) |
| B | `docs/plans/20260923-luminous_instrument_redesign.md` | Presentation — how the app **reads** | P1–P10, all PROPOSED |

Read A fully, then B fully, before starting Phase 0. B's §"Execution
discipline" reuses A's §2 verbatim — one rule set, stated once (here, §3).

## Run order

Strictly sequential. No parallel agents: every phase touches shared timeline /
shell / token state.
```text
A-0 baseline → A-1 S1 drag-scrub → A-2 S2 zoom+hover → A-3 S3+S4 waveform+grammar
  → A-4 M1 loop brace → A-5 M2 context menu
  → [OWNER CHECKPOINT 1: accept/reject each §6–§8 + N/V item, or defer]
  → B-P1 tokens → B-P2 waveforms → B-P3 transport → B-P4 chrome
  → B-P5 motion → B-P6 readouts → B-P7 async states → B-P8 storefront
  → [OWNER CHECKPOINT 2: review craft, approve P9 scope]
  → B-P9 docs + media → B-P10 archive + PR
```

- Fold-ins, if accepted at Checkpoint 1: N1 (+N2) into A-1; N5 into A-5;
  N3/N4 resolve in B-P7 instead of standalone phases.
- Skipped/deferred owner-gated items are recorded in the §6 ledger with
  `deferred — <reason>`, never silently dropped.

## Per-phase loop (every phase, no exceptions)

1. **Preflight** (all exit 0):
   `git branch --show-current && git status --short && python scripts/validate_repo.py && npm run --prefix frontend check`
2. **RED:** write the focused Playwright spec in `tests/ui/` FIRST; run it
   against unmodified code; confirm it fails for the right reason.
3. **GREEN:** implement per the planning doc's Files/Acceptance lines.
4. **Verify:** RED spec green; neighbouring existing specs pass
   (`studio.spec.js`, `voice-edit.spec.js` at minimum where touched);
   capture before/after pair inspected — differences attributable to the
   hunk, no layout shift, no truncated labels, no residue.
5. **Record:** append the §6 ledger row (gate result + commit hash); commit
   with the pre-assigned Conventional Commit title from the planning doc.
6. **Gate rule:** a failed gate reopens its phase. Never compensate in a
   later phase.

## Owner checkpoints

- **Checkpoint 1** (after A-5): owner accepts/rejects each owner-gated item
  (M3–M5, T1–T3, N1–N5, V1–V4). Accepted items get explicit acceptance notes
  appended to Plan A (§7 ledger area) before their phase is cut; T2 needs
  the recorded sign-off its section describes. Then B-P1 starts.
- **Checkpoint 2** (after B-P8): owner reviews craft against screenshots,
  approves P9's doc/media scope. Then B-P9 starts.

## Finish (B-P10, last step before review)

1. Both ledgers complete — every executed phase PASS with its commit hash.
2. Move both planning docs **plus this runbook** to
   `docs/archive/luminous-instrument/` (convention: cf.
   `docs/archive/stitch-studio/`), stamped with final hashes.
   Active `docs/plans/` left clean.
3. Final preflight + `git diff --check`, then open the PR with the Release
   Please override block (AGENTS.md) — one `feat(ui):` entry per craft phase
   plus the `docs:` media entry, so the changelog tells the whole story.
   PR body carries the capture before/after index.

## §6 Ledger (appended during execution)

| Phase | Plan | Gate | Commit | Notes |
| --- | --- | --- | --- | --- |
| A-0 baseline | A | | | |
| A-1 S1 drag-scrub | A | | | |
| A-2 S2 zoom+hover | A | | | |
| A-3 S3+S4 waveform+grammar | A | | | |
| A-4 M1 loop brace | A | | | |
| A-5 M2 context menu | A | | | |
| Checkpoint 1 decisions | — | | | |
| B-P1 tokens | B | | | |
| B-P2 waveforms | B | | | |
| B-P3 transport | B | | | |
| B-P4 chrome | B | | | |
| B-P5 motion | B | | | |
| B-P6 readouts | B | | | |
| B-P7 async states | B | | | |
| B-P8 storefront | B | | | |
| Checkpoint 2 decisions | — | | | |
| B-P9 docs + media | B | | | |
| B-P10 archive + PR | — | | | |

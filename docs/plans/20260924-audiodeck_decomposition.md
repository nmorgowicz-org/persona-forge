# AudioDeck decomposition — planning doc

**Status:** planned, not started. Execute **after** the luminous-instrument PR
merges (see "Sequencing"). Owner-requested follow-up from the B-P10 gate
(2026-09-24): §8 listed "split `AudioDeck.tsx`" as residue, and the owner asked
for it as its own planning doc rather than in-arc work.

**Read first:** `docs/archive/luminous-instrument/20260923-premium_ux_execution.md` §3 (per-phase loop)
and §7 (the B-P4/B-P10 rows), `docs/dev/DESIGN_SYSTEM.md`.

---

## 1. The finding, corrected

The carried item says `AudioDeck.tsx` "is now the largest component in the app
(stats header, two layouts, transport strip, view switch, spectrogram,
decoding) and trips the complexity/fan-out advisories."

Measured on 2026-09-24, that first clause is **stale** — it was written at B-P4
and the later phases grew the pages around it:

| File | Lines |
| --- | --- |
| `components/OmniVoicePanel.tsx` | 2697 |
| `pages/VoiceLibraryPage.tsx` | 2031 |
| `components/StitchTimeline.tsx` | 1105 |
| `components/stitch/StitchClipCard.tsx` | 790 |
| `components/VoiceDesignPanel.tsx` | 758 |
| **`components/audio/AudioDeck.tsx`** | **522** |

So this is not "the app's worst file" — it is a **522-line shared primitive**.
The reason it still earns its own card is different, and worth stating plainly:
it is rendered on **every** audio surface (Speak, Voice Design, OmniVoice, Voice
Library rows, Stitch clip players), so its size and its two layouts are paid for
in every future change to any of them. That is a real cost. It is also a
**maintainability** cost, not a user-visible one.

**If the actual goal is navigability, this is not the biggest lever** — the
OmniVoice panel and the Voice Library page are 4–5× its size and are each their
own (much larger, behaviour-bearing) project. This doc deliberately keeps the
deck bounded and says what it does *not* cover.

## 2. Target shape

Pure JSX extraction: three files, one of which is new.

| New file | Moves out of `AudioDeck.tsx` |
| --- | --- |
| `components/audio/DeckStatsHeader.tsx` | the readout row: `deck-peak-readout`, `deck-lufs-readout`, the clip LED, and the compact/full variants of that row |
| `components/audio/DeckTransportStrip.tsx` | the play/restart/loop cluster, the `view-wave`/`view-spectrum` switch, and the speed knob's placement |
| `components/audio/AudioDeck.tsx` (kept) | composition, the two layout branches, decode, the media clock, and the `LevelMeter` mounts |

## 3. Non-goals (binding)

- **No behaviour change.** No prop renames, no state moved between components,
  no new context, no memoisation added "while we're here".
- **No DOM change.** Testids, element order, classNames, and the compact/full
  branches must render identically. This is what makes the verification cheap.
- **No new dependencies.** No component library, no headless UI, no state
  manager.
- **Do not touch** decode, the media clock, `LevelMeter`, `WaveformCanvas`,
  `SpectrogramCanvas`, or the analysis caches — those are the parts P2–P4 built
  deliberately and they are not the problem.

## 4. Verification (this is the whole gate)

A pure extraction has one honest test: *nothing changed.*

1. `npm run --prefix frontend check` (lint + build) clean.
2. Full UI suite green at `--retries=0` — 163 tests, none of them skipped
   except the two known ones.
3. **Captures pixel-identical.** Re-run the deck-bearing scenarios
   (`speak-generate`, `hero-speak-result`, `hero-speak-filled`, `stitch-assembly`,
   `transport-playback`, `voice-edit`) and diff against the pre-refactor set.
   Expect **0.000%**, the way B-P7's motion work landed. A non-zero diff is a
   failed extraction, not "acceptable churn" — these captures should not move.
4. `git diff --stat` reviewed for anything that is not a move: the diff should
   read as deletions in one file and additions in two.

## 5. Risks, and what makes them small

| Risk | Why it is bounded here |
| --- | --- |
| A subtle DOM change breaks a spec that selects by testid | The suite exercises the deck on five surfaces; extraction keeps every testid and the element order |
| The compact/full branch diverges | Both branches are moved, not rewritten — the branch condition stays in `AudioDeck` |
| Props drift while moving | Move whole subtrees; if a value is needed in a child, pass what the parent already had. Any new prop is a signal the extraction is wrong |
| Review fatigue on a large diff | It is mostly moved lines; ask the reviewer to check *moves*, not content |

**Explicitly not a risk:** render performance. Per-frame work already lives in
canvas and rAF (P2/P4), not in React. This refactor must not add memoisation —
if it needs any, that is a finding for its own card.

## 6. Sequencing

1. **After** the luminous-instrument PR merges. It has zero effect on the CP2
   scorecard, and a large mechanical refactor does not belong in a
   redesign release — that is the whole reason it was deferred.
2. **Before** any further media shoot. If the published set is re-shot again
   later, do this first so the media is taken from the final code (and because
   the captures should come out identical, this is cheap either way).
3. One commit, one gate, same discipline as the arc: RED is not applicable
   (no behaviour), so the gate is §4 in full — build, suite, captures,
   diff review.

Suggested commit title: `refactor(ui): extract the deck's stats header and transport strip`.

## 7. Open questions for the owner

1. Do this at all, given §1's correction (522 lines, and not the app's largest
   file)? **Recommendation: yes, but as a small tidy-up, not as a priority** —
   it is a shared primitive and the extraction is bounded.
2. Should the follow-up then address `OmniVoicePanel.tsx` (2697) and
   `VoiceLibraryPage.tsx` (2031)? **Recommendation: separate docs, separately
   scoped** — both are behaviour-bearing and much larger; folding them in here
   would turn a safe move into a redesign.
3. `AlignmentCompare.tsx` (591) uses its own `<audio>` owner and its own lanes.
   Worth its own look at the same time? **Recommendation: no** — it is not
   shared the way the deck is.

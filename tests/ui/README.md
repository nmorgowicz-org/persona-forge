# UI screenshot/GIF capture harness

`node tests/ui/capture.mjs` drives a real (or fake) instance of the app with Puppeteer and
writes screenshots/GIFs to `docs/screenshots/artifacts/<feature>/`.

## Quick start

```bash
# Fake tier — fast, deterministic, no model inference (CI-safe).
node tests/ui/capture.mjs --scenario scenarioHome

# Real tier — spawns the actual Flask app + real model inference (0.6B by default).
node tests/ui/capture.mjs --real --scenario scenarioHome

# Run everything registered:
node tests/ui/capture.mjs --real

# See every registered scenario name:
node tests/ui/capture.mjs --list-scenarios
```

`--real` accepts `--model-size <0.6B|1.7B>` (default `0.6B`) and `--device <cpu|mps>` (default
`cpu`). `--real` and `--target <url>` (point at an already-running server) are mutually
exclusive. Real-tier fixtures (one base voice + variants, a duplicate, and a handful of
OmniVoice segments) are seeded from `tests/ui/fixtures/capture-data/` into disposable temp dirs
on every run — never your real `data/voices`/`data/segments`.

## Scenario catalog

**Core**
- `scenarioHealth` — `/health` readiness page
- `scenarioHome` — Speak page on first load
- `scenarioGenerate` — before/after a basic TTS generation
- `scenarioVoicesList` — Voice Library after designing + saving one voice

**Voice Design**
- `scenarioVoiceDesignPanel` — empty Voice Design panel
- `scenarioVoiceDesignGenerate` — filled panel + generated result

**Voice Library**
- `scenarioVoiceVariantList` — seeded family/variant/duplicate state, fork badges
- `scenarioVoicePromoteVariant` — before/after promoting a variant to family default
- `scenarioAccentProjectGrouping` — segments grouped by `project_id` vs. ungrouped

**Prosody**
- `scenarioAlignmentCompare` — `AlignmentCompare` waveform/legend/transport controls
  (ORIGINAL lane only — no adjustment is driven yet; see
  `docs/plans/20260709-app_roadmap_backlog.md` §8.4b for the tracked follow-up that would add an
  ADJUSTED-lane scenario and unblock the held GIF variant)

**Stitch Studio**
- `scenarioSegmentLibraryBrowse` — the saved-segments picker panel
- `scenarioStitchAssembly` — two clips inserted into the timeline

**Accent Design / OmniVoice**
- `scenarioOmniVoiceAudition` — live candidate generation + stitched result (requires `--real`)
- `scenarioPersonaForgeCandidates` — multi-candidate grid with 2 candidates/segment
- `scenarioOmniVoiceAuditionGif` — GIF of a live audition, script → generating → stitched result

**Wizard (GIF)**
- `scenarioDesignToStitchWizardGif` — full walkthrough: Voice Design → OmniVoice accent/script →
  live audition → lock segment → Stitch Studio → name + insert clips → save → Voice Library

Deferred (documented, not built): `scenarioVoiceMountedWarning` (needs a `seed.mjs` change, see
`docs/dev/resolved/POST_MERGE_INITIATIVES.md` §Phase B6) and `scenarioAlignmentCompareGif`
(on hold, see §8.4b above).

## Operator loop

1. Make a frontend change.
2. `cd frontend && npm run build` (real/fake servers both serve from `frontend/dist`).
3. `node tests/ui/capture.mjs --real --scenario <name>` — pick the scenario covering what you
   changed.
4. Inspect `docs/screenshots/artifacts/<feature>/` for the new/updated artifact.
5. Iterate — no server to keep running by hand; each invocation spawns, seeds, captures, and
   tears down.

## Adding a scenario

Add `async scenario<Name>({ page, baseURL })` to the `SCENARIOS` object in `capture.mjs`, modeled
on an existing one. Wait on real UI state (`page.waitForSelector`/`waitForFunction`), never a
fixed `sleep` — real-tier waits are generous by design. Add any missing `data-testid` in the same
change and rebuild `frontend/dist`. For a GIF, use `createRecorder`/`snap()` from
`tests/ui/lib/gif.mjs` and call `snap()` synchronously between driving steps — never from a
background loop running concurrently with clicks/typing/navigation, since a real model-inference
wait can starve `page.screenshot()` on the renderer's main thread for the entire scenario if the
capture loop and the driving actions contend for it.

## Troubleshooting

- **Port already in use**: `SCREENSHOT_PORT` (`tests/ui/capture.mjs`) is fixed at `8892`; kill any
  stale `run-real-server`/Flask process holding it before retrying.
- **Real tier hangs on startup**: gated HF downloads or a missing model dependency surface as the
  last `/health` body in `startRealServer`'s timeout error — read it before assuming a harness bug.
- **A GIF scenario produces zero/blank frames**: check whether the scenario has a concurrent
  background screenshot loop rather than sequential `snap()` calls — see "Adding a scenario" above.
- **A scenario races ahead of an animation or async state change**: prefer a `waitForFunction`
  gate on the actual DOM/computed-style condition (opacity, viewport visibility, element count)
  over a fixed delay.

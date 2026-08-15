# UI screenshot/GIF capture harness

`node tests/ui/capture/index.mjs` drives a real (or fake) instance of the app with Puppeteer and
writes screenshots/GIFs to `docs/screenshots/artifacts/<feature>/`.

## Quick start

```bash
# Fake tier — fast, deterministic, no model inference (CI-safe).
node tests/ui/capture/index.mjs --scenario health --source fake

# Real-local tier — spawns the actual Flask app + real model inference.
node tests/ui/capture/index.mjs --scenario health --source real-local

# Remote tier — points at an already-running instance (default source).
node tests/ui/capture/index.mjs --scenario health --source remote

# Run everything registered:
node tests/ui/capture/index.mjs

# See every registered scenario name:
node tests/ui/capture/index.mjs --list-scenarios
```

`--source` accepts `fake`, `real-local`, `remote`, or `auto`; each scenario also declares its own
default source, and `CAPTURE_SOURCE` (env) can override it — `--source` wins over both. Real-tier
fixtures (one base voice + variants, a duplicate, and a handful of OmniVoice segments) are seeded
from `tests/ui/fixtures/capture-data/` into disposable temp dirs on every run — never your real
`data/voices`/`data/segments`.

## Scenario catalog

**Core**
- `health` — `/health` readiness page
- `home` — Speak page on first load
- `speak-generate` — before/after a basic TTS generation
- `voices-list` — Voice Library after designing + saving one voice

**Voice Design**
- `voice-design-panel` — empty Voice Design panel
- `voice-design-generate` — filled panel + generated result

**Voice Library**
- `voice-variant-list` — seeded family/variant/duplicate state, fork badges
- `voice-promote-variant` — before/after promoting a variant to family default
- `accent-project-grouping` — segments grouped by `project_id` vs. ungrouped

**Prosody**
- `alignment-compare` — `AlignmentCompare` waveform/legend/transport controls
  (ORIGINAL lane only — no adjustment is driven yet; see
  `docs/plans/20260709-app_roadmap_backlog.md` §8.4b for the tracked follow-up that would add an
  ADJUSTED-lane scenario and unblock the held GIF variant)

**Stitch Studio**
- `segment-library-browse` — the saved-segments picker panel
- `stitch-assembly` — two clips inserted into the timeline

**Accent Design / OmniVoice**
- `omnivoice-audition` — live candidate generation + stitched result (requires `--source real-local`)
- `omnivoice-candidates` — multi-candidate grid with 2 candidates/segment
- `omnivoice-audition-gif` — GIF of a live audition, script → generating → stitched result

**Wizard (GIF)**
- `design-to-stitch-gif` — full walkthrough: Voice Design → OmniVoice accent/script →
  live audition → lock segment → Stitch Studio → name + insert clips → save → Voice Library

**Hero**
- `hero-speak-filled` — Speak page with text entered, pre-generation
- `hero-speak-result` — Speak page after a real generation completes
- `hero-voice-design` — Voice Design panel mid-flow
- `hero-library` — Voice Library populated view

## Operator loop

1. Make a frontend change.
2. `cd frontend && npm run build` (real/fake servers both serve from `frontend/dist`).
3. `node tests/ui/capture/index.mjs --scenario <name> --source real-local` — pick the scenario
   covering what you changed.
4. Inspect `docs/screenshots/artifacts/<feature>/` for the new/updated artifact.
5. Iterate — no server to keep running by hand; each invocation spawns, seeds, captures, and
   tears down.

## Adding a scenario

Add a new file under `tests/ui/capture/scenarios/<category>/<name>.mjs` exporting a scenario
object (`key`, `source`, `contract` with `intent`/`expectedOutputs`, and a `run({ page, baseURL })`
function), modeled on an existing one, then register it in the `SCENARIOS` map in
`tests/ui/capture/index.mjs`. Wait on real UI state (`page.waitForSelector`/`waitForFunction`),
never a fixed `sleep` — real-tier waits are generous by design. Add any missing `data-testid` in
the same change and rebuild `frontend/dist`. For a GIF, use the recorder helpers in
`tests/ui/capture/harness/shot.mjs` and call the snap function synchronously between driving
steps — never from a background loop running concurrently with clicks/typing/navigation, since a
real model-inference wait can starve `page.screenshot()` on the renderer's main thread for the
entire scenario if the capture loop and the driving actions contend for it.

## Troubleshooting

- **Port already in use**: `DEFAULT_PORT` (`tests/ui/capture/harness/paths.mjs`) is fixed at
  `8892`; kill any stale `run-real-server`/Flask process holding it before retrying.
- **Real tier hangs on startup**: gated HF downloads or a missing model dependency surface as the
  last `/health` body in `startRealServer`'s timeout error — read it before assuming a harness bug.
- **A GIF scenario produces zero/blank frames**: check whether the scenario has a concurrent
  background screenshot loop rather than sequential snap calls — see "Adding a scenario" above.
- **A scenario races ahead of an animation or async state change**: prefer a `waitForFunction`
  gate on the actual DOM/computed-style condition (opacity, viewport visibility, element count)
  over a fixed delay.

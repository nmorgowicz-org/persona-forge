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

# See every registered scenario name:
node tests/ui/capture/index.mjs --list-scenarios
```

`--source` accepts `fake`, `real-local`, or `remote`; each scenario also declares its own
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
- `voice-design-panel` — empty Qwen VoiceDesign panel (selects Qwen explicitly; OmniVoice is
  the default engine, and its default-state panel is covered by `hero-voice-design`)
- `voice-design-generate` — filled Qwen panel + generated result

**Voice Library**
- `voice-variant-list` — seeded family/variant/duplicate state, fork badges
- `voice-promote-variant` — before/after promoting a variant to family default
- `accent-project-grouping` — segments grouped by `project_id` vs. ungrouped

**Prosody**
- `alignment-compare` — `AlignmentCompare` waveform/legend/transport controls (ORIGINAL lane
  only — no adjustment is driven in this scenario; `prosody-adjustment` covers the ADJUSTED
  lane)
- `prosody-adjustment` — Precise-mode Calm-preset adjustment: A/B of original vs. adjusted
  waveform with pause markers, word labels, and the manufactured-pause band. Runs against
  fixture audio; the real-generated-audio cut-quality check is still tracked in
  `docs/plans/20260709-app_roadmap_backlog.md` §8.4b

**Voice Edit**
- `voice-edit` — dedicated saved-voice prosody workspace: the A/B strip on load (ORIGINAL
  lane), then the same strip after a preview (ADJUSTED lane + cut markers)

**Stitch Studio**
- `segment-library-browse` — the saved-segments picker panel
- `segment-browser-scale` — the segment/voice browser scrolled through a 250-row, five-project fixture library
- `stitch-assembly` — two clips inserted into the timeline
- `gap-editing` — always-visible seam controls, including a 0.00s seam next to a typed 250ms seam
- `transport-playback` — one shared transport driving the ruler playhead, arrangement toggle, and a per-clip range play button together
- `readiness-states` — blocked, warning, ideal, and overlong reference-readiness states; source speech remains distinct from spacing

**Accent Design / OmniVoice**
- `omnivoice-audition` — live candidate generation + stitched result
- `omnivoice-candidates` — multi-candidate grid with 2 candidates/segment
- `omnivoice-audition-gif` — GIF of a live audition, script → generating → stitched result

**Wizard (GIF)**
- `design-to-stitch-gif` — full walkthrough: Voice Design → OmniVoice accent/script →
  live audition → lock segment → Stitch Studio → name + insert clips → save → Voice Edit

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

### GIF pacing

`framesToGif(..., GIF_FPS)` encodes at one frame per `GIF_FRAME_MS` (1000 ms at the default
`GIF_FPS = 1`), so **one captured frame is one second of screen time**. State dwell in
milliseconds with `holdFor(recorder, page, ms)`, which repeats the current frame
`ms / GIF_FRAME_MS` times — never hand-count frames, and never leave a beat you want read on a
single un-held frame. Two rules that keep a GIF legible:

- **Snap on change, not on a timer.** A poll loop that screenshots every tick on a slow job
  produces hundreds of identical frames; the GIF then spends its runtime frozen. Snap when the
  thing you are waiting for actually changes.
- **Hold every beat.** Setup, the intermediate action, and the payoff all need an explicit
  `holdFor`; otherwise each is a one-second blur.

`captureShot` and `recorder.snap` both gate on `waitForUiSettled()`, which waits for the sidebar
version to resolve (the label renders a literal `vLoading...` placeholder until `/health`
answers) and for element geometry to hold still across consecutive samples (Framer Motion
springs, e.g. the engine selector's shared-layout highlight, otherwise land mid-flight). It is
bounded and never throws, so a permanently animating page cannot hang a capture.

### Fixture audio

The fake tier fabricates *inference*, not audio. Serve the real fixture clips — reference voices
from `tests/ui/fixtures/capture-data/voices/<id>/original.wav`, segments from
`capture-data/segments/<id>/clip.wav` — and let the real audio paths run against them
(`_fake_voice_dir` materializes a voice's master on disk; `get_prosody_adjusted_wav` and
`stitch_selected` are deliberately unpatched). Fabricated silence is not a neutral stand-in: it
blanks every waveform lane, makes forced alignment return zero-length word boundaries, empties
the prosody pause plan, and leaves the stitched preview flat — so a capture "proving" those
surfaces proves nothing.

## Troubleshooting

- **Port already in use**: the spawned servers pick the first free port starting at `8319`
  (`findAvailablePort` in `tests/ui/capture/harness/server.mjs`), so they won't collide with a
  running e2e fake server or a stale process holding `8319` — nothing to kill by hand.
- **Real tier hangs on startup**: gated HF downloads or a missing model dependency surface as the
  last `/health` body in `startRealServer`'s timeout error — read it before assuming a harness bug.
- **A GIF scenario produces zero/blank frames**: check whether the scenario has a concurrent
  background screenshot loop rather than sequential snap calls — see "Adding a scenario" above.
- **A GIF is mostly one frozen frame**: the scenario is snapping on a poll tick instead of on
  change, or the loop's exit condition never fires (a `$eval` where `$$eval` was meant hands the
  callback a single element, so `.length` is `undefined` and a `count >= n` break never happens).
  Compare unique frames: `ffmpeg -i out.gif -fps_mode passthrough f_%03d.png && md5 f_*.png | awk '{print $NF}' | sort -u | wc -l`.
- **Waveform lanes, word labels, or pause markers are missing from a capture**: the fixture is
  serving silence — see "Fixture audio" above.
- **A scenario races ahead of an animation or async state change**: prefer a `waitForFunction`
  gate on the actual DOM/computed-style condition (opacity, viewport visibility, element count)
  over a fixed delay; `captureShot` already waits for layout to settle and for the sidebar
  version to resolve.

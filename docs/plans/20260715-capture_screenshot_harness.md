# Real-model capture harness: full UI/UX screenshot + GIF coverage

Status: Proposed, not yet implemented

> Audience: a fresh AI agent with zero prior context. Read this whole document before writing
> any code. It extends (does not replace) `docs/dev/resolved/E2E_AND_SCREENSHOTTING.md` — that
> doc's fake-model-server tier stays exactly as-is (CI-safe, Playwright E2E, instant fake
> responses). This plan adds a second, local-only, real-model capture tier so a human or an
> agent can point at any part of the UI and get real screenshots/GIFs, the same way
> `../llama-monitor/tests/ui/capture.mjs` lets you point at a scenario and get real captures
> against a real running instance.

## 0. Why this exists (do not skip)

The existing `tests/ui/capture.mjs` (6 scenarios) only ever runs against
`fixtures/fake_model_server.py` — instant, silent, fake audio, a fake `voice_id`, no real
waveform, no real OmniVoice output. That's correct for CI and for basic layout screenshots, but
it cannot capture:
- Real waveforms (prosody `AlignmentCompare` A/B view, RegionEditor boundary markers).
- Real OmniVoice generation (Persona Forge accent audition, candidate diversity).
- Real Voice Library lifecycle state (a voice that has actually been duplicated, promoted,
  forked — "Forked from ..." badges, variant history).
- Real multi-second async states (swap-in-progress, OmniVoice generation spinner, alignment
  job progress) at their true timing.

Prior investigation (this session, prior to this plan) proved OmniVoice runs natively on this
Mac in ~3s on CPU alone (`OmniVoice.from_pretrained("k2-fsa/OmniVoice", dtype=torch.float32)`,
real `.generate()` call, no MPS needed, no Docker, no OpenVINO). The Base voice-clone model
already defaults to `TTS_BACKEND=pytorch` when unset (`src/qwen3_tts/model.py:47`), and
`MODEL_SIZE=0.6B` (`Qwen/Qwen3-TTS-12Hz-0.6B-Base`, `src/qwen3_tts/model_config.py:11`) is the
smallest/fastest preset. So **the whole app, including OmniVoice, can run for real, locally, on
this Mac** — the `linux/amd64`-only Docker image and dockermisc1 SSH-tunnel procedure in
`E2E_AND_SCREENSHOTTING.md` §7 are not required for this. That doc's §7 remains valid for anyone
who specifically wants to validate the *containerized* image; this plan is the native-Python
alternative, and is the one to use for day-to-day screenshot/GIF work.

The user's explicit requirements for this plan (do not relax any of these):
1. **Everything must be automated** — no "start the app yourself in another terminal first"
   step. `node tests/ui/capture.mjs --real --scenario <name>` (or equivalent) must, by itself,
   spawn a real backend, seed it with safe data, capture, and tear down.
2. **Point at any scenario, get screenshots/GIFs, use them to review UI/UX changes** — the same
   workflow as llama-monitor: change some frontend code, re-run one scenario, look at the new
   images, decide whether to fix something. This means scenario coverage should aim to span
   every significant surface of the app over time (see §6), not just a handful of happy paths.
3. **Privacy/isolation, modeled on llama-monitor's `seedConfig()`**: llama-monitor's capture
   harness runs against a temp `HOME`/`XDG_CONFIG_HOME`, seeding only specific known-safe files
   from the real config directory, specifically to keep real private chat content out of
   screenshots (and to avoid the mess of the capture run creating new real chat tabs). This
   project's analogue is real personal voice/segment library content
   (`VOICE_LIBRARY_DIR`/`SEGMENT_LIBRARY_DIR`, bind-mounted from `./data/voices` /
   `./data/segments` per `compose.yml`). **The capture harness must never point at those real
   host directories.** It must always run against disposable temp directories, seeded only from
   small, checked-in, synthetic fixture voices/segments committed to this repo — never copied
   from real user data at capture-run time.

## 1. Non-goals

- Not a CI change. This tier never runs in CI, same framing as `E2E_AND_SCREENSHOTTING.md` §7 —
  real model load time and real generation time make it unsuitable for CI, and that doc's
  fake-model tier already covers CI's needs. Do not add a workflow file for this.
- Not a replacement for the fake-model Playwright E2E suite. Both tiers coexist:
  fake-model tier = fast, deterministic, CI + routine layout checks; real-model tier (this plan)
  = slower, real, local-only, for genuine visual/UX review and demo assets.
- Not solving the Precise-prosody alignment accuracy issues tracked separately (see
  `docs/dev/voice/` prosody docs / any active plan on alignment quality). The `AlignmentCompare`
  scenario in this plan should capture whatever the UI currently renders, warts and all — it's a
  UI/UX coverage tool, not a correctness fix for the aligner.

## 2. Architecture decisions

### 2.1 Real-server spawn mode

Add a real-backend spawn function alongside the existing fake one. Keep `run-server.mjs`
untouched (it's shared with Playwright's fake-model `webServer` block — do not change its
contract) and add a new module, `tests/ui/run-real-server.mjs`, exporting `startRealServer(opts)`
with the same shape as `startFakeServer` (`{ child, url, port, waitUntilHealthy, stop }`) so
`capture.mjs` can use either interchangeably.

`startRealServer({ port, voiceLibraryDir, segmentLibraryDir, modelSize = '0.6B' })`:
- Resolves the venv Python the same way `run-server.mjs` does (`resolvePython()` — copy or
  factor out this helper into a small shared module, e.g. `tests/ui/lib/python.mjs`, imported by
  both `run-server.mjs` and `run-real-server.mjs`; do not duplicate the lookup logic verbatim).
- Spawns the **real** app entrypoint (`python -m qwen3_tts.app` or direct
  `src/qwen3_tts/app.py` — confirm the correct invocation by checking how the Dockerfile/
  Compose actually starts the process today (`grep -n "CMD\|ENTRYPOINT" Dockerfile`,
  `grep -n "command:" compose.yml`) and mirror it; do not invent a new entrypoint).
- Sets env (only these — do not pass through the caller's full real config beyond what's listed):
  ```
  TTS_BACKEND=pytorch
  DEVICE=cpu                      # cpu by default for determinism/simplicity; see §2.4 for MPS
  MODEL_SIZE=0.6B                 # fast preset; override via opts.modelSize if a scenario needs 1.7B
  VOICE_LIBRARY_DIR=<temp dir>     # never the real ./data/voices
  SEGMENT_LIBRARY_DIR=<temp dir>   # never the real ./data/segments
  FRONTEND_DIST_DIR=<repo>/frontend/dist
  FRONTEND_ENABLED=1
  IDLE_UNLOAD_SECONDS=0            # disable idle-unload; a whole scenario batch may run for
                                   # minutes and must not have the model evicted mid-run
  HF_TOKEN=<passthrough from process.env.HF_TOKEN if set>   # needed once, to download the
                                   # gated Qwen3-TTS / OmniVoice checkpoints on first run; do
                                   # NOT read this from any real app config file, only from the
                                   # operator's own shell env (same trust boundary as any other
                                   # local `pip install`/model download)
  ```
- Does **not** copy any file from a real `VOICE_LIBRARY_DIR`/`SEGMENT_LIBRARY_DIR` at any point,
  automatically or via any default flag. (See §2.3 for the one explicit, opt-in exception.)
- Readiness wait must poll `/health` until **`model_loaded: true`** (not just an HTTP 200) since
  `service_started`/`model_loaded` are exactly the fields `src/qwen3_tts/model.py`'s
  `health_state()` (~line 747) exposes for this. A bare 200 from Flask being up is not enough —
  first load of a real model can take real wall-clock time. Default timeout should be generous
  (e.g. 120s for 0.6B on CPU; make it configurable) and fail loudly with the last `/health` body
  on timeout, not a generic "did not become healthy" message.
- `stop()` must SIGTERM then SIGKILL-after-grace, same pattern as `run-server.mjs`/llama-monitor's
  `cleanupServer`.

### 2.2 Fixture voices/segments (the privacy-safe seed data)

New directory: `tests/ui/fixtures/capture-data/` (committed to the repo, small binaries — these
are synthetic TTS output, not recordings of any real person, so there is no privacy concern in
committing them). Two subtrees mirroring the real on-disk layout:

- `capture-data/voices/<voice_id>/` — one dir per fixture voice, same shape
  `voice_library.py` expects (`clip.wav`/reference audio + `meta.json` + any variant files —
  read `voice_library.py` in full before building this to get the exact expected file names/
  schema; do not guess the schema, derive it from `save_voice`/`create_voice_variant`/
  `list_voices` in that file).
- `capture-data/segments/<segment_id>/` — one dir per fixture segment, matching
  `segment_library.py`'s `clip.wav` + `meta.json` layout (already confirmed above: `save_segment`
  writes exactly `clip.wav` and `meta.json` under `SEGMENT_LIBRARY_DIR/<segment_id>/`).

Minimum fixture set needed to cover the scenarios in §6 (build the smallest set that satisfies
this, do not over-produce):
- One base voice with **two variants**, the second promoted to active (so "primary" badge/state
  is visible) — needed for the variant-lifecycle scenario.
- One voice that is a **duplicate of another**, with `duplicated_from` set — needed for the
  "Forked from ..." badge scenario (`VoiceLibraryPage.tsx`'s `getSourceBadges`).
- 2-3 segments sharing one `project_id`/`project_name` (Accent Design Project grouping) plus 1-2
  segments with no project — needed for the Accent Design Projects scenario.
- 2-3 segments with distinct `feature_tags`/`tags` (from `instruct`) — needed for the segment
  library filter/browse scenario.

Generation: write a one-time generator script, `tests/ui/fixtures/generate-capture-fixtures.mjs`
(or a Python script under the same dir if that's more natural given it needs to call the real
model) that:
1. Spawns the real server (reusing `run-real-server.mjs`) against a throwaway temp dir.
2. Drives the real HTTP API (find the exact routes by reading `src/qwen3_tts/app.py`'s
   `@app.post`/`@app.get` decorators directly — do not hardcode routes from memory; this plan
   deliberately does not enumerate them because they must be re-verified against the current
   source) to create the base voice, generate+lock a couple of OmniVoice segments with distinct
   `instruct` strings, assign `project_id`, duplicate a voice, promote a variant.
3. Copies the resulting `VOICE_LIBRARY_DIR`/`SEGMENT_LIBRARY_DIR` contents into
   `tests/ui/fixtures/capture-data/` and stops the server.
4. Is a **manual, occasional, one-time (or rarely re-run) tool** — not invoked automatically by
   `capture.mjs`. Re-run it only if the on-disk schema changes or more fixture variety is needed.
   Document this clearly at the top of the script.

Text content used for fixture generation must be generic/impersonal (e.g. "This is a sample
sentence for the voice library.", "Grab your bag, we're heading out.") — never anything drawn
from real personal use of the app.

### 2.3 Seeding into the temp dirs at capture time

`run-real-server.mjs`'s `startRealServer()` (or a small helper it calls,
`seedCaptureFixtures(voiceLibraryDir, segmentLibraryDir)`) copies
`tests/ui/fixtures/capture-data/voices/*` → the temp `VOICE_LIBRARY_DIR` and
`capture-data/segments/*` → the temp `SEGMENT_LIBRARY_DIR` before the server process starts (or
immediately after spawn, before the first request — either is fine since nothing reads these
dirs until a request arrives). This is the entire "seeding" step for routine capture runs — it
never touches real data.

One explicit, opt-in exception, mirroring llama-monitor's manual `RUNNING_PORT`/attach-to-remote
pattern: support `--target <url>` on `capture.mjs` (already exists) to point at an
operator-started real instance instead of spawning one — if the operator chooses to point that
at their real dev instance with real `VOICE_LIBRARY_DIR`, that's their explicit choice outside
this tool's control, same trust model as llama-monitor's `RUNNING_PORT`. The harness itself must
never do this automatically or by default.

### 2.4 CPU vs MPS

Default `DEVICE=cpu` for the spawn mode — simpler, no MPS-specific edge cases to debug, and the
~3s OmniVoice generation + Base model's small 0.6B size are already fast enough on CPU alone
(confirmed empirically this session). Leave `DEVICE=mps` as a documented, opt-in override
(`opts.device`) for anyone who wants to benchmark it, but do not make it the default — MPS
introduces its own float32/dtype edge cases that aren't worth routine exposure in a tool whose
job is UI screenshots, not model benchmarking.

### 2.5 One-model-at-a-time swap timing

Base and OmniVoice are never loaded simultaneously (`register_foreign_engine`/
`_ensure_base_loaded()` swap discipline, already confirmed in this session). A scenario batch
that exercises both Base-model scenarios and OmniVoice scenarios in the same run will incur real
swap latency between them — this is expected, not a bug. Scenario wait/timeout values in this
tier must be generous (multi-second, not the fake-tier's near-instant waits) and must wait on
real UI state (`waitForSelector` on a real result element), never a fixed `sleep`.

## 3. GIF capture support (port from llama-monitor)

Port three functions from `../llama-monitor/tests/ui/capture.mjs` (already reviewed this
session) into a new shared module `tests/ui/lib/gif.mjs`:
- `captureFrames(page, selectorOrRegion, { fps, durationMs, outDir })` — screenshots a fixed
  region/selector at a fixed interval into a temp `frames/` dir.
- `framesToGif(framesDir, outPath, { fps })` — shells out to `ffmpeg` with a two-pass
  `palettegen`/`paletteuse` filter chain (confirmed `ffmpeg 8.1.2` already installed at
  `/opt/homebrew/bin/ffmpeg` on this machine — no new dependency to install).
- `cleanupFrames(framesDir)` — removes the temp frame directory afterward.

Read the full implementations in `../llama-monitor/tests/ui/capture.mjs` before porting (this
session only read through line ~1314 of that 3796-line file; the frame-capture/ffmpeg functions
were summarized from that partial read — re-read the actual `captureFrames`/`framesToGif`
function bodies in full before porting, do not reconstruct them from memory/summary).

Adapt path conventions to this repo: reuse `ARTIFACTS_DIR`/`outPath(feature, filename)` already
in `tests/ui/capture.mjs`, writing `.gif` files there the same way `.png` files are written today.

Use `execFileSync`/`spawn` (not `exec`/template-string shell) when invoking `ffmpeg` to avoid
shell-injection risk from any path component.

## 4. `data-testid` additions required

Confirmed this session: `frontend/src/components/waveform/AlignmentCompare.tsx` currently has
**zero** `data-testid` attributes. Add them as each scenario needing them is implemented (§6),
not as a single blanket sweep — add only what a scenario actually needs to find/assert on, e.g.:
- A container id for the whole compare strip (for a full-strip screenshot).
- An id (or stable selector) per lane (original/adjusted) if a scenario needs to screenshot just
  one lane.
- An id on the pause-marker drag handle if a GIF scenario needs to simulate a drag.

Similarly check `VoiceLibraryPage.tsx` for testids needed on: the variant list/promote button,
the "Forked from ..." badge itself (`VoiceSourceBadges`), and the Accent Design Project grouping
UI (confirm current testid coverage by reading the file fresh — it was last edited today for the
fork badge and project-grouping fields; do not assume prior session summaries of its testids are
still accurate).

Every new testid must be added to the actual component file (not just asserted from
`capture.mjs`), and `npm run build` in `frontend/` must pass after each addition (compile gate).

## 5. `capture.mjs` CLI surface changes

Extend `parseArgs`:
- `--real` — use `run-real-server.mjs` instead of the default fake server (mutually exclusive
  with `--target`, same as today's fake/target mutual exclusivity).
- `--model-size <0.6B|1.7B>` — forwarded to `startRealServer`, default `0.6B`.
- `--device <cpu|mps>` — forwarded to `startRealServer`, default `cpu`.
- `--gif` — for scenarios that support both a static screenshot and a GIF capture, request the
  GIF path (or: give GIF-capable scenarios their own distinct names, e.g.
  `scenarioOmniVoiceAuditionGif`, mirroring llama-monitor's `scenarioGifs`/
  `scenarioSpawnWizardGif` naming — prefer this over an overloaded flag, since llama-monitor's
  own comments show flag-based mode-switching inside one scenario got confusing at scale;
  decide during §6 implementation, don't over-design this upfront).

Update `--list-scenarios` output to print categorized sections (Core, Voice Library, Prosody,
Stitch Studio, Accent Design / OmniVoice, GIFs), matching llama-monitor's `printUsage()` style,
so `--list-scenarios` alone tells an operator the current coverage map at a glance.

## 6. Scenario/GIF coverage plan (build incrementally, see Phase 5 gate)

This is the target coverage map — the point of this tool per the user's request is that, over
time, **every significant UI surface has a scenario**, so a UI change can be screenshotted and
reviewed on demand. Build these incrementally; do not attempt all of them in one PR.

**Core** (already exist, fake-tier only today — no real-tier equivalent needed, these are
layout-only):
- `scenarioHealth`, `scenarioHome`, `scenarioGenerate`, `scenarioVoiceDesignPanel`,
  `scenarioVoiceDesignGenerate`, `scenarioVoicesList` — unchanged.

**Voice Library lifecycle** (real-tier, needs seeded fixture voices from §2.2):
- `scenarioVoiceVariantList` — variant history view on the two-variant fixture voice.
- `scenarioVoicePromoteVariant` — before/after screenshots of promoting a variant to primary
  (covers the promotion-refresh bug fixed earlier this session — good regression-visibility
  value, not just a demo asset).
- `scenarioVoiceForkBadge` — the duplicated voice showing "Forked from ..." badge.
- `scenarioVoiceMountedWarning` — mounted-reference warning banner, if a mounted-reference
  fixture is feasible to seed (confirm what "mounted" means precisely by reading
  `isMountedRef`/related code in `VoiceLibraryPage.tsx` before deciding whether this needs a
  fixture or can use a config flag).

**Prosody / AlignmentCompare** (real-tier, needs a real generated reference + real alignment):
- `scenarioAlignmentCompare` — the shared-axis original/adjusted waveform view with word-text
  labels, hover readout.
- `scenarioAlignmentCompareGif` — drag a pause marker, capture the preview waveform updating
  (uses §3's GIF helpers). Sequence per §2.5/§0: hold off on this one until the trough-biased
  safe-cut fix (tracked in the separate active plan for Precise-prosody accuracy, if still open)
  lands, since the current alignment has known rough edges that would make a poor demo GIF; a
  plain static `scenarioAlignmentCompare` screenshot is fine sooner since it's for UI/UX review,
  not a polished demo asset.

**Stitch Studio**:
- `scenarioSegmentLibraryBrowse` — segment list filtered by accent/feature tag.
- `scenarioStitchAssembly` — multi-segment stitch assembly view with feature tags visible.

**Accent Design / OmniVoice** (real-tier, exercises the real OmniVoice model):
- `scenarioOmniVoiceAudition` — instruct string + script filled in, real generation, real
  waveform result (`omnivoice-result` testid already exists).
- `scenarioOmniVoiceAuditionGif` — spinner → waveform pop-in → play, live real generation
  (~3s, confirmed fast enough to capture cleanly).
- `scenarioPersonaForgeCandidates` — diverse-temperature candidate grid, if the current UI
  renders multiple candidates side by side (confirm this exists before scoping the scenario).
- `scenarioAccentProjectGrouping` — Accent Design Project view using the seeded grouped
  segments from §2.2.

**Wizard-style walkthrough GIF** (the highest-value single asset per earlier discussion):
- `scenarioDesignToStitchWizardGif` — pick text → set instruct/accent → generate (OmniVoice) →
  lock in as segment → stitch into a voice. Mirrors llama-monitor's `scenarioSpawnWizardGif`
  pattern (multi-step, single continuous GIF, not a still).

## 7. Phases and gates

Work through phases in order; each gate must pass before starting the next phase. An agent
picking this up mid-way should read this doc fully, then check which gates are already satisfied
(by inspecting the actual repo state, not by trusting a status note) before continuing.

### Phase 1 — Real-server spawn mode
- Implement `tests/ui/run-real-server.mjs` (§2.1), factor shared Python-resolution helper out of
  `run-server.mjs` into `tests/ui/lib/python.mjs`.
- Implement temp-dir isolation + `/health`-based readiness wait (poll `model_loaded: true`).
- **Gate**: `node tests/ui/run-real-server.mjs` (a standalone runnable check, mirroring
  `run-server.mjs`'s own `import.meta.url` direct-run block) starts a real backend from a clean
  checkout, reaches `model_loaded: true`, and prints its URL — with zero manual steps beyond
  having the venv and `HF_TOKEN` (if needed for gated download) set. Confirm via `ps`/env
  inspection that the spawned process's `VOICE_LIBRARY_DIR`/`SEGMENT_LIBRARY_DIR` are temp paths,
  never the real `./data/voices`/`./data/segments`.

### Phase 2 — Fixture generation + seeding
- Write and run `generate-capture-fixtures.mjs` (§2.2) once, producing
  `tests/ui/fixtures/capture-data/{voices,segments}/...`, committed to the repo.
- Implement `seedCaptureFixtures()` (§2.3), wired into `startRealServer()`.
- **Gate**: from a clean checkout, `--real` spawn produces a running instance whose `/voices` and
  segment-listing endpoints return exactly the fixture data (assert counts/ids), with no
  reference anywhere in the process env or filesystem writes to the real data directories.
  Fixture files reviewed for privacy (synthetic text only, no real personal recordings) and kept
  small (target: low hundreds of KB total, not multi-MB).

### Phase 3 — `capture.mjs` wiring + first real scenario
- Add `--real`/`--model-size`/`--device` flags (§5).
- Port one existing scenario (`scenarioHome` is enough) to run successfully in `--real` mode as
  a smoke test before building new scenarios.
- **Gate**: `node tests/ui/capture.mjs --real --scenario scenarioHome` succeeds end-to-end with a
  single command, no manual steps, producing a real screenshot against real seeded data.

### Phase 4 — GIF helper port
- Port `captureFrames`/`framesToGif`/`cleanupFrames` into `tests/ui/lib/gif.mjs` (§3), reading
  the full llama-monitor implementations first (not the partial summary in this doc).
- **Gate**: one trivial GIF scenario (e.g. a short home-page scroll or a button hover loop) runs
  and produces a valid, playable `.gif` in `docs/screenshots/artifacts/`; frame temp dir is
  cleaned up afterward (confirm via `ls` that no `frames/` dir survives the run).

### Phase 5 — `data-testid` additions
- Add testids to `AlignmentCompare.tsx` and any missing ones in `VoiceLibraryPage.tsx` (§4), each
  added alongside the scenario that first needs it (not a separate blanket PR).
- **Gate**: `npm run build` in `frontend/` passes after each addition.

### Phase 6 — Full scenario/GIF build-out
- Implement the remaining scenarios/GIFs from §6, incrementally, each as its own small change.
- **Gate per scenario**: runs standalone via `--scenario <name>`, produces the expected artifact,
  uses real waits (`waitForSelector`) not fixed sleeps, and is added to the categorized
  `--list-scenarios` output.
- **Gate for the phase overall**: `--list-scenarios` output covers Core, Voice Library, Prosody,
  Stitch Studio, Accent Design/OmniVoice, and GIFs, matching §6's map (adjust the map if reality
  diverges — e.g. a feature turns out not to exist as described — but document why in this file
  rather than silently dropping coverage).

### Phase 7 — Coverage checklist doc + operator workflow
- Add a short `tests/ui/README.md` section (or new doc) listing every scenario with a one-line
  description of what it covers, mirroring llama-monitor's `printUsage()` categorization, so an
  operator (or agent) can find "which scenario shows X" quickly.
- Document the point-and-shoot review workflow explicitly: change frontend code → rebuild
  (`npm run build` in `frontend/`) → `node tests/ui/capture.mjs --real --scenario <name>` →
  inspect the new image in `docs/screenshots/artifacts/<feature>/` → fix or promote.
- **Gate**: dry-run this workflow once for real — make a trivial, deliberate visual tweak,
  re-run one scenario, confirm the resulting screenshot reflects the change.

## 8. Explicit risks / things not to silently paper over

- **Gated model downloads**: first run of the real Base/VoiceDesign/OmniVoice checkpoints needs
  either a cached local HF cache or a valid `HF_TOKEN`. Do not swallow this failure quietly —
  `startRealServer`'s readiness-wait timeout error should surface the real `/health` error state
  (`_startup_error`, per `health_state()`) so a failed download is obvious, not a generic timeout.
- **First-run latency**: model download + first load can take minutes on a clean machine even at
  0.6B. Do not set an unrealistically short default timeout; make it configurable and document
  the expected first-run vs warm-cache timing difference.
- **Never weaken `E2E_AND_SCREENSHOTTING.md`'s fake-model tier or its CI usage** while building
  this — this plan is additive. If any shared file (`run-server.mjs`, `capture.mjs`) needs a
  change, verify the fake-model/CI path still passes (`npm run test:ci` in `tests/ui/`) after the
  change.
- **Do not commit real personal voice/segment data** at any point, including accidentally via a
  wrong path in the fixture generator or a debugging session. Before committing
  `capture-data/`, diff its contents against what §2.2 specifies and confirm every clip was
  synthetically generated by the fixture script, not copied from a real directory.

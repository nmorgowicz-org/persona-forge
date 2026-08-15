# Screenshot & Docs Overhaul — 2026-08-15

> **Status:** Ready for execution. Rewritten 2026-08-15 by Opus.
>
> **Revision 3** replaces Phase 1 entirely. Revisions 1–2 treated the capture harness as something to
> *patch*. It is not — persona-forge is running the **pre-split ancestor** of the harness that
> `../llama-monitor/tests/ui/capture/` has since become, and the correct move is to **port the split
> architecture**, then add scenarios in the new shape. See
> [Appendix E](#appendix-e--port-map) for the file-by-file mapping and
> [Appendix D](#appendix-d--corrections-log) for the full corrections log.
>
> **Revision 4** corrects a font finding that revision 3 got wrong (persona-forge *does* bundle a
> webfont), adds [Step 1.5a](#step-15a--frontend-font-determinism-) for the two remaining
> determinism gaps, and renames llama-monitor → **local-llm-foundry** throughout. Source-dir paths
> under `../llama-monitor/` are unchanged.
>
> **Executor:** any Claude model. Every command has been checked against the real repo, the real
> harness, and the real container host. Where a step needs judgment, it says so and stops for a
> human decision rather than guessing.
>
> **Repo root:** `/Users/nick/SCRIPTS/CLAUDE/persona-forge`
> **Reference implementation:** `/Users/nick/SCRIPTS/CLAUDE/llama-monitor/tests/ui/capture/`

---

## Goal

Three deliverables, in dependency order:

1. **A capture harness ported to the local-llm-foundry split architecture** — machine-checked capture
   contracts, one file per scenario, engine-tagged filenames, and a source-resolution model that
   makes real-vs-fake explicit. Then several hero candidates on top of it, so a human picks the
   README hero from real images.
2. **A docs correction pass plus a `docs/README.md` index** — fix stale product names and the
   `dockermisc1 → docker-agent` host migration, and give the docs folder a navigable front door.
   The index pass also *feeds back into* the harness: any doc that would read better with a
   screenshot gets a capture scenario added (see [Phase 4](#phase-4--docs-corrections--index)).
3. **A premium README** that showcases the app with real images and links into the corrected docs.

**Phase order matters.** Docs work (Phase 4) comes *before* the README rewrite (Phase 5), because
the README links into the docs and the index determines what those links should be. The hero-image
decision is a human checkpoint at the end of Phase 3.

---

## Ground truth (verified 2026-08-15)

Everything here was checked, not assumed. Do not re-derive it; do re-verify with
[Phase 0](#phase-0--preflight) before starting, in case the world moved.

### Repo facts

| Fact | Value |
|---|---|
| Capture harness | `tests/ui/capture.mjs` — **monolithic, 503 lines, 16 scenarios** |
| Harness lineage | Pre-split ancestor of local-llm-foundry's `capture/` (both still use `SCREENSHOT_PORT = 8892`) |
| Puppeteer | **`puppeteer` ^25.3.0** (not `puppeteer-core`) |
| Scenario registration | `SCENARIOS` is an **object** of named async methods, `capture.mjs:36` |
| Scenario signature | `async scenarioName({ page, baseURL })` — **`baseURL`**, capital URL (local-llm-foundry uses `baseUrl`) |
| Screenshot call | `await screenshot(page, feature, filename)` helper, `capture.mjs:25` |
| CLI flags | `--scenario <name>`, `--list`, `--target <url>`, `--real`, `--model-size`, `--device` |
| Support modules | `run-server.mjs` (fake), `run-real-server.mjs` (real local), `lib/{gif,seed,python}.mjs` |
| Voice fixtures | `tests/ui/fixtures/capture-data/voices/vd_*/meta.json` (+ `original.wav`) |
| Segment fixtures | `tests/ui/fixtures/capture-data/segments/seg_*/` |
| Existing artifacts | 36 files under `docs/screenshots/artifacts/` |
| `LICENSE`, `SECURITY.md` | **both exist** |
| Current version | **1.0.11** — from `.release-please-manifest.json`, **not** from `git tag` |

> **Version gotcha.** `git tag --sort=-v:refname | head -1` returns `qwen3-tts-openvino-v0.23.0` —
> tags predate the rebrand and are **not** the version authority. Use
> `.release-please-manifest.json` or the `x-release-please-version` line in `pyproject.toml`.

### Font determinism (verified 2026-08-15)

**local-llm-foundry** — the project whose source dir is still `../llama-monitor`, renaming ahead of
its 2.0 launch — hit a real cross-platform rendering bug here and fixed it under
`docs/plans/20260805-text_hierarchy_and_font_consistency.md`, implemented across commits
`849f7f2` (bundle fonts), `f691a2b` (record capture diagnostics), and `46f7c02` (font-scale test).
The finding that motivated it: **the UI rendered noticeably smaller on Windows than on macOS**, and
screenshots' typeface depended on whether Google Fonts was reachable and finished loading before
capture. Its conclusion — *"the release should not accept screenshots whose typeface depends on
whether Google Fonts was reachable"* — applies verbatim to this plan's deliverable.

persona-forge is **partly there already**, and better off than local-llm-foundry's starting point:

| Concern | persona-forge today | Verified at |
|---|---|---|
| Sans face bundled locally | ✅ `@fontsource-variable/geist` (npm → Vite-bundled WOFF2) | `frontend/src/index.css:4` |
| Applied to the document | ✅ `--font-sans: 'Geist Variable'` + `html { @apply font-sans }` | `index.css:100`, `index.css:237` |
| External font requests | ✅ **none** — no Google Fonts link or `@import url(...)` | `frontend/index.html` |
| Explicit root `16px` baseline | ⚠️ **unset but not currently divergent** — `html` sets only `scroll-behavior`; both platforms measured `16px` (Chromium's default). Worth setting as a guard against browser min-font-size/zoom, not an active bug. | `index.css:65`; measured 2026-08-15 |
| **Mono face bundled** | ❌ **missing** — `--font-mono` is unset, so Tailwind v4 falls back to its **system stack** | no `--font-mono` in `@theme` |
| Capture-time font contract | ❌ none | — |

#### Measured on the live container, 2026-08-15

Both platforms ran the same probe against `http://192.168.10.72:8318`, rendering the
string `0123456789 RTF 1.23x` at `font-size: 16px`:

| | macOS (`MacIntel`) | Windows (`Win32`) | Δ |
|---|---|---|---|
| `font-sans` resolved | `"Geist Variable", sans-serif` | `"Geist Variable", sans-serif` | — |
| `font-sans` width | 165.92px | 165.92px | **0** ✅ |
| `font-mono` resolved | `ui-monospace, SFMono-Regular, Menlo, …` → **SF Mono** | same stack → **Consolas** | — |
| `font-mono` width | 192.66px | 175.94px | **16.7px (9.5%)** ❌ |
| Root font size | `16px` | `16px` | 0 |
| Registered faces | `["Geist Variable"]` | `["Geist Variable"]` | — |

The sans path is provably deterministic. The mono path is provably not — same CSS
declaration, two different typefaces, a 9.5% width delta on a 20-character string.

#### Re-measured after Step 1.5a, 2026-08-15

Same probe, same container, after Geist Mono Variable was bundled and `--font-mono` set
(commit `cbad410`):

| | macOS (`MacIntel`) | Windows (`Win32`) | Δ |
|---|---|---|---|
| `font-sans` width | 165.92px | 165.92px | **0** ✅ |
| `font-mono` resolved | `"Geist Mono Variable", ui-monospace, monospace` | *(identical)* | — |
| `font-mono` width | **192.00px** | **192.00px** | **0** ✅ |
| Root font size | `16px` | `16px` | 0 ✅ |
| Loaded faces | `["Geist Mono Variable", "Geist Variable"]` | *(identical)* | — |
| `font-family: monospace` (control) | 192.66px | 175.94px | 16.7px — *still divergent* |

The last row is the control that proves the fix rather than assuming it: the bare
`monospace` keyword still splits exactly as before, so the system stack is unchanged and
the closure of the `font-mono` gap is attributable to the bundled face, not to some
environmental drift between the two runs.

> **The mono gap is the one that bites this plan.** `font-mono` is used in **at least 19 places**
> across `waveform/`, `StitchTimeline.tsx`, `audio/AudioDeck.tsx`, `OmniVoicePanel.tsx` and others —
> many of them paired with `tabular-nums`, where a proportional-metrics fallback defeats the point of
> the class outright. The originally-cited five are only the most obvious:
> and the worst cases are width-sensitive numeric readouts: `TakeDebugButton.tsx:34`
> (`matchScore.toFixed(2)`), `Waveform.tsx:235` (time ruler), `LevelMeter.tsx:29`, and two metric
> readouts in `VoiceDesignPanel.tsx:626,650`. With no bundled mono face, macOS renders SF
> Mono/Menlo and Windows renders Consolas — **different glyph advance widths, therefore different
> wrapping and column alignment** in exactly the prosody-fingerprint screenshots headed for the
> README. [Step 1.5a](#step-15a--frontend-font-determinism-) closes it.

> **Do not port `assertDeterministicFonts()` verbatim.** local-llm-foundry asserts Inter and Fira
> Code; persona-forge's faces are Geist Variable and (after Step 1.5a) Geist Mono Variable, and the
> variable-weight axis (`font-weight: 100 900`) needs a different `document.fonts.check()` probe.
> Port the *contract* — fail closed on missing faces or external requests — with persona-forge's
> face list. See [Step 1.5](#step-15--harnessbrowsermjs).

### ⚠️ The single most important fact

**`docs/screenshots/artifacts/` is gitignored** (`.gitignore:5`).

```
# Auto-captured UI screenshots/GIFs — curated ones get promoted to docs/screenshots/
docs/screenshots/artifacts/
```

A README that references `docs/screenshots/artifacts/...` **renders with broken images on GitHub
for every visitor**, because those files are never committed. `git ls-files docs/screenshots` is
empty.

The gitignore comment states the intended workflow: **capture into `artifacts/`, then promote the
curated keepers up into `docs/screenshots/`**. local-llm-foundry already encodes this by exporting
`SCREENSHOTS_DIR` alongside `ARTIFACTS_DIR` in `harness/paths.mjs`; the port inherits it, and
[Phase 3](#phase-3--curate--promote) uses it. Every README image path must point at
`docs/screenshots/<name>.png`, never at `artifacts/`.

### Live instance facts

| Fact | Value |
|---|---|
| URL | `http://192.168.10.72:8318` |
| SSH | `root@docker-agent` |
| Data root | `/var/data/autopirate/persona-forge/` |
| Compose | `/root/docker/docker-agent/docker-compose.yml` |
| Backend | `pocket_tts`, device `cpu` |
| Idle unload | **1800 s — the model unloads when idle** |
| `model_loaded` at time of writing | **`false`** (idle-unloaded) |

**The live instance is not empty.** `GET /voices` returns **2 voices**:

| Voice ID | Description | Notes |
|---|---|---|
| `vd_32eb29256158` | `Aussie-Female-YoungAdult-High` | OmniVoice engine, has `variants.json`, prosody variants (`Clean_1.0x`, `calm-1-0x`, `energetic-1-0x`), and a `stitch_plan` referencing real segments |
| `vd_000000000001` | `Mounted reference (Default)` | From mounted `reference/voice_A.wav` |

Plus **6 segments** in `/var/data/autopirate/persona-forge/segments/seg_*/` and a
`voices/projects.json` for project grouping.

**Consequence:** voice-library, prosody, project-grouping, and stitch scenarios can run against the
**real** instance. The fake server is a fallback for those, not the primary source.

### ⚠️ Content warning on `vd_000000000001`

Its `sample_text` reads, in part: *"You want me, don't you? I am on the menu too."*

That string is visible in Voice Library and Speak screenshots. **It must not appear in any image
committed to a public README.** [Step 1.13](#step-113--fix-the-live-instances-sample-text-) changes
it on the live host; [Step 3.3](#step-33--content-safety-re-check-) re-checks every promoted image.
Do not skip either.

---

## Phase 0 — Preflight

**Objective:** confirm the world still matches Ground Truth. Every check must pass before Phase 1.

```bash
cd /Users/nick/SCRIPTS/CLAUDE/persona-forge

# 1. Branch + clean tree
git branch --show-current
git status --short

# 2. Harness deps
node --version                                    # >= 18
ls tests/ui/node_modules/puppeteer >/dev/null 2>&1 && echo "puppeteer OK" || \
  { echo "INSTALLING"; (cd tests/ui && npm install); }

# 3. The OLD harness still parses and lists (this is the thing being ported)
node tests/ui/capture.mjs --list

# 4. The REFERENCE implementation is present
ls ../llama-monitor/tests/ui/capture/harness/ \
  || { echo "FATAL: reference implementation missing — cannot port"; exit 1; }

# 5. Live instance reachable + still has data
curl -s --max-time 15 http://192.168.10.72:8318/health \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('backend',d['backend'],'| loaded',d['model_loaded'],'| idle',d['idle_unload_seconds'])"
curl -s --max-time 15 http://192.168.10.72:8318/voices \
  | python3 -c "import sys,json;print(len(json.load(sys.stdin)['voices']),'voices')"
# Expect: backend pocket_tts, 2 voices.

# 6. Confirm the gitignore situation is still as documented
grep -n "docs/screenshots/artifacts" .gitignore
git ls-files docs/screenshots | wc -l    # 0 = nothing promoted yet
```

### Step 0.1 — Warm the model

`model_loaded` is `false` whenever the instance has idled for 30 minutes. A cold first capture will
time out on the generate scenarios. Warm it, and keep captures moving briskly once warm.

```bash
curl -s --max-time 180 http://192.168.10.72:8318/generate \
  -H "Content-Type: application/json" \
  -d '{"text":"Warming the model.","voice_id":"vd_000000000001"}' \
  -o /dev/null -w "warm request: %{http_code} in %{time_total}s\n"

curl -s --max-time 15 http://192.168.10.72:8318/health \
  | python3 -c "import sys,json;print('model_loaded:',json.load(sys.stdin)['model_loaded'])"
```

**Gate:** `model_loaded: True`. If it stays `False` after two attempts, stop — the capture phases
cannot succeed and something is wrong with the backend.

---

## Phase 1 — Port the Capture Architecture

**Objective:** replace the monolithic `tests/ui/capture.mjs` with the split architecture proven in
local-llm-foundry, migrate all 16 existing scenarios into the new shape, and add hero candidates.

**Why this is worth doing rather than patching.** Four things the split gives us that the monolith
structurally cannot:

| Capability | Where | What it buys us here |
|---|---|---|
| **Capture receipts** | `harness/receipt.mjs` | Scenarios declare `intent` + `expectedOutputs`; the harness fails the run if a file is missing, unexpected, or captured at an unrealistic viewport. This *replaces* the "flag anything under 40 KB" heuristic Revision 2 relied on to spot blank captures. |
| **`SCREENSHOTS_DIR`** | `harness/paths.mjs` | The promote-out-of-gitignore workflow becomes a first-class path instead of a bespoke `cp` step. |
| **Source resolution** | `harness/source.mjs` | `force → --source → CAPTURE_SOURCE → scenario default → remote`. Replaces the ad-hoc `--real`/`--target` pair with something a scenario can declare and CI can override. |
| **Runtime tagging** | `harness/paths.mjs` | `tagFilename()` yields `scenario--engine--rest.png`. For persona-forge the tag is the **engine** (`pocket-tts`, `omnivoice`, `qwen-pytorch`, `qwen-openvino`), so a README image self-documents which engine produced it. |

Plus `captureShot`'s three hard-won behaviors, which took real debugging to find and should not be
rediscovered: park the mouse at `(0,0)` before every shot (a prior `click()`/`hover()` leaves
Puppeteer's virtual mouse on an element, and headless Chrome renders that element's native `title`
tooltip *into the screenshot*); refuse non-`fullPage` captures by default; and scroll containers to
top rather than expanding them, to avoid 3000–5000px screenshots nobody's browser actually shows.

**Target layout:**

```
tests/ui/capture/
├── index.mjs                    # registry + parseArgs + runCli + main
├── cli-group.mjs                # run every scenario in a category
├── cli-manifest.mjs             # INTENT annotation auditor (--strict)
├── capture-receipt.test.mjs     # contract test
├── capture-source.test.mjs      # contract test
├── capture-manifest.test.mjs    # contract test
├── harness/
│   ├── paths.mjs      browser.mjs   server.mjs
│   ├── shot.mjs       receipt.mjs   source.mjs    fixtures.mjs
└── scenarios/
    ├── core/  generate/  voice-design/  voice-library/
    ├── prosody/  stitch-studio/  omnivoice/  wizard/  hero/
```

**Gate:** `node tests/ui/capture/index.mjs --list-scenarios` shows **20** scenarios; the three
contract tests pass; and a fake-source run of every migrated scenario writes its receipt without
throwing.

> **Do not delete `tests/ui/capture.mjs` until Step 1.14.** It is the reference for every scenario
> body being migrated, and the fallback if a migration stalls.

### Step 1.1 — Read both sides before writing anything

```bash
cd /Users/nick/SCRIPTS/CLAUDE/persona-forge

# The thing being ported FROM (reference)
ls -la ../llama-monitor/tests/ui/capture/harness/
sed -n '1,60p'   ../llama-monitor/tests/ui/capture/harness/paths.mjs
cat              ../llama-monitor/tests/ui/capture/harness/receipt.mjs
cat              ../llama-monitor/tests/ui/capture/harness/source.mjs
sed -n '195,260p' ../llama-monitor/tests/ui/capture/index.mjs   # SCENARIOS registry shape

# The thing being ported TO
sed -n '1,60p'    tests/ui/capture.mjs        # helpers, ARTIFACTS_DIR, SCENARIOS opening
sed -n '400,503p' tests/ui/capture.mjs        # parseArgs, main
```

Three naming decisions, settled here so they are not relitigated per-file:

- **`baseURL`, not `baseUrl`.** persona-forge uses `baseURL` in all 16 scenarios. local-llm-foundry uses
  `baseUrl`. Keep persona-forge's spelling — it is 16 call sites versus one, and the ported harness
  is the newcomer.
- **Scenario keys are kebab-case** (`hero-speak-filled`), matching local-llm-foundry. The old
  `scenarioCamelCase` names are retired; Phase 2's commands use the new keys.
- **Runtime tag means *engine*.** Values: `pocket-tts`, `omnivoice`, `qwen-pytorch`,
  `qwen-openvino`, `neutral`.

### Step 1.2 — Scaffold

```bash
cd /Users/nick/SCRIPTS/CLAUDE/persona-forge/tests/ui
mkdir -p capture/harness
mkdir -p capture/scenarios/{core,generate,voice-design,voice-library,prosody,stitch-studio,omnivoice,wizard,hero}
```

### Step 1.3 — `harness/paths.mjs`

Port from `../llama-monitor/tests/ui/capture/harness/paths.mjs`. **Keep verbatim:**
`setArtifactCategory` / `currentArtifactsDir`, `setArtifactRuntime` / `tagFilename`, `sleep`,
`DEFAULT_VIEWPORT`, `DEFAULT_PORT`.

**Adapt:**

- `ROOT_DIR` — resolve up **three** levels from `capture/harness/` (`../../../..` from the module),
  not two. Verify with `node -e` before moving on.
- Export **both** `ARTIFACTS_DIR` (`docs/screenshots/artifacts`) and `SCREENSHOTS_DIR`
  (`docs/screenshots`). The second is what makes Phase 3 clean.
- `DEFAULT_PORT` stays **8892** (`SCREENSHOT_PORT`), matching both projects today.
- **Drop** `TEMP_HOME` / `TEMP_CONFIG_HOME` / `TEMP_APP_CONFIG_DIR` / `TEMP_WINDOWS_*`,
  `REAL_APP_CONFIG_DIR`, `BINARY_PATH`, `CAPTURE_FORM_AUTH`, `SCREENSHOT_TAB_PREFIX`. These exist
  because local-llm-foundry spawns a Go binary that reads a user config dir. persona-forge spawns Python
  with env vars and `mkdtempSync` dirs — that isolation already lives in `run-real-server.mjs`.
- **Add** `REMOTE_SERVER = process.env.CAPTURE_REMOTE_SERVER || 'http://192.168.10.72:8318'`.

```bash
node -e "import('./capture/harness/paths.mjs').then(m => {
  console.log('ARTIFACTS_DIR ', m.ARTIFACTS_DIR);
  console.log('SCREENSHOTS_DIR', m.SCREENSHOTS_DIR);
  console.log('tagFilename    ', (m.setArtifactRuntime('demo','pocket-tts'), m.tagFilename('demo-speak.png')));
})"
# Expect absolute paths ending docs/screenshots/artifacts and docs/screenshots,
# and: demo--pocket-tts--speak.png
```

### Step 1.4 — `harness/receipt.mjs`

**Port verbatim.** No persona-forge-specific changes. It depends only on `currentArtifactsDir` from
`paths.mjs`.

One judgment call: the **viewport allowlist** in `finishCaptureReceipt()` is local-llm-foundry's
(`1440×900`, `1280×900`, `1280×1400`, `430×900`). persona-forge's existing captures are `1440×900`.
Keep the allowlist as-is — the extra entries cost nothing and the mobile `430×900` slot is useful if
a docs page ever wants a mobile shot.

### Step 1.5 — `harness/browser.mjs`

Port `launchBrowser` and `gotoApp` from local-llm-foundry. persona-forge currently launches Puppeteer
inline inside `capture.mjs:main()`; extracting it is the point.

**Adapt, do not copy:**

- **`assertDeterministicFonts` must be re-targeted, not weakened.** local-llm-foundry asserts Inter
  and Fira Code. persona-forge's faces are **Geist Variable** (already bundled) and **Geist Mono
  Variable** (added in [Step 1.5a](#step-15a--frontend-font-determinism-)), so the family list
  changes but the fail-closed contract stays.

  > ⚠️ **Do not use `document.fonts.check()` for this.** Measured on the live container
  > 2026-08-15 from both macOS and Windows: `document.fonts.check('400 1rem "Geist Mono
  > Variable"')` returned **`true` on both platforms while Geist Mono was not loaded at all**
  > (`[...document.fonts]` contained only `Geist Variable`). `check()` reports whether the
  > text *can be rendered* — a fallback satisfies it. An assertion built on `check()` passes
  > green in exactly the broken state it exists to catch. Enumerate the `FontFaceSet` and
  > compare family names instead.
  >
  > ⚠️ **And enumeration alone is not enough either.** Two further traps, both hit while
  > measuring on 2026-08-15:
  > 1. `[...document.fonts]` lists every face **declared** by an `@font-face` rule, whatever
  >    its load state. Fontsource ships one face per unicode subset, so Geist Mono appears as
  >    six entries — all `status: 'unloaded'` until a glyph is needed. Filter on
  >    `face.status === 'loaded'`, or the assertion is satisfied by a face that never
  >    downloaded. Note a family legitimately appears in *both* the loaded and unloaded
  >    buckets, since only the subsets actually used get fetched.
  > 2. Font loading is **lazy**, and `await document.fonts.ready` resolves against whatever
  >    was pending *at that moment*. Measuring a probe element right after appending it
  >    returns fallback metrics, because the face request has not finished. Call
  >    `document.fonts.load(font, text)` for each required family and await that **first**.

  Run this **after** Step 1.5a lands, or the mono assertion fails legitimately.

  ```js
  const REQUIRED_FACES = ['Geist Variable', 'Geist Mono Variable'];

  export async function assertDeterministicFonts(page) {
      const diagnostics = await page.evaluate(async (families) => {
          // Force the required faces to download first. They are lazy: until a glyph is
          // needed they sit at status 'unloaded', and both the measurement and the
          // enumeration below would then describe the fallback rather than the real face.
          await Promise.all(families.map((family) =>
              document.fonts.load(`400 16px "${family}"`, '0123456789 RTF 1.23x')));
          await document.fonts.ready;

          // Enumerate faces that actually loaded. Two things are deliberately avoided here:
          // document.fonts.check(), which returns true whenever a fallback can render the
          // string; and unfiltered enumeration, which includes merely-declared faces.
          const loadedFaces = [...new Set([...document.fonts]
              .filter((face) => face.status === 'loaded')
              .map((face) => face.family))];
          return {
              status: document.fonts.status,
              loadedFaces: loadedFaces.sort(),
              missingFaces: families.filter((family) => !loadedFaces.includes(family)),
              // Every face is bundled and Vite-served same-origin. Any request to a font CDN
              // means a regression that makes captures depend on network reachability.
              externalFontRequests: performance.getEntriesByType('resource')
                  .map((entry) => entry.name)
                  .filter((url) => /fonts\.(googleapis|gstatic)\.com|use\.typekit|fonts\.bunny/i.test(url)),
              rootFontSize: getComputedStyle(document.documentElement).fontSize,
              bodyFontFamily: getComputedStyle(document.body).fontFamily,
          };
      }, REQUIRED_FACES);

      if (diagnostics.status !== 'loaded' || diagnostics.missingFaces.length) {
          throw new Error(`Fonts not deterministically loaded: ${JSON.stringify(diagnostics)}`);
      }
      if (diagnostics.externalFontRequests.length) {
          throw new Error(`External font requests break capture determinism: ${JSON.stringify(diagnostics)}`);
      }
      if (diagnostics.rootFontSize !== '16px') {
          throw new Error(`Root font size is ${diagnostics.rootFontSize}, expected the explicit 16px baseline`);
      }
      return diagnostics;
  }
  ```

  Wire the return value into `setCaptureDiagnostics()` so `rootFontSize` and `bodyFontFamily` land in
  every receipt — this is what local-llm-foundry's `f691a2b` did, and it is what makes a stale or
  wrong-platform screenshot detectable from its receipt alone rather than by eye.

- **Drop** `waitForMonitor`, `switchTab`, `loadAppDocument`, `openAppearancePaneForCapture`. All four
  target local-llm-foundry's `#view-setup` / `#page-*` / `#settings-modal` DOM. persona-forge is a React
  SPA navigated by `[data-testid="nav-*"]`.

- **Add** a persona-forge navigation helper, since 8 of the 16 scenarios begin by navigating:

  ```js
  export async function gotoPage(page, baseURL, navTestId, readySelector) {
      await gotoApp(page, baseURL);
      await page.click(`[data-testid="${navTestId}"]`);
      await page.waitForSelector(readySelector, { timeout: 15000 });
  }
  ```

  The nav test-ids are already in use and verified: `nav-voice-design`, `nav-voice-library`,
  `nav-stitch-studio`.

### Step 1.5a — Frontend font determinism ⚠️

**This is a frontend source change, not a harness change**, and it is a prerequisite for Step 1.5's
assertions. It exists because the deliverable of this plan is *images*, and two of persona-forge's
font settings currently make those images machine-dependent. See
[Font determinism](#font-determinism-verified-2026-08-15) for the evidence.

**1.5a.1 — Bundle a mono face.**

```bash
cd frontend && npm install @fontsource-variable/geist-mono
```

**1.5a.2 — Wire it up** in `frontend/src/index.css`:

```diff
  @import "@fontsource-variable/geist";
+ @import "@fontsource-variable/geist-mono";
```

```diff
  @theme inline {
    --font-heading: var(--font-sans);
    --font-sans: 'Geist Variable', sans-serif;
+   --font-mono: 'Geist Mono Variable', ui-monospace, monospace;
```

Without `--font-mono`, Tailwind v4 resolves `font-mono` to its default system stack. The five
consumers — `TakeDebugButton.tsx:34`, `Waveform.tsx:235`, `LevelMeter.tsx:29`,
`VoiceDesignPanel.tsx:626` and `:650` — are all numeric readouts where glyph advance width drives
column alignment.

**1.5a.3 — Set the explicit root baseline.** `frontend/src/index.css:65` currently reads
`html { scroll-behavior: smooth; }`:

```diff
- html { scroll-behavior: smooth; }
+ html {
+   font-size: 16px;
+   scroll-behavior: smooth;
+ }
```

This is local-llm-foundry's **B2a** gate. It removes any dependence on the browser's or platform's
default root size, which is what made its UI render smaller on Windows than on macOS.

**1.5a.4 — Verify, don't assume.** Both faces come from npm and are bundled by Vite from
`node_modules`, so **no font binaries are vendored into this repo** and no `LICENSE-*.txt` /
`fonts/README.md` provenance file is needed — that part of local-llm-foundry's `849f7f2` does not
apply. Confirm the SIL OFL licences ship inside the packages, and record the versions:

```bash
cd frontend
ls node_modules/@fontsource-variable/geist-mono/
cat node_modules/@fontsource-variable/geist-mono/package.json | grep -E '"(name|version|license)"'
rtk proxy grep -rn "fonts.googleapis\|fonts.gstatic" dist/ || echo "OK: no external font requests in build"
```

**1.5a.5 — Guard the baseline with a test**, modelled on local-llm-foundry's `46f7c02`. persona-forge
has no font-scale control, so the test is simpler: assert the computed root size is `16px` and that
both required families report loaded. Put it with the existing frontend tests, not in the capture
harness — the capture assertion in Step 1.5 is the second line of defence, not the first.

> **Scope note.** This step touches product CSS. It is in scope because it is the difference between
> screenshots that reproduce and screenshots that don't, but it ships as its **own commit**
> (Phase 6, commit 2) so it can be reverted independently of the harness port.

### Step 1.6 — `harness/server.mjs`

This is a **merge**, not a port. local-llm-foundry's `server.mjs` spawns a Go binary; persona-forge's
equivalents already exist and work.

- **Move** `run-server.mjs` → `capture/harness/server.mjs` as `startFakeServer`.
- **Move** `run-real-server.mjs` into the same module as `startRealServer`.
- **Port** `findAvailablePort` and `waitForHttp` from local-llm-foundry — genuinely new capability. The
  current harness hardcodes port 8892 and fails outright if it is busy.
- **Keep** both modules' existing `process.on('exit'/'SIGINT'/'SIGTERM')` cleanup hooks and
  `waitUntilHealthy` implementations. `startRealServer`'s health check waits on
  `model_loaded === true`, which is stricter and better than local-llm-foundry's `response.ok`.
- Leave thin re-export shims at `tests/ui/run-server.mjs` and `tests/ui/run-real-server.mjs`:

  ```bash
  grep -rn "run-server\|run-real-server" tests/ui --include="*.mjs" --include="*.js" \
    | grep -v node_modules
  ```

  Playwright config or E2E specs may import them. Verify before deciding whether the shims can be
  dropped; if nothing imports them, delete outright in Step 1.14.

### Step 1.7 — `harness/fixtures.mjs`

local-llm-foundry's `fixtures.mjs` seeds MLX presets and GGUF model dirs — **none of it applies**. What
transfers is the *role*: a module that seeds capture-time state.

- **Move** `lib/seed.mjs` (`seedCaptureFixtures`) here.
- **Move** `lib/python.mjs` (`resolvePython`) here, or leave it as `harness/python.mjs` — it is a
  distinct concern and small either way.
- **Add** `seedHeroFixtures()` if the hero scenarios need state the default fixtures lack. Decide
  after Step 1.12 shows what the hero shots actually render; do not pre-build it.

### Step 1.8 — `harness/source.mjs`

Port the precedence logic verbatim, then redefine the source set for persona-forge:

```js
export const CAPTURE_SOURCES = Object.freeze(['fake', 'real-local', 'remote', 'auto']);
const IMPLEMENTED_SOURCES = new Set(['fake', 'real-local', 'remote']);
```

| Source | Backing | Replaces |
|---|---|---|
| `fake` | `startFakeServer()` — `fixtures/fake_model_server.py` | default (no flags) |
| `real-local` | `startRealServer()` — real Python app, real inference, seeded fixtures | `--real` |
| `remote` | the live docker-agent instance, no spawn | `--target <url>` |

`connectSource()` returns `{ kind, baseURL, teardown }`. For `fake`/`real-local`, `teardown()` calls
the server's `stop()`; for `remote` it is a no-op. This is the piece that makes real-vs-fake a
declared property of each scenario instead of a flag the operator has to remember.

**Default source is `remote`**, matching local-llm-foundry — and correct here, because the live instance
has real data. Scenarios that genuinely need the fake server declare `source: 'fake'` in the
registry.

### Step 1.9 — `harness/shot.mjs`

Port `captureShot`, `captureElementScreenshot`, and `cleanupScreenshotTabs`. **Preserve all three
behaviors** described in the Phase 1 preamble — the mouse-park, the `fullPage` default, and the
scroll-to-top policy. They are the reason this module is worth porting rather than reimplementing.

**Merge in the GIF path.** persona-forge's `lib/gif.mjs` (`createRecorder`, `framesToGif`,
`cleanupFrames`, ffmpeg palettegen) is *better suited* than local-llm-foundry's `captureFrames` for the
two existing GIF scenarios. Move it into `shot.mjs`, with two changes:

1. Route frame output through `currentArtifactsDir()` instead of the hardcoded `../frames`.
2. Call `recordArtifact(gifFilename)` after `framesToGif()`, so GIFs participate in the receipt
   contract like PNGs do.

**Drop** `captureSparklineClips`, `startLiveGeneration`, `waitForRapidTelemetry` — local-llm-foundry
telemetry concepts with no persona-forge analogue.

### Step 1.10 — `index.mjs`: registry, `parseArgs`, `runCli`

Port the structure from `../llama-monitor/tests/ui/capture/index.mjs`.

**Flags:** `--scenario <key>`, `--list-scenarios`, `--source <kind>`, `--help/-h`. Port
`--list-scenarios` and drop local-llm-foundry's domain-specific `--chat-only` / `--gpu-only` /
`--inference-only` / `--no-attach` / `--close-up`.

**Registry** — 20 entries. Every one carries `contract`; this is non-negotiable, because
`beginCaptureReceipt()` throws without it.

```js
export const SCENARIOS = {
  'health': { run: scenarioHealth, category: 'core', runtime: 'neutral', contract: {
      intent: 'Prove the service is up and reporting backend/model status.',
      expectedOutputs: ['health--neutral--health.png'],
  }},

  'speak-generate': { run: scenarioGenerate, category: 'generate', runtime: 'pocket-tts', contract: {
      intent: 'Show the Speak page before and after a real generation, including the AudioDeck waveform.',
      expectedOutputs: [
        'speak-generate--pocket-tts--before-generate.png',
        'speak-generate--pocket-tts--after-generate.png',
      ],
  }},

  'omnivoice-audition-gif': {
      run: scenarioOmniVoiceAuditionGif, source: 'fake',
      category: 'omnivoice', runtime: 'omnivoice', contract: {
      intent: 'Animate the accent audition loop: candidates stream in, takes get cherry-picked.',
      expectedOutputs: ['omnivoice-audition-gif--omnivoice--audition.gif'],
  }},

  // ... 17 more
};
```

> **`expectedOutputs` must be the *tagged* filenames.** `recordCapture()` records what
> `tagFilename()` produced, and `finishCaptureReceipt()` compares against `expectedOutputs`
> literally. Declaring `after-generate.png` while the harness writes
> `speak-generate--pocket-tts--after-generate.png` fails every run. Get one scenario green
> end-to-end before writing the other 19 contracts.

`runCli()` orchestrates: resolve source → `setArtifactCategory(entry.category)` →
`setArtifactRuntime(key, entry.runtime)` → `beginCaptureReceipt({...entry.contract, scenario: key})`
→ `launchBrowser()` → `entry.setup?.()` → `entry.run(ctx, options)` → `finishCaptureReceipt()` →
teardown. `main()` wraps it for direct invocation.

### Step 1.11 — Migrate the 16 existing scenarios

One file per scenario. Each exports a single default async function and adds a `// SCENARIO INTENT:`
header plus `// INTENT:` above each capture call — `cli-manifest.mjs --strict` fails the build
otherwise.

| # | Old method (`capture.mjs`) | New file | Key | Runtime | Source |
|---|---|---|---|---|---|
| 1 | `scenarioHealth` | `scenarios/core/health.mjs` | `health` | neutral | remote |
| 2 | `scenarioHome` | `scenarios/core/home.mjs` | `home` | neutral | remote |
| 3 | `scenarioGenerate` | `scenarios/generate/generate.mjs` | `speak-generate` | pocket-tts | remote |
| 4 | `scenarioVoiceDesignPanel` | `scenarios/voice-design/panel.mjs` | `voice-design-panel` | neutral | remote |
| 5 | `scenarioVoiceDesignGenerate` | `scenarios/voice-design/generate.mjs` | `voice-design-generate` | pocket-tts | remote |
| 6 | `scenarioVoiceVariantList` | `scenarios/voice-library/variant-list.mjs` | `voice-variant-list` | neutral | remote |
| 7 | `scenarioVoicePromoteVariant` | `scenarios/voice-library/promote-variant.mjs` | `voice-promote-variant` | neutral | **fake** |
| 8 | `scenarioAccentProjectGrouping` | `scenarios/voice-library/project-grouping.mjs` | `accent-project-grouping` | neutral | remote |
| 9 | `scenarioVoicesList` | `scenarios/voice-library/list.mjs` | `voices-list` | neutral | remote |
| 10 | `scenarioAlignmentCompare` | `scenarios/prosody/alignment-compare.mjs` | `alignment-compare` | pocket-tts | remote |
| 11 | `scenarioSegmentLibraryBrowse` | `scenarios/stitch-studio/segment-library-browse.mjs` | `segment-library-browse` | neutral | remote |
| 12 | `scenarioStitchAssembly` | `scenarios/stitch-studio/assembly.mjs` | `stitch-assembly` | neutral | remote |
| 13 | `scenarioOmniVoiceAudition` | `scenarios/omnivoice/audition.mjs` | `omnivoice-audition` | omnivoice | **fake** |
| 14 | `scenarioPersonaForgeCandidates` | `scenarios/omnivoice/candidates.mjs` | `omnivoice-candidates` | omnivoice | **fake** |
| 15 | `scenarioOmniVoiceAuditionGif` | `scenarios/omnivoice/audition-gif.mjs` | `omnivoice-audition-gif` | omnivoice | **fake** |
| 16 | `scenarioDesignToStitchWizardGif` | `scenarios/wizard/design-to-stitch-gif.mjs` | `design-to-stitch-gif` | pocket-tts | **fake** |

**Mechanical transform per scenario:**

1. Copy the method body verbatim from `capture.mjs`.
2. `async scenarioX({ page, baseURL }) {` → `export default async function(ctx, options) {` with
   `const { page, baseURL } = ctx`.
3. `await screenshot(page, 'feature', 'name.png')` → `await captureShot(page, '<key>-name.png', { fullPage: true })`.
   The `feature` argument is gone — the registry's `category` drives `setArtifactCategory()`.
   Prefixing the filename with the scenario key is what lets `tagFilename()` produce
   `key--runtime--rest.png`.
4. Add imports from `../../harness/*.mjs`.
5. Add the INTENT annotations.

**Do not "improve" scenario logic during migration.** A behavior change and a structural move in the
same step means a failure has two candidate causes. Fix content in Step 1.12 and after.

**One exception, deferred rather than taken here:** scenario #6 `scenarioVoiceVariantList` is already
broken — it times out waiting on `[data-testid="voice-card"]` against the fake server (correction
\#36). Migrate it verbatim anyway, let it fail, and fix it in **Step 1.12** as a content fix. That
keeps the rule intact: the structural move is still a pure move, and the behavior change lands in a
step where a failure has exactly one candidate cause. Start by checking whether the fake server's
voice fixtures render a different testid than the one the scenario waits on.

**Verify each one as you go** — this is 16 files and a silent typo in file 3 is expensive to find
from file 16:

```bash
cd /Users/nick/SCRIPTS/CLAUDE/persona-forge
node tests/ui/capture/index.mjs --scenario health --source fake 2>&1 | tail -5
cat docs/screenshots/artifacts/core/health--receipt.json
```

### Step 1.12 — Content fixes

Now that the structure is right, fix what the shots *show*.

**Sample text.** In `scenarios/generate/generate.mjs` the migrated body still contains:

```js
await page.type('[data-testid="speak-text-input"]', 'Hello from the capture harness.')
```

Replace **only the string literal**:

```js
await page.type('[data-testid="speak-text-input"]', 'The voice was warm and clear, carrying the kind of certainty that made you want to listen.')
```

"Hello from the capture harness" advertises the test rig in a marketing screenshot. The replacement
is long enough to produce a realistic multi-second waveform.

**Fake-server fixtures.** The fixture voices live in **per-voice directories**, not a `voices.json`:

```bash
ls tests/ui/fixtures/capture-data/voices/     # vd_c66abd9c8eb0/ vd_dba466fcad17/ vd_dd6c86850fc0/
cat tests/ui/fixtures/capture-data/voices/vd_dd6c86850fc0/meta.json
```

Each `meta.json` has flat `description` and `sample_text` fields (there is **no** `name` or
`reference_text` — do not invent them). Edit **only** those two, in all three voices. Leave
`voice_id`, `metrics`, `seed`, and every other key untouched — the metrics drive the prosody
fingerprint UI, and changing them makes the screenshots lie.

| Directory | `description` | `sample_text` |
|---|---|---|
| `vd_dd6c86850fc0` | `Warm British Narrator` | `Good afternoon, and welcome to today's programme.` |
| `vd_dba466fcad17` | `Calm Professional` | `Thank you for calling. How can I help you today?` |
| `vd_c66abd9c8eb0` | `Podcast Host` | `Alright, let's dive right in. Here's what you need to know.` |

Use the Edit tool — `sed` on JSON is needlessly fragile. Then verify all three parse:

```bash
for f in tests/ui/fixtures/capture-data/voices/*/meta.json; do
  python3 -c "import json,sys; d=json.load(open('$f')); print(d['voice_id'], '|', d['description'])"
done
```

### Step 1.13 — Fix the live instance's sample text ⚠️

Per the content warning in Ground Truth, `vd_000000000001` on the live host carries a sample line
that must not ship in a public README.

```bash
ssh root@docker-agent \
  "python3 - <<'PY'
import json
p = '/var/data/autopirate/persona-forge/voices/vd_000000000001/meta.json'
d = json.load(open(p))
print('BEFORE:', d['sample_text'])
d['sample_text'] = 'Good afternoon, and welcome to today\'s programme.'
json.dump(d, open(p, 'w'), indent=2)
print('AFTER: ', d['sample_text'])
PY"

ssh root@docker-agent "cd /root/docker/docker-agent && docker compose restart persona-forge"
sleep 45
curl -s --max-time 15 http://192.168.10.72:8318/voices \
  | python3 -c "import sys,json;[print(v['voice_id'],'|',v.get('sample_text','')[:60]) for v in json.load(sys.stdin)['voices']]"
```

Then repeat **Step 0.1** to re-warm the model after the restart.

> This edits live-instance state on a host you own. It is a text-field change to a sample line,
> reversible by editing the same field again. Nothing else on the host is touched.

**If the `ssh … <<'PY'` form is refused** (a remote-python heredoc reads as arbitrary remote code
execution to the permission classifier, and it was refused during this plan's own research), do not
fight it — use the round-trip that is plainly a file edit:

```bash
scp root@docker-agent:/var/data/autopirate/persona-forge/voices/vd_000000000001/meta.json /tmp/meta.json
# edit sample_text with the Edit tool, then:
scp /tmp/meta.json root@docker-agent:/var/data/autopirate/persona-forge/voices/vd_000000000001/meta.json
```

Use absolute paths on both ends. A `cd … &&` prefix on `scp` failed with a bare `EXIT=1` here.

Also prefer a health poll over a fixed `sleep`, which the harness blocks:

```bash
ssh root@docker-agent "until [ \"\$(docker inspect -f '{{.State.Health.Status}}' persona-forge)\" = healthy ]; do sleep 3; done"
```

### Step 1.14 — Hero candidates

Four new scenarios under `scenarios/hero/`, category `hero`, so the candidates sit in one directory
for side-by-side review at the Phase 3 checkpoint.

| Key | File | Runtime | Shot |
|---|---|---|---|
| `hero-speak-filled` | `hero/speak-filled.mjs` | pocket-tts | Speak with text entered, pre-generate |
| `hero-speak-result` | `hero/speak-result.mjs` | pocket-tts | Speak after real generation, waveform visible |
| `hero-voice-design` | `hero/voice-design.mjs` | neutral | Voice Design trait-chip grid |
| `hero-library` | `hero/library.mjs` | neutral | Voice Library with prosody fingerprints |

```js
// SCENARIO INTENT: Hero candidate — the Speak page as a first-time visitor sees it, text entered.
import { gotoApp } from '../../harness/browser.mjs';
import { captureShot } from '../../harness/shot.mjs';

export default async function(ctx) {
    const { page, baseURL } = ctx;
    await gotoApp(page, baseURL);
    await page.waitForSelector('[data-testid="speak-text-input"]');
    await page.type('[data-testid="speak-text-input"]', 'The voice was warm and clear, carrying the kind of certainty that made you want to listen.');
    // INTENT: Clean, uncluttered first impression — the thing a visitor will actually do first.
    await captureShot(page, 'hero-speak-filled-speak.png', { fullPage: true });
}
```

Registry entry:

```js
'hero-speak-filled': { run: heroSpeakFilled, category: 'hero', runtime: 'pocket-tts', contract: {
    intent: 'Hero candidate — the Speak page as a first-time visitor sees it, text entered.',
    expectedOutputs: ['hero-speak-filled--pocket-tts--speak.png'],
}},
```

`hero-voice-design` and `hero-library` use `gotoPage(page, baseURL, 'nav-voice-design',
'[data-testid="voice-design-description"]')` and `gotoPage(page, baseURL, 'nav-voice-library',
'[data-testid="voice-card"]')` respectively.

> **Puppeteer 25 API note.** `page.$x()` was **removed in v22** — it does not exist. Never use it.
> Prefer `[data-testid="..."]` selectors, which every existing scenario already uses and which do
> not break on copy changes. Verify a selector before relying on it:
> ```bash
> grep -rn 'data-testid="nav-\|data-testid="voice-card"\|data-testid="voice-design-description"' \
>   ../../frontend/src --include="*.tsx" --include="*.jsx" | head
> ```

> **`hero-speak-result` performs real CPU inference.** Its `waitForSelector` on
> `[data-testid="speak-result"] audio` needs a 120 s timeout. Do not shorten it.

With `stitch-assembly` and the two GIFs, this gives **seven** hero candidates for Phase 3.

### Step 1.15 — Contract tests

Port all three from `../llama-monitor/tests/ui/capture/`. They use `node:test` + `node:assert/strict`
and no extra dependencies.

| Test | Port fidelity | Notes |
|---|---|---|
| `capture-receipt.test.mjs` | **Verbatim** | Uses the `__capture-receipt-test__` category sandbox; nothing project-specific. |
| `capture-manifest.test.mjs` | **Verbatim** | Asserts every registry entry has a scenario file and every scenario file is registered. |
| `capture-platform.test.mjs` | **Rewrite as `capture-source.test.mjs`** | The original gates Rapid scenarios to Apple Silicon — no persona-forge analogue. Replace with assertions on `resolveCaptureSource` precedence: force beats `--source` beats `CAPTURE_SOURCE` beats scenario default beats `remote`, and an unimplemented source throws. |

Add to `tests/ui/package.json`:

```json
"capture": "node capture/index.mjs",
"capture:group": "node capture/cli-group.mjs",
"capture:manifest": "node capture/cli-manifest.mjs --strict",
"capture:test": "node --test capture/*.test.mjs"
```

Remove the old `"capture": "node capture.mjs"` entry.

### Step 1.16 — Retire the monolith

Only after every scenario is migrated and green:

```bash
cd /Users/nick/SCRIPTS/CLAUDE/persona-forge
git rm tests/ui/capture.mjs
git rm tests/ui/lib/gif.mjs tests/ui/lib/seed.mjs      # merged into harness/
# run-server.mjs / run-real-server.mjs: delete only if Step 1.6's grep found no importers
grep -rn "capture\.mjs\|lib/gif\|lib/seed" . \
  --include="*.mjs" --include="*.js" --include="*.json" --include="*.yml" --include="*.md" \
  | grep -v node_modules | grep -v docs/plans
```

That last grep is the real check — CI workflows and `tests/ui/README.md` reference the old entry
point and must be updated in the same commit.

**Phase 1 gate:**

```bash
cd /Users/nick/SCRIPTS/CLAUDE/persona-forge

node tests/ui/capture/index.mjs --list-scenarios | tee /tmp/scenarios.txt
test "$(grep -c . /tmp/scenarios.txt)" -ge 20 && echo "OK: 20 scenarios" || echo "FAIL: scenario count"

node --test tests/ui/capture/*.test.mjs                     # 3 files, all pass
node tests/ui/capture/cli-manifest.mjs --strict             # exit 0

for s in health home voice-design-panel hero-speak-filled hero-voice-design hero-library; do
  echo "=== $s ==="
  node tests/ui/capture/index.mjs --scenario "$s" --source fake 2>&1 | tail -3
done

find docs/screenshots/artifacts -name "*--receipt.json" | wc -l
echo "PHASE 1 GATE PASSED"
```

---

## Phase 2 — Capture Runs

**Objective:** produce the raw image set. Because the live instance **has real data**, `remote` is
the primary source; `fake` covers only what real data cannot express.

**Gate:** every file in the [Phase 3 curation table](#step-31--promote-the-keepers) exists, and every
scenario wrote a receipt.

### Step 2.1 — Real instance

The registry already declares each scenario's default source, so most of these need no `--source`
flag at all. It is passed explicitly here so the log records what was used.

```bash
cd /Users/nick/SCRIPTS/CLAUDE/persona-forge

for s in \
  home speak-generate voice-design-panel voice-design-generate \
  voice-variant-list accent-project-grouping \
  segment-library-browse stitch-assembly \
  hero-speak-filled hero-speak-result hero-voice-design hero-library ; do
  echo "=== $s ==="
  node tests/ui/capture/index.mjs --scenario "$s" --source remote 2>&1 | tail -4
done 2>&1 | tee /tmp/capture-real.log

grep -c "receipt" /tmp/capture-real.log
```

The voice-library, project-grouping, and stitch scenarios are here **because the live host has 2
voices and 6 segments**. If one fails anyway, note which and move it to Step 2.2.

> `hero-speak-result`, `speak-generate`, and `voice-design-generate` perform **real CPU inference**.
> Expect tens of seconds each.

Alternatively, by category:

```bash
node tests/ui/capture/cli-group.mjs hero --source remote
```

### Step 2.2 — Fake server for the remainder

These declare `source: 'fake'` in the registry, so the flag is redundant — but explicit is better in
a log.

```bash
for s in \
  omnivoice-audition omnivoice-candidates alignment-compare \
  voice-promote-variant omnivoice-audition-gif design-to-stitch-gif ; do
  echo "=== $s ==="
  node tests/ui/capture/index.mjs --scenario "$s" --source fake 2>&1 | tail -4
done 2>&1 | tee /tmp/capture-fake.log
```

Add anything that failed in Step 2.1.

### Step 2.3 — Catalogue

```bash
find docs/screenshots/artifacts -type f \( -name "*.png" -o -name "*.gif" \) \
  -exec ls -la {} \; | awk '{print $5, $NF}' | sort -k2 > /tmp/screenshot-catalog.txt
cat /tmp/screenshot-catalog.txt

# Receipts are the real check — every scenario that ran must have left one
find docs/screenshots/artifacts -name "*--receipt.json" -exec sh -c \
  'echo "--- $1"; python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(d[\"scenario\"], len(d.get(\"produced\",[])), \"outputs\")" "$1"' _ {} \;
```

The receipt contract already enforced that every expected output exists at a realistic viewport, so
the old "flag anything under 40 KB" heuristic is retired. **Still open the images and look at them**
— a receipt proves a file was written at the right size, not that the page rendered something worth
publishing.

---

## Phase 3 — Curate & Promote

**Objective:** move the keepers out of the gitignored `artifacts/` directory into committed
`docs/screenshots/`, and present the hero candidates for a human decision.

**This phase resolves the broken-images defect.** Nothing in `artifacts/` is ever committed.

**Gate:** every promoted file is tracked by git, and no promoted image contains the flagged text.

### Step 3.1 — Promote the keepers

Source paths now carry the runtime tag and live under the category directory
(`artifacts/<category>/<key>--<runtime>--<rest>.png`). Confirm the exact names from
`/tmp/screenshot-catalog.txt` before running this — the tag makes them predictable, not guessable.

```bash
cd /Users/nick/SCRIPTS/CLAUDE/persona-forge
mkdir -p docs/screenshots

cp docs/screenshots/artifacts/generate/speak-generate--pocket-tts--after-generate.png \
   docs/screenshots/speak.png
cp docs/screenshots/artifacts/voice-design/voice-design-generate--pocket-tts--filled.png \
   docs/screenshots/voice-design.png
cp docs/screenshots/artifacts/omnivoice/omnivoice-audition--omnivoice--candidates.png \
   docs/screenshots/omnivoice.png
cp docs/screenshots/artifacts/voice-library/voice-variant-list--neutral--variant-list.png \
   docs/screenshots/voice-library.png
cp docs/screenshots/artifacts/stitch-studio/stitch-assembly--neutral--assembly.png \
   docs/screenshots/stitch-studio.png

cp docs/screenshots/artifacts/omnivoice/omnivoice-audition-gif--omnivoice--audition.gif \
   docs/screenshots/omnivoice-audition.gif
cp docs/screenshots/artifacts/wizard/design-to-stitch-gif--pocket-tts--design-to-stitch.gif \
   docs/screenshots/design-to-stitch.gif

mkdir -p docs/screenshots/hero-candidates
cp docs/screenshots/artifacts/hero/*.png docs/screenshots/hero-candidates/
cp docs/screenshots/artifacts/stitch-studio/stitch-assembly--neutral--assembly.png \
   docs/screenshots/hero-candidates/stitch-assembly.png

ls -la docs/screenshots/ docs/screenshots/hero-candidates/
```

Flat destination slugs are deliberate: README image paths are the most-linked strings in the repo,
and pinning them to `docs/screenshots/<feature>.png` decouples them from harness churn — including
from the runtime tag, which is useful in `artifacts/` and noise in a README URL.

### Step 3.2 — Confirm the promoted files are committable

```bash
git check-ignore -v docs/screenshots/speak.png && \
  echo "STILL IGNORED — STOP" || echo "OK: promoted files are committable"

git add -n docs/screenshots/ | head -20
```

If `git check-ignore` matches, the promotion target is wrong — re-read `.gitignore:5`. Only
`docs/screenshots/artifacts/` is ignored.

### Step 3.3 — Content safety re-check ⚠️

```bash
curl -s --max-time 15 http://192.168.10.72:8318/voices \
  | python3 -c "
import sys, json
bad = ['on the menu', 'want me']
for v in json.load(sys.stdin)['voices']:
    t = (v.get('sample_text') or '').lower()
    hit = [b for b in bad if b in t]
    print(('FAIL ' if hit else 'ok   '), v['voice_id'], '|', (v.get('sample_text') or '')[:70])
"
```

Any `FAIL` means Step 1.13 did not take effect, or the images predate it. Re-run Step 1.13, then
re-capture and re-promote every real-instance image. **Then open each promoted PNG and look at it.**
The API check catches the known string; only your eyes catch the unknown one.

### Step 3.4 — 🛑 HUMAN CHECKPOINT: pick the hero

**Stop here. Do not proceed to Phase 4 or 5 without a decision.**

| Candidate | File | Argument for it |
|---|---|---|
| Speak, filled | `hero-candidates/hero-speak-filled--pocket-tts--speak.png` | The first thing a visitor will actually do. Clean, uncluttered. |
| Speak, generated | `hero-candidates/hero-speak-result--pocket-tts--speak.png` | Same, plus the AudioDeck waveform — proves the app works. |
| Voice Design | `hero-candidates/hero-voice-design--neutral--panel.png` | Trait chip grid; the most "designed"-looking surface. |
| Voice Library | `hero-candidates/hero-library--neutral--library.png` | Prosody fingerprints; signals depth and real data. |
| Stitch Studio | `hero-candidates/stitch-assembly.png` | Pink/purple/blue timeline; the most visually distinctive. |
| OmniVoice GIF | `omnivoice-audition.gif` | Motion outperforms static on GitHub; shows accent audition. |
| Wizard GIF | `design-to-stitch.gif` | Shows the full design→stitch journey end to end. |

Record the choice here (replace `{{HERO}}` in Phase 5 Step 5.2 with the chosen path) before
continuing. If the human wants a candidate that does not exist yet, add a scenario under
`scenarios/hero/`, register it, and re-run Phase 2 for that key only — which is exactly what the
`hero` category is for.

---

## Phase 4 — Docs Corrections & Index

**Objective:** correct stale content across the live docs, then build `docs/README.md` as the
navigable front door. This phase runs **before** the README rewrite because the README links into
these docs, and it **feeds back into the harness** — see Step 4.4.

**Gate:** no stale product name or stale host in the live doc set; `docs/README.md` exists and every
link in it resolves.

> **macOS `sed` note.** BSD `sed` requires an argument to `-i`. Every in-place edit below uses
> `sed -i ''`. A bare `sed -i '...'` **fails on this machine**. Where a change is more than a line
> swap, use the Edit tool instead.

### Step 4.1 — Fix the HTTP API reference

Current first three lines, verified:

```
# Qwen3-TTS OpenVINO — HTTP API Reference

Single-source reference for all HTTP endpoints on branch `voice-design-accent-and-queueing`.
```

Both are stale: the product is no longer "Qwen3-TTS OpenVINO", and the branch is long dead. Line 3
needs its **suffix trimmed**, not deletion — deleting it removes the file's only description.

```bash
cd /Users/nick/SCRIPTS/CLAUDE/persona-forge
sed -i '' '1s/.*/# Persona Forge — HTTP API Reference/' docs/api/HTTP_API_REFERENCE.md
sed -i '' '3s/.*/Single-source reference for all HTTP endpoints exposed by Persona Forge./' docs/api/HTTP_API_REFERENCE.md
head -4 docs/api/HTTP_API_REFERENCE.md
```

### Step 4.2 — Fix remaining stale product names

```bash
grep -rln "Qwen3-TTS OpenVINO" docs --include="*.md" | grep -v resolved | grep -v plans
# docs/architecture/MODEL_SWAP_AND_QUEUEING.md
# docs/dev/architecture/OPENVINO_IMPLEMENTATION.md
# docs/dev/benchmarks/OPENVINO_RESULTS.md
```

Judgment applies, per file:

- **`MODEL_SWAP_AND_QUEUEING.md`** — a current architecture doc. Update the phrase where it names
  *the product*; **leave it** where it names *the Qwen engine or the OpenVINO backend*, which still
  exist. Read each hit before editing.
- **`dev/architecture/OPENVINO_IMPLEMENTATION.md`** and **`dev/benchmarks/OPENVINO_RESULTS.md`** —
  historical records. **Leave the titles alone**; renaming a benchmark log falsifies the record of
  what was measured. Add one line under each H1:
  ```
  > Historical record from the Qwen3-TTS/OpenVINO era. The project is now Persona Forge; see
  > [SYSTEM_OVERVIEW](../../architecture/SYSTEM_OVERVIEW.md) for current architecture.
  ```
  (Check relative depth from each file and adjust `../../`.)

### Step 4.3 — Fix the host migration (`dockermisc1` → `docker-agent`)

**20 live docs still say `dockermisc1`**, including two a contributor follows as instructions:

```bash
grep -rln "dockermisc1" docs --include="*.md" | grep -v resolved | grep -v plans
```

**Fix now (actionable — someone will follow these and hit a dead host):**

| File | Issue |
|---|---|
| `docs/DEV_TEST_LOOP.md` | H1 is literally `# Dev / Test Loop with dockermisc1` |
| `docs/dev/INTERNAL_OPERATIONS.md` | H1 is `# Internal operations (dockermisc1 and related)` |
| `docs/dev/validation_checks.md` | Validation commands target the old host |
| `docs/TEST_STRATEGY.md` | Test-host references |
| `docs/architecture/pocket_tts_integration.md` | Deployment references |

Replace `dockermisc1` with `docker-agent` and any IP with `192.168.10.72`. Verify each command still
makes sense on the new host before rewriting it — paths changed too
(`/var/data/autopirate/persona-forge/` data root, `/root/docker/docker-agent/` compose dir).

**Leave alone (historical):** everything under `docs/dev/features/`, `docs/dev/voice/`,
`docs/dev/prosody/`, `docs/dev/integration/`, `docs/dev/ci/`, `docs/dev/benchmarks/`, and
`docs/dev/architecture/`. These are dated plan and analysis records; the host they ran on is part of
the record.

### Step 4.4 — 🔁 Screenshot coverage feedback

**This step is why Phase 4 precedes Phase 5.** While correcting the docs above, note any doc where a
screenshot would do more than prose. Two known candidates:

- **`docs/architecture/FRONTEND_OVERVIEW.md`** — describes pages and flows entirely in text. One
  annotated shot per page would make it far more useful.
- **`docs/dev/DESIGN_SYSTEM.md`** — documents tokens and component primitives with no visual
  reference at all.

For each doc that needs one:

1. Check whether an existing artifact already covers it (`/tmp/screenshot-catalog.txt`).
2. If not, **add a scenario file under the matching `scenarios/<category>/`**, register it with a
   `contract`, run it via `--scenario`, promote it to `docs/screenshots/<name>.png`, and reference
   it from the doc. The port makes this cheap: a new scenario is one file plus one registry entry.
3. If a needed shot cannot be captured (requires state the harness cannot reach), record it in
   [Open questions](#open-questions) rather than faking it.

Keep this bounded: **at most three new scenarios**. A docs-illustration pass is its own project.

### Step 4.5 — Fix filename-as-title H1s

```bash
head -1 docs/architecture/FRONTEND_OVERVIEW.md   # "# FRONTEND_OVERVIEW"
head -1 docs/TEST_STRATEGY.md                    # "# TEST_STRATEGY"

sed -i '' '1s/.*/# Frontend Overview/' docs/architecture/FRONTEND_OVERVIEW.md
sed -i '' '1s/.*/# Test Strategy/'     docs/TEST_STRATEGY.md
```

Leave `docs/architecture/SYSTEM_OVERVIEW.md` at `# System Overview`. It is inside a repo named
persona-forge; prefixing the product name onto every H1 is noise.

### Step 4.6 — Create `docs/README.md`

GitHub renders this automatically when someone clicks into `docs/`.

```markdown
# Persona Forge — Documentation

Start here. Docs are grouped by what you are trying to do.

## Run it

| Doc | What it covers |
|---|---|
| [HOW_TO_RUN.md](HOW_TO_RUN.md) | Docker Compose setup, first boot, the export step for Qwen/OpenVINO |
| [ENV_REFERENCE.md](ENV_REFERENCE.md) | Every environment variable, with defaults |
| [api/HTTP_API_REFERENCE.md](api/HTTP_API_REFERENCE.md) | Every HTTP endpoint, request and response shapes |

## Understand it

| Doc | What it covers |
|---|---|
| [architecture/SYSTEM_OVERVIEW.md](architecture/SYSTEM_OVERVIEW.md) | Components, request flow, endpoint map |
| [architecture/FRONTEND_OVERVIEW.md](architecture/FRONTEND_OVERVIEW.md) | React pages, zustand state, key UI flows |
| [architecture/MODEL_SWAP_AND_QUEUEING.md](architecture/MODEL_SWAP_AND_QUEUEING.md) | Backend swapping, request queueing, idle unload |
| [architecture/pocket_tts_integration.md](architecture/pocket_tts_integration.md) | The default CPU backend and its prosody behavior |
| [architecture/OMNIVOICE_REFERENCE.md](architecture/OMNIVOICE_REFERENCE.md) | OmniVoice accent engine, audition flow, licensing |

## Develop it

| Doc | What it covers |
|---|---|
| [dev/LOCAL_SETUP.md](dev/LOCAL_SETUP.md) | `uv`-managed local environment |
| [DEV_TEST_LOOP.md](DEV_TEST_LOOP.md) | The edit → test → deploy loop |
| [TEST_STRATEGY.md](TEST_STRATEGY.md) | Test tiers and what belongs in each |
| [dev/DESIGN_SYSTEM.md](dev/DESIGN_SYSTEM.md) | Frontend design tokens and component primitives |
| [dev/validation_checks.md](dev/validation_checks.md) | Pre-merge validation commands |

## Agent reference

Compact references written for AI coding agents working in this repo.

| Doc | What it covers |
|---|---|
| [agent-reference/RUNTIME_AND_MEMORY.md](agent-reference/RUNTIME_AND_MEMORY.md) | Runtime invariants, memory ceilings |
| [agent-reference/EXPORT_SYSTEM.md](agent-reference/EXPORT_SYSTEM.md) | The OpenVINO export pipeline |
| [agent-reference/TRANSFORMERS_COMPAT.md](agent-reference/TRANSFORMERS_COMPAT.md) | Transformers 5 compatibility shims |

## Archive

- [`dev/features/`](dev/features/), [`dev/voice/`](dev/voice/), [`dev/prosody/`](dev/prosody/) —
  dated design and implementation plans, kept as a record
- [`dev/benchmarks/`](dev/benchmarks/) — benchmark logs from the OpenVINO era
- [`dev/resolved/`](dev/resolved/) — completed plans
- [`plans/`](plans/) — in-flight plans

> Docs under the archive are **historical**. Where they conflict with the current docs above,
> the current docs win.
```

Then verify every link resolves:

```bash
cd docs
grep -o '](\([^)]*\))' README.md | sed 's/](//;s/)//' | while read p; do
  [ -e "$p" ] && echo "OK   $p" || echo "BROKEN $p"
done
cd ..
```

**Phase 4 gate:**

```bash
cd /Users/nick/SCRIPTS/CLAUDE/persona-forge

grep -l "Qwen3-TTS OpenVINO" docs/api/HTTP_API_REFERENCE.md 2>/dev/null \
  && echo "FAIL: api ref still stale" || echo "OK: api ref clean"

grep -rn "voice-design-accent-and-queueing" docs/api/ && echo "FAIL" || echo "OK: branch ref clean"

for f in docs/DEV_TEST_LOOP.md docs/dev/INTERNAL_OPERATIONS.md docs/dev/validation_checks.md \
         docs/TEST_STRATEGY.md docs/architecture/pocket_tts_integration.md; do
  grep -q dockermisc1 "$f" && echo "FAIL: $f" || echo "OK: $f"
done

test -f docs/README.md && echo "OK: index exists" || echo "FAIL: no index"
echo "PHASE 4 GATE DONE"
```

---

## Phase 5 — README Rewrite

**Objective:** replace `README.md` with a showcase document that references **promoted** images and
the **corrected** docs.

**Prerequisite:** Step 3.4 (hero pick) and all of Phase 4 are complete.

**Gate:** every image path and doc link resolves on disk, and no image path points into `artifacts/`.

### Step 5.1 — Current README, for reference

```bash
cat README.md    # What it does / Getting started / Model profiles / HTTP API / Images
```

Keep the accurate technical content from `Model profiles` and the image-tagging guidance. Anything
dropped should be dropped because it is wrong or better placed in `docs/`, not because it was
inconvenient.

### Step 5.2 — Write the new README

Replace `README.md` entirely. **Substitute `{{HERO}}`** with the path chosen at Step 3.4.

```markdown
<div align="center">

# Persona Forge

**Open-source voice-cloning and voice-design studio**

Clone a voice from a single reference WAV. Design accents from scratch. Assemble clips in a
timeline editor. Serve it all over an OpenAI-compatible API. One container, one process,
no training required.

[![Release](https://img.shields.io/github/v/release/nmorgowicz-org/persona-forge)](https://github.com/nmorgowicz-org/persona-forge/releases)
[![Container](https://img.shields.io/badge/ghcr.io-persona--forge-blue?logo=docker)](https://github.com/nmorgowicz-org/persona-forge/pkgs/container/persona-forge)
[![License](https://img.shields.io/github/license/nmorgowicz-org/persona-forge)](LICENSE)

</div>

---

![Persona Forge]({{HERO}})

---

## What it does

| | Feature | Description |
|---|---|---|
| 🎙️ | **Voice cloning** | Clone a voice from one reference WAV. No fine-tuning, no training data. |
| 🎨 | **Voice Design** | Compose a voice from trait chips — gender, register, texture, persona — or a free-form description. Preview, then save. |
| 🌏 | **Accent design** | OmniVoice generates candidates per segment across accents. Audition them, cherry-pick the best takes, stitch the winners into a reference voice. |
| ✂️ | **Stitch Studio** | Drag segments onto a timeline. Per-clip trim, fade, gain, and DSP, with live preview. |
| 📚 | **Voice Library** | Prosody fingerprints (LUFS, speech rate, pause ratio, peak dBFS) for every saved voice. Fork, edit, compare variants. |
| 🔌 | **OpenAI-compatible API** | `POST /v1/audio/speech` — a drop-in TTS endpoint for any OpenAI SDK client. |
| ⚡ | **CPU-first** | The default pocket-tts backend runs on any CPU. Qwen3-TTS (PyTorch or OpenVINO) is opt-in. |
| 🎛️ | **Live runtime config** | Change backend, idle-unload timer, and DSP knobs from the UI. No restart. |

---

## Screenshots

<table>
<tr>
<td width="50%">

**Speak** — generate from any saved voice

![Speak](docs/screenshots/speak.png)

</td>
<td width="50%">

**Voice Design** — compose from trait chips

![Voice Design](docs/screenshots/voice-design.png)

</td>
</tr>
<tr>
<td width="50%">

**OmniVoice** — accent audition, per segment

![OmniVoice](docs/screenshots/omnivoice.png)

</td>
<td width="50%">

**Voice Library** — prosody fingerprints

![Voice Library](docs/screenshots/voice-library.png)

</td>
</tr>
</table>

**Stitch Studio** — assemble clips into a new reference voice:

![Stitch Studio](docs/screenshots/stitch-studio.png)

### In motion

| OmniVoice audition | Voice Design → Stitch |
|---|---|
| ![Audition](docs/screenshots/omnivoice-audition.gif) | ![Wizard](docs/screenshots/design-to-stitch.gif) |

---

## Getting started

**Prerequisites:** Docker and Docker Compose.

```bash
git clone https://github.com/nmorgowicz-org/persona-forge.git
cd persona-forge
cp .env.example .env          # optional: set HF_TOKEN, REF_AUDIO_PATH
docker compose up -d persona-forge
open http://localhost:8318
```

The service is ready when `GET /health` reports `"model_loaded": true` — roughly 30–60 seconds on
first boot with the default pocket-tts backend.

> **Want the Qwen engine with OpenVINO acceleration?** Run the export step first and set
> `TTS_BACKEND=openvino`. See [HOW_TO_RUN.md](docs/HOW_TO_RUN.md).

---

## HTTP API

Everything is served on port 8318. There is **no authentication by default**.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health, model status, backend and mount info |
| `POST` | `/v1/audio/speech` | **OpenAI-compatible TTS** |
| `POST` | `/generate` | Native TTS — adds `language`, `seed`, `prosody_repair` |
| `GET` | `/voices` | Saved voices with prosody metrics |
| `POST` | `/voice_design` | Generate a voice from a description |
| `POST` | `/omnivoice/audition` | Accent audition (streaming, multi-segment) |
| `GET`/`POST` | `/runtime/config` | Live runtime configuration |

```bash
curl -s http://localhost:8318/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello world", "voice_id": "vd_000000000001", "response_format": "mp3"}' \
  --output speech.mp3
```

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8318/v1", api_key="unused")
client.audio.speech.create(
    model="tts-1", voice="vd_000000000001", input="Hello world"
).stream_to_file("speech.mp3")
```

Full reference: **[docs/api/HTTP_API_REFERENCE.md](docs/api/HTTP_API_REFERENCE.md)**

---

## Container image

```bash
docker pull ghcr.io/nmorgowicz-org/persona-forge:latest
```

Pin a version — or a digest — for anything you depend on:

```bash
docker pull ghcr.io/nmorgowicz-org/persona-forge:v1.0.11
```

Tags: `latest`, `v<major>.<minor>.<patch>`, `<git-sha>`.

---

## Documentation

**[📖 Full documentation index](docs/README.md)**

Quick links: [Setup](docs/HOW_TO_RUN.md) · [Environment](docs/ENV_REFERENCE.md) ·
[HTTP API](docs/api/HTTP_API_REFERENCE.md) ·
[Architecture](docs/architecture/SYSTEM_OVERVIEW.md) ·
[Contributing](docs/dev/LOCAL_SETUP.md)

---

## Security

No authentication and no TLS out of the box. Persona Forge is built to run on a trusted LAN or
behind an authenticated reverse proxy. **Do not expose port 8318 to the internet** without putting
auth in front of it.

Reporting: [SECURITY.md](SECURITY.md)

---

## License

[MIT](LICENSE) — with the exception of OmniVoice model weights, which are CC-BY-NC
(non-commercial). See [OMNIVOICE_REFERENCE.md](docs/architecture/OMNIVOICE_REFERENCE.md).
```

### Step 5.3 — Verify

```bash
cd /Users/nick/SCRIPTS/CLAUDE/persona-forge

echo "=== no artifacts/ paths (these would be broken on GitHub) ==="
grep -n "screenshots/artifacts" README.md && echo "FAIL" || echo "OK"

echo "=== every image resolves ==="
grep -o 'docs/screenshots/[^)]*' README.md | sort -u | while read f; do
  [ -f "$f" ] && echo "OK   $f" || echo "MISS $f"
done

echo "=== every doc link resolves ==="
grep -o '](\(docs/[^)]*\|LICENSE\|SECURITY\.md\))' README.md | sed 's/](//;s/)$//' | sort -u | while read f; do
  [ -e "$f" ] && echo "OK   $f" || echo "MISS $f"
done

echo "=== version matches the release manifest (NOT git tag) ==="
grep -o 'persona-forge:v[0-9.]*' README.md
python3 -c "import json;print('manifest:', json.load(open('.release-please-manifest.json'))['.'])"
```

> **Do not use `git tag` to check the version.** Tags still carry the pre-rebrand
> `qwen3-tts-openvino-v*` prefix, so `git tag --sort=-v:refname | head -1` returns `v0.23.0` and is
> misleading. `.release-please-manifest.json` is the authority.

**Phase 5 gate:** the first check prints `OK`, and no line in checks 2 or 3 prints `MISS`.

---

## Phase 6 — Commit

**Objective:** land the work as five reviewable commits.

**Why five:** the harness *port* is a large structural change that reviewers need to read on its own
— burying it under a megabyte of PNGs, or mixing it with prose, makes it unreviewable. The font fix
is the only commit that touches shipped product CSS, so it stays separately revertable. Commit in
this order.

```bash
cd /Users/nick/SCRIPTS/CLAUDE/persona-forge

# --- 1. The port itself (structure only, no behavior change) ---
git add tests/ui/capture/ tests/ui/package.json
git rm --cached tests/ui/capture.mjs tests/ui/lib/gif.mjs tests/ui/lib/seed.mjs 2>/dev/null
git commit -m "test(ui): port capture harness to split architecture

Ports the capture harness from the monolithic capture.mjs to the split
architecture proven in local-llm-foundry's tests/ui/capture/.

- harness/: paths, browser, server, shot, receipt, source, fixtures
- scenarios/: one file per scenario, grouped by category
- index.mjs registry with per-scenario capture contracts
- cli-group.mjs and cli-manifest.mjs --strict
- Three contract tests (receipt, manifest, source resolution)

Capture receipts now fail a run when a scenario produces missing,
unexpected, or unrealistically-sized output. Source resolution replaces
the --real/--target flag pair. Filenames are engine-tagged.

Adapted rather than copied: the font contract targets Geist rather than
Inter/Fira Code, and harness/server.mjs wraps the existing Python
spawners.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"

# --- 2. Font determinism (the only commit touching product CSS) ---
git add frontend/src/index.css frontend/package.json frontend/package-lock.json
git commit -m "fix(ui): make font rendering deterministic across platforms

Screenshots and layout depended on the capturing machine's fonts:

- font-mono was used in five components but --font-mono was never
  defined, so Tailwind fell through to its system stack. macOS rendered
  SF Mono and Windows rendered Consolas, giving different glyph advance
  widths in numeric readouts. Bundles @fontsource-variable/geist-mono
  and sets --font-mono.
- html had no explicit font-size, leaving the root baseline to the
  platform default. Sets it to 16px.

Geist Variable was already bundled and self-hosted; no external font
request is introduced or removed.

Not covered: side-by-side Windows/macOS visual comparison, which needs
a Windows host and is tracked as a follow-up.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"

# --- 3. Scenario content + hero candidates ---
git add tests/ui/capture/scenarios/ tests/ui/fixtures/
git commit -m "test(ui): add hero candidates and fix capture sample text

- Four hero-candidate scenarios under scenarios/hero/
- Speak sample text no longer advertises the test harness
- Refresh fake-server fixture voice descriptions and sample text

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"

# --- 4. Promoted screenshots ---
git add docs/screenshots/
git commit -m "docs: promote curated screenshots out of the ignored artifacts dir

docs/screenshots/artifacts/ is gitignored, so README images had to be
promoted to docs/screenshots/ to render on GitHub.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"

# --- 5. Docs corrections, index, README ---
git add README.md docs/README.md docs/api/ docs/architecture/ docs/dev/ docs/*.md
git status --short           # review before committing
git commit -m "docs: README showcase rewrite, docs index, and staleness pass

- Rewrite README as a showcase: hero, feature table, screenshot grid,
  API table, and links into the new docs index
- Add docs/README.md as the documentation front door
- Fix stale product name and dead branch reference in HTTP_API_REFERENCE
- Update dockermisc1 -> docker-agent in actionable docs (historical
  plan records left as-is)
- Fix filename-as-title H1s in FRONTEND_OVERVIEW and TEST_STRATEGY

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

**Phase 6 gate:**

```bash
git log --oneline -4
git status --short          # clean apart from intentionally-ignored artifacts/
node --test tests/ui/capture/*.test.mjs
```

> Do not push or open a PR without asking. Landing this is a human decision.

---

## Appendix A — Scenario reference

Post-port keys. "Real OK" reflects the live host **having 2 voices and 6 segments**.

| Key | Category | Runtime | Default source | Real OK? |
|---|---|---|---|---|
| `health` | core | neutral | remote | ✅ |
| `home` | core | neutral | remote | ✅ |
| `speak-generate` | generate | pocket-tts | remote | ✅ real audio |
| `voice-design-panel` | voice-design | neutral | remote | ✅ |
| `voice-design-generate` | voice-design | pocket-tts | remote | ✅ |
| `voice-variant-list` | voice-library | neutral | remote | ✅ `vd_32eb29256158` has variants |
| `voice-promote-variant` | voice-library | neutral | **fake** | ⚠️ mutates state |
| `accent-project-grouping` | voice-library | neutral | remote | ✅ real `projects.json` |
| `voices-list` | voice-library | neutral | remote | ✅ |
| `alignment-compare` | prosody | pocket-tts | remote | ⚠️ try real, fall back |
| `segment-library-browse` | stitch-studio | neutral | remote | ✅ 6 real segments |
| `stitch-assembly` | stitch-studio | neutral | remote | ✅ 6 real segments |
| `omnivoice-audition` | omnivoice | omnivoice | **fake** | ⚠️ slow on CPU |
| `omnivoice-candidates` | omnivoice | omnivoice | **fake** | ⚠️ prefer fake |
| `omnivoice-audition-gif` | omnivoice | omnivoice | **fake** | ❌ fake |
| `design-to-stitch-gif` | wizard | pocket-tts | **fake** | ❌ fake |
| `hero-speak-filled` *(new)* | hero | pocket-tts | remote | ✅ |
| `hero-speak-result` *(new)* | hero | pocket-tts | remote | ✅ slow |
| `hero-voice-design` *(new)* | hero | neutral | remote | ✅ |
| `hero-library` *(new)* | hero | neutral | remote | ✅ |

## Appendix B — Image path map

| README slot | Committed path | Promoted from |
|---|---|---|
| Hero | *(chosen at Step 3.4)* | `artifacts/hero/` or `artifacts/stitch-studio/` |
| Speak | `docs/screenshots/speak.png` | `artifacts/generate/speak-generate--pocket-tts--after-generate.png` |
| Voice Design | `docs/screenshots/voice-design.png` | `artifacts/voice-design/voice-design-generate--pocket-tts--filled.png` |
| OmniVoice | `docs/screenshots/omnivoice.png` | `artifacts/omnivoice/omnivoice-audition--omnivoice--candidates.png` |
| Voice Library | `docs/screenshots/voice-library.png` | `artifacts/voice-library/voice-variant-list--neutral--variant-list.png` |
| Stitch Studio | `docs/screenshots/stitch-studio.png` | `artifacts/stitch-studio/stitch-assembly--neutral--assembly.png` |
| GIF 1 | `docs/screenshots/omnivoice-audition.gif` | `artifacts/omnivoice/omnivoice-audition-gif--omnivoice--audition.gif` |
| GIF 2 | `docs/screenshots/design-to-stitch.gif` | `artifacts/wizard/design-to-stitch-gif--pocket-tts--design-to-stitch.gif` |

## Appendix C — Live instance

- **Host:** `root@docker-agent` (`192.168.10.72`), port **8318**
- **Data root:** `/var/data/autopirate/persona-forge/` — `voices/`, `segments/`, `reference/`,
  `model/` (HF cache), `ov/` (OpenVINO IR)
- **Compose:** `/root/docker/docker-agent/docker-compose.yml`
- **Backend:** `pocket_tts` on CPU; **idle unload at 1800 s** — always warm before capturing
- **Real data:** 2 voices, 6 segments, `voices/projects.json`

```bash
curl -s http://192.168.10.72:8318/health | python3 -m json.tool | head -20
ssh root@docker-agent "cd /root/docker/docker-agent && docker compose restart persona-forge"
```

## Appendix D — Corrections log

Each item verified against the repo, the reference implementation, or the live host.

### Revision 3 (this revision) — the harness premise

| # | Revisions 1–2 said | Reality | Impact |
|---|---|---|---|
| 20 | Phase 1 = patch `capture.mjs`: add 4 hero methods, fix a string | persona-forge's harness is the **pre-split ancestor** of local-llm-foundry's `capture/`. Its `index.mjs` header states it was "Rebuilt from tests/ui/capture.mjs (Phase A1-A4 split)"; both still use `SCREENSHOT_PORT = 8892` | 🔴 **Critical.** The plan patched the thing that was supposed to be replaced. Phase 1 rewritten as a full port. |
| 21 | Step 2.3: "flag anything under 40 KB" to detect blank captures | `harness/receipt.mjs` already enforces expected-vs-produced outputs, on-disk existence, and a viewport allowlist | 🟠 A worse reinvention of a solved problem. Heuristic retired. |
| 22 | Phase 3: bespoke `cp` promotion out of the gitignored dir | `harness/paths.mjs` already exports `SCREENSHOTS_DIR` as a first-class path | 🟡 The port makes promotion structural rather than ad-hoc. |
| 23 | *(not noticed)* | local-llm-foundry's `assertDeterministicFonts` asserts Inter/Fira Code, which persona-forge does not ship | 🟡 A verbatim port would throw. Step 1.5 re-targets it. **Superseded in part by #26** — the reason is the wrong family names, not the absence of webfonts. |
| 24 | Phase 5 verify: `git tag --sort=-v:refname \| head -1` | Tags are pre-rebrand `qwen3-tts-openvino-v0.23.0`; the authority is `.release-please-manifest.json` | 🟠 The version check would have reported v0.23.0 and been ignored or acted on wrongly. |
| 25 | Three commits | The port is a large structural change needing its own reviewable diff | 🟡 Split into four. |
| 26 | *(this plan, revision 3)* "persona-forge ships **no webfonts at all** — no `@font-face`, no `font-family`, no Google Fonts link" | **Wrong.** `frontend/src/index.css:4` is `@import "@fontsource-variable/geist"` — Geist Variable is bundled and self-hosted, applied via `--font-sans` + `html { @apply font-sans }` | 🔴 **My own error.** The grep that produced it searched for `@font-face`/`font-family` literals; the `@import` is a *bare npm specifier* (faces live in `node_modules`) and the family is set through a Tailwind v4 theme variable, so both evade it. Reframes the font work: B1 is already satisfied; the real gaps are the missing `--font-mono` and root baseline. Step 1.5 re-targeted, Step 1.5a added. |
| 27 | *(not noticed)* | `font-mono` is used in ≥5 components but `--font-mono` is never defined, so it falls through to Tailwind's **system** stack — SF Mono on macOS, Consolas on Windows | 🟠 Different glyph advance widths in numeric readouts headed for the README. Step 1.5a bundles Geist Mono Variable. |
| 28 | *(not noticed)* | No explicit `html { font-size: 16px }` — local-llm-foundry's **B2a** gate, the fix for its Windows-renders-smaller-than-macOS bug | 🟠 Added in Step 1.5a and asserted in Step 1.5. |
| 29 | "llama-monitor" used as a product name throughout | The project is renaming to **local-llm-foundry** for its 2.0 launch | 🟢 Renamed. `../llama-monitor/` **paths** left as-is — the source dir has not moved. |

### Revision 5 — measured against the live container, 2026-08-15

Everything below came out of running a real macOS↔Windows A/B against
`http://192.168.10.72:8318`, not from reading code. Two of these are corrections to
*this plan*.

| # | Plan said / assumed | Reality | Impact |
|---|---|---|---|
| 30 | *(this plan, Step 1.5)* `assertDeterministicFonts` builds `missingFaces` from `document.fonts.check('400 1rem "<family>"')` | `check()` returned **`true` on both platforms while Geist Mono was not loaded at all** — `[...document.fonts]` contained only `Geist Variable`. `check()` answers "can this string be rendered", and a fallback satisfies it | 🔴 **My own error, and the worst kind:** the assertion would have gone green in exactly the broken state it exists to catch. Rewritten to enumerate the `FontFaceSet` and compare family names. |
| 31 | *(this plan, #28)* Missing `html { font-size: 16px }` presented as an active divergence | Both platforms already report `16px` (Chromium's default) | 🟡 Reclassified ⚠️ — a hardening guard against a future `rem`/zoom regression, not a bug being fixed. Still worth adding; the framing was overstated. |
| 32 | `font-mono` divergence was a code-read inference | **Measured:** same CSS stack resolves to SF Mono (macOS) vs Consolas (Windows); a 20-char probe at 16px measures **192.66px vs 175.94px — 16.7px, 9.5%**. `font-sans` measured **165.92px on both** | 🟢 Confirms B1 is satisfied and isolates the whole cross-platform gap to mono. Step 1.5a is the fix. |
| 33 | `font-mono` used in "at least five components" | **At least 19 places** across `waveform/`, `StitchTimeline.tsx`, `audio/AudioDeck.tsx`, `OmniVoicePanel.tsx` and others — many paired with `tabular-nums` | 🟠 Blast radius is ~4× the estimate, and `tabular-nums` on a proportional-metrics fallback defeats the class outright. |
| 34 | *(not noticed)* | `capture.mjs` passed `headless: 'new'`. That value was **removed from Puppeteer**; the option is `boolean \| 'shell'`. macOS tolerated the stale string; Windows failed with `EBUSY … first_party_sets.db` / "browser is already running" on a *fresh* profile dir | 🔴 Windows capture was impossible. Fixed to `headless: !args.noAttach`. Any port of the harness must carry this. |
| 35 | *(not noticed)* | `capture.mjs`'s arg parser **silently ignores unknown flags** — `--help` runs a full capture | 🟡 Add real arg validation + `--help` during the Phase 1 port. |
| 36 | *(not noticed)* | `scenarioVoiceVariantList` **times out** waiting on `[data-testid="voice-card"]` against the fake server | 🟠 A pre-existing broken scenario. Must be fixed as part of the migration, not carried across. |
| 37 | Step 1.13 treats the risqué sample text as living only in voice `vd_000000000001`'s record | It was **also** the `REF_TEXT` env var in `~/docker/docker-agent/docker-compose.yml`'s persona-forge block | 🟢 **Resolved 2026-08-15.** Removed from compose and pushed (`3a475f4` on `nmorgowicz-org/docker-compose-config`) — pocket_tts ignores `REF_TEXT` entirely (`model.py:462` sets `REF_TEXT_SOURCE = "unused"`), so it was dead config. Container recreated and healthy with the var absent. **Step 1.13 still owns the voice-record copy.** |
| 38 | *(not noticed)* | Prod container is pinned to **v1.0.10**; the repo is at **1.0.11** | 🟡 Captures against prod are one release behind unless the dev override is active. Note it when promoting images. |
| 39 | *(this plan, revision 5)* Corrected `assertDeterministicFonts` to enumerate `[...document.fonts]` and compare families | Still wrong. `FontFaceSet` enumerates **declared** faces regardless of load state — Fontsource ships one face per unicode subset, so Geist Mono appeared as six entries, every one `status: 'unloaded'`, while the assertion counted the family as present | 🔴 **My own error, second iteration on the same assertion.** Now filters `face.status === 'loaded'`. Worth stating plainly: I twice wrote a font check that would have passed on an unloaded font. |
| 40 | *(not noticed)* | Font loading is **lazy** and `await document.fonts.ready` only settles what was already pending. Measuring a probe element immediately after appending it returns **fallback metrics** — my first post-fix run reported Windows mono at 175.94px and looked like the fix had failed | 🔴 Nearly caused a correct fix to be reverted. Must `await document.fonts.load(font, text)` per family *before* measuring. Folded into the Step 1.5 snippet. |
| 41 | *(dev loop)* `docker-compose.persona-forge-dev.yml` bind-mounted `frontend/dist` | `vite build` deletes and recreates `dist/`, swapping the directory inode. The container kept the **deleted** inode and served the build from before last — silently | 🟠 Caught only because the served asset hashes did not match the fresh build. Override now mounts the stable `frontend/` parent. This also invalidates my earlier "no restart needed" verification, which appended to `index.html` in place and so never exercised directory replacement. |

### Revisions 1–2 — the original handoff and plan

| # | Original said | Reality | Impact |
|---|---|---|---|
| 1 | README references `docs/screenshots/artifacts/...` | That directory is **gitignored** (`.gitignore:5`) | 🔴 **Critical.** Every README image would have been broken on GitHub. |
| 2 | Live instance has "no voices seeded" | **2 voices, 6 segments, `projects.json`** | 🔴 Invalidated the whole real-vs-fake split. |
| 3 | "Model loaded on startup — no cold-boot wait" | `model_loaded: false`; idle-unloads at 1800 s | 🔴 First capture would have timed out. Added Step 0.1. |
| 4 | Harness uses `puppeteer-core` | Uses **`puppeteer` ^25.3.0** | 🟠 Wrong premise for the API guidance. |
| 5 | Snippets use `page.$x()` | **Removed in Puppeteer v22**. Also `$x() \|\| $()` never falls back — `$x` returns an array, truthy when empty | 🔴 Both new scenarios would throw. |
| 6 | "Add the function to the scenarios list in `main()`" | `SCENARIOS` is an **object**; signature is `({ page, baseURL })`; screenshots go through the `screenshot()` helper | 🔴 Snippets were structurally incompatible. |
| 7 | Edit `fixtures/capture-data/voices.json`, fields `name`/`reference_text` | No such file. Per-voice `voices/vd_*/meta.json`, fields `description`/`sample_text` | 🔴 Executor would have searched for a nonexistent file and invented fields. |
| 8 | "Consider whether a `--scenario` flag exists" | It existed (`capture.mjs:436`), with `--list`, `--real`, `--target` | 🟠 Phase 2 replaced with deterministic per-scenario runs. |
| 9 | Create `SECURITY.md`; check `LICENSE` | **Both already exist** | 🟡 Two dead steps removed. |
| 10 | `sed -i '1s/.../'` | macOS BSD sed needs `sed -i ''` | 🟠 Four commands would have failed. |
| 11 | Phase 4 gate greps wider than its edits | Gate failed even on success | 🟠 Gate narrowed to match the work. |
| 12 | Delete the stale-branch line in the API ref | That line is the file's only description | 🟠 Would have destroyed content. |
| 13 | v1.0.10 throughout | Repo is at **1.0.11** | 🟡 Corrected. |
| 14 | Docs audit = one title fix | 3 more stale product names, **20 files** with the dead host, 2 filename-as-title H1s | 🟠 Phase 4 substantially expanded. |
| 15 | No docs index | Added `docs/README.md` + feedback step 4.4 | 🟢 Requested addition. |
| 16 | Hero pre-decided as `stitch-studio/assembly.png` | — | 🟢 Replaced with 4 candidates and a human checkpoint. |
| 17 | Single commit | — | 🟢 Split. |
| 18 | *(not noticed)* | `vd_000000000001` sample text is unsuitable for a public README | 🔴 Added Step 1.13 fix and Step 3.3 re-check. |
| 19 | Trailer `Co-Authored-By: Claude` | Repo convention is `Claude Opus 5` | 🟡 Corrected. |

## Appendix E — Port map

Reference: `/Users/nick/SCRIPTS/CLAUDE/llama-monitor/tests/ui/capture/`

| local-llm-foundry | persona-forge | Fidelity | Note |
|---|---|---|---|
| `harness/paths.mjs` | `capture/harness/paths.mjs` | **Adapt** | Keep tagging/category/`SCREENSHOTS_DIR`; drop the Go-binary config-dir constants; add `REMOTE_SERVER` |
| `harness/receipt.mjs` | `capture/harness/receipt.mjs` | **Verbatim** | Highest-value module in the port |
| `harness/source.mjs` | `capture/harness/source.mjs` | **Adapt** | Same precedence; sources become `fake` / `real-local` / `remote` |
| `harness/shot.mjs` | `capture/harness/shot.mjs` | **Adapt** | Keep `captureShot` hardening; merge in `lib/gif.mjs`; drop telemetry helpers |
| `harness/browser.mjs` | `capture/harness/browser.mjs` | **Adapt** | Rewrite the font contract; drop local-llm-foundry DOM helpers; add `gotoPage` |
| `harness/server.mjs` | `capture/harness/server.mjs` | **Merge** | Wrap existing `run-server.mjs` / `run-real-server.mjs`; port `findAvailablePort` + `waitForHttp` |
| `harness/fixtures.mjs` | `capture/harness/fixtures.mjs` | **Replace** | Role transfers; contents do not. Absorbs `lib/seed.mjs` |
| `harness/attach.mjs` | — | **Drop** | persona-forge has no auth shell or attach flow |
| `harness/chat.mjs`, `wizard.mjs` | — | **Drop** | No analogue |
| `index.mjs` | `capture/index.mjs` | **Adapt** | Same registry/`runCli` shape; persona-forge scenarios and flags |
| `cli-group.mjs` | `capture/cli-group.mjs` | **Near-verbatim** | Drop the temp-config-dir recreation between runs |
| `cli-manifest.mjs` | `capture/cli-manifest.mjs` | **Verbatim** | The INTENT-annotation regex is language-level, not project-level |
| `capture-receipt.test.mjs` | same | **Verbatim** | |
| `capture-manifest.test.mjs` | same | **Verbatim** | |
| `capture-platform.test.mjs` | `capture-source.test.mjs` | **Rewrite** | Platform gating → source-precedence assertions |

## Open questions

Record anything the executor cannot resolve here rather than guessing.

- **Hero image** — pending the Step 3.4 checkpoint.
- **`real-local` source viability** — `startRealServer` downloads weights and runs CPU inference. It
  is wired into `source.mjs` for completeness, but Phase 2 never uses it (`remote` is faster and has
  better data). If it turns out to be unusable in CI, mark it unimplemented in `IMPLEMENTED_SOURCES`
  rather than deleting the branch.
- **Cross-platform visual gate** — Step 1.5a closes the *mechanical* font gaps (bundled mono face,
  explicit 16px root), and Step 1.5 asserts them at capture time. What it does **not** do is
  local-llm-foundry's fourth gate: fresh same-commit Windows and macOS captures compared side by
  side for wrapping, clipping, overflow, and control-reachability defects. That surfaced real
  layout bugs there (e.g. `ed09606`, a flexbox text-splitting fault in help callouts). Doing it here
  needs a Windows host and is a follow-up. Note it in the Phase 6 commit body so it is not
  mistaken for done.
- **WCAG carry-over** — local-llm-foundry's Part A study found `#6b7280` (3.91:1) and `#64748b`
  (4.08:1) both fail AA for faint text and explicitly "must not be copied into production."
  persona-forge's palette is OKLCH and was not audited in this pass. Out of scope, worth a
  follow-up.
- **Doc illustration scope** — Step 4.4 caps new scenarios at three. More is a follow-up plan.
- **Historical `dockermisc1` references** — ~15 archived plan docs still name the old host. Left
  deliberately. An "archived" banner would be a separate pass.

# Luminous Instrument — Presentation Overhaul

Date: 2026-09-23 (revised same day after a code-truth audit, §"Baseline truth audit")
Status: **ACCEPTED FOR EXECUTION** — every decision closed at CP0a/CP0b and
the owner-selected Signal Crucible refinement: D1 **Obsidian**, D7 **Signal
Crucible**, D9 **S-c hybrid** signal palette.
Execution order, gates, and the step-by-step phase cards live in the
runbook `docs/plans/20260923-premium_ux_execution.md` and
`docs/plans/20260923-premium_ux_phase_cards.md`.
Branch: `feat/premium-audio-plugin-ux-20260923` (same branch as the interaction
plan; this doc is its visual sibling, sequenced **after** interaction Phases 0–5
land — except P0 look-dev, which runs before anything, see runbook).

## Goal statement

The interaction plan (`20260922-premium_audio_plugin_ux.md`) fixes how the app
*behaves*. This plan fixes how it *reads* and how its signal is *shown*:
Persona Forge should look and feel like a modern 2026 audio plugin that had
real time and care put into it — FabFilter-clean, Xfer-bright where signal
lives, UAD-solid in its materials — not a competent dark-mode web form with
audio in it. Same layout and IA everywhere; the change is the presentation
system and the signal-display layer sitting on top of it.

Owner direction (2026-09-23): **new visual system, same layout** ·
**FabFilter-clean aesthetic** · **confident motion design** · reference set
FabFilter / Xfer / UAD "and countless others".

## What "premium plugin" means here (grounded, not vibes)

Surveyed against FabFilter/Xfer/UAD-class surfaces plus our own README
screenshots. The delta is seven concrete things. Each maps to a workstream:

1. **Honest signal (the one nobody sees missing until it's there).** Every
   premium plugin's meters, playheads, and waveforms are *true* — they move at
   display rate and report real levels. Ours don't (see audit A1–A5): the
   LEVEL meter is a lookup, the playhead steps at ~4 Hz, every waveform is
   normalized to itself. Craft on top of untrue signal still reads as a toy.
   → P2, P4.
2. **Light, not paint.** Premium surfaces are dark *so that signal glows
   against them* — playheads, meters, active states emit light. Our dark
   surfaces are matte shadcn neutrals; nothing emits. → P1, P6, P7.
3. **One elevation language and one material.** Chrome → panel → well →
   readout, read instantly by depth, on slightly tinted (not dead-grey)
   neutrals with a consistent top-lit edge. Ours: one flat charcoal, two
   ad-hoc radii. → P1.
4. **A hero visualization.** FabFilter's analyzer, Serum's oscilloscope, RX's
   spectrogram: the plugin's *face* is a rich, true view of the sound. For a
   voice studio that face is a spectrogram — it shows sibilance, breath,
   pitch and formant structure a waveform can't. We ship a fake one (A6). → P3.
5. **Instrument controls.** Knobs/faders you drag, scroll, double-click to
   reset, with a value bubble while you move them. Plan A's S1/N1/N2 build the
   behavior; P5 gives it the instrument form. → P5.
6. **Numeric readouts are instruments.** Tabular figures, dBFS and ms units,
   parameter labels above values, exact timecodes. → P8.
7. **Motion is feedback; the storefront is finished.** Playheads sweep,
   meters fall ballistically, views transition; no lab-notebook copy or
   `v0.0.0-fake` in published media. → P7, P10, P11.

## Baseline truth audit (verified against code, 2026-09-23)

Every workstream below cites these. Line numbers are at `753da87`.

| # | Finding | Evidence |
| --- | --- | --- |
| A1 | **LEVEL meter is not a meter.** `currentLevel` is the normalized max-abs peak bucket at the playhead index; `peakLevel` is the max of the whole file (static). Readout is `%`, not dBFS. | `components/audio/AudioDeck.tsx:95-101`, `LevelMeter.tsx:22-29` |
| A2 | **Playhead and meter step at ~4 Hz.** `progress` is set only from `onTimeUpdate` (browser fires ~4×/s); no RAF clock outside Stitch. | `AudioDeck.tsx:196-204`; `VariantCompare.tsx` (`onTimeUpdate`); RAF exists only in `hooks/useStitchTransport.ts` |
| A3 | **Every waveform is normalized to its own maximum.** In the Stitch timeline and A/B lanes a quiet clip draws as tall as a loud one — the loudness mismatch between stitched segments (the single most useful thing to see) is invisible. | `lib/waveform.ts:32-33` (`p / overallMax`), shared by every consumer via `computePeaks`/analysis cache |
| A4 | **Resolution capped at 120 max-abs buckets regardless of lane width**, no RMS body. | `lib/waveform.ts:11-15, 17-31` |
| A5 | **Deck waveform is 64–120 animated DOM nodes** (`motion.div` per bar, per-bar spring with index delay, per-bar `drop-shadow` filter) re-rendered on every `timeupdate`; a flat fake `Array(64).fill(0.15)` renders while loading. `WaveformLane` already proves the right approach (canvas, DPR-aware). | `components/Waveform.tsx:123-147`; `AudioDeck.tsx:211`; `waveform/WaveformLane.tsx:29-39` |
| A6 | **`SpectralAccent` is not spectral and fakes data**: it re-draws the peak array as cells, and with no peaks renders a synthetic sine. | `components/audio/SpectralAccent.tsx:10` |
| A7 | **No exclusive audition.** Five independent `<audio>` owners (+ AlignmentCompare decode-play) can sound at once; starting one never stops another. | `<audio>` in `StitchTimeline.tsx` (2), `VariantCompare.tsx`, `AudioDeck.tsx`, `AlignmentCompare.tsx`; no coordination symbol anywhere |
| A8 | **Neutrals are stock shadcn achromatic greys** (`oklch(L 0 0)`); only `--surface-1` carries a tint (hue 285). | `index.css:161-201`, `42`, `184` |
| A9 | **Brand CTA is hard-coded cyan in all four accent themes** (`--brand-from/to/glow`), and the signal palette is a separate fixed cyan→magenta — two unrelated "brand" colors plus the theme accent, with no doctrine. | `index.css:38-40`; `lib/waveform.ts` `waveformBarColor` |
| A10 | **Radius is ad hoc and generic**: 38× `rounded-lg`, 29× `rounded-xl`, 2× `rounded-2xl` across components; `--radius` is the shadcn default `0.625rem`. | `grep` count 2026-09-23; `index.css:51` |
| A11 | **There is no Persona Forge mark in the product.** The sidebar tile is a stock lucide `AudioLines` icon, and `assets/brand/exports/persona-forge-mark.svg` (also `frontend/public/favicon.svg`, `src/persona_forge/static/favicon.svg`) is **byte-identical to the stock Vite scaffold favicon**. The owner rejected the interim lightning-centered concepts and selected the Signal Crucible family under `assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/`. | `components/AppShell.tsx:371-372`; md5 `7e840862…` shared by all three repo copies; owner selection 2026-09-23 |

Nothing above needs a backend change. A1–A6 are the "honest signal" gap;
A8–A11 are the "material" gap.

## Doctrines (binding for every workstream)

- **Honest signal.** Nothing renders as audio data unless it is audio data.
  No synthetic fallbacks, no flat placeholder bars — loading is a designed
  skeleton state (P9), never fake signal. Meters report dBFS computed from the
  decoded buffer.
- **Analysis is allowed; processing is not.** The standing "no DSP
  changes" constraint covers what the user *hears*. Offline analysis of an
  already-decoded buffer (envelopes, STFT, loudness) changes no output and is
  in scope. Nothing is inserted into the playback path (no
  `createMediaElementSource`), so element playback, CORS, and the existing
  audio graph are untouched.
- **Two color roles, never mixed.** *Accent* (theme `--primary`, 4 themes)
  = selection, focus, chrome glow, and the CTA (D3 = follow accent). *Signal*
  (one fixed palette — the S-c hybrid chosen at D9, specified in P1 "Signal
  constants") = waveforms, meters, spectrogram,
  playhead. Signal never re-skins with the theme — like a plugin whose
  analyzer stays readable under any skin. Semantic status tokens
  (`DESIGN_SYSTEM.md`) stay a third, separate role.
- **Brand is the north star, not wallpaper.** Signal Crucible is the selected
  identity: multiple blue/violet voice fields converge through open Obsidian
  arcs at one amber calibration line and leave as one coherent pale waveform.
  The UI borrows this transformation grammar, glow physics, and material
  restraint. Full artwork appears only where nothing is being operated:
  startup state (P9), empty states (P9), README, and social media (P11).
  Never place the artwork behind working controls.
- **Draw at display rate without React.** Anything that moves per frame
  (playhead, meters, scrolling spectrogram cursor) draws imperatively into a
  canvas from a RAF loop reading `audio.currentTime`. No React commit per
  frame.

## Non-goals / constraints (carry forward)

- Same layout and IA on every page. No page restructuring, no new routes.
  Control *form* may change inside its existing slot (P5, owner-gated).
- No new frontend dependencies. `motion/react` covers motion; canvas, Web
  Workers (native Vite `new Worker(new URL(...), { type: 'module' })`) and
  `AudioContext.decodeAudioData` cover rendering and analysis.
- No light theme. Dark-only; all four accent themes keep working.
- No backend contract changes, no change to what the user hears, no
  undo/history (Plan A T2 remains the only, owner-gated exception).
- `docs/dev/DESIGN_SYSTEM.md` stays binding; the oxlint
  `no-raw-status-colors` guard keeps passing. New tokens are documented there
  in the phase that adds them.
- Reduced motion: every animation ships a `prefers-reduced-motion` path
  (static end-state). Meters under reduced motion drop ballistic *easing* but
  still show true level (it's data, not decoration).
- **Performance budget (every phase that renders signal):** during playback
  on the `segment-browser-scale` and `stitch-assembly` scenarios — zero
  `longtask` entries > 50 ms (PerformanceObserver in the phase spec), no React
  commit per animation frame on deck/lane components, spectrogram STFT off the
  main thread.

## Workstreams (one phase = one commit; the whole arc ships as one PR at P12)

### P0 — Look-dev + brand board (zero production code; closes runbook CP0b)

Pick the look *before* eleven phases of code commit to it. A capture scenario
injects candidate token CSS into the real app via `page.addStyleTag` (no
production edit) and shoots the four hero surfaces — Speak (after generate),
Stitch Studio (assembly), Voice Design (panel), Voice Edit (prosody A/B) —
in two accent themes (`violet`, `amber`) per candidate.

Candidates (each is only a token set — neutrals ramp, material recipe, radius
scale; see P1 for the token list):

- **L1 "Graphite"** — cool blue-grey neutrals (hue ~255, chroma ≤ 0.012),
  soft top-lit edges, 6/10 px radii. Closest to FabFilter.
- **L2 "Obsidian"** — near-black neutrals (L ≈ 0.12), higher-contrast signal,
  tighter 4/8 px radii, stronger glow. Closest to Xfer.
- **L3 "Machined"** — warmer neutrals (hue ~60, chroma ≤ 0.01), visible bevel
  highlights and inset wells. Closest to UAD, without skeuomorphic textures.
- **L4 "Forge"** (added after CP0a, derived from the Option E hero) — deep
  indigo neutrals (hue ~275, chroma ~0.02–0.03, L 0.11–0.24), violet default
  accent (already `DEFAULT_THEME = 'violet'` in `lib/theme.ts`), glow
  strongest of the four, 6/10 px radii. The on-brand candidate; the board
  must show it with the amber accent too, to prove the tinted neutrals don't
  fight non-violet themes.

**Signal palette variants (decision D9)** — shown on a dedicated signal board
(the app's palette is compiled into `waveformBarColor`, so CSS injection
cannot swap it without a production edit). The board decodes a real fixture
voice and draws the P2/P3/P4 designs — true-scale waveform, STFT
spectrogram, dBFS meter with peak-hold — on every look's surfaces, with:
S-a the current cyan→magenta `waveformBarColor` grammar, and S-b a
brand-aligned ramp taken from the hero's ribbons (electric blue → violet →
pale lavender `#ede6ff` at peaks). Signal stays fixed across accents either
way (doctrine); D9 only chooses which fixed palette.

**Brand direction (decision D7).** The current product mark is the Vite
favicon and cannot stay. P0 originally tested three ring-based marks and an
Option E lightning hero. The owner later rejected the lightning-centered
identity and selected **Signal Crucible**. Its concept-stage SVG set is:

- `hero-v2/finalists/signal-crucible/svg/mark.svg` for 48 px and above.
- `hero-v2/finalists/signal-crucible/svg/mark-small.svg` for compact UI use.
- `hero-v2/finalists/signal-crucible/svg/favicon.svg` for favicon/app-icon use.
- `hero-v2/finalists/signal-crucible/svg/lockup.svg` for horizontal brand use.

The identity uses open Obsidian arcs, converging voice fields, one coherent
output waveform, and an amber calibration point. It contains no lightning.

**Acceptance:** 4 looks × 4 surfaces × 2 themes (violet, amber) shot on the
real app via token injection; per-look and accent-check contact sheets; the
signal board (4 looks × 2 palettes); the brand board (marks + context); owner
records D1, D7, D9 in the runbook ledger (CP0b).
**Files:** `tests/ui/capture/lookdev/{common,graphite,obsidian,machined,forge}.css`,
`tests/ui/capture/lookdev/pages.mjs`, scenarios
`tests/ui/capture/scenarios/lookdev/{board,brand}.mjs` (registered as
`lookdev-board` / `lookdev-brand`). The selected public assets live under
`assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/`.
Run: `node tests/ui/capture/index.mjs --scenario lookdev-board --source fake`
(and `lookdev-brand`); outputs land in `docs/screenshots/artifacts/lookdev/`.
Commit: `test(ui): look-dev and brand-mark capture boards`.

### P1 — Material + token layer (the foundation everything sits on)

Implement the D1 look (**Obsidian**) as tokens in `frontend/src/index.css` and a
single `frontend/src/lib/motion.ts` module. No component restyle yet —
changing the `.dark` neutral values is visible app-wide by design; the new
utilities stay unused until P6.

- **Neutral ramp (fixes A8):** copy the exact values from
  `tests/ui/capture/lookdev/obsidian.css` (the look the owner approved on the
  board) into the `.dark` block: `--background`, `--card`, `--popover`,
  `--secondary`, `--muted`, `--accent`, `--muted-foreground`, `--surface-1`,
  `--sidebar`, `--sidebar-accent`, `--border`, `--sidebar-border`, `--input`,
  `--radius: 0.3rem`. Add `--well` (`oklch(0.1 0.004 270)`) for inset
  surfaces.
- **Material recipe:** `.panel-1 / .panel-2 / .well` utilities built from the
  Obsidian `--ld-panel-shadow` / `--ld-well-shadow` values in
  `obsidian.css` (renamed `--shadow-panel` / `--shadow-well`). One recipe,
  used everywhere. `tests/ui/capture/lookdev/common.css` shows where each
  maps onto today's classes; it is a board-only shim — do **not** copy its
  class-hijacking selectors (`.bg-card { box-shadow }`) into `index.css`.
- **Glow:** `--glow-accent` / `.glow-active` keyed off `--primary`;
  `--glow-signal` keyed off the fixed signal palette.
- **Radius scale (fixes A10):** `--radius-well`, `--radius-control`,
  `--radius-panel` with Tailwind aliases; P6 migrates the 69 ad-hoc usages.
- **Type scale:** `.micro-label` (uppercase, tracked, 10–11 px, muted),
  `.readout` (Geist Mono, `tabular-nums`, unit span styling), `.display`
  (page title). Geist stays — already self-hosted for metric stability
  (`index.css:107-112`).
- **Focus:** focus-visible ring becomes an accent glow (keyboard users get
  the same "lit" feedback as pointer users).
- **Signal constants (D9 = S-c hybrid):** new `lib/signal.ts` is the single
  source for every signal color. Exact definition (verified on the board):
  - `SIGNAL_RAMP` OKLCH stops `(t, L, C, H)`: `(0, 0.72, 0.13, 235)` blue →
    `(0.45, 0.64, 0.22, 285)` violet → `(0.8, 0.70, 0.21, 332)` hot magenta →
    `(1, 0.95, 0.04, 330)` near-white. Linear interpolation per channel.
  - `signalColor(t, played)`: played = `oklch(L C H / 0.6 + 0.4t)`;
    unplayed = `oklch(L−0.2 0.6C H / 0.32 + 0.2t)`.
  - `SIGNAL_PLAYHEAD = 'hsl(38 95% 62%)'` (unchanged amber;
    `WAVEFORM_PLAYHEAD_COLOR` becomes an alias of it).
  - `SPECTRO_STOPS = ['#05040f', 'oklch(0.26 0.1 275)', 'oklch(0.58 0.16 245)', 'oklch(0.62 0.23 290)', 'oklch(0.7 0.22 335)', 'oklch(0.97 0.03 330)']`
    (evenly spaced); spectrogram dB window −72…−12 dB.
  - `heat(amp)` = clamp((20·log10(amp) + 48) / 48, 0, 1): color intensity
    follows dBFS, never linear amplitude (linear never reaches the hot end
    for speech peaking at −6 dBFS).
  - Meter scale −60…0 dBFS, ticks `[-48,-36,-24,-18,-12,-6,-3,0]`, clip at
    ≥ −0.1 dBFS.
  - `waveformBarColor(peak, played)` keeps its name and signature but
    delegates to `signalColor(peak, played)` in P1; P2 switches callers to
    `signalColor(heat(absAmp), played)`.
  - Reference renderer: `renderSignalBoard` in
    `tests/ui/capture/lookdev/pages.mjs` (palette `c`).
- **Motion tokens:** `lib/motion.ts` exports named durations, easings and
  springs (`snappy`, `settle`, `meterFall`) + `useReducedMotionSafe()`;
  mirrored as CSS vars for CSS transitions.
- **Brand CTA (fixes A9, D3 = follow accent):** `--brand-from/to/glow` are
  derived from `--primary` with relative color syntax
  (`oklch(from var(--primary) …)`), so the Generate button is violet in
  violet, amber in amber. `.btn-brand` keeps its API; no component changes.

**Acceptance:** tokens render correctly under all four themes (capture:
`lookdev-board` Obsidian shots vs the real P1 build — neutrals match);
`waveformBarColor` output changed to S-c; lint + oxlint guard clean;
`DESIGN_SYSTEM.md` gains a "Materials, signal, motion" section.
**Files:** `frontend/src/index.css`, `lib/motion.ts`, `lib/signal.ts`,
`docs/dev/DESIGN_SYSTEM.md`.
Commit: `feat(ui): luminous material, signal, and motion token layer`.

### P2 — One true waveform renderer (fixes A3, A4, A5)

Replace the DOM-bar `Waveform.tsx` drawing with the canvas approach
`WaveformLane` already proves, as one shared renderer.

- **Multi-resolution envelope:** at decode, compute a min/max/RMS pyramid
  (e.g. 256-sample base, ×4 levels) **in absolute sample units** (not
  normalized). Stored *additively* in the existing analysis cache entry under
  the unchanged `<kind>:<persistent-id>:<revision>` key (locked contract
  honored: new fields only; `peaks` stays for any consumer not yet migrated).
- **Density follows pixels:** buckets = lane CSS width × DPR ÷ bar pitch,
  picked from the pyramid — zoom never re-decodes.
- **Two-tone silhouette:** mirrored peak outline + brighter RMS body (the
  pro-DAW look), colored `signalColor(heat(amp) * 0.7, played)` for the peak
  outline and `signalColor(min(1, heat(rms) * 1.15), played)` for the body —
  exactly as the P0 reference renderer draws it; played region tinted.
- **Gain truth in multi-clip views:** Stitch timeline, A/B lanes, and
  variant compare share one vertical scale across all clips on screen, so a
  quiet segment *looks* quiet. Single-clip views may auto-fit but show a
  small `−x dBFS` peak readout so the fit is never mistaken for level.
- **Playhead:** drawn in the same canvas pass from a RAF media clock
  (`hooks/useMediaClock.ts` — reads `audio.currentTime` per frame, no React
  state per frame); fixes A2 for every waveform consumer.
- **Loading:** designed skeleton (P9 style), never `Array(64).fill(0.15)`.
- **Delete** the per-bar `motion.div`/spring/`drop-shadow` rendering.

**Acceptance:** every waveform consumer (Speak deck, VoiceDesign/OmniVoice
decks, `StitchClipCard`, `WaveformLane`, A/B + `VariantCompare`,
`RegionEditor`, `AlignmentCompare`) draws through the shared renderer;
Playwright asserts a quieter fixture clip renders shorter than a louder one on
the Stitch timeline; playhead position sampled at two RAF ticks < 50 ms apart
differs (proves display-rate motion); performance budget met; existing
region-select/seek specs unregressed.
**Files:** `lib/waveform.ts`, new `components/waveform/WaveformCanvas.tsx`,
new `hooks/useMediaClock.ts`, `components/Waveform.tsx` (becomes a thin
wrapper or is removed with callers migrated), `WaveformLane.tsx`, consumers
listed above.
Commit: `feat(ui): true-scale hi-res waveform renderer with RAF playhead`.

### P3 — Spectrogram view (the hero visualization; fixes A6; CP0 decision D4)

Real STFT spectrogram of any decoded clip, rendered to canvas.

- **Compute:** Hann-windowed FFT (1024, hop 256; radix-2 implementation in
  ~80 lines, no dependency) in a module Web Worker; decoded
  `Float32Array` transferred from the main thread. Budget: a 30 s mono clip
  at 24 kHz ≈ 2.8k frames — well under 300 ms off-thread.
- **Render:** log-frequency axis (voice-relevant 50 Hz–12 kHz), dB magnitude
  mapped through a signal-palette colormap (black → cyan → magenta → white,
  the waveform grammar extended), drawn once to an offscreen canvas and
  blitted; playhead shares P2's media clock. Hover shows `time · Hz · dB`.
- **Cache:** additive key `spectrogram:<kind>:<persistent-id>:<revision>`
  in the same LRU (count budget respected).
- **Where:** a `Wave | Spectrum` view toggle on stacked `AudioDeck`
  (Speak result, Voice Design results) and on Voice Edit A/B lanes. Retires
  `SpectralAccent` entirely.

**Acceptance:** fixture tone at a known frequency renders its band at the
correct axis position (Playwright reads the canvas pixel column); toggle
persists per session; STFT runs off-thread (no long task); `SpectralAccent`
and its synthetic fallback deleted.
**Files:** new `lib/stft.worker.ts`, `lib/spectrogram.ts`,
`components/waveform/SpectrogramCanvas.tsx`; `AudioDeck.tsx`,
`VariantCompare.tsx`/Voice Edit lanes; delete `audio/SpectralAccent.tsx`.
Commit: `feat(ui): spectrogram view for decoded clips`.

### P4 — Instrument transport + truthful metering (fixes A1, A2)

One transport strip everywhere audio plays, with a real meter.

- **Meter:** driven by P2's absolute envelope sampled at the media clock
  every frame. Scale −60…0 dBFS (ticks −48/−36/−24/−18/−12/−6/−3/0),
  instant attack, ballistic fall (~20 dB per 1.5 s), peak-hold line 1.5 s
  then fall, **clip LED** latched at ≥ −0.1 dBFS sample peak (click to
  clear). Readouts: live dBFS, held peak dBFS. Signal palette only.
- **Strip layout:** grouped transport cluster (play/restart/loop), meter,
  labeled speed (P5 control once shipped), trailing cluster (download, seed)
  — ≥ 32 px hit targets, same arrangement in every deck.
- **Clip stats (D5 accepted):** file peak dBFS, RMS dBFS, and integrated
  loudness (ITU-R BS.1770-4 LUFS: K-weighting biquads + 400 ms gated blocks,
  run offline on the decoded buffer in the P3 worker — analysis only) in the
  deck header readout.

**Acceptance:** a fixture with a known −6 dBFS peak reads −6.0 ± 0.1 on the
held-peak readout; a mono 997 Hz sine at −20 dBFS peak reads −23.0 ± 0.1
LUFS (BS.1770: sine mean-square −3.01 dB, K-weighting gain at 997 Hz cancels
the −0.691 offset); a fixture with a full-scale sample lights the clip LED;
meter bar height changes between consecutive frames during playback; every
deck instance (Speak, library rows via `MiniAudioDeck`, candidate audition,
Voice Design) uses the same strip; performance budget met.
**Files:** `components/audio/AudioDeck.tsx`, `MiniAudioDeck.tsx`,
`LevelMeter.tsx` (rebuilt on canvas), `AudioPlayer.tsx`,
`OmniVoice/ClipPlayer.tsx`, `lib/signal.ts`.
Commit: `feat(ui): instrument transport strip with true dBFS metering`.

### P5 — Instrument control primitives (D2 accepted)

Give Plan A's drag-scrub behavior (S1 + N1 + N2) its instrument form.

- **`Knob`** — SVG arc (track, value arc in accent, pointer), vertical drag
  via `useDragScrubValue` (same hook as S1: Shift fine, Alt bypass snap,
  double-click reset, wheel nudge, click-to-type), **value bubble** while
  dragging/hovering, `role="slider"` + full keyboard.
- **`Fader`** — the linear sibling for long-range parameters.
- **Placement (same slots, new form):** Stitch DSP controls (`SliderField`,
  `StitchTimeline.tsx:527-552`) become a knob row; AudioDeck speed becomes a
  compact knob; trim/fade/gap keep their numeric-field form (they are
  timecodes, not parameters).

**Acceptance:** knob and fader pass the same Playwright contract as S1
controls (drag, Shift-fine, double-click reset, wheel, typed entry, keyboard);
value bubble visible during drag; no page layout shift (capture diff).
**Files:** new `components/ui/knob.tsx`, `components/ui/fader.tsx`;
`StitchTimeline.tsx` (DSP row), `AudioDeck.tsx` (speed).
Commit: `feat(ui): knob and fader instrument controls`.

### P6 — App chrome depth (sidebar, headers, banners, status, info strip, brand)

- Sidebar active item: accent glow instead of flat fill; radius migration
  (A10) across the shell.
- **One header grammar:** every page opens with the same plugin-style title
  band — `.display` title, `.micro-label` context readouts, primary action
  aligned right. Same content as today, one form.
- **Banner convergence:** `SwapBanner`, `HealthStatusBanner`,
  `UpdateAvailableBanner` → `.status-badge` tones, one component shape.
- **Info view (CP0 decision D6):** hovering or focusing any control with a
  `data-help` string shows its explanation in `ActivityStatusBar` (the
  Ableton/FabFilter help-strip idiom). This is also where Plan A V2's genuine
  warnings (e.g. the high-pitch tinniness note) live, instead of paragraphs.
- **Brand mark (D7 = Signal Crucible):** copy
  `assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/svg/favicon.svg`
  over `frontend/public/favicon.svg` and
  `src/persona_forge/static/favicon.svg`; copy the adjacent `mark.svg` over
  `assets/brand/exports/persona-forge-mark.svg`. In `AppShell.tsx:371-372`,
  replace the `AudioLines` gradient tile with `<img src="/favicon.svg">` at
  24 px inside the existing 32 px tile. Rewrite `assets/brand/README.md` so
  Signal Crucible is the canonical identity. Before wiring, verify the SVGs
  at 16/24/32/48 px on light and dark backgrounds without relying on glow.

**Acceptance:** one header, banner, and status grammar across every page;
info view announces via the same live region as Plan A N3; shell captures at
all four themes.
**Files:** `components/AppShell.tsx`, banner components,
`components/ui/ActivityStatusBar.tsx`, page headers, the three favicon
copies, `assets/brand/README.md`.
Commit: `feat(ui): chrome depth, header grammar, info strip, and brand mark`.

### P7 — Motion as feedback

Using `lib/motion.ts` tokens only: view/section enter transitions,
`AnimatePresence` on dialogs/menus/popovers, `layout` animation on clip
reorder (today reorder jumps), spring tap states extended from chips to
transport buttons, playhead + meter glow (motion that reads as light).
Motion animates `transform`/`opacity` only; never per-bar or per-row node
counts that scale with data.

**Acceptance:** reorder animates; dialogs/menus transition; reduced-motion
path verified per surface via emulation in the spec; performance budget met.
**Files:** page shells, `StitchTimeline.tsx` (reorder), dialog/menu
primitives, transport buttons.
Commit: `feat(ui): motion-as-feedback system`.

### P8 — Readout typography + labeled controls (Speak first)

`.readout` on every time/level value; dropdowns get `.micro-label` parameter
labels above the control (VOICE / LANGUAGE / the `Off` control's actual
function) instead of value-as-label; icon buttons reuse the `tooltip=`
pattern (`AudioDeck.tsx:255`). Absorbs Plan A V3; extends S4's grammar.

**Acceptance:** no unlabeled select on Speak, Voice Design, or Voice Edit;
every numeric readout tabular with a visible unit (`GAP 520` → `520 ms`).
**Files:** `pages/SpeakPage.tsx`, Voice Design / Voice Edit selects.
Commit: `feat(ui): instrument readout typography`.

### P9 — Async states with craft

Crafted empty → working → done/error states everywhere. Determinate progress
wherever the backend reports it (Speak already polls
`getGenerateJobProgress` with `progress_pct` + ETA — surface a real readout),
skeletons in the material recipe (these also replace P2's former fake
placeholder), `role="status"`/`progressbar` semantics. Absorbs Plan A N3/N4.
A designed startup state for the initial-load 503 window uses the Signal
Crucible `svg/mark.svg` at 72 px over a dimmed copy of
`finalists/signal-crucible/startup-field.png`, with a determinate or stepped
model-load readout. Empty states use the open-arc and converging-wave motif as
a quiet line illustration with one next action. Never put full artwork behind
controls.

**Acceptance:** every async surface has all four states; progress
determinate wherever measured; startup state captured.
**Files:** per-surface, plus shared `components/ui/` primitives
(`toast.tsx`/announcer, `progress.tsx` on the installed `radix-ui` export).
Commit: `feat(ui): crafted async states`.

### P10 — Residue sweep + craft verdict

Sweep prototype residue (Plan A V2: `AccentChipPanel.tsx:104-125` lab copy →
info view/contextual hints; `v0.0.0-fake` chrome; placeholder voice names).
Capture every hero surface for the **premium scorecard** (runbook §5) —
verdict only; publishing happens once, in P11.

**Acceptance:** residue checklist closed; scorecard fully PASS/N-A, reviewed
at runbook Checkpoint 2.
Commit: `feat(ui): residue sweep and craft verdict`.

### P11 — Reference docs, walkthroughs, and full media refresh

The **single** publishing re-shoot. Docs describe the product P0–P10 built.

- **Re-take everything published:** all 8 README PNGs (`speak-generate`,
  `hero-voice-design`, `prosody-adjustment`, `stitch-assembly`, `voice-edit`
  workspace, `readiness-states`, `voice-edit` prosody-ab,
  `omnivoice-audition` candidates) **plus** both README GIFs
  (`omnivoice-audition-gif`, `design-to-stitch-gif`) via the existing capture
  scenarios, and one **new** GIF showing the signal layer (meter + playhead +
  spectrogram toggle during playback). The README gains the selected Signal
  Crucible `app-hero.png` as its top banner. The optimized
  `github-social.jpg` (1280×640 and below 1 MB) becomes the GitHub social
  preview.
- **Illustrate the reference docs:** captioned screenshots per major flow
  (Speak → Voice Design → Audition → Stitch → Voice Edit) in
  `docs/architecture/PERSONA_FORGE_STUDIO.md`, `VOICE_DESIGN.md`,
  `OMNIVOICE_REFERENCE.md`, `STUDIO_LIBRARIES.md`, `docs/HOW_TO_RUN.md`,
  `docs/README.md`; a controls reference (knob/fader gestures, keymap, meter
  scale) in `FRONTEND_OVERVIEW.md`. New images under `docs/screenshots/`.
- **Capability audit:** walk each reference doc against the shipped UI —
  drag-scrub/zoom/loop/context-menu (Plan A), metering/spectrogram/knobs/
  motion (this plan), current engine names, routes, nav labels. Rewrite
  anything describing pre-overhaul behavior.
- **Walkthrough check:** clone/design → audition → stitch → edit → generate
  over API reads start-to-finish without gaps.

**Acceptance:** `python scripts/validate_repo.py` clean; every image the
README and touched docs embed was regenerated in P11; a reviewer can follow
the walkthrough cold.
**Files:** `README.md`, `docs/architecture/*.md`, `docs/HOW_TO_RUN.md`,
`docs/README.md`, `docs/screenshots/**`, `tests/ui/capture/scenarios/**`
(dwell/selector fixes only, plus the new signal GIF scenario).
Commit: `docs: refresh reference docs, walkthroughs, and published media`.

### P12 — Archive planning docs and open the PR

1. Both plan ledgers and the runbook ledger complete — every executed phase
   PASS with its commit; every CP0 decision recorded.
2. Move `20260922-premium_audio_plugin_ux.md`, this file,
   `20260923-premium_ux_execution.md`,
   `20260923-premium_ux_phase_cards.md`, and
   `20260923-native_codex_hero_generation_handoff.md` to
   `docs/archive/luminous-instrument/` (convention:
   `docs/archive/stitch-studio/`), stamped with final hashes. Active
   `docs/plans/` is left clean.
3. Final preflight + `git diff --check`; open the PR with the Release Please
   override block (AGENTS.md) — one entry per phase commit; PR body carries
   the scorecard and the capture before/after index.

**Acceptance:** `docs/plans/` holds nothing for this arc; PR body carries the
override block, scorecard, and capture index.
Commit: `chore: archive luminous-instrument planning docs`.

## Execution discipline

Owned by the runbook (`20260923-premium_ux_execution.md` §3), which applies
Plan A §2 verbatim to every phase here. Sequencing: P0 at Checkpoint 0;
P1–P12 after interaction Phases 0–5 and Checkpoint 1. P1 first — everything
consumes its tokens; P2 before P3/P4 — both consume its envelope and clock.

## Phase ledger

| Phase | Gate result | Commit | Notes |
| --- | --- | --- | --- |
| P0 look-dev + brand board | PASS 2026-09-23 (38 + 2 outputs, receipts green; capture self-tests 15/15) | | D1 = Obsidian, D7 refined to Signal Crucible, D9 = S-c hybrid |
| P1 tokens | PASS 2026-09-23 (tokens 3/3, suite 124/0/1 skipped) | a9282ce | D3 = follow accent; neutrals match the board by pixel count |
| P2 waveform renderer | PASS 2026-09-23 (waveform-truth 4/4, suite 128/0/1 skipped, 0 long tasks > 50 ms) | 1e78662 | fixes A2, A3, A4, A5; one canvas renderer, absolute-unit envelope, shared scale |
| P3 spectrogram | PASS 2026-09-23 (spectrogram 3/3, suite 131/0/1 skipped, 0 long tasks > 50 ms) | 073ecaa | fixes A6; real STFT in a worker, log axis, SpectralAccent deleted |
| P4 transport + metering | | | D5 = accepted (LUFS) |
| P5 knob/fader | | | D2 = accepted |
| P6 chrome | | | D6 = accepted; D7 from P0 |
| P7 motion | | | |
| P8 readouts | | | |
| P9 async states | | | |
| P10 residue + verdict | | | |
| P11 docs + media | | | |
| P12 archive + PR | | | |

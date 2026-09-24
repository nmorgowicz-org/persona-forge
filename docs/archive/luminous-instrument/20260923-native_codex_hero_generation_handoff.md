# Native Codex Handoff — Persona Forge Hero Exploration

> **Archived 2026-09-24.** Executed to completion on branch
> `feat/premium-audio-plugin-ux-20260923`; the last phase commit before archiving is `e32498e`,
> and the per-phase results (gate, commit, evidence) are recorded in the runbook's §7 ledger.
> Kept for provenance — this is not a live plan; active plans live in `docs/plans/`.

Date: 2026-09-23
Status: Exploration complete — Signal Crucible selected; production integration pending

## Reason for existence

Use native Codex with internal GPT image generation to create a new Persona Forge hero-art family. The prior lightning-centered identity is rejected. Do not implement the product overhaul during this task.

## Repository context

Work in:

`/Users/nick/SCRIPTS/CLAUDE/persona-forge`

Read these sources before generation:

1. `docs/archive/luminous-instrument/20260923-luminous_instrument_redesign.md`
2. `docs/archive/luminous-instrument/20260923-premium_ux_execution.md`
3. `docs/screenshots/artifacts/lookdev/lookdev-board--neutral--signal-palettes.png`
4. `docs/screenshots/artifacts/lookdev/lookdev-board--neutral--sheet-obsidian.png`
5. `assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/app-hero.png`
6. `assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/svg/mark.svg`

The rejected Option E and ring-plus-spark sources remain local and ignored.

## Approved direction

The product identity must communicate:

- voice creation
- voice transformation
- persona and individuality
- precision audio tooling
- forging many signals into one coherent voice

The art system must use:

- an Obsidian near-black material field
- electric blue, violet, and restrained hot magenta signal light
- amber only for precise calibration or focus
- controlled glow instead of broad neon bloom
- technically credible waveform, formant, or spectral structures
- generous negative space
- a premium professional-audio character

The art must not use:

- lightning bolts or electrical sparks
- microphones
- human heads, profiles, or portraits
- play buttons
- brains or generic AI symbols
- fake application interfaces
- circuit-board patterns
- cyberpunk cities
- decorative text generated inside the image
- watermarks

## Required output set

Create five clearly different directions. Generate at least three 16:9 candidates per direction before selecting one.

Save selected masters in:

`assets/brand/concepts/persona-forge/hero-v2/masters/`

Use these filenames:

- `voice-aperture.png`
- `formant-forge.png`
- `persona-bloom.png`
- `signal-crucible.png`
- `quiet-instrument.png`

Keep exploratory outputs local. Publish only the owner-selected finalist family.

## Direction 1 — Voice Aperture

### Intent

Show several distinct voice fields entering a precision aperture and leaving as one coherent voice.

### Generation prompt

> Premium abstract hero artwork for a professional voice synthesis and voice design application. A precise aperture sits on the right third of a wide Obsidian composition. Three separated matte-black ceramic arcs form the aperture around an empty dark center. Several delicate blue and violet voice-formant ribbons approach from the left at different heights. The ribbons converge through the aperture and leave to the right as one coherent speech waveform. Use selective hot magenta only at high-energy details. Add one tiny amber calibration marker. Use controlled signal glow, subtle top-lit material edges, technically credible acoustic geometry, and generous uninterrupted dark space in the upper-left. Pure abstract artwork. No text, letters, numbers, lightning, speaker cone, microphone, person, face, play symbol, circuit pattern, or watermark.

### Selection test

Reject any result where the aperture resembles a loudspeaker, camera lens, portal, or power button.

## Direction 2 — Formant Forge

### Intent

Make vocal formants the hero. Show diffuse voice structure becoming ordered and legible.

### Generation prompt

> Premium scientific hero artwork for a professional voice-design instrument. A wide human-voice spectrogram field crosses a near-black Obsidian background. Diffuse layered formant contours enter from the left. Five thin black-glass acoustic vanes shape them near the right third. The contours leave as clean, ordered harmonic bands and a precise speech waveform. Use a blue-to-violet-to-magenta intensity map with monotonically increasing brightness. Add a few tiny amber analysis points. Keep the scene abstract, restrained, and technically credible. Use no physical machine, speaker, lens, device platform, typography, lightning, microphone, person, fake interface, circuitry, or watermark.

### Selection test

Reject any result that becomes a speaker, turbine, engine, or generic hardware render.

## Direction 3 — Persona Bloom

### Intent

Express individuality. Many timbral strands form one ownable vocal identity.

### Generation prompt

> Sophisticated editorial hero artwork for a voice-identity creation product. Hundreds of extremely fine timbral threads flow across an almost-black indigo field. The threads organize into an asymmetric oval vocal fingerprint made from curved spectral contour lines at center-right. They then continue as one calm, precise voice waveform. The central structure is abstract and geometric. It is not a literal fingerprint, flower, face, brain, or head. Use electric-blue outer strands, violet inner contours, restrained hot-magenta high-energy details, and a few tiny amber nodes. Keep the luminance controlled and the composition quiet, human, and ownable. Leave generous dark space. Use no typography, logo, lightning, microphone, portrait, play symbol, circuitry, stars, or watermark.

### Selection test

Reject literal fingerprints, flowers, eyes, heads, or generic AI-network imagery.

## Direction 4 — Signal Crucible

### Intent

Connect the art most directly to the word “Forge.” The forge must shape sound, not metal or electricity.

### Generation prompt

> Premium abstract voice-forging artwork on a deep Obsidian indigo field. Four incomplete concentric black-ceramic arcs form an open signal crucible on the right third. Several cool spectral ribbons enter from the left. They compress through the central void, become violet and selective hot magenta at the narrowest point, and leave as one clean icy-blue speech waveform. Add one thin amber vertical calibration line. Use subtle top-lit edges, strong silhouette, disciplined glow, and large dark negative space. Use no gray studio backdrop, text, emblem, lightning, sparks, fire, speaker cone, microphone, person, play symbol, gears, circuitry, or watermark.

### Selection test

Reject literal furnaces, flames, anvils, speakers, camera lenses, and science-fiction portals.

## Direction 5 — Quiet Instrument

### Intent

Create the most restrained direction. This option must work in startup, loading, and empty states.

### Generation prompt

> Minimal premium hero artwork for a professional voice-design instrument. Use an almost-black Obsidian field with subtle indigo depth. Place a small segmented voice aperture slightly right of center. Form it from three restrained blue-violet arcs around empty negative space. One very fine incoming waveform enters from the left, passes through the aperture, and leaves as a clean brighter voice signal. Add one tiny amber playhead marker. Use vast deliberate negative space, museum-product restraint, and controlled luminance. Keep the image calm enough for a loading state. Use no text, lightning, microphone, person, play symbol, circuitry, stars, particles, lens flare, or watermark.

### Selection test

Reject results that are empty without intent. The aperture and transformation must remain legible at small sizes.

## Composition requirements

Each selected master must:

- use a 16:9 canvas of at least 2048 × 1152 pixels
- keep important geometry inside the central 70 percent
- preserve a clean upper-left title-safe zone
- survive a centered square crop
- retain a recognizable silhouette at 320 pixels wide
- contain no generated text
- avoid crushed shadow detail around the central structure
- avoid clipped blue or magenta highlights

## Review workflow

1. Generate at least three candidates for each direction.
2. Inspect every candidate at full size and at 320 pixels wide.
3. Reject candidates that violate a forbidden motif.
4. Select one master for each direction.
5. Save the five selected masters with the required filenames.
6. Create a contact sheet with all five masters and direction labels outside the artwork.
7. Save the contact sheet as:
   `assets/brand/concepts/persona-forge/hero-v2/contact-sheet.png`
8. Stop and ask the owner to choose one or two finalists.
9. Do not create production assets before owner selection.

## Selection and delivery record

The review workflow completed on 2026-09-23. Native Codex generated three
candidates for each of the five directions, all of which were inspected at full
size and at 320 px wide. The owner selected **Signal Crucible**.

The five staged masters and labeled comparison sheet remain local and are
ignored by Git:

- `assets/brand/concepts/persona-forge/hero-v2/masters/`
- `assets/brand/concepts/persona-forge/hero-v2/contact-sheet.png`

Only the selected finalist family is Git-visible. Delivery assets are:

- `finalists/signal-crucible/github-social.jpg` — 1280 × 640; 96,119 bytes
- `finalists/signal-crucible/app-hero.png` — canonical 1920 × 1080 composition
- `finalists/signal-crucible/startup-field.png` — 1600 × 900; darkened for
  foreground status text
- `finalists/signal-crucible/square-social.png` — 1080 × 1080
- `finalists/signal-crucible/avatar-study.png` — 512 × 512

Every derivative comes from `app-hero.png`. Arc count, proportions,
orientation, right-of-center crucible placement, and amber calibration line
therefore stay consistent.

At the owner's request, the finalist also includes a concept-stage scalable SVG
pack under `finalists/signal-crucible/svg/`:

- `mark.svg` — full-detail Signal Crucible mark
- `mark-small.svg` — compact UI mark
- `favicon.svg` — rounded-square favicon/app icon
- `lockup.svg` — horizontal Persona Forge lockup

The SVG pack preserves the open ceramic arcs, voice-transformation signal, and
amber calibration point. It intentionally excludes lightning and does not yet
replace the production mark.

## Finalist work after owner selection — completed

For each approved finalist, create:

- GitHub social: 1280 × 640
- app hero: 1920 × 1080
- startup field: 1600 × 900 with extra darkening for foreground status text
- square social: 1080 × 1080
- avatar study: 512 × 512

Saved under:

`assets/brand/concepts/persona-forge/hero-v2/finalists/<direction>/`

Delivered app assets use lossless PNG. The GitHub preview uses optimized JPEG.

## Branding boundary

This task explored hero art. The owner subsequently requested a concept-stage
SVG pack for the selected Signal Crucible direction; it remains staged beside
the finalist and is not integrated into production.

The selected hero direction may inform a later production mark replacement. Do
not put the old lightning mark into new artwork.

## Repository rules

- Preserve existing exploration files locally.
- Keep rejected, superseded, master, and contact-sheet assets ignored by Git.
- Do not edit frontend production code during the exploration.
- Do not add external dependencies.
- Do not commit generated text, watermarks, model metadata, or temporary files.
- Keep generation identifiers in this report, not in image metadata.

## Verification

Run:

```bash
python scripts/validate_repo.py
git diff --check
test -f assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/app-hero.png
test -f assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/startup-field.png
test -f assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/github-social.jpg
test -f assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/square-social.png
test -f assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/avatar-study.png
test -f assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/svg/mark.svg
test -f assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/svg/mark-small.svg
test -f assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/svg/favicon.svg
test -f assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/svg/lockup.svg
test \"$(stat -f %z assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/github-social.jpg)\" -lt 1000000
```

## Execution report

**Tool.** Native Codex built-in `image_gen`; the tool did not expose a model
identifier or seeds, so generation identifiers are retained below.

**Selected master identifiers.**

- Voice Aperture — `exec-3bc044ec-a6e9-468f-9745-8373a14b1915`
- Formant Forge — `exec-4743892a-39e6-415d-afc8-cf903e1f2593`
- Persona Bloom — `exec-8931717b-041e-4ad6-95e5-d0819abf61bc`
- Signal Crucible — `exec-485a3340-4fe9-4a39-b915-53e9b8013a37`
- Quiet Instrument — `exec-5b1f1508-0769-4d1e-a21f-8161250522f4`

**Selected finalist provenance.**

- Canonical app hero — `exec-c6964175-76cb-4735-9b2c-eda649208d93`
- GitHub social — centered 2:1 crop from the canonical app hero
- Startup field — darkened 1600×900 derivative of the canonical app hero
- Square social — square crop preserving the app hero's right-of-center crucible placement
- Avatar study — 512×512 derivative of the square social crop

**Rejected-candidate rationale.** Voice Aperture alternatives were more
sculptural or ring-like than the selected signal-led study. Formant Forge
alternatives risked reading as a turbine or hardware. Persona Bloom alternatives
read as a literal fingerprint or generic network. Signal Crucible alternatives
were either less legible at small size or too sparse. Quiet Instrument
alternatives were either under-articulated or risked a power-button reading.

**Selection.** Signal Crucible was the recommended first finalist because it
most directly communicates shaping many signals into one voice; Formant Forge
was the runner-up for its analytical professional-audio character.

**Validation.** Repository validation, diff hygiene, SVG XML validation,
output-dimension checks, required-file checks, GitHub's sub-1 MB limit, and
visual inspection must pass before production integration.

**Repository publication.** Only
`assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/` is
Git-visible. Previous concepts, rejected masters, and the contact sheet remain
local and ignored.

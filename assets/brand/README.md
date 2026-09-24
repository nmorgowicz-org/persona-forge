# Persona Forge branding

This directory holds the Git-visible Persona Forge identity. Persona Forge
turns voice identities into designed, editable, synthesized speech.

## Selected identity

**Signal Crucible** is the owner-selected direction. Multiple blue and violet
voice fields converge through open Obsidian arcs at one amber calibration
point. One coherent pale waveform leaves the Crucible.

The identity communicates voice transformation and precision audio tooling. It
does not use lightning, microphones, human profiles, or generic AI symbols.

Core colors:

- Obsidian: `#080B14`
- Electric blue: `#47BFFF`
- Violet: `#9B6BFF`
- Restrained magenta: `#E853FF`
- Amber calibration: `#FFBE55`
- Pale signal: `#C9F1FF`

## Published assets

```text
assets/brand/
├── exports/
│   └── persona-forge-mark.svg
└── concepts/persona-forge/hero-v2/finalists/signal-crucible/
    ├── app-hero.png
    ├── startup-field.png
    ├── github-social.jpg
    ├── square-social.png
    ├── avatar-study.png
    └── svg/
        ├── mark.svg
        ├── mark-small.svg
        ├── favicon.svg
        └── lockup.svg
```

Use `github-social.jpg` for the GitHub repository social preview. It is
1280×640 and below GitHub's 1 MB limit.

Use `app-hero.png` only on non-operational surfaces such as documentation and
onboarding. Use `startup-field.png` behind startup status. Never put full hero
art behind working controls.

The SVG set **passed the B-P6 optical gate** (2026-09-23): `favicon.svg`,
`mark-small.svg` and `mark.svg` were rendered at 16, 24, 32 and 48 px on light
and dark grounds and judged without any glow behind them. `favicon.svg` and
`mark-small.svg` carry their own Obsidian ground, so they read at 16 px on
either background; `mark.svg` is light-on-transparent and is therefore for
**dark backgrounds only** — do not place it on a light surface.

`favicon.svg` is now the production favicon in both copies the app serves
(`frontend/public/favicon.svg` and `src/persona_forge/static/favicon.svg`), and
`mark.svg` is `exports/persona-forge-mark.svg`. All three are byte-identical to
the finalist originals, and the B-P6 spec asserts that, so a future edit cannot
silently drift from the selected identity.

## Local exploration assets

Rejected and superseded concepts remain local for provenance but are ignored
by Git. This includes prior hero, social, avatar, mark-draft, mark-final,
multi-direction master, and contact-sheet directories.

Do not add those exploration files back to Git. Publish only the selected
Signal Crucible finalist family.

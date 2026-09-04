# Persona Forge branding

This directory is the source-of-truth home for Persona Forge visual identity
assets and review material. Persona Forge is the voice design and voice-cloning
studio: it turns a voice identity into designed, editable, synthesized speech
through Voice Design, OmniVoice auditioning, Stitch Studio, prosody controls,
voice libraries, and an OpenAI-compatible TTS API.

## Existing identity

The canonical mark is the purple-to-cyan lightning bolt already used by the
frontend favicon. It is preserved unchanged at
`exports/persona-forge-mark.svg` and remains the mark to use for small square
repo and organization icons until a replacement is explicitly selected.

Core palette:

- Violet: `#863bff`
- Electric purple: `#7e14ff`
- Cyan: `#47bfff`
- Pale lavender: `#ede6ff`
- Midnight indigo / near-black backgrounds

The visual language pairs the bolt's decisive shape with waveform ribbons,
voiceprints, timelines, and precise studio-like synthesis. The goal is to make
the product legible as voice tooling rather than generic music or microphone
software.

## Asset layout

```text
assets/brand/
├── exports/
│   └── persona-forge-mark.svg       canonical existing favicon/mark
└── concepts/persona-forge/
    ├── hero-options/                full-resolution concept artwork
    ├── social-ready/                1280×640 JPEG previews, under 1 MB each
    └── avatar-options/              1024×1024 square crops for icon review
```

Options A–E are intentionally retained together for review. The hero PNGs are
the source concepts; the JPEGs are derived upload candidates and should be used
for repository social previews, not as logo replacements. The square crops are
visual tests for how the artwork survives a small icon treatment. They are
review material, not a final mark system.

The social-ready files use a controlled center crop only along the vertical
axis to reach GitHub's 2:1 preview shape. No text is baked into the artwork, so
the images can be reused in repository previews, project pages, or other
product-facing surfaces without creating a false wordmark.

## Selection guidance

Prefer the existing SVG bolt for favicon, repo-avatar, and other small-square
uses. Select one of the hero concepts for a social preview or landing-page
surface based on the desired emphasis:

- A–C explore waveform, voiceprint, and multi-persona studio directions.
- D makes the existing bolt-to-voice relationship the clearest.
- E most directly communicates voice identities entering a synthesis workflow.

Before promoting any concept to a permanent product surface, check it at the
actual rendered size, in both light and dark surrounding UI, and against the
upload service's current dimensions and file-size limits.

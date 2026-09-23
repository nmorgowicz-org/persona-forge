# Frontend Design System

Single source of truth for color, elevation, and reusable UI primitives. Tokens
live in `frontend/src/index.css` and are consumed through Tailwind utility
classes.

## Principles

1. Do not use raw palette colors to express status. Use semantic tokens such as
   `text-warning`, `bg-success/10`, and `border-destructive/30`.
2. Raw palette colors are allowed only for categorical identity, not severity.
   Examples: voice provenance badges (`VoiceDesign`, `OmniVoice`, `Upload`) and
   audio-edit lane accents.
3. Use `.btn-brand` for primary generate/save/commit calls instead of repeating
   the cyan gradient and glow in components.

## Semantic Tokens

| Token | Utility examples | Use for |
| --- | --- | --- |
| `--success` | `text-success`, `bg-success/10`, `border-success/30` | Passed, healthy, committed |
| `--warning` | `text-warning`, `bg-warning/10`, `border-warning/30` | Needs review, long text, pending action |
| `--info` | `text-info`, `bg-info/10`, `border-info/30` | Neutral informative state |
| `--destructive` | `text-destructive`, `bg-destructive/10`, `border-destructive/30` | Errors, failed checks, destructive actions |
| `--surface-1` | `bg-surface-1` | Elevated app chrome distinct from page background |

All semantic tokens are defined in both `:root` and `.dark`, then registered in
the `@theme inline` block so `bg-*`, `text-*`, `border-*`, and `ring-*` utilities
work.

## Utilities

`.btn-brand` encodes the product CTA gradient, glow, hover lift, and disabled
treatment. Components should add only layout classes:

```tsx
<button className="btn-brand inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-medium">
  Save to library
</button>
```

`.status-badge` and `.status-tone-*` encode semantic status pills:

```tsx
<span className="status-badge status-tone-warning px-2 py-0.5 text-xs">
  Needs review
</span>
```

Supported tones: `success`, `warning`, `info`, `danger`, and `neutral`.

## Materials, signal, motion (B-P1)

The look is **Obsidian** (chosen on the look-dev board, CP0b D1): near-black
neutrals at hue 270, hairline edges, tight radii. Its values live in the `.dark`
block of `index.css` and came verbatim from
`tests/ui/capture/lookdev/obsidian.css`, the file the owner approved — if the two
ever disagree, the board is the reference and one of them is a bug.

### Two color roles, never mixed

- **Accent** (`--primary`, four themes) — selection, focus, chrome glow, and the
  CTA. `--brand-from` / `--brand-to` / `--brand-glow` are *derived* from it with
  relative color syntax (`oklch(from var(--primary) …)`), so `.btn-brand` is
  violet in violet and amber in amber (D3). Never hard-code a CTA color.
- **Signal** (`frontend/src/lib/signal.ts`) — waveforms, meters, spectrogram,
  playhead. **One fixed palette, no theme awareness**: like a plugin whose
  analyzer stays readable under any skin. `SIGNAL_RAMP` (blue → violet → magenta
  → near-white), `SIGNAL_PLAYHEAD` (amber), `SPECTRO_STOPS`, the meter scale, and
  `heat()` (dBFS, not linear amplitude — linear never reaches the hot end for
  speech peaking at −6 dBFS). Every waveform draws through `WaveformCanvas` (B-P2), which feeds `signalColor(heat(...))` from an absolute-unit envelope — the transition shim `waveformBarColor` was deleted once its last caller moved.

Semantic status tokens stay a third, separate role.

### Material

One recipe, three surfaces — never a bespoke shadow in a component:

| Class | Use for |
| --- | --- |
| `.panel-1` | A raised surface: `--card` + `--shadow-panel` |
| `.panel-2` | A floating surface above panels: `--popover` + a deeper drop |
| `.well` | An inset surface: `--well` (darker than the page) + `--shadow-well` |

`--shadow-panel` / `--shadow-well` are the board's `--ld-panel-shadow` /
`--ld-well-shadow` renamed. Glow is keyed to a role: `--glow-accent` (follows the
theme, used by `.glow-active` and keyboard focus) and `--glow-signal` (fixed).

Radii come from one knob: `--radius` (0.3rem) with `--radius-well`,
`--radius-control`, `--radius-panel` registered in `@theme inline` as
`rounded-well` / `rounded-control` / `rounded-panel`.

### Type

`.display` (page title), `.micro-label` (uppercase, tracked, muted — field and
section labels), `.readout` (Geist Mono + `tabular-nums`, with `.readout-unit`
for the unit span). Readouts must not reflow when their value changes: that is
what `tabular-nums` is for, and it is why the mono family is self-hosted.

### Motion

`frontend/src/lib/motion.ts` owns the named durations, easings and springs
(`MOTION.snappy`, `.settle`, `.drift`, `SPRING.meterFall`). Use those names, not
raw numbers. The same values are mirrored as `--motion-*` / `--ease-*` in
`index.css` for transitions that never touch React; keep the two in step.
`useReducedMotionSafe()` starts `false` so the first client paint matches the
server. Every animation needs a static end-state under reduced motion — reduced
motion removes travel, never information.

## Lint Guard

`frontend/oxlint-design-system.cjs` adds
`design-system/no-raw-status-colors`. It rejects raw status palette classes such
as `text-amber-500`, `bg-emerald-500/10`, `border-rose-500/30`, and
`text-red-400` in frontend source. If a new categorical color is genuinely
needed, keep it local and document why it is not status.

Run:

```bash
npm --prefix frontend run lint
```

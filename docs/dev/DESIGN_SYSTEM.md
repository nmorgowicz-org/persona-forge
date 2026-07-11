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

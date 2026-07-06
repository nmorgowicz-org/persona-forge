import React from 'react'
import { Check } from 'lucide-react'
import { THEMES, type Theme } from '@/lib/theme'
import { useAppStore } from '@/store'
import { cn } from '@/lib/utils'

const SWATCH_COLOR: Record<Theme, string> = {
  violet: 'oklch(0.62 0.19 280)',
  teal: 'oklch(0.6 0.13 175)',
  amber: 'oklch(0.78 0.16 70)',
  rose: 'oklch(0.64 0.2 10)',
}

const SWATCH_LABEL: Record<Theme, string> = {
  violet: 'Violet',
  teal: 'Teal',
  amber: 'Amber',
  rose: 'Rose',
}

export function ThemeSwitcher() {
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const [open, setOpen] = React.useState(false)
  const ref = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  return (
    <div
      ref={ref}
      className="relative inline-flex"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex size-5 shrink-0 items-center justify-center rounded-full border border-white/10 bg-muted text-muted-foreground transition-all hover:bg-accent hover:text-foreground hover:scale-110"
        title="Theme"
      >
        <Check className="size-3" strokeWidth={3} />
      </button>

      {open && (
        <div className="absolute right-0 top-0 mt-7 mb-1 flex gap-1.5 rounded-lg border border-border bg-popover px-2.5 py-1.5 shadow-lg">
          {THEMES.map((t) => {
            const active = theme === t
            return (
              <button
                key={t}
                type="button"
                onClick={() => {
                  setTheme(t)
                }}
                className={cn(
                  'flex size-5 shrink-0 items-center justify-center rounded-full ring-1 ring-white/10 transition-transform hover:scale-110',
                  active && 'ring-2 ring-white/80',
                )}
                style={{ background: SWATCH_COLOR[t] }}
                title={SWATCH_LABEL[t]}
              >
                {active && <Check className="size-3 text-black/70" strokeWidth={3} />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

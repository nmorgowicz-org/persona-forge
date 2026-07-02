import { Check } from 'lucide-react'
import { THEMES, type Theme } from '@/lib/theme'
import { useAppStore } from '@/store'
import { cn } from '@/lib/utils'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

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

  return (
    <div className="flex items-center gap-1.5 px-1">
      {THEMES.map((t) => (
        <Tooltip key={t}>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={`${SWATCH_LABEL[t]} theme`}
              onClick={() => setTheme(t)}
              className={cn(
                'flex size-5 shrink-0 items-center justify-center rounded-full ring-1 ring-white/10 transition-transform hover:scale-110',
                theme === t && 'ring-2 ring-white/70',
              )}
              style={{ background: SWATCH_COLOR[t] }}
            >
              {theme === t && <Check className="size-3 text-black/70" strokeWidth={3} />}
            </button>
          </TooltipTrigger>
          <TooltipContent side="top">{SWATCH_LABEL[t]}</TooltipContent>
        </Tooltip>
      ))}
    </div>
  )
}

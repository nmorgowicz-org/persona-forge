// The app banner (B-P6). Three banners used to hand-roll their own bar: their own border
// colour, their own background tint, their own icon sizing. Same job, three shapes.
//
// One shape now, with a tone from the same vocabulary the status badges use -- so a warning
// looks like a warning wherever it appears, and a new banner cannot invent a fourth look.
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export type BannerTone = 'neutral' | 'info' | 'warning' | 'danger'

const TONE_CLASS: Record<BannerTone, string> = {
  neutral: 'border-border bg-muted/30 text-muted-foreground',
  info: 'border-info/30 bg-info/10 text-info',
  warning: 'border-warning/30 bg-warning/10 text-warning',
  danger: 'border-destructive/30 bg-destructive/10 text-destructive',
}

export interface AppBannerProps {
  tone?: BannerTone
  icon?: ReactNode
  /** Main line: what is happening. */
  children: ReactNode
  /** Secondary line or details, shown muted under the main line. */
  detail?: ReactNode
  /** Trailing controls. */
  actions?: ReactNode
}

export function AppBanner({ tone = 'neutral', icon, children, detail, actions }: AppBannerProps) {
  return (
    <div
      data-testid="app-banner"
      data-tone={tone}
      className={cn('flex flex-wrap items-center gap-x-2 gap-y-1 border-b px-4 py-1.5 text-xs', TONE_CLASS[tone])}
    >
      {icon}
      <div className="min-w-0 flex-1 leading-tight">
        {children}
        {detail && <span className="mt-0.5 block truncate text-[10px] opacity-70">{detail}</span>}
      </div>
      {actions}
    </div>
  )
}

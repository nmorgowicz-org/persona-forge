import { memo } from 'react'
import { cn } from '@/lib/utils'

interface LevelMeterProps {
  level?: number
  peak?: number
  label?: string
  className?: string
}

function clamp01(value: number | undefined) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0
  return Math.max(0, Math.min(1, value))
}

export const LevelMeter = memo(function LevelMeter({
  level = 0,
  peak,
  label = 'Level',
  className,
}: LevelMeterProps) {
  const levelPct = clamp01(level) * 100
  const peakPct = clamp01(peak ?? level) * 100

  return (
    <div className={cn('flex min-w-28 flex-col gap-1', className)}>
      <div className="flex items-center justify-between text-[10px] font-medium uppercase text-muted-foreground">
        <span>{label}</span>
        <span className="font-mono">{Math.round(levelPct)}%</span>
      </div>
      <div
        className="relative h-2.5 overflow-hidden rounded bg-background/80 shadow-inner ring-1 ring-border/70"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(levelPct)}
      >
        <div className="absolute inset-0 bg-[linear-gradient(90deg,hsl(185_90%_48%/.85),hsl(142_70%_48%/.85)_62%,hsl(38_95%_56%/.9)_82%,hsl(332_86%_58%/.95))]" />
        <div className="absolute inset-y-0 right-0 bg-background/90" style={{ width: `${100 - levelPct}%` }} />
        <div className="absolute inset-y-0 w-px bg-white shadow-[0_0_6px_rgba(255,255,255,.8)]" style={{ left: `${peakPct}%` }} />
      </div>
    </div>
  )
})

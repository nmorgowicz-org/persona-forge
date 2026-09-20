import { memo } from 'react'
import { createTimeTicks } from '@/lib/timeAxis'
import { useElementWidth } from '@/hooks/useElementWidth'

// A thin second-scale ruler for the reference editor lane. Tick marks align exactly to
// their timestamp; labels clamp at the edges so the first/last stay in-bounds.
export const TimeRuler = memo(function TimeRuler({ durationMs }: { durationMs: number }) {
  const [ref, widthPx] = useElementWidth<HTMLDivElement>()
  if (!durationMs || durationMs <= 0) return null
  const durSec = durationMs / 1000
  const ticks =
    widthPx > 0
      ? createTimeTicks({ durationSeconds: durSec, pixelsPerSecond: widthPx / durSec, widthPx })
      : []

  return (
    <div ref={ref} className="relative h-4 select-none">
      {ticks.map((t, index) => {
        const pos = (t.x / Math.max(1, widthPx)) * 100
        return (
          <span key={index}>
            <span className="absolute top-0 h-1.5 w-px -translate-x-1/2 bg-border/70" style={{ left: `${pos}%` }} />
            <span
              className="absolute top-2 text-[9px] font-mono tabular-nums text-muted-foreground/60"
              style={{ left: `${pos}%`, transform: pos >= 99.5 ? 'translateX(-100%)' : pos <= 0.5 ? 'translateX(0)' : 'translateX(-50%)' }}
            >
              {t.label}
            </span>
          </span>
        )
      })}
    </div>
  )
})

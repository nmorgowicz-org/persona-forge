// Shared, real-pixel-scale time ruler for the Stitch Studio timeline. Renders tick labels
// through the top of the row and thin gridlines that extend down behind the clip row, both
// computed from lib/timeAxis.ts so tick spacing/labels never drift from Waveform.tsx or
// waveform/TimeRuler.tsx (locked contract: docs/plans/20260920-stitch_studio_ux_execution_plan.md
// "Time-axis contract"). `widthPx` is the real content width (durationSeconds * pixelsPerSecond),
// not the visible viewport -- ticks must cover content that scrolls off-screen, not just the fold.
import { useMemo } from 'react'
import { createTimeTicks } from '@/lib/timeAxis'

export function TimelineRuler({
  durationSeconds,
  pixelsPerSecond,
  widthPx,
  laneHeightPx,
}: {
  durationSeconds: number
  pixelsPerSecond: number
  widthPx: number
  laneHeightPx: number
}) {
  const ticks = useMemo(
    () => createTimeTicks({ durationSeconds, pixelsPerSecond, widthPx }),
    [durationSeconds, pixelsPerSecond, widthPx],
  )

  if (widthPx <= 0 || ticks.length === 0) return null

  return (
    <div
      className="pointer-events-none absolute inset-y-0 left-0 z-0"
      style={{ width: widthPx, height: laneHeightPx }}
    >
      {ticks.map((tick) => (
        <div
          key={tick.seconds}
          data-testid="stitch-ruler-tick"
          data-seconds={tick.seconds}
          className="absolute top-0 border-l border-border/20"
          style={{ left: tick.x, height: laneHeightPx }}
        >
          <span className="absolute top-0 ml-1 whitespace-nowrap text-[10px] font-mono text-muted-foreground/50">
            {tick.label}
          </span>
        </div>
      ))}
    </div>
  )
}

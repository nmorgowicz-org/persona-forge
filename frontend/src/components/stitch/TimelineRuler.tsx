// Shared, real-pixel-scale time ruler for the Stitch Studio timeline. Renders tick labels
// through the top of the row and thin gridlines that extend down behind the clip row, both
// computed from lib/timeAxis.ts so tick spacing/labels never drift from Waveform.tsx or
// waveform/TimeRuler.tsx (locked contract: docs/plans/20260920-stitch_studio_ux_execution_plan.md
// "Time-axis contract"). `widthPx` is the real content width (durationSeconds * pixelsPerSecond),
// not the visible viewport -- ticks must cover content that scrolls off-screen, not just the fold.
//
// Packet 7 adds the shared transport's playhead and click-to-seek: `transport` renders a
// pointer-events-none line whose position is pushed via `subscribeTime` (never React state, so
// scrubbing/playback never re-renders the ruler), and clicking anywhere in the ruler computes
// an arrangement-relative second from the click's own x and asks the caller to seek. Arrangement
// seconds and the shared audio element's own seconds usually differ slightly (trims/gaps/crossfade
// are a client approximation of the backend's actual render), so the mapping is the caller's job
// via `previewScale` (previewSec / arrangementSec) -- this component only ever computes and
// reports/consumes arrangement-relative positions.
import { useEffect, useMemo, useRef } from 'react'
import { createTimeTicks } from '@/lib/timeAxis'
import { type StitchTransport } from '@/hooks/useStitchTransport'

function RulerPlayhead({
  transport,
  previewScale,
  pixelsPerSecond,
  laneHeightPx,
}: {
  transport: StitchTransport
  previewScale: number
  pixelsPerSecond: number
  laneHeightPx: number
}) {
  const ref = useRef<HTMLDivElement>(null)
  const { subscribeTime, getCurrentTime } = transport

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const apply = (previewSec: number) => {
      const arrangementSec = previewScale > 0 ? previewSec / previewScale : previewSec
      el.style.transform = `translateX(${Math.max(0, arrangementSec * pixelsPerSecond)}px)`
    }
    apply(getCurrentTime())
    return subscribeTime(apply)
  }, [subscribeTime, getCurrentTime, previewScale, pixelsPerSecond])

  return (
    <div
      ref={ref}
      data-testid="stitch-transport-playhead"
      className="pointer-events-none absolute inset-y-0 left-0 z-30 w-px bg-warning"
      style={{ height: laneHeightPx }}
    />
  )
}

export function TimelineRuler({
  durationSeconds,
  pixelsPerSecond,
  widthPx,
  laneHeightPx,
  transport,
  previewScale = 1,
  onSeekSeconds,
}: {
  durationSeconds: number
  pixelsPerSecond: number
  widthPx: number
  laneHeightPx: number
  transport?: StitchTransport
  previewScale?: number
  onSeekSeconds?: (arrangementSec: number) => void
}) {
  const ticks = useMemo(
    () => createTimeTicks({ durationSeconds, pixelsPerSecond, widthPx }),
    [durationSeconds, pixelsPerSecond, widthPx],
  )

  if (widthPx <= 0 || ticks.length === 0) return null

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!onSeekSeconds) return
    const rect = e.currentTarget.getBoundingClientRect()
    const arrangementSec = Math.max(0, (e.clientX - rect.left) / pixelsPerSecond)
    onSeekSeconds(arrangementSec)
  }

  return (
    <div
      data-testid="stitch-timeline-ruler"
      onClick={handleClick}
      className={onSeekSeconds ? 'absolute inset-y-0 left-0 z-0 cursor-pointer' : 'pointer-events-none absolute inset-y-0 left-0 z-0'}
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
      {transport && <RulerPlayhead transport={transport} previewScale={previewScale} pixelsPerSecond={pixelsPerSecond} laneHeightPx={laneHeightPx} />}
    </div>
  )
}

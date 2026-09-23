// Shared, real-pixel-scale time ruler for the Stitch Studio timeline. Renders tick labels
// through the top of the row and thin gridlines that extend down behind the clip row, both
// computed from lib/timeAxis.ts so tick spacing/labels never drift from Waveform.tsx or
// waveform/TimeRuler.tsx (locked contract: docs/archive/stitch-studio/20260920-stitch_studio_ux_execution_plan.md
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
//
// M1 adds the loop brace: dragging across the ruler reports an arrangement-relative
// [startSec, endSec] to the caller, and the brace is rendered from that same pair, so it is
// expressed in seconds and therefore survives zoom and scroll by construction. While a
// gesture is in flight the live band is written straight to the DOM (never React state), the
// same discipline the playhead and hover guide use -- a ruler drag must not re-render the
// timeline under the pointer. A drag that does not travel is still a click-to-seek, and
// clicking inside an existing brace still seeks (only its handles take pointer events).
import { useEffect, useMemo, useRef, type PointerEvent as ReactPointerEvent } from 'react'
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
  loopRange = null,
  onLoopChange,
}: {
  durationSeconds: number
  pixelsPerSecond: number
  widthPx: number
  laneHeightPx: number
  transport?: StitchTransport
  previewScale?: number
  onSeekSeconds?: (arrangementSec: number) => void
  /** Active arrangement loop in arrangement seconds, or null. */
  loopRange?: { startSec: number; endSec: number } | null
  /** Reports a new loop (drag across the ruler, or a handle drag), or null to clear it. */
  onLoopChange?: (range: { startSec: number; endSec: number } | null) => void
}) {
  const ticks = useMemo(
    () => createTimeTicks({ durationSeconds, pixelsPerSecond, widthPx }),
    [durationSeconds, pixelsPerSecond, widthPx],
  )

  // Brace gesture state, declared before the early return below so the hooks run on every
  // render (the ruler renders nothing until it has a width and at least one tick).
  const dragRef = useRef<{ pointerId: number; mode: 'new' | 'start' | 'end'; anchorSec: number; fixedSec: number } | null>(null)
  const liveRef = useRef<HTMLDivElement | null>(null)
  const suppressClickRef = useRef(false)

  if (widthPx <= 0 || ticks.length === 0) return null

  const secAtClientX = (clientX: number, el: Element) => {
    const rect = el.getBoundingClientRect()
    return Math.max(0, Math.min(durationSeconds, (clientX - rect.left) / pixelsPerSecond))
  }

  // Brace gesture. `mode` distinguishes a drag that creates a new loop from one that moves an
  // existing edge; both commit once, on release, and paint a live band in the meantime.

  const paintLive = (startSec: number, endSec: number) => {
    const live = liveRef.current
    if (!live) return
    live.style.display = ''
    live.style.left = `${startSec * pixelsPerSecond}px`
    live.style.width = `${Math.max(0, (endSec - startSec) * pixelsPerSecond)}px`
  }
  const clearLive = () => {
    const live = liveRef.current
    if (live) live.style.display = 'none'
  }

  const onBracePointerDown = (mode: 'new' | 'start' | 'end') => (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!onLoopChange) return
    e.stopPropagation()
    const sec = secAtClientX(e.clientX, e.currentTarget.closest('[data-testid="stitch-timeline-ruler"]') ?? e.currentTarget)
    dragRef.current = {
      pointerId: e.pointerId,
      mode,
      anchorSec: sec,
      fixedSec: mode === 'start' ? (loopRange?.endSec ?? sec) : mode === 'end' ? (loopRange?.startSec ?? sec) : sec,
    }
    e.currentTarget.setPointerCapture(e.pointerId)
    if (mode !== 'new') paintLive(Math.min(sec, dragRef.current.fixedSec), Math.max(sec, dragRef.current.fixedSec))
  }

  const onBracePointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== e.pointerId) return
    const sec = secAtClientX(e.clientX, e.currentTarget)
    if (drag.mode === 'new') paintLive(Math.min(drag.anchorSec, sec), Math.max(drag.anchorSec, sec))
    else paintLive(Math.min(sec, drag.fixedSec), Math.max(sec, drag.fixedSec))
  }

  const onBracePointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== e.pointerId) return
    dragRef.current = null
    clearLive()
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
    if (e.type === 'pointercancel') return
    const sec = secAtClientX(e.clientX, e.currentTarget)
    const startSec = drag.mode === 'new' ? Math.min(drag.anchorSec, sec) : Math.min(sec, drag.fixedSec)
    const endSec = drag.mode === 'new' ? Math.max(drag.anchorSec, sec) : Math.max(sec, drag.fixedSec)
    // A drag shorter than a few pixels is the click-to-seek gesture, not a loop.
    if ((endSec - startSec) * pixelsPerSecond < 4) {
      if (drag.mode !== 'new') onLoopChange?.(null)
      return
    }
    // A drag across the ruler creates a loop and must not also seek to where it ended.
    if (drag.mode === 'new') suppressClickRef.current = true
    onLoopChange?.({ startSec, endSec })
  }

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false
      return
    }
    if (!onSeekSeconds) return
    onSeekSeconds(secAtClientX(e.clientX, e.currentTarget))
  }

  return (
    <div
      data-testid="stitch-timeline-ruler"
      onClick={handleClick}
      onPointerDown={onLoopChange ? onBracePointerDown('new') : undefined}
      onPointerMove={onLoopChange ? onBracePointerMove : undefined}
      onPointerUp={onLoopChange ? onBracePointerUp : undefined}
      onPointerCancel={onLoopChange ? onBracePointerUp : undefined}
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
      {/* Live band for the gesture in flight: written imperatively so a drag across the
          ruler never re-renders the timeline under the pointer. */}
      {onLoopChange && (
        <div
          ref={liveRef}
          data-testid="loop-brace-live"
          className="pointer-events-none absolute top-0 z-20 hidden h-full border-x-2 border-cyan-400/50 bg-cyan-400/10"
        />
      )}
      {loopRange && loopRange.endSec > loopRange.startSec && (
        <div
          data-testid="loop-brace"
          data-loop-start={loopRange.startSec.toFixed(3)}
          data-loop-end={loopRange.endSec.toFixed(3)}
          title="Arrangement loop — double-click to clear"
          onDoubleClick={() => onLoopChange?.(null)}
          className="pointer-events-none absolute top-0 z-20 h-full border-x-2 border-cyan-400/70 bg-cyan-400/10"
          style={{ left: loopRange.startSec * pixelsPerSecond, width: (loopRange.endSec - loopRange.startSec) * pixelsPerSecond }}
        >
          <div
            data-testid="loop-brace-handle-start"
            onPointerDown={onBracePointerDown('start')}
            onPointerMove={onBracePointerMove}
            onPointerUp={onBracePointerUp}
            onPointerCancel={onBracePointerUp}
            className="pointer-events-auto absolute inset-y-0 -left-1 w-2 cursor-ew-resize"
          />
          <div
            data-testid="loop-brace-handle-end"
            onPointerDown={onBracePointerDown('end')}
            onPointerMove={onBracePointerMove}
            onPointerUp={onBracePointerUp}
            onPointerCancel={onBracePointerUp}
            className="pointer-events-auto absolute inset-y-0 -right-1 w-2 cursor-ew-resize"
          />
        </div>
      )}
      {transport && <RulerPlayhead transport={transport} previewScale={previewScale} pixelsPerSecond={pixelsPerSecond} laneHeightPx={laneHeightPx} />}
    </div>
  )
}

import { memo, useEffect, useRef, type PointerEvent as ReactPointerEvent } from 'react'
import { waveformBarColor } from '@/lib/waveform'
import { HOVER_TIME_GUIDE_LABEL_CLASS, HOVER_TIME_GUIDE_LINE_CLASS, useHoverTimeGuide } from '@/hooks/useHoverTimeGuide'

interface WaveformLaneProps {
  peaks: number[] | null
  durMs: number | null
  trimStartMs: number
  trimEndMs: number
  fadeInMs: number
  fadeOutMs: number
  pauseIntervals?: [number, number][]
  /** Opt-in hover time readout, named for tests. Hosts that already render their own readout
   * with extra semantics (the prosody region editor, the voice-edit compare) leave it off. */
  timeGuideTestId?: string
}

export const WaveformLane = memo(function WaveformLane({
  peaks,
  durMs,
  trimStartMs,
  trimEndMs,
  fadeInMs,
  fadeOutMs,
  pauseIntervals,
  timeGuideTestId,
}: WaveformLaneProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const guide = useHoverTimeGuide()
  const hasScale = durMs != null && durMs > 0

  // The lane's box is measured at hover time rather than observed: a per-lane ResizeObserver
  // would add a state update and a re-render to every clip for a readout that only exists
  // while a pointer is over it.
  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!hasScale || event.pointerType === 'touch') return
    const rect = event.currentTarget.getBoundingClientRect()
    if (rect.width <= 0) return
    const frac = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))
    guide.show(`${frac * 100}%`, frac * ((durMs as number) / 1000), frac)
  }

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !peaks || !durMs || durMs <= 0) return

    const draw = () => {
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      // Backing store follows the device pixel ratio so the waveform stays crisp on hi-DPI
      // screens instead of being upscaled from a 1x bitmap; drawing math below stays in CSS
      // pixel units via the reset transform.
      const dpr = window.devicePixelRatio || 1
      const width = canvas.clientWidth
      const height = canvas.clientHeight
      if (width <= 0 || height <= 0) return
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)

      // The lane renders the clip's kept (effective) window [trimStartMs, durMs - trimEndMs]:
      // peaks are sliced to that window and rescaled so the slice spans the full lane width.
      // The card sizes itself from the same effective duration at the timeline's single
      // pixels-per-second scale, so one lane pixel here equals one effective millisecond and
      // one ruler pixel, and every interactive boundary (trim/fade handles, selection,
      // region overlays) sits on the same coordinate as the waveform.
      const effectiveDuration = Math.max(1, durMs - trimStartMs - trimEndMs)
      const keepStartMs = Math.max(0, Math.min(trimStartMs, durMs))
      const keepEndMs = Math.max(keepStartMs, Math.min(durMs - trimEndMs, durMs))
      const startIdx = Math.floor((keepStartMs / durMs) * peaks.length)
      const endIdx = Math.max(startIdx + 1, Math.ceil((keepEndMs / durMs) * peaks.length))
      const keptPeaks = peaks.slice(startIdx, Math.min(peaks.length, endIdx))

      const barWidth = width / keptPeaks.length
      keptPeaks.forEach((peak, index) => {
        const x = index * barWidth
        const barHeight = Math.max(1, peak * height)
        const y = (height - barHeight) / 2
        ctx.fillStyle = waveformBarColor(peak, false)
        ctx.fillRect(x, y, Math.max(1, barWidth - 1), barHeight)
      })

      if (pauseIntervals) {
        // Pause intervals are in source time; shift them into the effective window.
        ctx.fillStyle = 'rgba(0, 0, 0, 0.18)'
        pauseIntervals.forEach(([startSec, endSec]) => {
          const startX = Math.max(0, Math.min(1, (startSec * 1000 - keepStartMs) / effectiveDuration)) * width
          const endX = Math.max(0, Math.min(1, (endSec * 1000 - keepStartMs) / effectiveDuration)) * width
          ctx.fillRect(startX, 0, Math.max(1, endX - startX), height)
        })
      }
    }

    draw()

    // Redraw on real layout changes -- the canvas backing store is sized from clientWidth/
    // clientHeight, which don't update themselves when the lane's flex/grid box resizes.
    const observer = new ResizeObserver(draw)
    observer.observe(canvas)
    return () => observer.disconnect()
  }, [peaks, durMs, trimStartMs, trimEndMs, pauseIntervals])

  if (!peaks || !durMs) {
    return <div className="flex h-full items-center justify-center text-[10px] text-muted-foreground/60">No waveform</div>
  }

  return (
    <div
      className="relative flex h-full items-center overflow-hidden px-0.5"
      onPointerMove={hasScale ? onPointerMove : undefined}
      onPointerLeave={hasScale ? guide.hide : undefined}
    >
      <canvas ref={canvasRef} className="block h-full w-full" data-testid="stitch-waveform-canvas" />
      {hasScale && (
        <div ref={guide.guideRef} data-testid={timeGuideTestId} className={HOVER_TIME_GUIDE_LINE_CLASS} style={{ left: 0, display: 'none' }}>
          <span ref={guide.labelRef} className={HOVER_TIME_GUIDE_LABEL_CLASS}>
            0.0s
          </span>
        </div>
      )}
      {/* Trim/fade values stay readable as text -- the canvas is never the sole information
          channel. */}
      <span className="sr-only">
        Trim start {trimStartMs}ms, trim end {trimEndMs}ms, fade in {fadeInMs}ms, fade out {fadeOutMs}ms.
      </span>
    </div>
  )
})

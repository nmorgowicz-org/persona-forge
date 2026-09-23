// A clip lane: the shared renderer plus the edit overlays that belong to a lane (the kept
// window, trims and fades are already expressed by the window the renderer draws, so what
// remains here is the pause band and the hover readout).
//
// Level comes from the envelope in absolute units and, in a multi-clip view, from a scale
// shared with every other lane on screen -- that is what makes a quiet segment look quiet next
// to its neighbour.
import { memo, type PointerEvent as ReactPointerEvent } from 'react'
import type { AudioEnvelope } from '@/lib/waveform'
import { WaveformCanvas } from '@/components/waveform/WaveformCanvas'
import { HOVER_TIME_GUIDE_LABEL_CLASS, HOVER_TIME_GUIDE_LINE_CLASS, useHoverTimeGuide } from '@/hooks/useHoverTimeGuide'

interface WaveformLaneProps {
  envelope: AudioEnvelope | null
  durMs: number | null
  trimStartMs: number
  trimEndMs: number
  fadeInMs: number
  fadeOutMs: number
  pauseIntervals?: [number, number][]
  /** Opt-in hover time readout, named for tests. Hosts that already render their own readout
   * with extra semantics (the prosody region editor, the voice-edit compare) leave it off. */
  timeGuideTestId?: string
  /** Absolute amplitude at full lane height, shared across every lane on screen. Omitted for a
   * single-lane view, which auto-fits and shows the peak readout instead. */
  scaleAbs?: number | null
  showPeakReadout?: boolean
  /** The clip's audio could not be decoded -- distinct from still loading, so the surface can
   * say so instead of shimmering forever. */
  failed?: boolean
}

export const WaveformLane = memo(function WaveformLane({
  envelope,
  durMs,
  trimStartMs,
  trimEndMs,
  fadeInMs,
  fadeOutMs,
  pauseIntervals,
  timeGuideTestId,
  scaleAbs = null,
  showPeakReadout = false,
  failed = false,
}: WaveformLaneProps) {
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

  // The lane renders the clip's kept (effective) window [trimStartMs, durMs - trimEndMs]; the
  // card sizes itself from the same effective duration at the timeline's single
  // pixels-per-second scale, so one lane pixel equals one effective millisecond and one ruler
  // pixel, and every interactive boundary (trim/fade handles, selection, region overlays) sits
  // on the same coordinate as the waveform.
  const effectiveDuration = durMs != null ? Math.max(1, durMs - trimStartMs - trimEndMs) : 1
  const keepStartMs = durMs != null ? Math.max(0, Math.min(trimStartMs, durMs)) : 0
  const keepEndMs = durMs != null ? Math.max(keepStartMs, Math.min(durMs - trimEndMs, durMs)) : 0

  const drawPauseBands = (ctx: CanvasRenderingContext2D, size: { width: number; height: number }) => {
    if (!pauseIntervals?.length) return
    // Pause intervals are in source time; shift them into the effective window.
    ctx.fillStyle = 'rgba(0, 0, 0, 0.18)'
    for (const [startSec, endSec] of pauseIntervals) {
      const startX = Math.max(0, Math.min(1, (startSec * 1000 - keepStartMs) / effectiveDuration)) * size.width
      const endX = Math.max(0, Math.min(1, (endSec * 1000 - keepStartMs) / effectiveDuration)) * size.width
      ctx.fillRect(startX, 0, Math.max(1, endX - startX), size.height)
    }
  }

  return (
    <div
      className="relative flex h-full items-center overflow-hidden px-0.5"
      onPointerMove={hasScale ? onPointerMove : undefined}
      onPointerLeave={hasScale ? guide.hide : undefined}
    >
      <WaveformCanvas
        envelope={envelope}
        startMs={keepStartMs}
        endMs={keepEndMs}
        scaleAbs={scaleAbs}
        showPeakReadout={showPeakReadout}
        failed={failed}
        canvasTestId="stitch-waveform-canvas"
        onOverlay={drawPauseBands}
      />
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

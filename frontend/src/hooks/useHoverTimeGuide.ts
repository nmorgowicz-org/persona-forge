// One hover time readout, shared by every waveform surface (the playback deck, the clip
// lane, the prosody and voice-edit lanes, and the stitch timeline's ruler).
//
// The guide is written straight to the DOM -- never through React state -- so pointer
// movement cannot re-render a waveform that may be hosting a drag gesture (the same
// discipline the stitch ruler's playhead uses for playback position). A hover sweep must
// leave the waveform's element identity untouched.
//
// Geometry stays with the caller: each surface knows its own coordinate space (percent of
// the lane for a fixed-width waveform, content pixels inside the timeline's scroll
// container), so `show` takes the CSS `left` the caller computed plus the time it maps to.
import { useCallback, useRef } from 'react'
import { formatHoverTime } from '@/lib/timeAxis'

export interface HoverTimeGuide {
  /** Attach to the guide element (a zero-width vertical line, hidden until first hover). */
  guideRef: React.RefObject<HTMLDivElement | null>
  /** Attach to the label inside the guide. */
  labelRef: React.RefObject<HTMLSpanElement | null>
  /** `left` is the CSS position the caller's own geometry produced; `fraction` (0..1 across
   * the surface) only decides which way the label flips at the edges so it stays inside. */
  show: (left: string, seconds: number, fraction: number) => void
  hide: () => void
}

export function useHoverTimeGuide({ pixelsPerSecond }: { pixelsPerSecond: number }): HoverTimeGuide {
  const guideRef = useRef<HTMLDivElement | null>(null)
  const labelRef = useRef<HTMLSpanElement | null>(null)
  // Read at call time so a re-render never invalidates the callbacks (they stay
  // identity-stable, like the drag-scrub hook's gesture callbacks).
  const ppsRef = useRef(pixelsPerSecond)
  ppsRef.current = pixelsPerSecond

  const show = useCallback((left: string, seconds: number, fraction: number) => {
    const guide = guideRef.current
    const label = labelRef.current
    if (!guide || !label) return
    guide.style.display = ''
    guide.style.left = left
    label.textContent = formatHoverTime(seconds, ppsRef.current)
    // Keep the label inside the surface at its edges instead of letting it hang off.
    label.style.transform = fraction <= 0.06 ? 'translateX(0)' : fraction >= 0.94 ? 'translateX(-100%)' : 'translateX(-50%)'
  }, [])

  const hide = useCallback(() => {
    const guide = guideRef.current
    if (guide) guide.style.display = 'none'
  }, [])

  return { guideRef, labelRef, show, hide }
}

/** The guide markup every surface renders: a cyan line plus its time label. */
export const HOVER_TIME_GUIDE_LINE_CLASS = 'pointer-events-none absolute inset-y-0 z-20 w-px bg-cyan-300/70'
export const HOVER_TIME_GUIDE_LABEL_CLASS =
  'pointer-events-none absolute top-0.5 whitespace-nowrap rounded bg-background/90 px-1 text-[9px] font-mono tabular-nums text-cyan-200 shadow-sm'

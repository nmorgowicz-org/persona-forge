import { memo, useEffect, useRef } from 'react'
import { waveformBarColor } from '@/lib/waveform'

interface WaveformLaneProps {
  peaks: number[] | null
  durMs: number | null
  trimStartMs: number
  trimEndMs: number
  fadeInMs: number
  fadeOutMs: number
  pauseIntervals?: [number, number][]
}

export const WaveformLane = memo(function WaveformLane({
  peaks,
  durMs,
  trimStartMs,
  trimEndMs,
  fadeInMs,
  fadeOutMs,
  pauseIntervals,
}: WaveformLaneProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

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

      const trimStartRatio = Math.max(0, Math.min(1, trimStartMs / durMs))
      const trimEndRatio = Math.max(0, Math.min(1, trimEndMs / durMs))
      const trimStartX = trimStartRatio * width
      const trimEndX = (1 - trimEndRatio) * width

      // Draw every peak across the clip's full duration (truthful geometry: trimmed material
      // stays visible, just dimmed) rather than slicing peaks out of the array, which used to
      // silently rescale the remaining bars to fill the lane.
      const barWidth = width / peaks.length
      const effectiveDuration = Math.max(1, durMs - trimStartMs - trimEndMs)
      peaks.forEach((peak, index) => {
        const x = index * barWidth
        const barHeight = Math.max(1, peak * height)
        const y = (height - barHeight) / 2
        const trimmedOut = x + barWidth <= trimStartX || x >= trimEndX
        ctx.fillStyle = waveformBarColor(peak, false)
        ctx.globalAlpha = trimmedOut ? 0.22 : 1
        ctx.fillRect(x, y, Math.max(1, barWidth - 1), barHeight)
        ctx.globalAlpha = 1
      })

      // Fade gain ramps: a linear gain-vs-time wedge drawn over the kept (untrimmed) region,
      // so trimming and fading read as one truthful picture instead of a flat DOM gradient
      // guessing at width.
      const drawFadeRamp = (fadeMs: number, direction: 'in' | 'out') => {
        if (fadeMs <= 0) return
        const fadeRatio = Math.min(1, fadeMs / effectiveDuration)
        const fadeWidth = fadeRatio * (trimEndX - trimStartX)
        if (fadeWidth <= 0) return
        ctx.beginPath()
        ctx.fillStyle = 'rgba(0, 0, 0, 0.55)'
        if (direction === 'in') {
          ctx.moveTo(trimStartX, 0)
          ctx.lineTo(trimStartX + fadeWidth, 0)
          ctx.lineTo(trimStartX, height)
          ctx.closePath()
        } else {
          ctx.moveTo(trimEndX, 0)
          ctx.lineTo(trimEndX - fadeWidth, 0)
          ctx.lineTo(trimEndX, height)
          ctx.closePath()
        }
        ctx.fill()
      }
      drawFadeRamp(fadeInMs, 'in')
      drawFadeRamp(fadeOutMs, 'out')

      if (pauseIntervals) {
        ctx.fillStyle = 'rgba(0, 0, 0, 0.18)'
        pauseIntervals.forEach(([startSec, endSec]) => {
          const startX = Math.max(0, Math.min(1, (startSec * 1000) / durMs)) * width
          const endX = Math.max(0, Math.min(1, (endSec * 1000) / durMs)) * width
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
  }, [peaks, durMs, trimStartMs, trimEndMs, fadeInMs, fadeOutMs, pauseIntervals])

  if (!peaks || !durMs) {
    return <div className="flex h-full items-center justify-center text-[10px] text-muted-foreground/60">No waveform</div>
  }

  return (
    <div className="relative flex h-full items-center overflow-hidden px-0.5">
      <canvas ref={canvasRef} className="block h-full w-full" data-testid="stitch-waveform-canvas" />
      {/* Trim/fade values stay readable as text even though the canvas also draws them --
          canvas is never the sole information channel. */}
      <span className="sr-only">
        Trim start {trimStartMs}ms, trim end {trimEndMs}ms, fade in {fadeInMs}ms, fade out {fadeOutMs}ms.
      </span>
    </div>
  )
})

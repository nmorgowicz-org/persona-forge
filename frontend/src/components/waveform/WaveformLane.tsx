import { memo, useEffect, useRef } from 'react'

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
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const width = canvas.clientWidth
    const height = canvas.clientHeight
    canvas.width = width
    canvas.height = height
    ctx.clearRect(0, 0, width, height)

    const trimStartRatio = Math.max(0, Math.min(1, trimStartMs / durMs))
    const trimEndRatio = Math.max(0, Math.min(1, trimEndMs / durMs))
    const startIndex = Math.floor(trimStartRatio * peaks.length)
    const endIndex = Math.max(startIndex + 1, peaks.length - Math.floor(trimEndRatio * peaks.length))
    const filteredPeaks = peaks.slice(startIndex, endIndex)
    if (filteredPeaks.length === 0) return

    const barWidth = width / filteredPeaks.length
    filteredPeaks.forEach((peak, index) => {
      const x = index * barWidth
      const barHeight = Math.max(1, peak * height)
      const y = (height - barHeight) / 2
      const hue = 190 + peak * 140
      const light = 40 + peak * 10
      const alpha = 0.3 + peak * 0.25
      ctx.fillStyle = `hsl(${hue} 45% ${light}% / ${alpha})`
      ctx.fillRect(x, y, Math.max(1, barWidth - 1), barHeight)
    })

    if (pauseIntervals) {
      ctx.fillStyle = 'rgba(0, 0, 0, 0.18)'
      pauseIntervals.forEach(([startSec, endSec]) => {
        const startX = Math.max(0, Math.min(1, (startSec * 1000) / durMs)) * width
        const endX = Math.max(0, Math.min(1, (endSec * 1000) / durMs)) * width
        ctx.fillRect(startX, 0, Math.max(1, endX - startX), height)
      })
    }
  }, [peaks, durMs, trimStartMs, trimEndMs, fadeInMs, fadeOutMs, pauseIntervals])

  if (!peaks || !durMs) {
    return <div className="flex h-full items-center justify-center text-[10px] text-muted-foreground/60">No waveform</div>
  }

  return (
    <div className="relative flex h-full items-center overflow-hidden px-0.5">
      <canvas ref={canvasRef} className="block h-full w-full" />
    </div>
  )
})

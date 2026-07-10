import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'

interface WaveformProps {
  peaks: number[]
  progress?: number // 0..1, how much of the waveform is \"played\"
  isActive?: boolean // pulses idle bars gently while audio is loading/generating
  duration?: number | null // total audio duration in seconds, drives time axis
  className?: string
  onClick?: (progress: number) => void
}

function formatTime(sec: number): string {
  if (sec < 0 || !isFinite(sec)) return '0.0s'
  // For short clips (< 10s) or small intervals, prefer compact seconds with decimals.
  // For longer clips, use m:ss.
  const isShort = sec < 10
  if (isShort) {
    return `${sec.toFixed(1)}s`
  }
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

// A dedicated meter palette, independent of the app's neutral (grayscale) theme —
// real DAW/VST meters use their own color language rather than the plugin chrome.
// Quiet material reads cool cyan/teal, loud peaks push into hot magenta, like a level meter.
function barColor(peak: number, played: boolean) {
  const hue = 190 + peak * 140 // 190 = cyan, 330 = magenta
  if (played) {
    const light = 58 + peak * 14
    const alpha = 0.55 + peak * 0.45
    return `hsl(${hue} 90% ${light}% / ${alpha})`
  }
  const light = 40 + peak * 10
  const alpha = 0.28 + peak * 0.22
  return `hsl(${hue} 45% ${light}% / ${alpha})`
}

const PLAYHEAD_COLOR = 'hsl(38 95% 62%)' // warm amber cursor, pops against the cool waveform

export function Waveform({ peaks, progress = 0, isActive = false, duration = null, className, onClick }: WaveformProps) {
  const playheadPct = Math.min(100, Math.max(0, progress * 100))
  const hasTimeAxis = duration != null && duration > 0 && isFinite(duration)

  const handleWaveformClick = (e: React.MouseEvent) => {
    if (!onClick) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const pct = x / rect.width
    onClick(Math.min(1, Math.max(0, pct)))
  }

  // Compute time ticks: simple, evenly spaced, 3-7 labels.
  // For short clips (< 5s) use small step (0.2–1s) and decimal labels.
  // For longer clips use m:ss labels.
  const ticks = hasTimeAxis
    ? (() => {
        const dur = duration as number
        const isShort = dur < 5
        // Decide target number of ticks
        const targetTicks = isShort ? 5 : 4
        // Compute ideal step
        const idealStep = dur / targetTicks

        const niceShort = [0.2, 0.3, 0.5, 1]
        const niceLong = [1, 2, 3, 5, 10, 15, 20]
        const scale = isShort ? niceShort : niceLong

        let step = idealStep
        let bestDiff = Infinity
        for (const s of scale) {
          const diff = Math.abs(s - idealStep)
          if (diff < bestDiff) {
            bestDiff = diff
            step = s
          }
        }

        const n = Math.max(2, Math.round(dur / step))
        const labels: { pos: number; text: string }[] = []
        for (let i = 0; i <= n; i++) {
          const t = i * step
          if (t > dur + 0.001) break
          labels.push({
            pos: (i / n) * 100,
            text: formatTime(t),
          })
        }
        // Always show the clip's exact total duration at the far right, even if
        // the last evenly-spaced tick landed short of it.
        const lastLabel = labels[labels.length - 1]
        if (!lastLabel || lastLabel.pos < 99.5) {
          labels.push({ pos: 100, text: formatTime(dur) })
        }
        return labels
      })()
    : null

  return (
    <div
      className={cn(
        'relative cursor-pointer overflow-hidden rounded-md bg-gradient-to-b from-black/30 to-transparent px-0.5',
        hasTimeAxis ? 'h-20' : 'h-16',
        className,
      )}
      onClick={handleWaveformClick}
    .
    >
      {/* center track line, like a DAW lane */}
      <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border/60" />

      {/* time grid lines */}
      {ticks != null &&
        ticks.map((t, i) => (
          <div
            key={i}
            className="absolute inset-y-0 w-px bg-white/[0.06]"
            style={{ left: `${t.pos}%` }}
          />
        ))}

      <div className="relative -m-px flex h-full items-center">
        {peaks.map((peak, i) => {
          const played = (i / peaks.length) * 100 <= playheadPct
          const height = Math.max(0.06, peak)
          const color = barColor(height, played)

          return (
            <motion.div
              key={i}
              className="h-full min-w-[1px] flex-1 rounded-full"
              style={{
                transformOrigin: 'center',
                background: color,
                filter: played && height > 0.35 ? `drop-shadow(0 0 3px ${color})` : undefined,
              }}
              initial={{ scaleY: 0 }}
              animate={{
                scaleY: isActive ? [height * 0.55, height, height * 0.55] : height,
              }}
              transition={
                isActive
                  ? { duration: 0.85 + (i % 5) * 0.09, repeat: Infinity, ease: 'easeInOut' }
                  : { type: 'spring', stiffness: 320, damping: 24, delay: i * 0.004 }
              }
            />
          )
        })}
      </div>

      {progress > 0 && (
        <motion.div
          className="pointer-events-none absolute top-0 h-full w-px"
          style={{ background: PLAYHEAD_COLOR, boxShadow: `0 0 8px 1px ${PLAYHEAD_COLOR}` }}
          animate={{ left: `${playheadPct}%` }}
          transition={{ type: 'tween', ease: 'linear', duration: 0.1 }}
        >
          <span
            className="absolute -top-0.5 -left-[3px] size-[7px] rounded-full"
            style={{ background: PLAYHEAD_COLOR, boxShadow: `0 0 6px 1px ${PLAYHEAD_COLOR}` }}
          />
        </motion.div>
      )}

      {/* bottom time axis */}
      {hasTimeAxis && ticks != null && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end">
          {ticks.map((t, i) => (
            <span
              key={i}
              className={cn(
                'absolute -bottom-0 text-[9px] font-mono text-muted-foreground/50',
                t.pos >= 99.5 ? '-translate-x-full' : '-translate-x-1/2',
              )}
              style={{ left: `${t.pos}%` }}
            >
              {t.text}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export function idlePeaks(buckets = 64): number[] {
  return Array.from({ length: buckets }, (_, i) => 0.15 + 0.1 * Math.sin(i / 3))
}

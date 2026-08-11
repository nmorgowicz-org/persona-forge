import { memo } from 'react'

// Pick an evenly-spaced tick step that yields ~4-5 labels, mirroring Waveform.tsx's
// axis language so the reference editor reads the same as the playback deck.
function niceStep(durSec: number): number {
  const ideal = durSec / (durSec < 5 ? 5 : 4)
  const scale = durSec < 5 ? [0.1, 0.2, 0.25, 0.5, 1] : [1, 2, 3, 5, 10, 15, 20, 30, 60]
  return scale.reduce((best, s) => (Math.abs(s - ideal) < Math.abs(best - ideal) ? s : best), scale[0])
}

function label(sec: number, step: number): string {
  if (sec < 10) return `${sec.toFixed(step < 0.5 ? 2 : 1)}s`
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

// A thin second-scale ruler for the reference editor lane. Tick marks align exactly to
// their timestamp; labels clamp at the edges so the first/last stay in-bounds.
export const TimeRuler = memo(function TimeRuler({ durationMs }: { durationMs: number }) {
  if (!durationMs || durationMs <= 0) return null
  const durSec = durationMs / 1000
  const step = niceStep(durSec)
  const n = Math.max(2, Math.round(durSec / step))
  const ticks: { pos: number; text: string }[] = []
  for (let i = 0; i <= n; i++) {
    const t = i * step
    if (t > durSec + 0.001) break
    ticks.push({ pos: (t / durSec) * 100, text: label(t, step) })
  }
  if (!ticks.length || ticks[ticks.length - 1].pos < 99.5) ticks.push({ pos: 100, text: label(durSec, step) })

  return (
    <div className="relative h-4 select-none">
      {ticks.map((t, index) => (
        <span key={index}>
          <span className="absolute top-0 h-1.5 w-px -translate-x-1/2 bg-border/70" style={{ left: `${t.pos}%` }} />
          <span
            className="absolute top-2 text-[9px] font-mono tabular-nums text-muted-foreground/60"
            style={{ left: `${t.pos}%`, transform: t.pos >= 99.5 ? 'translateX(-100%)' : t.pos <= 0.5 ? 'translateX(0)' : 'translateX(-50%)' }}
          >
            {t.text}
          </span>
        </span>
      ))}
    </div>
  )
})

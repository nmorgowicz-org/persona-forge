import { useEffect, useMemo, useState } from 'react'
import type { AlignmentBoundary, ProsodyPausePlanEntry } from '@/lib/api'
import { getVoice } from '@/lib/api'
import { base64ToBlob } from '@/lib/utils'
import { WaveformLane } from './WaveformLane'
import { TimeRuler } from './TimeRuler'

// A shared-time-axis A/B view of the reference clip (original vs prosody-adjusted).
// Both lanes are drawn at the *same* seconds-per-pixel — the shorter one simply stops
// where its audio ends — so a manufactured pause visibly pushes the adjusted content
// right of its original position. Word text rides the ORIGINAL lane (the aligner's
// boundaries are in original time); cut markers + inserted-gap shading ride the ADJUSTED
// lane (cut positions are in rendered/adjusted sample space).

type Decoded = { peaks: number[]; durationMs: number; sampleCount: number }

function useDecodedPeaks(base64: string | null, perSec = 48): Decoded | null {
  const [decoded, setDecoded] = useState<Decoded | null>(null)
  useEffect(() => {
    if (!base64) {
      setDecoded(null)
      return
    }
    let cancelled = false
    const ctx = new AudioContext()
    void base64ToBlob(base64)
      .arrayBuffer()
      .then((data) => ctx.decodeAudioData(data))
      .then((buffer) => {
        if (cancelled) return
        const channel = buffer.getChannelData(0)
        const durationMs = (buffer.length / buffer.sampleRate) * 1000
        const count = Math.max(24, Math.round((durationMs / 1000) * perSec))
        const width = Math.max(1, Math.floor(channel.length / count))
        const values = Array.from({ length: count }, (_, index) => {
          let peak = 0
          for (let i = index * width; i < Math.min(channel.length, (index + 1) * width); i++) peak = Math.max(peak, Math.abs(channel[i]))
          return peak
        })
        const max = Math.max(...values, 0.01)
        setDecoded({ peaks: values.map((value) => value / max), durationMs, sampleCount: buffer.length })
      })
      .catch(() => {
        if (!cancelled) setDecoded(null)
      })
      .finally(() => void ctx.close())
    return () => {
      cancelled = true
    }
  }, [base64, perSec])
  return decoded
}

function wordClass(boundary: AlignmentBoundary): string {
  if (boundary.kind === 'uncertain') return 'text-muted-foreground/50 italic'
  if (boundary.kind === 'sentence_split') return 'text-cyan-300 font-semibold'
  if (boundary.owns_clause) return 'text-warning'
  return 'text-foreground/70'
}

export function AlignmentCompare({ voiceId, adjustedBase64, adjustedSampleCount, boundaryPlan = [], boundaries }: {
  voiceId: string
  adjustedBase64: string
  adjustedSampleCount: number
  boundaryPlan?: ProsodyPausePlanEntry[]
  boundaries: AlignmentBoundary[] | null
}) {
  const [originalBase64, setOriginalBase64] = useState<string | null>(null)
  const [hoverPct, setHoverPct] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    setOriginalBase64(null)
    void getVoice(voiceId)
      .then((full) => {
        if (!cancelled) setOriginalBase64(full.audio_base64 ?? null)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [voiceId])

  const original = useDecodedPeaks(originalBase64)
  const adjusted = useDecodedPeaks(adjustedBase64)

  const maxDurMs = Math.max(original?.durationMs ?? 0, adjusted?.durationMs ?? 0, 1)
  const pct = (ms: number) => `${Math.max(0, Math.min(100, (ms / maxDurMs) * 100))}%`
  const cutMs = (sample: number) => (adjusted ? (sample / Math.max(1, adjustedSampleCount)) * adjusted.durationMs : 0)

  // Space words so short ones stay readable: min-width per label, truncate overflow.
  const words = useMemo(() => (boundaries ?? []).filter((b) => b.text), [boundaries])

  if (!adjusted) return null

  const hoverMs = hoverPct !== null ? (hoverPct / 100) * maxDurMs : null

  return (
    <div
      className="relative space-y-1"
      onMouseMove={(event) => {
        const rect = event.currentTarget.getBoundingClientRect()
        setHoverPct(Math.max(0, Math.min(100, ((event.clientX - rect.left) / rect.width) * 100)))
      }}
      onMouseLeave={() => setHoverPct(null)}
    >
      {/* ORIGINAL lane — word text rides its true (pre-insertion) timeline. */}
      <div className="relative">
        <div className="absolute -top-2 left-2 z-20 rounded bg-muted px-1 py-px text-[9px] font-bold text-muted-foreground">ORIGINAL</div>
        <div className="relative h-16 overflow-hidden rounded border border-border bg-muted/20">
          <div className="absolute inset-y-0 left-0 opacity-70" style={{ width: pct(original?.durationMs ?? 0) }}>
            <WaveformLane peaks={original?.peaks ?? null} durMs={original?.durationMs ?? null} trimStartMs={0} trimEndMs={0} fadeInMs={0} fadeOutMs={0} />
          </div>
          {words.map((word, index) => (
            <span
              key={`${word.text}-${index}`}
              className={`pointer-events-none absolute bottom-0.5 overflow-hidden text-ellipsis whitespace-nowrap px-0.5 text-[9px] leading-tight ${wordClass(word)}`}
              style={{ left: pct(word.start * 1000), maxWidth: pct(Math.max(0.001, word.end - word.start) * 1000) }}
              title={`"${word.text}"  ${word.start.toFixed(2)}–${word.end.toFixed(2)}s · conf ${word.score.toFixed(2)}${word.kind === 'uncertain' ? ' · low confidence (skipped)' : ''}`}
            >
              {word.text}
            </span>
          ))}
        </div>
      </div>

      {/* ADJUSTED lane — cut markers + manufactured-gap shading in rendered time. */}
      <div className="relative">
        <div className="absolute -top-2 left-2 z-20 rounded bg-cyan-500 px-1 py-px text-[9px] font-bold text-white">ADJUSTED</div>
        <div className="relative h-16 overflow-hidden rounded border border-border bg-muted/20">
          <div className="absolute inset-y-0 left-0" style={{ width: pct(adjusted.durationMs) }}>
            <WaveformLane peaks={adjusted.peaks} durMs={adjusted.durationMs} trimStartMs={0} trimEndMs={0} fadeInMs={0} fadeOutMs={0} />
          </div>
          {boundaryPlan.map((marker, index) => {
            const start = cutMs(marker.cut_sample)
            const manufactured = marker.insert_ms > 0
            const color = marker.origin === 'alignment' ? 'border-cyan-300 text-cyan-300' : marker.origin === 'vad' ? 'border-warning text-warning' : 'border-violet-300 text-violet-300'
            const title = `${manufactured ? 'Manufactured' : 'Natural'} ${marker.origin} boundary\nTarget ${marker.target_ms.toFixed(0)} ms · inserted ${marker.insert_ms.toFixed(0)} ms\n${marker.provenance.replace('_', ' ')}`
            return (
              <span key={`${marker.cut_sample}-${index}`}>
                {manufactured && (
                  <span className="pointer-events-none absolute inset-y-0 z-0 bg-cyan-400/15" style={{ left: pct(start), width: pct(marker.insert_ms) }} />
                )}
                <span className={`absolute inset-y-0 z-10 -translate-x-1/2 border-l-2 ${manufactured ? 'border-solid' : 'border-dashed'} ${color}`} style={{ left: pct(start) }} title={title} aria-label={title}>
                  <span className={`absolute left-1/2 top-1 -translate-x-1/2 border-current bg-background ${manufactured ? 'size-2 rotate-45 border' : 'size-2 rounded-full border-2'}`} />
                </span>
              </span>
            )
          })}
        </div>
      </div>

      <TimeRuler durationMs={maxDurMs} />

      {/* Shared scrub cursor for eyeballing where original and adjusted diverge. */}
      {hoverPct !== null && hoverMs !== null && (
        <>
          <div className="pointer-events-none absolute inset-x-0 top-0 bottom-4 z-30" style={{ left: `${hoverPct}%` }}>
            <div className="absolute inset-y-0 w-px bg-cyan-300/70" />
          </div>
          <span className="pointer-events-none absolute top-0 z-30 rounded bg-background/90 px-1 text-[9px] font-mono tabular-nums text-cyan-200 shadow-sm" style={{ left: `${hoverPct}%`, transform: hoverPct <= 8 ? 'translateX(0)' : hoverPct >= 92 ? 'translateX(-100%)' : 'translateX(-50%)' }}>{(hoverMs / 1000).toFixed(2)}s</span>
        </>
      )}

      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[9px] text-muted-foreground">
        <span>◆ manufactured pause</span>
        <span>● natural boundary</span>
        <span className="text-cyan-300">sentence</span>
        <span className="text-warning">clause</span>
        <span className="italic text-muted-foreground/50">uncertain (skipped)</span>
      </div>
    </div>
  )
}

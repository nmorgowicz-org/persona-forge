import { useEffect, useMemo, useRef, useState } from 'react'
import { Pause, Play } from 'lucide-react'
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

// A play/scrub-able <audio> for a lane, sourced from a base64 clip via an object URL.
function useLaneAudio(base64: string | null) {
  const ref = useRef<HTMLAudioElement | null>(null)
  useEffect(() => {
    if (!base64) return
    const url = URL.createObjectURL(base64ToBlob(base64))
    const el = new Audio(url)
    el.preload = 'auto'
    ref.current = el
    return () => {
      el.pause()
      ref.current = null
      URL.revokeObjectURL(url)
    }
  }, [base64])
  return ref
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
  const [playing, setPlaying] = useState<'original' | 'adjusted' | null>(null)
  const [positionMs, setPositionMs] = useState(0)

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
  const origAudio = useLaneAudio(originalBase64)
  const adjAudio = useLaneAudio(adjustedBase64)

  const maxDurMs = Math.max(original?.durationMs ?? 0, adjusted?.durationMs ?? 0, 1)
  const pct = (ms: number) => `${Math.max(0, Math.min(100, (ms / maxDurMs) * 100))}%`
  const cutMs = (sample: number) => (adjusted ? (sample / Math.max(1, adjustedSampleCount)) * adjusted.durationMs : 0)

  const words = useMemo(() => (boundaries ?? []).filter((b) => b.text), [boundaries])

  // Drive the shared playhead off whichever lane is playing (rAF, so it stays smooth).
  const rafRef = useRef<number | undefined>(undefined)
  useEffect(() => {
    if (!playing) return
    const el = playing === 'original' ? origAudio.current : adjAudio.current
    if (!el) return
    const onEnd = () => setPlaying(null)
    el.addEventListener('ended', onEnd)
    const tick = () => {
      setPositionMs(el.currentTime * 1000)
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      el.removeEventListener('ended', onEnd)
    }
  }, [playing, origAudio, adjAudio])

  const togglePlay = (lane: 'original' | 'adjusted') => {
    const el = lane === 'original' ? origAudio.current : adjAudio.current
    const other = lane === 'original' ? adjAudio.current : origAudio.current
    other?.pause()
    if (!el) return
    if (playing === lane) {
      el.pause()
      setPlaying(null)
      return
    }
    el.currentTime = Math.max(0, positionMs / 1000)
    void el.play().then(() => setPlaying(lane)).catch(() => {})
  }

  const seekTo = (ms: number) => {
    setPositionMs(ms)
    const el = playing === 'original' ? origAudio.current : adjAudio.current
    if (el) el.currentTime = Math.max(0, ms / 1000)
  }

  if (!adjusted) return null

  const hoverMs = hoverPct !== null ? (hoverPct / 100) * maxDurMs : null
  const hovered = hoverMs !== null
    ? words.find((w) => hoverMs / 1000 >= w.start && hoverMs / 1000 <= w.end) ?? null
    : null

  const PlayButton = ({ lane }: { lane: 'original' | 'adjusted' }) => (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); togglePlay(lane) }}
      className="absolute right-1.5 top-1.5 z-20 grid size-6 place-items-center rounded-full border border-border bg-background/80 text-foreground/80 transition hover:bg-background hover:text-foreground"
      title={playing === lane ? 'Pause' : 'Play this lane'}
    >
      {playing === lane ? <Pause className="size-3" /> : <Play className="size-3 translate-x-px" />}
    </button>
  )

  return (
    <div
      className="relative space-y-1"
      onMouseMove={(event) => {
        const rect = event.currentTarget.getBoundingClientRect()
        setHoverPct(Math.max(0, Math.min(100, ((event.clientX - rect.left) / rect.width) * 100)))
      }}
      onMouseLeave={() => setHoverPct(null)}
    >
      {/* ORIGINAL lane — word text + the snapped cut in its true (pre-insertion) time. */}
      <div className="relative">
        <div className="absolute -top-2 left-2 z-20 rounded bg-muted px-1 py-px text-[9px] font-bold text-muted-foreground">ORIGINAL</div>
        <div
          className="relative h-14 cursor-text overflow-hidden rounded border border-border bg-muted/20"
          onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); seekTo(((e.clientX - r.left) / r.width) * maxDurMs) }}
        >
          <div className="absolute inset-y-0 left-0 opacity-80" style={{ width: pct(original?.durationMs ?? 0) }}>
            <WaveformLane peaks={original?.peaks ?? null} durMs={original?.durationMs ?? null} trimStartMs={0} trimEndMs={0} fadeInMs={0} fadeOutMs={0} />
          </div>
          {/* The cut mapped back to original time (src_cut_ms) — lines up with the words. */}
          {boundaryPlan.map((marker, index) => {
            const at = marker.src_cut_ms ?? marker.at_ms
            const color = marker.origin === 'alignment' ? 'border-cyan-300' : marker.origin === 'vad' ? 'border-warning' : 'border-violet-300'
            return (
              <span
                key={`o-${marker.cut_sample}-${index}`}
                className={`pointer-events-none absolute inset-y-0 z-10 -translate-x-1/2 border-l ${marker.insert_ms > 0 ? 'border-solid' : 'border-dashed'} ${color} opacity-80`}
                style={{ left: pct(at) }}
              />
            )
          })}
          <PlayButton lane="original" />
        </div>
        {/* Word labels ride below, tilted so dense clips stay readable. */}
        <div className="pointer-events-none relative h-7">
          {words.map((word, index) => (
            <span
              key={`${word.text}-${index}`}
              className={`absolute top-0 origin-top-left rotate-[30deg] whitespace-nowrap text-[9px] leading-none ${wordClass(word)} ${hovered === word ? 'z-10 !text-foreground' : ''}`}
              style={{ left: pct((word.start + word.end) / 2 * 1000) }}
            >
              {word.text}
            </span>
          ))}
        </div>
      </div>

      {/* ADJUSTED lane — cut markers + manufactured-gap shading in rendered time. */}
      <div className="relative">
        <div className="absolute -top-2 left-2 z-20 rounded bg-cyan-500 px-1 py-px text-[9px] font-bold text-white">ADJUSTED</div>
        <div
          className="relative h-14 cursor-text overflow-hidden rounded border border-border bg-muted/20"
          onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); seekTo(((e.clientX - r.left) / r.width) * maxDurMs) }}
        >
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
                <span className={`pointer-events-none absolute inset-y-0 z-10 -translate-x-1/2 border-l-2 ${manufactured ? 'border-solid' : 'border-dashed'} ${color}`} style={{ left: pct(start) }} title={title} aria-label={title}>
                  <span className={`absolute left-1/2 top-1 -translate-x-1/2 border-current bg-background ${manufactured ? 'size-2 rotate-45 border' : 'size-2 rounded-full border-2'}`} />
                </span>
              </span>
            )
          })}
          <PlayButton lane="adjusted" />
        </div>
      </div>

      <TimeRuler durationMs={maxDurMs} />

      {/* Playhead (during playback) + hover cursor with the word under the pointer. */}
      {playing && (
        <div className="pointer-events-none absolute inset-x-0 top-0 bottom-4 z-30" style={{ left: pct(positionMs) }}>
          <div className="absolute inset-y-0 w-0.5 -translate-x-1/2 bg-emerald-400/90" />
        </div>
      )}
      {hoverPct !== null && hoverMs !== null && (
        <>
          <div className="pointer-events-none absolute inset-x-0 top-0 bottom-4 z-30" style={{ left: `${hoverPct}%` }}>
            <div className="absolute inset-y-0 w-px bg-cyan-300/70" />
          </div>
          <span className="pointer-events-none absolute top-0 z-30 rounded bg-background/90 px-1 text-[9px] font-mono tabular-nums text-cyan-200 shadow-sm" style={{ left: `${hoverPct}%`, transform: hoverPct <= 8 ? 'translateX(0)' : hoverPct >= 92 ? 'translateX(-100%)' : 'translateX(-50%)' }}>
            {(hoverMs / 1000).toFixed(2)}s{hovered ? ` · "${hovered.text}" ${(hovered.score * 100).toFixed(0)}%` : ''}
          </span>
        </>
      )}

      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[9px] text-muted-foreground">
        <span>▶ click a lane to play · click the strip to seek</span>
        <span>◆ manufactured pause</span>
        <span>● natural boundary</span>
        <span className="text-cyan-300">sentence</span>
        <span className="text-warning">clause</span>
        <span className="italic text-muted-foreground/50">uncertain (skipped)</span>
      </div>
    </div>
  )
}

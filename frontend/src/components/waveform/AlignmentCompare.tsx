import { useEffect, useMemo, useRef, useState } from 'react'
import { Pause, Play, Repeat, X } from 'lucide-react'
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
  const [selection, setSelection] = useState<{ start: number; end: number } | null>(null)
  const [loop, setLoop] = useState(false)

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

  const laneAudio = (lane: 'original' | 'adjusted') => (lane === 'original' ? origAudio.current : adjAudio.current)

  const containerRef = useRef<HTMLDivElement | null>(null)
  const rafRef = useRef<number | undefined>(undefined)
  // The active play region (loop bounds) and loop flag are read inside the rAF loop, so
  // keep them in refs to dodge stale closures.
  const regionRef = useRef<{ start: number; end: number } | null>(null)
  const loopRef = useRef(loop)
  loopRef.current = loop
  const dragRef = useRef<{ lane: 'original' | 'adjusted'; startMs: number; endMs: number; moved: boolean } | null>(null)

  const msAtClientX = (clientX: number) => {
    const r = containerRef.current?.getBoundingClientRect()
    if (!r) return 0
    return Math.max(0, Math.min(1, (clientX - r.left) / r.width)) * maxDurMs
  }

  // Drive the shared playhead off whichever lane is playing (rAF, so it stays smooth),
  // honouring the loop region when one is set from a drag-selection.
  useEffect(() => {
    if (!playing) return
    const el = laneAudio(playing)
    if (!el) return
    const onEnd = () => setPlaying(null)
    el.addEventListener('ended', onEnd)
    const tick = () => {
      const region = regionRef.current
      if (region && el.currentTime * 1000 >= region.end) {
        if (loopRef.current) {
          el.currentTime = region.start / 1000
        } else {
          el.pause()
          setPositionMs(region.end)
          setPlaying(null)
          return
        }
      }
      setPositionMs(el.currentTime * 1000)
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      el.removeEventListener('ended', onEnd)
    }
  }, [playing, origAudio, adjAudio])

  const startPlay = (lane: 'original' | 'adjusted', fromMs: number, region: { start: number; end: number } | null) => {
    const el = laneAudio(lane)
    laneAudio(lane === 'original' ? 'adjusted' : 'original')?.pause()
    if (!el) return
    regionRef.current = region
    el.currentTime = Math.max(0, fromMs / 1000)
    setPositionMs(fromMs)
    void el.play().then(() => setPlaying(lane)).catch(() => {})
  }

  const togglePlay = (lane: 'original' | 'adjusted') => {
    if (playing === lane) {
      laneAudio(lane)?.pause()
      setPlaying(null)
      return
    }
    // Play the selection if one is set, else the whole lane from the playhead.
    if (selection) startPlay(lane, selection.start, selection)
    else startPlay(lane, positionMs, null)
  }

  const seekTo = (ms: number) => {
    setPositionMs(ms)
    const el = playing ? laneAudio(playing) : null
    if (el) el.currentTime = Math.max(0, ms / 1000)
  }

  // Click = seek, click-and-drag = select a region and immediately play (loop-aware) it.
  const onLaneDown = (lane: 'original' | 'adjusted') => (e: React.MouseEvent) => {
    e.preventDefault()
    const ms = msAtClientX(e.clientX)
    dragRef.current = { lane, startMs: ms, endMs: ms, moved: false }
  }

  const onStripMove = (e: React.MouseEvent) => {
    const r = containerRef.current?.getBoundingClientRect()
    if (r) setHoverPct(Math.max(0, Math.min(100, ((e.clientX - r.left) / r.width) * 100)))
    const d = dragRef.current
    if (!d) return
    d.endMs = msAtClientX(e.clientX)
    if (Math.abs(d.endMs - d.startMs) > 40) d.moved = true
    setSelection({ start: Math.min(d.startMs, d.endMs), end: Math.max(d.startMs, d.endMs) })
  }

  const finishDrag = () => {
    const d = dragRef.current
    dragRef.current = null
    if (!d) return
    if (!d.moved) {
      setSelection(null)
      regionRef.current = null
      seekTo(d.startMs)
      return
    }
    const region = { start: Math.min(d.startMs, d.endMs), end: Math.max(d.startMs, d.endMs) }
    setSelection(region)
    startPlay(d.lane, region.start, region)
  }

  if (!adjusted) return null

  const hoverMs = hoverPct !== null ? (hoverPct / 100) * maxDurMs : null
  const hovered = hoverMs !== null
    ? words.find((w) => hoverMs / 1000 >= w.start && hoverMs / 1000 <= w.end) ?? null
    : null

  const selWidth = selection ? `${Math.max(0, ((selection.end - selection.start) / maxDurMs) * 100)}%` : '0%'
  const TransportButton = ({ lane }: { lane: 'original' | 'adjusted' }) => (
    <button
      type="button"
      onClick={() => togglePlay(lane)}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px] font-semibold transition ${
        playing === lane ? 'border-amber-400 bg-amber-400/15 text-amber-200' : 'border-border bg-background/60 text-foreground/80 hover:bg-background'
      }`}
      title={playing === lane ? 'Pause' : selection ? 'Play selection' : 'Play from playhead'}
    >
      {playing === lane ? <Pause className="size-3" /> : <Play className="size-3 translate-x-px" />}
      {lane === 'original' ? 'Original' : 'Adjusted'}
    </button>
  )

  return (
    <div
      ref={containerRef}
      className="relative select-none space-y-1"
      onMouseMove={onStripMove}
      onMouseUp={finishDrag}
      onMouseLeave={() => { setHoverPct(null); finishDrag() }}
    >
      {/* Transport — A/B play, loop, and the current drag-selection. */}
      <div className="flex items-center gap-2 pb-0.5">
        <TransportButton lane="original" />
        <TransportButton lane="adjusted" />
        <button
          type="button"
          onClick={() => setLoop((v) => !v)}
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px] font-semibold transition ${
            loop ? 'border-cyan-400 bg-cyan-400/15 text-cyan-200' : 'border-border bg-background/60 text-foreground/70 hover:bg-background'
          }`}
          title="Loop the selected region"
        >
          <Repeat className="size-3" /> Loop
        </button>
        {selection && (
          <span className="inline-flex items-center gap-1 rounded-full border border-amber-400/50 bg-amber-400/10 px-2 py-1 font-mono text-[10px] tabular-nums text-amber-200">
            {(selection.start / 1000).toFixed(2)}–{(selection.end / 1000).toFixed(2)}s
            <button type="button" onClick={() => { setSelection(null); regionRef.current = null }} title="Clear selection" className="text-amber-200/70 hover:text-amber-100">
              <X className="size-3" />
            </button>
          </span>
        )}
        <span className="ml-auto text-[9px] text-muted-foreground/70">drag a lane to loop a slice</span>
      </div>

      {/* ORIGINAL lane — word text + the snapped cut in its true (pre-insertion) time. */}
      <div className="relative">
        <div className="absolute -top-2 left-2 z-20 rounded bg-muted px-1 py-px text-[9px] font-bold text-muted-foreground">ORIGINAL</div>
        <div
          className="relative h-14 cursor-ew-resize overflow-hidden rounded border border-border bg-muted/20"
          onMouseDown={onLaneDown('original')}
        >
          <div className="absolute inset-y-0 left-0 opacity-80" style={{ width: pct(original?.durationMs ?? 0) }}>
            <WaveformLane peaks={original?.peaks ?? null} durMs={original?.durationMs ?? null} trimStartMs={0} trimEndMs={0} fadeInMs={0} fadeOutMs={0} />
          </div>
          {selection && (
            <div className="pointer-events-none absolute inset-y-0 z-0 border-x border-amber-300/60 bg-amber-300/15" style={{ left: pct(selection.start), width: selWidth }} />
          )}
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
          className="relative h-14 cursor-ew-resize overflow-hidden rounded border border-border bg-muted/20"
          onMouseDown={onLaneDown('adjusted')}
        >
          <div className="absolute inset-y-0 left-0" style={{ width: pct(adjusted.durationMs) }}>
            <WaveformLane peaks={adjusted.peaks} durMs={adjusted.durationMs} trimStartMs={0} trimEndMs={0} fadeInMs={0} fadeOutMs={0} />
          </div>
          {selection && (
            <div className="pointer-events-none absolute inset-y-0 z-0 border-x border-amber-300/60 bg-amber-300/15" style={{ left: pct(selection.start), width: selWidth }} />
          )}
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
        </div>
      </div>

      <TimeRuler durationMs={maxDurMs} />

      {/* Amber playhead — pins the current position across both lanes, like the decks. */}
      {positionMs > 0 && (
        <div className="pointer-events-none absolute inset-x-0 top-6 bottom-4 z-30" style={{ left: pct(positionMs) }}>
          <div className="absolute inset-y-0 w-0.5 -translate-x-1/2" style={{ backgroundColor: 'hsl(38 95% 62%)' }} />
          <div className="absolute -top-1 size-1.5 -translate-x-1/2 rotate-45" style={{ backgroundColor: 'hsl(38 95% 62%)' }} />
        </div>
      )}
      {hoverPct !== null && hoverMs !== null && (
        <>
          <div className="pointer-events-none absolute inset-x-0 top-6 bottom-4 z-30" style={{ left: `${hoverPct}%` }}>
            <div className="absolute inset-y-0 w-px bg-cyan-300/70" />
          </div>
          <span className="pointer-events-none absolute top-6 z-30 rounded bg-background/90 px-1 text-[9px] font-mono tabular-nums text-cyan-200 shadow-sm" style={{ left: `${hoverPct}%`, transform: hoverPct <= 8 ? 'translateX(0)' : hoverPct >= 92 ? 'translateX(-100%)' : 'translateX(-50%)' }}>
            {(hoverMs / 1000).toFixed(2)}s{hovered ? ` · "${hovered.text}" ${(hovered.score * 100).toFixed(0)}%` : ''}
          </span>
        </>
      )}

      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[9px] text-muted-foreground">
        <span>click to seek · drag to select &amp; loop</span>
        <span>◆ manufactured pause</span>
        <span>● natural boundary</span>
        <span className="text-cyan-300">sentence</span>
        <span className="text-warning">clause</span>
        <span className="italic text-muted-foreground/50">uncertain (skipped)</span>
      </div>
    </div>
  )
}

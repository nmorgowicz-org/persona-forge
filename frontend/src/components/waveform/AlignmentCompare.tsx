import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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

export function AlignmentCompare({ voiceId, adjustedBase64 = null, adjustedSampleCount = null, boundaryPlan = [], boundaries, overrides = {}, onNudgeTarget, onResetTarget, stylePreset }: {
  voiceId: string
  // Absent when there is no prosody-adjusted preview yet — the strip then shows only the
  // original clip (word labels, transport, hover) with no second lane or cut markers.
  adjustedBase64?: string | null
  adjustedSampleCount?: number | null
  boundaryPlan?: ProsodyPausePlanEntry[]
  boundaries: AlignmentBoundary[] | null
  // Per-boundary target deltas (ms) keyed by rounded at_ms, and callbacks to change them by
  // dragging a manufactured pause's trailing edge. Absent callbacks = read-only (e.g. busy).
  overrides?: Record<string, number>
  onNudgeTarget?: (key: string, deltaMs: number) => void
  onResetTarget?: (key: string) => void
  // The prosody style preset this adjusted clip was rendered with — mirrors the label on the
  // preview deck above so the choice stays visible all the way down to this lane.
  stylePreset?: string
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

  const hasAdjusted = adjustedBase64 != null
  const maxDurMs = Math.max(original?.durationMs ?? 0, adjusted?.durationMs ?? 0, 1)
  const pct = (ms: number) => `${Math.max(0, Math.min(100, (ms / maxDurMs) * 100))}%`
  const cutMs = (sample: number) => (adjusted && adjustedSampleCount ? (sample / Math.max(1, adjustedSampleCount)) * adjusted.durationMs : 0)

  const words = useMemo(() => (boundaries ?? []).filter((b) => b.text), [boundaries])

  const laneAudio = useCallback(
    (lane: 'original' | 'adjusted') => (lane === 'original' ? origAudio.current : adjAudio.current),
    [origAudio, adjAudio],
  )

  // Cut positions per lane (original lane in src time, adjusted in rendered time) so a
  // drag-selection can snap its edges to the boundaries we actually cut at.
  const snapPointsFor = (lane: 'original' | 'adjusted') =>
    boundaryPlan.map((m) => (lane === 'original' ? m.src_cut_ms ?? m.at_ms : cutMs(m.cut_sample)))
  const snapMs = (ms: number, lane: 'original' | 'adjusted') => {
    const tol = maxDurMs * 0.02
    let best = ms
    let bestD = tol
    for (const p of snapPointsFor(lane)) {
      const d = Math.abs(p - ms)
      if (d < bestD) {
        bestD = d
        best = p
      }
    }
    return best
  }

  const containerRef = useRef<HTMLDivElement | null>(null)
  // Which lane space/keyboard transport acts on — the last one the user played. Defaults to
  // whichever lane actually exists — 'adjusted' when there's a preview, else 'original'.
  const lastLaneRef = useRef<'original' | 'adjusted'>(hasAdjusted ? 'adjusted' : 'original')
  const rafRef = useRef<number | undefined>(undefined)
  // The active play region (loop bounds) and loop flag are read inside the rAF loop, so
  // keep them in refs to dodge stale closures.
  const regionRef = useRef<{ start: number; end: number } | null>(null)
  const loopRef = useRef(loop)
  loopRef.current = loop
  const dragRef = useRef<{ lane: 'original' | 'adjusted'; startMs: number; endMs: number; moved: boolean } | null>(null)
  // A live drag on a manufactured pause's trailing edge — resizes the inserted gap. Kept in a
  // ref for the math, mirrored into state so the band grows under the cursor before re-preview.
  const markerDragRef = useRef<{ key: string; baseInsertMs: number; startX: number; deltaMs: number } | null>(null)
  const [liveNudge, setLiveNudge] = useState<{ key: string; insertMs: number } | null>(null)

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
  }, [playing, laneAudio])

  const startPlay = (lane: 'original' | 'adjusted', fromMs: number, region: { start: number; end: number } | null) => {
    const el = laneAudio(lane)
    laneAudio(lane === 'original' ? 'adjusted' : 'original')?.pause()
    if (!el) return
    regionRef.current = region
    lastLaneRef.current = lane
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
    // Play the selection if one is set, else the whole lane from the playhead — but if the
    // playhead is sitting at (or past) this lane's own end, e.g. it just finished playing,
    // restart from the top instead of no-op'ing at the tail.
    if (selection) {
      startPlay(lane, selection.start, selection)
      return
    }
    const el = laneAudio(lane)
    const durMs = el && Number.isFinite(el.duration) ? el.duration * 1000 : Infinity
    startPlay(lane, positionMs >= durMs - 25 ? 0 : positionMs, null)
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

  // Start resizing a manufactured pause. Stops propagation so the lane's select-drag doesn't fire.
  const onMarkerDown = (key: string, baseInsertMs: number) => (e: React.MouseEvent) => {
    if (!onNudgeTarget) return
    e.preventDefault()
    e.stopPropagation()
    markerDragRef.current = { key, baseInsertMs, startX: e.clientX, deltaMs: 0 }
    setLiveNudge({ key, insertMs: baseInsertMs })
  }

  const onStripMove = (e: React.MouseEvent) => {
    const r = containerRef.current?.getBoundingClientRect()
    if (r) setHoverPct(Math.max(0, Math.min(100, ((e.clientX - r.left) / r.width) * 100)))
    const m = markerDragRef.current
    if (m && r) {
      m.deltaMs = ((e.clientX - m.startX) / r.width) * maxDurMs
      setLiveNudge({ key: m.key, insertMs: Math.max(0, m.baseInsertMs + m.deltaMs) })
      return
    }
    const d = dragRef.current
    if (!d) return
    d.endMs = msAtClientX(e.clientX)
    if (Math.abs(d.endMs - d.startMs) > 40) d.moved = true
    setSelection({ start: Math.min(d.startMs, d.endMs), end: Math.max(d.startMs, d.endMs) })
  }

  const finishDrag = () => {
    const m = markerDragRef.current
    if (m) {
      markerDragRef.current = null
      setLiveNudge(null)
      if (Math.abs(m.deltaMs) > 5) onNudgeTarget?.(m.key, m.deltaMs)
      return
    }
    const d = dragRef.current
    dragRef.current = null
    if (!d) return
    if (!d.moved) {
      setSelection(null)
      regionRef.current = null
      seekTo(d.startMs)
      return
    }
    const rawStart = Math.min(d.startMs, d.endMs)
    const rawEnd = Math.max(d.startMs, d.endMs)
    // Snap each edge to the nearest cut in this lane; fall back to raw if snapping collapses it.
    const start = snapMs(rawStart, d.lane)
    const end = snapMs(rawEnd, d.lane)
    const region = end - start > 30 ? { start, end } : { start: rawStart, end: rawEnd }
    setSelection(region)
    startPlay(d.lane, region.start, region)
  }

  // Keyboard transport: space = play/pause the last lane, L = loop, ←/→ = step the playhead
  // (hold Shift for a fine 20 ms nudge instead of 100 ms).
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault()
      togglePlay(playing ?? lastLaneRef.current)
    } else if (e.key === 'l' || e.key === 'L') {
      e.preventDefault()
      setLoop((v) => !v)
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault()
      const step = (e.shiftKey ? 20 : 100) * (e.key === 'ArrowRight' ? 1 : -1)
      seekTo(Math.max(0, Math.min(maxDurMs, positionMs + step)))
    }
  }

  if (hasAdjusted && !adjusted) return null
  if (!hasAdjusted && !original) {
    return <p className="text-xs text-muted-foreground">Loading waveform…</p>
  }

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
        playing === lane ? 'border-warning bg-warning/15 text-warning' : 'border-border bg-background/60 text-foreground/80 hover:bg-background'
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
      tabIndex={0}
      role="group"
      aria-label="A/B waveform comparison"
      data-testid="alignment-compare"
      className="relative select-none space-y-1 rounded outline-none focus-visible:ring-1 focus-visible:ring-warning/50"
      onMouseMove={onStripMove}
      onMouseUp={finishDrag}
      onMouseLeave={() => { setHoverPct(null); finishDrag() }}
      onMouseDownCapture={() => containerRef.current?.focus()}
      onKeyDown={onKeyDown}
    >
      {/* Transport — A/B play, loop, and the current drag-selection. */}
      <div className="flex items-center gap-2 pb-0.5">
        <TransportButton lane="original" />
        {hasAdjusted && <TransportButton lane="adjusted" />}
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
          <span className="inline-flex items-center gap-1 rounded-full border border-warning/50 bg-warning/10 px-2 py-1 font-mono text-[10px] tabular-nums text-warning">
            {(selection.start / 1000).toFixed(2)}–{(selection.end / 1000).toFixed(2)}s
            <button type="button" onClick={() => { setSelection(null); regionRef.current = null }} title="Clear selection" className="text-warning/70 hover:text-warning">
              <X className="size-3" />
            </button>
          </span>
        )}
        <span className="ml-auto text-[9px] text-muted-foreground/70">drag to loop a slice · space play · L loop · ←/→ step</span>
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
            <div className="pointer-events-none absolute inset-y-0 z-0 border-x border-warning/60 bg-warning/15" style={{ left: pct(selection.start), width: selWidth }} />
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

      {/* ADJUSTED lane — cut markers + manufactured-gap shading in rendered time. Only
          rendered once a prosody-adjusted preview actually exists. */}
      {hasAdjusted && adjusted && (
      <div className="relative">
        <div className="absolute -top-2 left-2 z-20 rounded bg-cyan-500 px-1 py-px text-[9px] font-bold text-white">
          {stylePreset ? `${stylePreset.toUpperCase()} ADJUSTED` : 'ADJUSTED'}
        </div>
        <div
          className="relative h-14 cursor-ew-resize overflow-hidden rounded border border-border bg-muted/20"
          onMouseDown={onLaneDown('adjusted')}
        >
          <div className="absolute inset-y-0 left-0" style={{ width: pct(adjusted.durationMs) }}>
            <WaveformLane peaks={adjusted.peaks} durMs={adjusted.durationMs} trimStartMs={0} trimEndMs={0} fadeInMs={0} fadeOutMs={0} />
          </div>
          {selection && (
            <div className="pointer-events-none absolute inset-y-0 z-0 border-x border-warning/60 bg-warning/15" style={{ left: pct(selection.start), width: selWidth }} />
          )}
          {boundaryPlan.map((marker, index) => {
            const start = cutMs(marker.cut_sample)
            const manufactured = marker.insert_ms > 0
            const key = String(Math.round(marker.at_ms))
            // While dragging this marker, grow the band under the cursor; otherwise use the plan.
            const insertMs = liveNudge?.key === key ? liveNudge.insertMs : marker.insert_ms
            const overridden = overrides[key] != null
            const color = marker.origin === 'alignment' ? 'border-cyan-300 text-cyan-300' : marker.origin === 'vad' ? 'border-warning text-warning' : 'border-violet-300 text-violet-300'
            const title = `${manufactured ? 'Manufactured' : 'Natural'} ${marker.origin} boundary\nTarget ${marker.target_ms.toFixed(0)} ms · inserted ${insertMs.toFixed(0)} ms${overridden ? ` (nudged ${overrides[key] > 0 ? '+' : ''}${overrides[key].toFixed(0)} ms)` : ''}\n${marker.provenance.replace('_', ' ')}${onNudgeTarget && manufactured ? '\nDrag the edge to resize · double-click to reset' : ''}`
            return (
              <span key={`${marker.cut_sample}-${index}`}>
                {manufactured && (
                  <span className={`pointer-events-none absolute inset-y-0 z-0 ${overridden || liveNudge?.key === key ? 'bg-warning/20' : 'bg-cyan-400/15'}`} style={{ left: pct(start), width: pct(insertMs) }} />
                )}
                <span className={`pointer-events-none absolute inset-y-0 z-10 -translate-x-1/2 border-l-2 ${manufactured ? 'border-solid' : 'border-dashed'} ${color}`} style={{ left: pct(start) }} title={title} aria-label={title}>
                  <span className={`absolute left-1/2 top-1 -translate-x-1/2 border-current bg-background ${manufactured ? 'size-2 rotate-45 border' : 'size-2 rounded-full border-2'}`} />
                </span>
                {/* Trailing-edge resize handle — drag to lengthen/shorten the inserted silence. */}
                {manufactured && onNudgeTarget && (
                  <span
                    className="group absolute inset-y-0 z-20 flex w-3 -translate-x-1/2 cursor-ew-resize items-center justify-center"
                    style={{ left: pct(start + insertMs) }}
                    onMouseDown={onMarkerDown(key, marker.insert_ms)}
                    onDoubleClick={(e) => { e.stopPropagation(); if (overridden) onResetTarget?.(key) }}
                    title={title}
                  >
                    <span className={`h-2/3 w-0.5 rounded ${overridden || liveNudge?.key === key ? 'bg-warning' : 'bg-cyan-300/70 group-hover:bg-cyan-200'}`} />
                  </span>
                )}
              </span>
            )
          })}
        </div>
      </div>
      )}

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
        <span>◆ manufactured pause{onNudgeTarget ? ' · drag its edge to resize, double-click to reset' : ''}</span>
        <span>● natural boundary</span>
        <span className="text-cyan-300">sentence</span>
        <span className="text-warning">clause</span>
        <span className="italic text-muted-foreground/50">uncertain (skipped)</span>
      </div>
    </div>
  )
}

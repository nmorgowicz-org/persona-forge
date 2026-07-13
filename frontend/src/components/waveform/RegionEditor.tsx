import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { Plus, Scissors, Trash2, Volume2, X } from 'lucide-react'
import type { ProsodyPausePlanEntry, StitchPlanRegionEdit } from '@/lib/api'
import { base64ToBlob } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { MiniAudioDeck } from '@/components/audio/MiniAudioDeck'
import { WaveformLane } from './WaveformLane'
import { TimeRuler } from './TimeRuler'
import { encodeRegionWav, renderRegionEdits, type RegionAudio } from './regionAudio'

type Selection = { startMs: number; endMs: number }
type DecodedAudio = RegionAudio

export function RegionEditor({ audioBase64, edits = [], pauseIntervals = [], boundaryPlan = [], sampleCount, readOnly = false, showPlayer = true, onChange, onApply, onClose, busy = false }: {
  audioBase64: string
  edits?: StitchPlanRegionEdit[]
  pauseIntervals?: [number, number][]
  boundaryPlan?: ProsodyPausePlanEntry[]
  sampleCount?: number
  readOnly?: boolean
  showPlayer?: boolean
  onChange?: (edits: StitchPlanRegionEdit[]) => void
  onApply?: () => void
  onClose?: () => void
  busy?: boolean
}) {
  const laneRef = useRef<HTMLDivElement>(null)
  const [durationMs, setDurationMs] = useState(0)
  const [peaks, setPeaks] = useState<number[]>([])
  const [selection, setSelection] = useState<Selection | null>(null)
  const [silenceMs, setSilenceMs] = useState(250)
  const [audioUrl, setAudioUrl] = useState('')
  const [decoded, setDecoded] = useState<DecodedAudio | null>(null)
  const [hoverMs, setHoverMs] = useState<number | null>(null)

  useEffect(() => {
    const blob = base64ToBlob(audioBase64)
    const url = URL.createObjectURL(blob)
    setAudioUrl(url)
    let cancelled = false
    const ctx = new AudioContext()
    void blob.arrayBuffer().then((data) => ctx.decodeAudioData(data)).then((buffer) => {
      if (cancelled) return
      setDecoded({ channels: Array.from({ length: buffer.numberOfChannels }, (_, index) => new Float32Array(buffer.getChannelData(index))), sampleRate: buffer.sampleRate })
    }).finally(() => void ctx.close())
    return () => { cancelled = true; URL.revokeObjectURL(url) }
  }, [audioBase64])

  useEffect(() => {
    if (!decoded) return
    const channels = renderRegionEdits(decoded, edits)
    const blob = encodeRegionWav(channels, decoded.sampleRate)
    const url = URL.createObjectURL(blob)
    setAudioUrl((previous) => { if (previous) URL.revokeObjectURL(previous); return url })
    setDurationMs(Math.round((channels[0].length / decoded.sampleRate) * 1000))
    const channel = channels[0]
    const count = 160
    const width = Math.max(1, Math.floor(channel.length / count))
    const values = Array.from({ length: count }, (_, index) => { let peak = 0; for (let i = index * width; i < Math.min(channel.length, (index + 1) * width); i++) peak = Math.max(peak, Math.abs(channel[i])); return peak })
    const max = Math.max(...values, 0.01)
    setPeaks(values.map((value) => value / max))
    return () => URL.revokeObjectURL(url)
  }, [decoded, edits])

  const selected = selection ?? { startMs: 0, endMs: Math.min(300, durationMs) }
  const pointToMs = (clientX: number) => {
    const rect = laneRef.current?.getBoundingClientRect()
    if (!rect) return 0
    return Math.round(Math.max(0, Math.min(1, (clientX - rect.left) / rect.width)) * durationMs)
  }
  const normalized = (a: number, b: number): Selection => {
    const startMs = Math.min(a, b)
    return { startMs, endMs: Math.max(Math.min(durationMs, Math.max(a, b)), startMs + 10) }
  }
  const startSelection = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (readOnly) return
    event.preventDefault()
    const start = pointToMs(event.clientX)
    setSelection(normalized(start, start + 10))
    const move = (next: MouseEvent) => setSelection(normalized(start, pointToMs(next.clientX)))
    const up = () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up) }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }
  const add = (edit: StitchPlanRegionEdit) => onChange?.([...edits, edit])
  const selectionStyle = useMemo(() => {
    const s = selection ?? { startMs: 0, endMs: Math.min(300, durationMs) }
    return { left: `${s.startMs / Math.max(1, durationMs) * 100}%`, width: `${(s.endMs - s.startMs) / Math.max(1, durationMs) * 100}%` }
  }, [durationMs, selection])

  const renderedSamples = sampleCount ?? decoded?.channels[0]?.length ?? 0
  const originClass = (origin: ProsodyPausePlanEntry['origin']) =>
    origin === 'alignment' ? 'border-cyan-300 text-cyan-300' : origin === 'vad' ? 'border-warning text-warning' : 'border-violet-300 text-violet-300'

  return <div className={readOnly ? 'space-y-1.5' : 'space-y-3 border-t border-border/60 pt-3'}>
    {!readOnly && <div className="flex items-center justify-between"><div><p className="text-xs font-medium">Reference audio editor</p><p className="text-[10px] text-muted-foreground">Playback and waveform include all queued edits.</p></div><Button size="icon-sm" variant="ghost" aria-label="Close audio editor" tooltip="Close audio editor" onClick={onClose}><X /></Button></div>}
    {showPlayer && audioUrl && <MiniAudioDeck src={audioUrl} autoPlay={false} />}
    <div ref={laneRef} className={`relative h-20 overflow-hidden rounded border border-border bg-muted/20 ${readOnly ? 'cursor-default' : 'cursor-crosshair'}`} onMouseDown={startSelection} onMouseMove={(event) => setHoverMs(pointToMs(event.clientX))} onMouseLeave={() => setHoverMs(null)}>
      <WaveformLane peaks={peaks} durMs={durationMs} trimStartMs={0} trimEndMs={0} fadeInMs={0} fadeOutMs={0} />
      {pauseIntervals.map(([start, end], index) => <div key={`${start}-${end}-${index}`} className="pointer-events-none absolute inset-y-0 border-x border-warning/40 bg-warning/10" style={{ left: `${start * 1000 / Math.max(1, durationMs) * 100}%`, width: `${(end - start) * 1000 / Math.max(1, durationMs) * 100}%` }} />)}
      {boundaryPlan.map((marker, index) => {
        const pct = Math.max(0, Math.min(100, marker.cut_sample / Math.max(1, renderedSamples) * 100))
        const manufactured = marker.insert_ms > 0
        const title = `${manufactured ? 'Manufactured' : 'Natural'} ${marker.origin} boundary\nTarget ${marker.target_ms.toFixed(0)} ms · inserted ${marker.insert_ms.toFixed(0)} ms\n${marker.provenance.replace('_', ' ')} · sample ${marker.cut_sample}`
        return <div key={`${marker.cut_sample}-${index}`} className={`absolute inset-y-0 z-10 -translate-x-1/2 border-l-2 ${manufactured ? 'border-solid' : 'border-dashed'} ${originClass(marker.origin)}`} style={{ left: `${pct}%` }} title={title} aria-label={title}>
          <span className={`absolute left-1/2 top-1 -translate-x-1/2 border-current bg-background ${manufactured ? 'size-2 rotate-45 border' : 'size-2 rounded-full border-2'}`} />
        </div>
      })}
      {!readOnly && <div className="pointer-events-none absolute inset-y-0 border-x border-cyan-400 bg-cyan-400/15" style={selectionStyle} />}
      {hoverMs !== null && durationMs > 0 && (() => {
        const pct = hoverMs / durationMs * 100
        return <>
          <div className="pointer-events-none absolute inset-y-0 z-10 w-px bg-cyan-300" style={{ left: `${pct}%` }} />
          <span className="pointer-events-none absolute top-0.5 z-10 rounded bg-background/90 px-1 text-[9px] font-mono tabular-nums text-cyan-200 shadow-sm" style={{ left: `${pct}%`, transform: pct <= 8 ? 'translateX(0)' : pct >= 92 ? 'translateX(-100%)' : 'translateX(-50%)' }}>{(hoverMs / 1000).toFixed(3)}s</span>
        </>
      })()}
    </div>
    <TimeRuler durationMs={durationMs} />
    {readOnly ? (
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[9px] text-muted-foreground">
        <span>◆ manufactured</span><span>● natural</span><span className="text-cyan-300">alignment</span><span className="text-warning">VAD fallback</span><span className="text-violet-300">energy fallback</span>
      </div>
    ) : <p className="text-[10px] tabular-nums text-muted-foreground">Selection {selected.startMs}-{selected.endMs}ms ({(selected.startMs / 1000).toFixed(3)}-{(selected.endMs / 1000).toFixed(3)}s) · cursor {hoverMs !== null ? `${(hoverMs / 1000).toFixed(3)}s` : '—'} · amber regions are detected pauses</p>}
    {!readOnly && <>
    <div className="flex flex-wrap items-center gap-2">
      <Button size="sm" variant="outline" onClick={() => add({ type: 'delete', startMs: selected.startMs, endMs: selected.endMs })}><Scissors /> Delete</Button>
      <Button size="sm" variant="outline" onClick={() => add({ type: 'fade', startMs: selected.startMs, endMs: selected.endMs, fadeInMs: 50, fadeOutMs: 50 })}><Volume2 /> Fade</Button>
      <input className="h-8 w-20 rounded border border-border bg-background px-2 text-xs" type="number" min={10} max={5000} step={10} value={silenceMs} onChange={(e) => setSilenceMs(Number(e.target.value) || 10)} aria-label="Silence duration in milliseconds" />
      <Button size="sm" variant="outline" onClick={() => add({ type: 'insert_silence', atMs: selected.startMs, durationMs: silenceMs })}><Plus /> Before</Button>
      <Button size="sm" variant="outline" onClick={() => add({ type: 'insert_silence', atMs: selected.endMs, durationMs: silenceMs })}><Plus /> After</Button>
    </div>
    {edits.map((edit, index) => <div key={`${edit.type}-${index}`} className="flex items-center justify-between rounded bg-muted/30 px-2 py-1 text-[10px]"><span>{edit.type === 'insert_silence' ? `silence ${edit.durationMs}ms at ${edit.atMs}ms` : `${edit.type} ${edit.startMs}-${edit.endMs}ms`}</span><Button size="icon-sm" variant="ghost" aria-label="Remove edit" tooltip="Remove edit" onClick={() => onChange?.(edits.filter((_, i) => i !== index))}><Trash2 /></Button></div>)}
    <div className="flex justify-end gap-2"><Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button><Button size="sm" disabled={busy || edits.length === 0} onClick={onApply}>Apply edits</Button></div>
    </>}
  </div>
}

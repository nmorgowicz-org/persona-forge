import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Play, Plus, Shuffle, Square, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

interface ModelEntry {
  id: string
  label: string
  installed?: boolean
  capabilities: { clone?: boolean }
}
interface VoiceEntry {
  voice_id: string
  engine: string | null
  kind: 'library' | 'preset'
  display_name: string
}
interface Slot {
  engine: string
  voice: string
}
interface Result {
  status: 'idle' | 'running' | 'done' | 'error'
  url?: string
  ms?: number
  seconds?: number
  gain?: number
  error?: string
}
interface Rating {
  naturalness: number
  artifacts: number
  favourite: boolean
}

const SAMPLES = [
  'Hello there. Your timer is set for ten minutes, and the kitchen lights are now on.',
  'Invoice AB-104 totals $1,234.56, due on the 23rd at 3:30 PM.',
  'I did not expect that at all, but honestly, it turned out better than I had hoped.',
]
const TARGET_RMS_DB = -23
const STORE_KEY = 'pf-compare-results'
const LETTERS = 'ABCD'
const clock = () => performance.now()
const DEFAULT_RATING: Rating = { naturalness: 3, artifacts: 3, favourite: false }

function shuffled<T>(items: T[]): T[] {
  const copy = [...items]
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
  }
  return copy
}

/** Gain that brings a clip to the target loudness without clipping. */
function levelGain(buffer: AudioBuffer): number {
  const data = buffer.getChannelData(0)
  let sum = 0
  let peak = 0
  for (let i = 0; i < data.length; i++) {
    sum += data[i] * data[i]
    peak = Math.max(peak, Math.abs(data[i]))
  }
  const rms = Math.sqrt(sum / Math.max(data.length, 1)) || 1e-6
  const wanted = Math.pow(10, TARGET_RMS_DB / 20) / rms
  return peak > 0 ? Math.min(wanted, 0.98 / peak) : 1
}

export function CompareTab() {
  const [models, setModels] = useState<ModelEntry[]>([])
  const [voices, setVoices] = useState<VoiceEntry[]>([])
  const [text, setText] = useState(SAMPLES[0])
  const [slots, setSlots] = useState<Slot[]>([])
  const [results, setResults] = useState<Result[]>([])
  const [order, setOrder] = useState<number[]>([])
  const [blind, setBlind] = useState(true)
  const [revealed, setRevealed] = useState(false)
  const [ratings, setRatings] = useState<Record<number, Rating>>({})
  const [running, setRunning] = useState(false)
  const [playing, setPlaying] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const buffers = useRef<Record<number, AudioBuffer>>({})
  const audio = useRef<{ ctx: AudioContext; source?: AudioBufferSourceNode } | null>(null)

  useEffect(() => {
    Promise.all([fetch('/v1/models').then((r) => r.json()), fetch('/v1/audio/voices').then((r) => r.json())])
      .then(([m, v]) => {
        const list: ModelEntry[] = m.data ?? []
        setModels(list)
        setVoices(v.data ?? [])
        const ready = list.filter((e) => e.installed !== false)
        setSlots(ready.slice(0, 2).map((e) => ({ engine: e.id, voice: '' })))
      })
      .catch((err: unknown) => setError(String((err as Error)?.message || err)))
  }, [])

  function voicesFor(engine: string): VoiceEntry[] {
    const info = models.find((m) => m.id === engine)
    return voices.filter(
      (v) => (v.kind === 'preset' && v.engine === engine) || (v.kind === 'library' && info?.capabilities.clone),
    )
  }

  function updateSlot(index: number, change: Partial<Slot>) {
    setSlots((current) => current.map((slot, i) => (i === index ? { ...slot, ...change } : slot)))
  }

  async function generate() {
    stop()
    setError(null)
    setRunning(true)
    setRevealed(false)
    setRatings({})
    setOrder(shuffled(slots.map((_, i) => i)))
    setResults(slots.map(() => ({ status: 'idle' })))
    const ctx = (audio.current ??= { ctx: new AudioContext() }).ctx
    for (let i = 0; i < slots.length; i++) {
      setResults((cur) => cur.map((r, k) => (k === i ? { status: 'running' } : r)))
      const slot = slots[i]
      const voice = slot.voice || voicesFor(slot.engine)[0]?.voice_id
      const started = clock()
      try {
        const res = await fetch('/v1/audio/speech', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: slot.engine, input: text, voice, response_format: 'wav' }),
        })
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(body?.error?.message || `HTTP ${res.status}`)
        }
        const bytes = await res.arrayBuffer()
        const ms = clock() - started
        const decoded = await ctx.decodeAudioData(bytes.slice(0))
        const url = URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }))
        setResults((cur) =>
          cur.map((r, k) =>
            k === i ? { status: 'done', url, ms, seconds: decoded.duration, gain: levelGain(decoded) } : r,
          ),
        )
        buffers.current[i] = decoded
      } catch (err) {
        setResults((cur) =>
          cur.map((r, k) => (k === i ? { status: 'error', error: String((err as Error)?.message || err) } : r)),
        )
      }
    }
    setRunning(false)
  }

  function stop() {
    audio.current?.source?.stop()
    setPlaying(null)
  }

  function play(index: number) {
    const buffer = buffers.current[index]
    const result = results[index]
    if (!buffer || !audio.current) return
    stop()
    const { ctx } = audio.current
    const source = ctx.createBufferSource()
    const gain = ctx.createGain()
    gain.gain.value = result?.gain ?? 1
    source.buffer = buffer
    source.connect(gain).connect(ctx.destination)
    source.onended = () => setPlaying((p) => (p === index ? null : p))
    source.start()
    audio.current.source = source
    setPlaying(index)
  }

  function rate(index: number, change: Partial<Rating>) {
    setRatings((cur) => ({
      ...cur,
      [index]: { ...DEFAULT_RATING, ...cur[index], ...change },
    }))
  }

  function favourite(index: number) {
    setRatings((cur) => {
      const next: Record<number, Rating> = {}
      for (const i of slots.keys()) {
        next[i] = { ...DEFAULT_RATING, ...cur[i], favourite: i === index }
      }
      return next
    })
  }

  function reveal() {
    setRevealed(true)
    try {
      const saved = JSON.parse(localStorage.getItem(STORE_KEY) || '[]')
      saved.push({
        at: new Date().toISOString(),
        text,
        slots: slots.map((slot, i) => ({
          ...slot,
          ms: results[i]?.ms,
          seconds: results[i]?.seconds,
          ...(ratings[i] ?? {}),
        })),
      })
      localStorage.setItem(STORE_KEY, JSON.stringify(saved.slice(-200)))
    } catch {
      // Ratings are a convenience; failing to save them must not hide the reveal.
    }
  }

  const done = results.filter((r) => r.status === 'done').length
  const showNames = !blind || revealed
  const display = useMemo(() => (blind ? order : slots.map((_, i) => i)), [blind, order, slots])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <label className="text-xs font-medium" htmlFor="compare-text">Text</label>
        <textarea
          id="compare-text"
          className="min-h-20 rounded-control border border-border bg-background p-2 text-sm"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <div className="flex flex-wrap gap-1.5">
          {SAMPLES.map((sample) => (
            <Button key={sample} type="button" size="xs" variant="outline" onClick={() => setText(sample)}>
              {sample.slice(0, 28)}…
            </Button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {slots.map((slot, index) => (
          <div key={index} className="flex flex-wrap items-center gap-2 text-xs">
            <select
              className="rounded-control border border-border bg-background px-2 py-1"
              aria-label={`Engine for slot ${index + 1}`}
              value={slot.engine}
              onChange={(event) => updateSlot(index, { engine: event.target.value, voice: '' })}
            >
              {models.map((m) => (
                <option key={m.id} value={m.id} disabled={m.installed === false}>
                  {m.label}
                  {m.installed === false ? ' (install to compare)' : ''}
                </option>
              ))}
            </select>
            <select
              className="max-w-64 rounded-control border border-border bg-background px-2 py-1"
              aria-label={`Voice for slot ${index + 1}`}
              value={slot.voice}
              onChange={(event) => updateSlot(index, { voice: event.target.value })}
            >
              {voicesFor(slot.engine).map((v) => (
                <option key={v.voice_id} value={v.voice_id}>
                  {v.display_name}
                </option>
              ))}
            </select>
            <Button
              type="button"
              size="xs"
              variant="ghost"
              disabled={slots.length <= 2}
              onClick={() => setSlots((cur) => cur.filter((_, i) => i !== index))}
            >
              <Trash2 />
              Remove
            </Button>
          </div>
        ))}
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="xs"
            variant="outline"
            disabled={slots.length >= 4 || models.length === 0}
            onClick={() => setSlots((cur) => [...cur, { engine: models[0]?.id ?? '', voice: '' }])}
          >
            <Plus />
            Add slot
          </Button>
          <label className="flex items-center gap-1.5 text-xs">
            <input type="checkbox" checked={blind} onChange={(event) => setBlind(event.target.checked)} />
            <Shuffle className="size-3" />
            Blind mode (hide engine names until you reveal)
          </label>
          <Button type="button" size="sm" disabled={running || slots.length < 2 || !text.trim()} onClick={() => void generate()}>
            {running ? <Loader2 className="animate-spin" /> : <Play />}
            Generate
          </Button>
        </div>
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      {results.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-[11px] text-muted-foreground">
            Clips are level-matched to {TARGET_RMS_DB} dB RMS on playback, so loudness cannot decide the result.
          </p>
          {display.map((slotIndex, position) => {
            const result = results[slotIndex]
            const slot = slots[slotIndex]
            const rating = ratings[slotIndex]
            if (!result || !slot) return null
            return (
              <div key={slotIndex} className="flex flex-col gap-1.5 rounded-control border border-border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className="text-[10px]">
                    {blind ? LETTERS[position] : (models.find((m) => m.id === slot.engine)?.label ?? slot.engine)}
                  </Badge>
                  {showNames && blind && (
                    <span className="text-xs">{models.find((m) => m.id === slot.engine)?.label ?? slot.engine}</span>
                  )}
                  {result.status === 'running' && <Loader2 className="size-3 animate-spin" />}
                  {result.status === 'done' && (
                    <>
                      <Button
                        type="button"
                        size="xs"
                        variant="outline"
                        onClick={() => (playing === slotIndex ? stop() : play(slotIndex))}
                      >
                        {playing === slotIndex ? <Square /> : <Play />}
                        {playing === slotIndex ? 'Stop' : 'Play'}
                      </Button>
                      <span className="text-[11px] text-muted-foreground">
                        {((result.ms ?? 0) / 1000).toFixed(2)} s to generate · {(result.seconds ?? 0).toFixed(1)} s of audio
                      </span>
                    </>
                  )}
                  {result.status === 'error' && <span className="text-[11px] text-destructive">{result.error}</span>}
                </div>
                {result.status === 'done' && (
                  <div className="flex flex-wrap items-center gap-3 text-[11px]">
                    {(['naturalness', 'artifacts'] as const).map((key) => (
                      <label key={key} className="flex items-center gap-1">
                        {key === 'naturalness' ? 'Natural' : 'Clean (no artifacts)'}
                        <select
                          className="rounded-control border border-border bg-background px-1"
                          value={rating?.[key] ?? 3}
                          onChange={(event) => rate(slotIndex, { [key]: Number(event.target.value) })}
                        >
                          {[1, 2, 3, 4, 5].map((n) => (
                            <option key={n} value={n}>{n}</option>
                          ))}
                        </select>
                      </label>
                    ))}
                    <label className="flex items-center gap-1">
                      <input type="radio" name="compare-favourite" checked={rating?.favourite ?? false} onChange={() => favourite(slotIndex)} />
                      Favourite
                    </label>
                  </div>
                )}
              </div>
            )
          })}
          {blind && !revealed && !running && done > 0 && (
            <Button type="button" size="sm" variant="outline" onClick={reveal}>
              Reveal engines and save ratings
            </Button>
          )}
          {revealed && <p className="text-[11px] text-muted-foreground">Saved on this device.</p>}
        </div>
      )}
    </div>
  )
}

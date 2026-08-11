import { memo, useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion, Reorder } from 'motion/react'
import { ChevronUp, ChevronDown, GripVertical, X, Loader2, Play, Pause, Scissors, Trash2, Volume2, VolumeX, Gauge } from 'lucide-react'
import { useAppStore, type StitchPlanClip } from '@/store'
import { base64ToBlob, cn } from '@/lib/utils'
import {
  renderStitchPlan,
  getStitchPacingTargets,
  getSegmentAudioBase64,
  getVoice,
  type StitchPlanPayload,
  type StitchPlanRegionEdit,
  type SegmentMeta,
  type VoiceMeta,
} from '@/lib/api'
import { AudioPlayer } from './AudioPlayer'
import { WaveformLane } from './waveform/WaveformLane'
import { renderRegionEdits } from './waveform/regionAudio'

// Helper for reduced motion
const useReducedMotion = () => {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (media.matches) setReduced(true)
    const listener = (e: MediaQueryListEvent) => setReduced(e.matches)
    media.addEventListener('change', listener)
    return () => media.removeEventListener('change', listener)
  }, [])
  return reduced
}


/* ---------- helpers ---------- */

/* ---------- helpers ---------- */

function clipEffectiveDurationMs(clip: StitchPlanClip): number {
  const base = clip.durationMs ?? 0
  if (!base) return 0
  return Math.max(10, base - clip.trimStartMs - clip.trimEndMs)
}

type RegionEdit =
  | { id: string; type: 'gain'; startMs: number; endMs: number; gainDb: number; fadeInMs: number; fadeOutMs: number }
  | { id: string; type: 'mute'; startMs: number; endMs: number; fadeInMs: number; fadeOutMs: number }
  | { id: string; type: 'delete'; startMs: number; endMs: number }
  | { id: string; type: 'fade'; startMs: number; endMs: number; fadeInMs: number; fadeOutMs: number }
  | { id: string; type: 'insert_silence'; atMs: number; durationMs: number; placement: 'before' | 'after' }

type RegionEditsByClip = Record<string, RegionEdit[]>

function hasRegionEdits(editsByClip: RegionEditsByClip): boolean {
  return Object.values(editsByClip).some((edits) => edits.length > 0)
}

function clampMs(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.round(v)))
}

function makeRegionEditId(type: RegionEdit['type']): string {
  return `${type}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function msToSample(ms: number, sampleRate: number): number {
  return Math.max(0, Math.round((ms / 1000) * sampleRate))
}

function cloneChannels(buffer: AudioBuffer): Float32Array[] {
  return Array.from({ length: buffer.numberOfChannels }, (_, channel) => new Float32Array(buffer.getChannelData(channel)))
}

function sliceChannels(channels: Float32Array[], start: number, end: number): Float32Array[] {
  return channels.map((channel) => channel.slice(start, end))
}

function applyClipFade(channels: Float32Array[], sampleRate: number, fadeInMs: number, fadeOutMs: number) {
  const length = channels[0]?.length ?? 0
  if (!length) return
  const fadeIn = Math.min(length, msToSample(fadeInMs, sampleRate))
  const fadeOut = Math.min(length, msToSample(fadeOutMs, sampleRate))
  for (const channel of channels) {
    for (let i = 0; i < fadeIn; i++) channel[i] *= i / Math.max(1, fadeIn)
    for (let i = 0; i < fadeOut; i++) {
      const idx = length - 1 - i
      channel[idx] *= i / Math.max(1, fadeOut)
    }
  }
}

async function decodeClipAudio(ctx: AudioContext, clip: StitchPlanClip): Promise<AudioBuffer> {
  const blob = base64ToBlob(clip.sourceAudioBase64)
  const arrayBuffer = await blob.arrayBuffer()
  return ctx.decodeAudioData(arrayBuffer.slice(0))
}

function processClipAudio(buffer: AudioBuffer, clip: StitchPlanClip, edits: RegionEdit[]): Float32Array[] {
  const sampleRate = buffer.sampleRate
  const start = msToSample(clip.trimStartMs, sampleRate)
  const end = Math.max(start + 1, buffer.length - msToSample(clip.trimEndMs, sampleRate))
  let channels = sliceChannels(cloneChannels(buffer), start, Math.min(end, buffer.length))

  channels = renderRegionEdits({ channels, sampleRate }, edits)

  applyClipFade(channels, sampleRate, clip.fadeInMs, clip.fadeOutMs)
  return channels
}

function appendWithGapAndCrossfade(
  output: Float32Array[],
  clip: Float32Array[],
  sampleRate: number,
  gapMs: number,
  crossfadeMs: number,
): Float32Array[] {
  if (!output.length) return clip
  const channels = Math.max(output.length, clip.length)
  const gap = msToSample(gapMs, sampleRate)
  const fade = gap > 0 ? 0 : Math.min(msToSample(crossfadeMs, sampleRate), output[0].length, clip[0].length)
  return Array.from({ length: channels }, (_, channelIndex) => {
    const prev = output[channelIndex] ?? output[0]
    const next = clip[channelIndex] ?? clip[0]
    const length = prev.length + gap + next.length - fade
    const merged = new Float32Array(length)
    merged.set(prev, 0)
    if (fade > 0) {
      const start = prev.length - fade
      for (let i = 0; i < fade; i++) {
        const a = 1 - i / fade
        const b = i / fade
        merged[start + i] = prev[start + i] * a + next[i] * b
      }
      merged.set(next.slice(fade), prev.length + gap)
    } else {
      merged.set(next, prev.length + gap)
    }
    return merged
  })
}

function encodeWav(channels: Float32Array[], sampleRate: number): Blob {
  const channelCount = channels.length
  const frameCount = channels[0]?.length ?? 0
  const bytesPerSample = 2
  const dataSize = frameCount * channelCount * bytesPerSample
  const buffer = new ArrayBuffer(44 + dataSize)
  const view = new DataView(buffer)
  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i))
  }
  writeString(0, 'RIFF')
  view.setUint32(4, 36 + dataSize, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, channelCount, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * channelCount * bytesPerSample, true)
  view.setUint16(32, channelCount * bytesPerSample, true)
  view.setUint16(34, bytesPerSample * 8, true)
  writeString(36, 'data')
  view.setUint32(40, dataSize, true)
  let offset = 44
  for (let i = 0; i < frameCount; i++) {
    for (let channel = 0; channel < channelCount; channel++) {
      const sample = Math.max(-1, Math.min(1, channels[channel][i]))
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
      offset += bytesPerSample
    }
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

async function renderEditedStitchPreview(
  clips: StitchPlanClip[],
  paddingMs: number[],
  crossfadeMs: number,
  editsByClip: RegionEditsByClip,
): Promise<Blob> {
  const AudioContextCtor = window.AudioContext || (window as any).webkitAudioContext
  if (!AudioContextCtor) throw new Error('Browser audio rendering is unavailable.')
  const ctx = new AudioContextCtor() as AudioContext
  try {
    let sampleRate = 24000
    let output: Float32Array[] = []
    for (let i = 0; i < clips.length; i++) {
      const clip = clips[i]
      if (!clip.sourceAudioBase64) throw new Error('Region preview needs source audio for every clip.')
      const buffer = await decodeClipAudio(ctx, clip)
      sampleRate = buffer.sampleRate
      const processed = processClipAudio(buffer, clip, editsByClip[clip.clipId] ?? [])
      output = appendWithGapAndCrossfade(output, processed, sampleRate, i > 0 ? paddingMs[i - 1] || 0 : 0, i > 0 ? crossfadeMs : 0)
    }
    return encodeWav(output, sampleRate)
  } finally {
    await ctx.close()
  }
}

/* ---------- sub-components ---------- */

function StitchTimelineClip({
  clip,
  onRemove,
  onUpdate,
  regionEdits,
  onAddRegionEdit,
  onRemoveRegionEdit,
  onSplitRegion,
  isReordering,
  reducedMotion: _reducedMotion,
}: {
  clip: StitchPlanClip
  onRemove: (clipId: string) => void
  onUpdate: (clipId: string, patch: Partial<StitchPlanClip>) => void
  regionEdits: RegionEdit[]
  onAddRegionEdit: (clipId: string, edit: RegionEdit) => void
  onRemoveRegionEdit: (clipId: string, editId: string) => void
  onSplitRegion: (clipId: string, startMs: number, endMs: number) => void
  isReordering?: boolean
  reducedMotion: boolean
}) {
  const [peaks, setPeaks] = useState<number[] | null>(null)
  const [durMs, setDurMs] = useState<number | null>(null)
  const [clipPlaying, setClipPlaying] = useState(false)
  const clipAudioRef = useRef<HTMLAudioElement | null>(null)
  const clipAudioUrlRef = useRef<string | null>(null)
  const [editingText, setEditingText] = useState(false)
  const [draftText, setDraftText] = useState(clip.text ?? '')
  const [selection, setSelection] = useState<{ startMs: number; endMs: number } | null>(null)
  const [gainDb, setGainDb] = useState(-3)
  const [regionFadeInMs, setRegionFadeInMs] = useState(15)
  const [regionFadeOutMs, setRegionFadeOutMs] = useState(35)
  const [silenceMs, setSilenceMs] = useState(180)
  const textInputRef = useRef<HTMLInputElement | null>(null)
  const activeHandle = useRef<'leftTrim' | 'rightTrim' | 'leftFade' | 'rightFade' | null>(null)
  const selectionDrag = useRef<{ startMs: number } | null>(null)
  const laneRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (editingText) textInputRef.current?.focus()
  }, [editingText])

  const beginEditText = () => {
    setDraftText(clip.text ?? '')
    setEditingText(true)
  }

  const commitText = () => {
    setEditingText(false)
    const trimmed = draftText.trim()
    if (trimmed !== (clip.text ?? '')) onUpdate(clip.clipId, { text: trimmed })
  }

  const cancelEditText = () => {
    setEditingText(false)
    setDraftText(clip.text ?? '')
  }

  useEffect(() => {
    return () => {
      clipAudioRef.current?.pause()
      if (clipAudioUrlRef.current) URL.revokeObjectURL(clipAudioUrlRef.current)
    }
  }, [])

  const toggleClipPlay = () => {
    if (!clip.sourceAudioBase64) return
    if (!clipAudioRef.current) {
      const url = URL.createObjectURL(base64ToBlob(clip.sourceAudioBase64))
      clipAudioUrlRef.current = url
      const audio = new Audio(url)
      audio.addEventListener('ended', () => setClipPlaying(false))
      clipAudioRef.current = audio
    }
    if (clipPlaying) {
      clipAudioRef.current.pause()
      setClipPlaying(false)
    } else {
      void clipAudioRef.current.play()
      setClipPlaying(true)
    }
  }

  useEffect(() => {
    let dead = false
    ;(async () => {
      if (!clip.sourceAudioBase64) return
      const blob = base64ToBlob(clip.sourceAudioBase64)
      try {
        const arrayBuffer = await blob.arrayBuffer()
        const ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
        const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0))
        const channel = audioBuffer.getChannelData(0)
        if (!dead) setDurMs(Math.round(audioBuffer.duration * 1000))
        const count = 48
        const bucketSize = Math.max(1, Math.floor(channel.length / count))
        const pks: number[] = []
        for (let i = 0; i < count; i++) {
          const start = i * bucketSize
          const end = Math.min(start + bucketSize, channel.length)
          let max = 0
          for (let j = start; j < end; j++) {
            const abs = Math.abs(channel[j])
            if (abs > max) max = abs
          }
          pks.push(max)
        }
        const overallMax = Math.max(...pks, 0.01)
        if (!dead) setPeaks(pks.map((p) => p / overallMax))
        ctx.close()
      } catch {
        if (!dead) setPeaks([])
      }
    })()
    return () => { dead = true }
  }, [clip.sourceAudioBase64])

  const effectiveDuration = clipEffectiveDurationMs(clip)

  const clampTrimStart = useCallback((v: number) => {
    const nv = Math.max(0, Math.min(v, (durMs ?? 0) - 20))
    if (nv + clip.trimEndMs >= (durMs ?? 0)) return durMs ? durMs - 20 - clip.trimEndMs : 0
    return nv
  }, [clip.trimEndMs, durMs])
  const clampTrimEnd = useCallback((v: number) => {
    const nv = Math.max(0, Math.min(v, (durMs ?? 0) - 20))
    if (nv + clip.trimStartMs >= (durMs ?? 0)) return durMs ? durMs - 20 - clip.trimStartMs : 0
    return nv
  }, [clip.trimStartMs, durMs])
  const clampFade = useCallback((v: number) => {
    const maxMs = Math.max(10, effectiveDuration - 10)
    return Math.max(0, Math.min(v, maxMs))
  }, [effectiveDuration])
  const clampSelection = useCallback((startMs: number, endMs: number) => {
    let start = clampMs(Math.min(startMs, endMs), 0, effectiveDuration)
    let end = clampMs(Math.max(startMs, endMs), 0, effectiveDuration)
    if (end - start < 10) {
      if (end >= effectiveDuration) start = Math.max(0, end - 10)
      else end = Math.min(effectiveDuration, start + 10)
    }
    return { startMs: start, endMs: end }
  }, [effectiveDuration])
  const selectedRegion = selection ?? { startMs: 0, endMs: Math.min(500, effectiveDuration) }
  const selectedDuration = Math.max(10, selectedRegion.endMs - selectedRegion.startMs)
  const regionPercent = (ms: number) => `${(ms / Math.max(1, effectiveDuration)) * 100}%`

  const pointToMs = useCallback((clientX: number) => {
    if (!laneRef.current) return 0
    const rect = laneRef.current.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    return ratio * effectiveDuration
  }, [effectiveDuration])

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!activeHandle.current || !laneRef.current || !durMs) return

      const rect = laneRef.current.getBoundingClientRect()
      const offsetX = e.clientX - rect.left
      const width = rect.width
      const msPerPx = effectiveDuration / width

      const handle = activeHandle.current
      if (handle === 'leftTrim') {
        onUpdate(clip.clipId, { trimStartMs: clampTrimStart(clip.trimStartMs + offsetX * msPerPx) })
      } else if (handle === 'rightTrim') {
        onUpdate(clip.clipId, { trimEndMs: clampTrimEnd(clip.trimEndMs + (width - offsetX) * msPerPx) })
      } else if (handle === 'leftFade') {
        onUpdate(clip.clipId, { fadeInMs: clampFade(clip.fadeInMs + offsetX * msPerPx) })
      } else if (handle === 'rightFade') {
        onUpdate(clip.clipId, { fadeOutMs: clampFade(clip.fadeOutMs + (width - offsetX) * msPerPx) })
      }
    },
    [clip, durMs, effectiveDuration, onUpdate, clampTrimStart, clampTrimEnd, clampFade],
  )

  const handleMouseUp = useCallback(() => {
    activeHandle.current = null
    window.removeEventListener('mousemove', handleMouseMove)
    window.removeEventListener('mouseup', handleMouseUp)
  }, [handleMouseMove])

  const startDrag = (handle: 'leftTrim' | 'rightTrim' | 'leftFade' | 'rightFade') => {
    activeHandle.current = handle
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }

  const handleSelectionMove = useCallback(
    (e: MouseEvent) => {
      if (!selectionDrag.current) return
      setSelection(clampSelection(selectionDrag.current.startMs, pointToMs(e.clientX)))
    },
    [clampSelection, pointToMs],
  )

  const handleSelectionUp = useCallback(() => {
    selectionDrag.current = null
    window.removeEventListener('mousemove', handleSelectionMove)
    window.removeEventListener('mouseup', handleSelectionUp)
  }, [handleSelectionMove])

  const startSelection = (e: ReactMouseEvent<HTMLDivElement>) => {
    if (!durMs) return
    e.preventDefault()
    e.stopPropagation()
    const startMs = pointToMs(e.clientX)
    selectionDrag.current = { startMs }
    setSelection(clampSelection(startMs, startMs + 10))
    window.addEventListener('mousemove', handleSelectionMove)
    window.addEventListener('mouseup', handleSelectionUp)
  }

  const addRegionEdit = (edit: RegionEdit) => onAddRegionEdit(clip.clipId, edit)

  const applyGain = () => {
    addRegionEdit({
      id: makeRegionEditId('gain'),
      type: 'gain',
      startMs: selectedRegion.startMs,
      endMs: selectedRegion.endMs,
      gainDb,
      fadeInMs: regionFadeInMs,
      fadeOutMs: regionFadeOutMs,
    })
  }

  const applyMute = () => {
    addRegionEdit({
      id: makeRegionEditId('mute'),
      type: 'mute',
      startMs: selectedRegion.startMs,
      endMs: selectedRegion.endMs,
      fadeInMs: regionFadeInMs,
      fadeOutMs: regionFadeOutMs,
    })
  }

  const applyDelete = () => {
    addRegionEdit({
      id: makeRegionEditId('delete'),
      type: 'delete',
      startMs: selectedRegion.startMs,
      endMs: selectedRegion.endMs,
    })
  }

  const applyFade = () => {
    addRegionEdit({
      id: makeRegionEditId('fade'),
      type: 'fade',
      startMs: selectedRegion.startMs,
      endMs: selectedRegion.endMs,
      fadeInMs: regionFadeInMs,
      fadeOutMs: regionFadeOutMs,
    })
  }

  const insertSilenceAt = (placement: 'before' | 'after') => {
    addRegionEdit({
      id: makeRegionEditId('insert_silence'),
      type: 'insert_silence',
      atMs: placement === 'before' ? selectedRegion.startMs : selectedRegion.endMs,
      durationMs: silenceMs,
      placement,
    })
  }

  const describeEdit = (edit: RegionEdit) => {
    if (edit.type === 'insert_silence') return `silence ${edit.durationMs}ms ${edit.placement} ${edit.atMs}ms`
    if (edit.type === 'gain') return `gain ${edit.gainDb}dB ${edit.startMs}-${edit.endMs}ms`
    return `${edit.type} ${edit.startMs}-${edit.endMs}ms`
  }

  const fadeOverlay = (side: 'left' | 'right', ms: number) => {
    if (!ms || ms <= 0) return null
    return (
      <div
        className={cn(
          'pointer-events-none absolute inset-y-0 w-[32px]',
          side === 'left' ? 'left-0' : 'right-0',
        )}
        style={{
          background:
            side === 'left'
              ? 'linear-gradient(to right, rgba(0,0,0,0.7) 0%, transparent 100%)'
              : 'linear-gradient(to left, rgba(0,0,0,0.7) 0%, transparent 100%)',
        }}
      />
    )
  }

  return (
    <div
      className={cn(
        "group relative flex w-full min-w-0 flex-col overflow-hidden rounded-lg border border-border/50 bg-muted/10 p-1.5",
        isReordering && 'cursor-grab',
      )}
    >
      <div className="flex items-center justify-between gap-2 px-1.5 pt-1 pb-1">
        {editingText ? (
          <input
            ref={textInputRef}
            type="text"
            value={draftText}
            onChange={(e) => setDraftText(e.target.value)}
            onBlur={commitText}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                commitText()
              } else if (e.key === 'Escape') {
                e.preventDefault()
                cancelEditText()
              }
            }}
            className="min-w-0 flex-1 rounded border border-cyan-500/40 bg-muted/40 px-1.5 py-0.5 text-xs font-medium text-foreground outline-none"
            aria-label="Edit clip text"
          />
        ) : (
          <span
            className="min-w-0 flex-1 cursor-text truncate text-xs font-medium text-foreground hover:text-cyan-400"
            title={`${clip.text ?? ''}\\n(click to edit reference text)`}
            onClick={beginEditText}
          >
            {clip.text || '(untitled — click to add reference text)'}
          </span>
        )}
        <div className="flex shrink-0 items-center gap-1.5">
          <select
            value={clip.prosodyMode ?? 'auto'}
            onChange={(event) => onUpdate(clip.clipId, { prosodyMode: event.currentTarget.value as StitchPlanClip['prosodyMode'] })}
            onMouseDown={(event) => event.stopPropagation()}
            className="rounded border border-border/50 bg-muted/50 px-1 py-0.5 text-[10px] text-muted-foreground"
            aria-label="Internal pacing repair mode"
            title="Repair internal blended sentence boundaries before stitching"
          >
            <option value="off">Repair off</option>
            <option value="auto">Repair auto</option>
            <option value="precise">Repair precise</option>
          </select>
          {isReordering && (
            <div className="flex items-center text-muted-foreground/60">
              <GripVertical className="size-3.5" />
            </div>
          )}
          <button
            type="button"
            className="rounded p-0.5 text-muted-foreground hover:text-foreground"
            onClick={toggleClipPlay}
            disabled={!clip.sourceAudioBase64}
            aria-label={clipPlaying ? "Pause clip playback" : "Play clip playback"}
            title="Listen to just this segment"
          >
            {clipPlaying ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
          </button>
          <button
            type="button"
            className="rounded p-0.5 text-muted-foreground hover:text-destructive"
            onClick={() => onRemove(clip.clipId)}
            aria-label="Remove clip"
            title="Remove clip"
          >
            <X className="size-3.5" />
          </button>
        </div>
      </div>

      <div className="relative h-24 overflow-hidden rounded-md bg-black/40">
        <div ref={laneRef} className="relative h-full w-full" onMouseDown={startSelection}>
          <WaveformLane peaks={peaks} durMs={durMs} trimStartMs={clip.trimStartMs} trimEndMs={clip.trimEndMs} fadeInMs={clip.fadeInMs} fadeOutMs={clip.fadeOutMs} />
          {fadeOverlay('left', clip.fadeInMs)}
          {fadeOverlay('right', clip.fadeOutMs)}

          {regionEdits.map((edit) => {
            if (edit.type === 'insert_silence') {
              return (
                <div
                  key={edit.id}
                  className="pointer-events-none absolute inset-y-2 w-1 rounded-full bg-sky-300/70"
                  style={{ left: regionPercent(edit.atMs) }}
                  title={describeEdit(edit)}
                />
              )
            }
            const left = regionPercent(edit.startMs)
            const width = regionPercent(Math.max(10, edit.endMs - edit.startMs))
            return (
              <div
                key={edit.id}
                className={cn(
                  'pointer-events-none absolute inset-y-1 rounded-sm border',
                  edit.type === 'delete' && 'border-destructive/60 bg-destructive/20',
                  edit.type === 'mute' && 'border-zinc-300/40 bg-zinc-950/55',
                  edit.type === 'gain' && 'border-warning/50 bg-warning/15',
                  edit.type === 'fade' && 'border-cyan-300/50 bg-gradient-to-r from-transparent via-cyan-300/20 to-transparent',
                )}
                style={{ left, width }}
                title={describeEdit(edit)}
              />
            )
          })}

          {selection && (
            <div
              className="pointer-events-none absolute inset-y-0 rounded-sm border border-cyan-300/80 bg-cyan-300/15"
              style={{ left: regionPercent(selection.startMs), width: regionPercent(selection.endMs - selection.startMs) }}
            >
              <div className="absolute inset-y-0 left-0 w-1 bg-cyan-300" />
              <div className="absolute inset-y-0 right-0 w-1 bg-cyan-300" />
            </div>
          )}

          {durMs && (
            <>
              <div
                className="absolute inset-y-0 left-0 w-[2px] cursor-ew-resize bg-cyan-500/50 hover:bg-cyan-400 transition-colors"
                onMouseDown={(e) => {
                  e.stopPropagation()
                  startDrag('leftTrim')
                }}
              />
              <div
                className="absolute inset-y-0 right-0 w-[2px] cursor-ew-resize bg-cyan-500/50 hover:bg-cyan-400 transition-colors"
                onMouseDown={(e) => {
                  e.stopPropagation()
                  startDrag('rightTrim')
                }}
              />
              <div
                className="absolute inset-y-0 w-[2px] cursor-ew-resize bg-cyan-500/50 hover:bg-cyan-400 transition-colors"
                style={{ left: `${(clip.fadeInMs / effectiveDuration) * 100}%` }}
                onMouseDown={(e) => {
                  e.stopPropagation()
                  startDrag('leftFade')
                }}
              />
              <div
                className="absolute inset-y-0 w-[2px] cursor-ew-resize bg-cyan-500/50 hover:bg-cyan-400 transition-colors"
                style={{ right: `${(clip.fadeOutMs / effectiveDuration) * 100}%` }}
                onMouseDown={(e) => {
                  e.stopPropagation()
                  startDrag('rightFade')
                }}
              />
            </>
          )}
        </div>
      </div>

      <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1.5">
        <MsStepper label="Trim start" value={clip.trimStartMs} min={0} max={durMs ?? 0} step={10} onChange={(v) => onUpdate(clip.clipId, { trimStartMs: clampTrimStart(v) })} />
        <MsStepper label="Trim end" value={clip.trimEndMs} min={0} max={durMs ?? 0} step={10} onChange={(v) => onUpdate(clip.clipId, { trimEndMs: clampTrimEnd(v) })} />
        <MsStepper label="Fade in" value={clip.fadeInMs} min={0} max={2000} step={10} onChange={(v) => onUpdate(clip.clipId, { fadeInMs: clampFade(v) })} />
        <MsStepper label="Fade out" value={clip.fadeOutMs} min={0} max={2000} step={10} onChange={(v) => onUpdate(clip.clipId, { fadeOutMs: clampFade(v) })} />
      </div>

      <div className="mt-2 rounded-md border border-border/50 bg-black/20 p-2">
        <div className="grid grid-cols-3 gap-1.5">
          <MsStepper label="Region start" value={selectedRegion.startMs} min={0} max={effectiveDuration} step={10} onChange={(v) => setSelection(clampSelection(v, selectedRegion.endMs))} compact />
          <MsStepper label="Region end" value={selectedRegion.endMs} min={0} max={effectiveDuration} step={10} onChange={(v) => setSelection(clampSelection(selectedRegion.startMs, v))} compact />
          <span className="self-center text-[10px] font-mono text-muted-foreground">{selectedDuration}ms</span>
          <MsStepper label="Gain" value={gainDb} min={-24} max={12} step={1} onChange={setGainDb} compact />
          <MsStepper label="Fade in" value={regionFadeInMs} min={0} max={500} step={5} onChange={setRegionFadeInMs} compact />
          <MsStepper label="Fade out" value={regionFadeOutMs} min={0} max={500} step={5} onChange={setRegionFadeOutMs} compact />
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <button type="button" className="inline-flex items-center gap-1 rounded bg-muted/70 px-2 py-1 text-[10px] text-foreground hover:bg-muted" onClick={applyGain} title="Apply gain to selected region"><Volume2 className="size-3" /> gain</button>
          <button type="button" className="inline-flex items-center gap-1 rounded bg-muted/70 px-2 py-1 text-[10px] text-foreground hover:bg-muted" onClick={applyMute} title="Mute selected region"><VolumeX className="size-3" /> mute</button>
          <button type="button" className="inline-flex items-center gap-1 rounded bg-muted/70 px-2 py-1 text-[10px] text-foreground hover:bg-muted" onClick={applyDelete} title="Delete selected region"><Trash2 className="size-3" /> delete</button>
          <button type="button" className="inline-flex items-center gap-1 rounded bg-muted/70 px-2 py-1 text-[10px] text-foreground hover:bg-muted" onClick={applyFade} title="Fade selected region"><ChevronUp className="size-3" /> fade</button>
          <button type="button" className="inline-flex items-center gap-1 rounded bg-muted/70 px-2 py-1 text-[10px] text-foreground hover:bg-muted" onClick={() => onSplitRegion(clip.clipId, selectedRegion.startMs, selectedRegion.endMs)} title="Split clip at selected region boundaries"><Scissors className="size-3" /> split</button>
          <MsStepper label="Silence" value={silenceMs} min={20} max={2000} step={10} onChange={setSilenceMs} compact />
          <button type="button" className="rounded bg-muted/70 px-2 py-1 text-[10px] text-foreground hover:bg-muted" onClick={() => insertSilenceAt('before')} title="Insert silence before selected region">+ before</button>
          <button type="button" className="rounded bg-muted/70 px-2 py-1 text-[10px] text-foreground hover:bg-muted" onClick={() => insertSilenceAt('after')} title="Insert silence after selected region">+ after</button>
        </div>
        {regionEdits.length > 0 && (
          <div className="mt-2 flex flex-col gap-1 border-t border-border/40 pt-2">
            {regionEdits.map((edit) => (
              <div key={edit.id} className="flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
                <span className="truncate">{describeEdit(edit)}</span>
                <button type="button" className="shrink-0 rounded p-0.5 hover:bg-muted hover:text-foreground" onClick={() => onRemoveRegionEdit(clip.clipId, edit.id)} title="Remove edit">
                  <X className="size-3" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// Independent, always-visible control for the gap between two adjacent clips —
// rendered between clips in the timeline (not nested inside either clip's card),
// so it reads as belonging to \"the space between\" rather than to one clip.
function GapControl({
  gapIndex,
  paddingMs,
  onSetPadding,
}: {
  gapIndex: number
  paddingMs: number
  onSetPadding: (gapIndex: number, ms: number) => void
}) {
  if (paddingMs <= 0) {
    return (
      <button
        type="button"
        onClick={() => onSetPadding(gapIndex, 200)}
        title="Add a gap between these clips"
        className="mt-3 flex h-24 w-8 shrink-0 items-center justify-center rounded border border-dashed border-border/40 text-sm text-muted-foreground/50 hover:border-cyan-500/50 hover:text-cyan-400"
      >
        +
      </button>
    )
  }
  return (
    <div
      className="mt-3 flex h-24 shrink-0 flex-col items-center justify-center gap-1.5 rounded border border-dashed border-cyan-500/40 bg-cyan-500/5 px-1.5"
      style={{ flex: `${Math.max(1, paddingMs)} 0 auto`, minWidth: 56 }}
      title={`${paddingMs}ms gap`}
    >
      <span className="text-[10px] uppercase text-muted-foreground">gap</span>
      <MsStepper label="gap" value={paddingMs} min={0} max={3000} step={10} onChange={(v) => onSetPadding(gapIndex, v)} compact />
    </div>
  )
}

function MsStepper({
  label,
  value,
  min,
  max,
  step,
  onChange,
  compact,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  compact?: boolean
}) {
  return (
    <div className={cn('flex min-w-0 items-center gap-1', compact && 'gap-0.5')} title={label}>
      {!compact && <span className="min-w-0 flex-1 truncate text-[10px] uppercase text-muted-foreground/70">{label}</span>}
      <button type="button" className="inline-flex size-5 shrink-0 items-center justify-center rounded bg-muted/70 text-xs text-muted-foreground hover:bg-muted" aria-label={`Decrease ${label}`} onClick={() => onChange(Math.max(min, value - step))}>−</button>
      <span className="inline-flex min-w-[28px] shrink-0 justify-center text-xs font-mono tabular-nums text-foreground">{value}</span>
      <button type="button" className="inline-flex size-5 shrink-0 items-center justify-center rounded bg-muted/70 text-xs text-muted-foreground hover:bg-muted" aria-label={`Increase ${label}`} onClick={() => onChange(Math.min(max, value + step))}>+</button>
    </div>
  )
}

// Generic multi-select library picker: filter, per-item checkboxes, select-all toggle,
// and a single bulk \"Insert selected\" action — used for both the segment library and the
// voice library (each saved voice inserts as one whole clip, same shape as a segment clip).
function LibraryPickerButton<T>({
  label,
  testidPrefix,
  items,
  getId,
  getLabel,
  getMeta,
  getDurationSec,
  getAudioBase64,
  onInsertMany,
}: {
  label: string
  /** Distinguishes the "Saved segments" vs "Voice library" instances for capture-harness testids. */
  testidPrefix: string
  items: T[]
  getId: (item: T) => string
  getLabel: (item: T) => string
  /** Optional secondary line under the label (accent/tags for segments, language/sample text
   * for voices) — the whole point is to give enough context to choose without inserting blind. */
  getMeta?: (item: T) => string | null
  getDurationSec?: (item: T) => number | null | undefined
  /** Lazily resolves full audio for the inline preview player — list endpoints omit audio for
   * payload size, so this is only called once, on first preview, and cached per item. */
  getAudioBase64?: (item: T) => Promise<string | null>
  onInsertMany: (items: T[]) => void
}) {
  const reducedMotion = useReducedMotion()
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [audioCache, setAudioCache] = useState<Record<string, { url: string; blob: Blob }>>({})

  useEffect(() => {
    return () => {
      Object.values(audioCache).forEach((a) => URL.revokeObjectURL(a.url))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) return items
    return items.filter((it) => getLabel(it).toLowerCase().includes(q))
  }, [items, filter, getLabel])

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const allFilteredSelected = filtered.length > 0 && filtered.every((it) => selected.has(getId(it)))

  const toggleSelectAll = () => {
    setSelected((prev) => {
      if (allFilteredSelected) {
        const next = new Set(prev)
        for (const it of filtered) next.delete(getId(it))
        return next
      }
      const next = new Set(prev)
      for (const it of filtered) next.add(getId(it))
      return next
    })
  }

  const handleInsert = () => {
    const chosen = items.filter((it) => selected.has(getId(it)))
    if (chosen.length === 0) return
    onInsertMany(chosen)
    setSelected(new Set())
    setOpen(false)
    setFilter('')
  }

  const togglePreview = async (item: T) => {
    const id = getId(item)
    if (expandedId === id) {
      setExpandedId(null)
      return
    }
    setExpandedId(id)
    if (!audioCache[id] && getAudioBase64) {
      setLoadingId(id)
      try {
        const b64 = await getAudioBase64(item)
        if (b64) {
          const blob = base64ToBlob(b64)
          const url = URL.createObjectURL(blob)
          setAudioCache((prev) => ({ ...prev, [id]: { url, blob } }))
        }
      } finally {
        setLoadingId(null)
      }
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        data-testid={`stitch-picker-toggle-${testidPrefix}`}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:bg-muted"
      >
        {open ? `Hide ${label.toLowerCase()}` : `Add ${label.toLowerCase()}`}
      </button>

      <AnimatePresence>
        {open && (
       <motion.div
          initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: reducedMotion ? 0 : 0 }}
          exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: -4 }}
          className="absolute right-0 top-9 z-30 flex max-h-96 w-96 flex-col gap-1.5 overflow-hidden rounded-lg border border-border bg-background p-2 shadow-lg"
        >

            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] uppercase text-muted-foreground">{label}</span>
              <button
                type="button"
                onClick={toggleSelectAll}
                disabled={filtered.length === 0}
                className="shrink-0 text-[10px] text-muted-foreground underline decoration-dotted hover:text-foreground disabled:opacity-40"
              >
                {allFilteredSelected ? 'Deselect all' : 'Select all'}
              </button>
            </div>
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter…"
              className="rounded-md border border-border bg-muted/40 px-2 py-1 text-xs text-foreground outline-none focus:border-cyan-500/50"
            />
            <div className="flex flex-col gap-1 overflow-y-auto">
              {filtered.length === 0 && (
                <span className="px-2 py-1 text-xs text-muted-foreground/60">No matches</span>
              )}
              {filtered.map((it) => {
                const id = getId(it)
                const checked = selected.has(id)
                const meta = getMeta?.(it)
                const duration = getDurationSec?.(it)
                const isExpanded = expandedId === id
                const cached = audioCache[id]
                return (
                  <div
                    key={id}
                    className="rounded-md border border-transparent hover:border-border hover:bg-muted"
                  >
                    <label className="flex cursor-pointer items-center gap-2 px-2 py-1 text-xs text-foreground">
                      <input
                        type="checkbox"
                        data-testid={`stitch-picker-item-${testidPrefix}`}
                        checked={checked}
                        onChange={() => toggle(id)}
                        className="size-3.5 shrink-0 accent-cyan-500"
                      />
                      {getAudioBase64 && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.preventDefault()
                            void togglePreview(it)
                          }}
                          title="Preview"
                          className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground"
                        >
                          {loadingId === id ? (
                            <Loader2 className="size-3.5 animate-spin" />
                          ) : isExpanded ? (
                            <Pause className="size-3.5" />
                          ) : (
                            <Play className="size-3.5" />
                          )}
                        </button>
                      )}
                      <span
                        className="min-w-0 flex-1"
                        title={meta ? `${getLabel(it)}\\n${meta}` : getLabel(it)}
                      >
                        <span className="block truncate">{getLabel(it)}</span>
                        {meta && (
                          <span className="block truncate text-[10px] text-muted-foreground">{meta}</span>
                        )}
                      </span>
                      {duration != null && (
                        <span className="shrink-0 text-[10px] text-muted-foreground">
                          {duration.toFixed(1)}s
                        </span>
                      )}
                    </label>
                    {isExpanded && cached && (
                      <div className="px-2 pb-1.5">
                        <AudioPlayer src={cached.url} blob={cached.blob} autoPlay />
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            <button
              type="button"
              data-testid={`stitch-picker-insert-${testidPrefix}`}
              onClick={handleInsert}
              disabled={selected.size === 0}
              className="mt-1 rounded-md bg-cyan-500/90 px-2 py-1 text-xs font-medium text-background hover:bg-cyan-500 disabled:opacity-40"
            >
              Insert selected ({selected.size})
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ---------- main component ---------- */

interface StitchTimelineProps {
  totalDurationMs: number
  isPreviewStale: boolean
  library: SegmentMeta[]
  onInsertFromLibrary: (seg: SegmentMeta) => void
  regionEditsByClip: RegionEditsByClip
  onAddRegionEdit: (clipId: string, edit: RegionEdit) => void
  onRemoveRegionEdit: (clipId: string, editId: string) => void
  voiceLibrary?: VoiceMeta[]
  onInsertVoiceFromLibrary?: (voice: VoiceMeta) => void
}

export const StitchTimeline = memo(function StitchTimeline({
  totalDurationMs: _totalDurationMs,
  isPreviewStale: _isPreviewStale,
  library,
  onInsertFromLibrary,
  regionEditsByClip,
  onAddRegionEdit,
  onRemoveRegionEdit,
  voiceLibrary,
  onInsertVoiceFromLibrary,
}: StitchTimelineProps) {
  const reducedMotion = useReducedMotion()
  const clips = useAppStore((s) => s.ovStitchPlanClips)
  const paddingMs = useAppStore((s) => s.ovStitchPlanPaddingMs)
  const reorderClip = useAppStore((s) => s.reorderOvStitchPlanClip)
  const removeClip = useAppStore((s) => s.removeOvStitchPlanClip)
  const updateClip = useAppStore((s) => s.updateOvStitchPlanClip)
  const setClips = useAppStore((s) => s.setOvStitchPlanClips)
  const setPadding = useAppStore((s) => s.setOvStitchPlanPaddingAt)
  const setPaddingMs = useAppStore((s) => s.setOvStitchPlanPaddingMs)
  const hasVoiceLibrary = (voiceLibrary?.length ?? 0) > 0 && !!onInsertVoiceFromLibrary

  const handleReorder = useCallback(
    (next: StitchPlanClip[]) => {
      const newIndices: number[] = []
      for (const c of next) {
        const idx = clips.findIndex((oc) => oc.clipId === c.clipId)
        if (idx !== -1) newIndices.push(idx)
      }
      // Build a mapping: for each new position, find the original index
      for (let i = 0; i < next.length; i++) {
        const from = clips.findIndex((oc) => oc.clipId === next[i].clipId)
        if (from !== i) {
          reorderClip(from, i)
          break
        }
      }
    },
    [clips, reorderClip],
  )

  const moveClip = useCallback(
    (index: number, direction: 'left' | 'right') => {
      const to = direction === 'left' ? index - 1 : index + 1
      if (to < 0 || to >= clips.length) return
      reorderClip(index, to)
    },
    [clips.length, reorderClip],
  )

  const splitRegion = useCallback(
    (clipId: string, startMs: number, endMs: number) => {
      const index = clips.findIndex((clip) => clip.clipId === clipId)
      if (index === -1) return
      const clip = clips[index]
      const duration = clip.durationMs ?? 0
      if (!duration) return
      const effectiveDuration = clipEffectiveDurationMs(clip)
      const start = clampMs(startMs, 0, effectiveDuration)
      const end = clampMs(endMs, start + 10, effectiveDuration)
      const absoluteStart = clip.trimStartMs + start
      const absoluteEnd = clip.trimStartMs + end
      const parts: StitchPlanClip[] = []
      const addPart = (label: string, trimStartMs: number, trimEndMs: number) => {
        if (duration - trimStartMs - trimEndMs < 20) return
        parts.push({
          ...clip,
          clipId: `${clip.clipId}-${label}-${Date.now()}`,
          trimStartMs,
          trimEndMs,
          fadeInMs: 0,
          fadeOutMs: 0,
        })
      }
      addPart('pre', clip.trimStartMs, duration - absoluteStart)
      addPart('region', absoluteStart, duration - absoluteEnd)
      addPart('post', absoluteEnd, clip.trimEndMs)
      if (parts.length <= 1) return
      setClips((prev) => {
        const next = [...prev]
        next.splice(index, 1, ...parts)
        return next
      })
      const nextPadding = [...paddingMs]
      const inheritedGap = nextPadding[index] ?? 0
      nextPadding.splice(index, 0, ...new Array(parts.length - 1).fill(0))
      if (index + parts.length - 1 < nextPadding.length) nextPadding[index + parts.length - 1] = inheritedGap
      setPaddingMs(nextPadding.slice(0, Math.max(0, clips.length + parts.length - 2)))
    },
    [clips, paddingMs, setClips, setPaddingMs],
  )

  // Hooks must run unconditionally on every render — this used to sit after an early return
  // for the empty-timeline case, which threw \"rendered more hooks than previous render\" (React
  // error #310) the instant a first clip was inserted (0 clips -> hook skipped, 1+ clips -> hook
  // ran), crashing the page. Stitch Studio hits the empty state on first load, so it surfaced
  // this immediately; OmniVoice's editor rarely opened with zero clips, so it went unnoticed.
  const effectiveTotalMs = useMemo(() => {
    let sum = 0
    for (const c of clips) {
      sum += clipEffectiveDurationMs(c)
    }
    sum += (paddingMs || []).reduce((a, b) => a + b, 0)
    return Math.max(1, sum)
  }, [clips, paddingMs])

  const autoPace = useCallback(() => {
    setPaddingMs(clips.slice(0, -1).map((clip) => {
      const text = (clip.text ?? '').trim()
      if (/[.!?]["')\]]?$/.test(text)) return 520
      if (/[,;:]["')\]]?$/.test(text)) return 260
      return 90
    }))
  }, [clips, setPaddingMs])

  if (!clips.length) {
    return (
      <div className="flex h-24 flex-col items-center justify-center gap-2 text-xs text-muted-foreground">
        <span>No clips in timeline</span>
        <div className="flex items-center gap-2">
          {library.length > 0 && (
            <LibraryPickerButton
              label="Saved segments"
              testidPrefix="segments"
              items={library}
              getId={(seg) => seg.segment_id}
              getLabel={(seg) => seg.text}
              getMeta={(seg) => [seg.language, ...(seg.tags ?? [])].filter(Boolean).join(' · ') || null}
              getDurationSec={(seg) => seg.duration_sec ?? null}
              getAudioBase64={async (seg) => seg.audio_base64 ?? (await getSegmentAudioBase64(seg.segment_id))}
              onInsertMany={(segs) => segs.forEach(onInsertFromLibrary)}
            />
          )}
          {hasVoiceLibrary && (
            <LibraryPickerButton
              label="Voice library"
              testidPrefix="voices"
              items={voiceLibrary!}
              getId={(v) => v.voice_id}
              getLabel={(v) => v.description || v.voice_id}
              getMeta={(v) =>
                [v.language, v.sample_text ? `Sample: ${v.sample_text.slice(0, 60)}${v.sample_text.length > 60 ? '…' : ''}` : null]
                  .filter(Boolean)
                  .join(' · ') || null
              }
              getAudioBase64={async (v) => v.audio_base64 ?? (await getVoice(v.voice_id)).audio_base64 ?? null}
              onInsertMany={(vs) => vs.forEach(onInsertVoiceFromLibrary!)}
            />
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="relative flex min-w-0 flex-col gap-2">
      {/* Library insert bar */}
      {(library.length > 0 || hasVoiceLibrary) && (
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">
            Drag to reorder clips, trim edges, and adjust gaps to build your 10–15s reference voice.
          </span>
          <div className="flex shrink-0 items-center gap-2">
            <button type="button" className="inline-flex h-8 items-center gap-1.5 rounded border border-border bg-background px-2.5 text-xs hover:bg-muted" onClick={autoPace}>
              <Gauge className="size-3.5" /> Auto-pace
            </button>
            {library.length > 0 && (
              <LibraryPickerButton
                label="Saved segments"
                testidPrefix="segments"
                items={library}
                getId={(seg) => seg.segment_id}
                getLabel={(seg) => seg.text}
                onInsertMany={(segs) => segs.forEach(onInsertFromLibrary)}
              />
            )}
            {hasVoiceLibrary && (
              <LibraryPickerButton
                label="Voice library"
                testidPrefix="voices"
                items={voiceLibrary!}
                getId={(v) => v.voice_id}
                getLabel={(v) => v.description || v.voice_id}
                onInsertMany={(vs) => vs.forEach(onInsertVoiceFromLibrary!)}
              />
            )}
          </div>
        </div>
      )}

      {/* Timeline */}
      <div className="relative flex items-stretch gap-0 overflow-x-auto overflow-y-visible pl-5" style={{ minWidth: 0 }}>
        {effectiveTotalMs > 0 && (
          <div className="pointer-events-none absolute inset-x-5 top-0 flex h-4 items-start border-b border-border/30">
            {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
              const ms = ratio * effectiveTotalMs
              const sec = ms / 1000
              return (
                <div
                  key={ratio}
                  className="absolute text-[10px] font-mono text-muted-foreground/50"
                  style={{ left: `${ratio * 100}%`, transform: 'translateX(-50%)' }}
                >
                  {sec < 10 ? `${sec.toFixed(1)}s` : `${Math.floor(sec / 60)}:${(sec % 60).toFixed(0).padStart(2, '0')}`}
                </div>
              )
            })}
          </div>
        )}

        <Reorder.Group
          axis="x"
          values={clips}
          onReorder={handleReorder}
          className="mt-3 flex flex-1 items-start gap-0"
        >
          {clips.map((clip, i) => (
            <div key={clip.clipId} className="flex items-start gap-4">
              {i > 0 && (
                <GapControl gapIndex={i - 1} paddingMs={paddingMs[i - 1] || 0} onSetPadding={setPadding} />
              )}
              <Reorder.Item
                value={clip}
                data-testid="stitch-clip"
                className="group relative flex flex-col"
                style={{ flex: `${Math.max(300, clipEffectiveDurationMs(clip))} 0 auto`, minWidth: 320 }}
              >
                {/* Keyboard-accessible reorder buttons */}
                <div className="absolute -left-5 top-6 flex flex-col gap-0.5 opacity-40 group-hover:opacity-100 z-10">
                  <button type="button" className="size-4 rounded bg-muted/70 text-[10px] text-muted-foreground hover:bg-muted" onClick={() => moveClip(i, 'left')} title="Move left">
                    <ChevronUp className="size-3" />
                  </button>
                  <button type="button" className="size-4 rounded bg-muted/70 text-[10px] text-muted-foreground hover:bg-muted" onClick={() => moveClip(i, 'right')} title="Move right">
                    <ChevronDown className="size-3" />
                  </button>
                </div>
                <StitchTimelineClip
                  clip={clip}
                  onRemove={removeClip}
                  onUpdate={updateClip}
                  regionEdits={regionEditsByClip[clip.clipId] ?? []}
                  onAddRegionEdit={onAddRegionEdit}
                  onRemoveRegionEdit={onRemoveRegionEdit}
                  onSplitRegion={splitRegion}
                  isReordering
                  reducedMotion={reducedMotion}
                />
              </Reorder.Item>
            </div>
          ))}
        </Reorder.Group>
      </div>
    </div>
  )
})

/* ---------- DSP controls panel ---------- */

export function StitchDspControls({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const reducedMotion = useReducedMotion()
  const dsp = useAppStore((s) => s.ovStitchPlanDsp)
  const setDsp = useAppStore((s) => s.setOvStitchPlanDsp)

  return (
    <div className="mt-2 flex flex-col gap-2">
      <button
        type="button"
        onClick={onToggle}
        className="self-start text-xs text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground"
      >
        {open ? 'Hide DSP controls' : 'DSP controls'}
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={reducedMotion ? { opacity: 0 } : { opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={reducedMotion ? { opacity: 0 } : { opacity: 0, height: 0 }}
            className="grid grid-cols-2 gap-x-6 gap-y-3 overflow-hidden rounded-lg border border-border/60 bg-muted/40 px-4 py-3"
          >
            <SliderField label="Segment target" value={dsp.segmentTargetDbfs} min={-40} max={-10} step={0.5} format={(v) => `${v} dBFS`} onChange={(v) => setDsp({ segmentTargetDbfs: v })} />
            <SliderField label="Final target" value={dsp.finalTargetDbfs} min={-40} max={-10} step={0.5} format={(v) => `${v} dBFS`} onChange={(v) => setDsp({ finalTargetDbfs: v })} />
            <SliderField label="Final ceiling" value={dsp.finalCeilingDb} min={-6} max={0} step={0.2} format={(v) => `${v} dB`} onChange={(v) => setDsp({ finalCeilingDb: v })} />
            <SliderField label="Crossfade" value={dsp.crossfadeMs} min={0} max={400} step={5} format={(v) => `${v} ms`} onChange={(v) => setDsp({ crossfadeMs: v })} />
            <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
              Pacing style
              <select value={dsp.prosodyStylePreset} onChange={(e) => setDsp({ prosodyStylePreset: e.currentTarget.value as typeof dsp.prosodyStylePreset })} className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground">
                {['Neutral', 'Storyteller', 'Calm', 'Energetic', 'Broadcast', 'Clean'].map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
            </label>
            <SliderField label="Pace" value={dsp.paceMultiplier} min={0.5} max={2} step={0.05} format={(v) => `${v.toFixed(2)}×`} onChange={(v) => setDsp({ paceMultiplier: v })} />
            <div className="col-span-2 flex items-center justify-between pt-1">
              <label className="flex items-center gap-2 text-xs text-foreground">
                <input type="checkbox" checked={dsp.compressEnabled} onChange={(e) => setDsp({ compressEnabled: e.currentTarget.checked })} className="h-3.5 w-3.5 accent-cyan-500" />
                Compression
              </label>
              <div className="flex items-center gap-4">
                <SliderField label="Threshold" value={dsp.compressThresholdDb} min={-60} max={-12} step={0.5} format={(v) => `${v} dB`} onChange={(v) => setDsp({ compressThresholdDb: v })} disabled={!dsp.compressEnabled} />
                <SliderField label="Ratio" value={dsp.compressRatio} min={1} max={10} step={0.1} format={(v) => `${v}:1`} onChange={(v) => setDsp({ compressRatio: v })} disabled={!dsp.compressEnabled} />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function SliderField({
  label,
  value,
  min,
  max,
  step,
  format,
  onChange,
  disabled,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  format: (v: number) => string
  onChange: (v: number) => void
  disabled?: boolean
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-muted-foreground">{label}</span>
        <span className="text-[11px] font-mono tabular-nums text-foreground">{format(value)}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} disabled={disabled} className="h-1.5 w-full cursor-pointer accent-cyan-500" />
    </div>
  )
}

/* ---------- Editor shell ---------- */

interface StitchEditorBodyProps {
  /** Reference texts, in clip order, used as the transcript for the saved voice's cloning
   * reference audio -- kept separate from onSave's plan payload because it's derived from the
   * clips' (possibly user-edited) text, not from DSP/trim/fade params. */
  onSave: (plan: StitchPlanPayload, segments: string[]) => Promise<void>
  library: SegmentMeta[]
  onInsertFromLibrary: (seg: SegmentMeta) => void
  voiceLibrary?: VoiceMeta[]
  onInsertVoiceFromLibrary?: (voice: VoiceMeta) => void
  /** Renders a close button in the header when set — the standalone Stitch Studio page has
   * nothing to \"close\" back to, so it omits this. */
  onClose?: () => void
}

// Shared editor internals (timeline + DSP controls + live preview + render/save footer), with
// no opinion on how it's framed — StitchEditorPanel wraps it in a full-screen modal (used from
// the OmniVoice flow, popping over an existing workflow); StitchEditorInline renders
// it as plain page content (used by the standalone Stitch Studio page).
function StitchEditorBody({
  onClose,
  onSave,
  library,
  onInsertFromLibrary,
  voiceLibrary,
  onInsertVoiceFromLibrary,
}: StitchEditorBodyProps) {
  const clips = useAppStore((s) => s.ovStitchPlanClips)
  const paddingMs = useAppStore((s) => s.ovStitchPlanPaddingMs)
  const dsp = useAppStore((s) => s.ovStitchPlanDsp)
  const previewUrl = useAppStore((s) => s.ovStitchPreviewUrl)
  const _previewBlob = useAppStore((s) => s.ovStitchPreviewBlob)
  void _previewBlob
  const isRendering = useAppStore((s) => s.ovIsRenderingPreview)
  const setPreviewUrl = useAppStore((s) => s.setOvStitchPreviewUrl)
  const setPreviewBlob = useAppStore((s) => s.setOvStitchPreviewBlob)
  const setIsRendering = useAppStore((s) => s.setOvIsRenderingPreview)
  const setPaddingMs = useAppStore((s) => s.setOvStitchPlanPaddingMs)
  const setClips = useAppStore((s) => s.setOvStitchPlanClips)
  const [showDsp, setShowDsp] = useState(false)
  const [staleFlags, setStaleFlags] = useState(true)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [isNormalizingPacing, setIsNormalizingPacing] = useState(false)
  const [regionEditsByClip, setRegionEditsByClip] = useState<RegionEditsByClip>({})
  const debounceRef = useRef<number | null>(null)
  const lastHashRef = useRef('')
  // Guards against out-of-order network responses: an older in-flight render
  // (e.g. from before a clip was removed) can resolve after a newer one and
  // silently overwrite the correct preview with stale audio. Bumped on every
  // new render attempt; a response is only applied if it's still current.
  const renderSeqRef = useRef(0)

  const planPayload = useMemo<StitchPlanPayload>(() => {
    return {
      clips: clips.map((c) => {
        const anyRef = c.ref as Record<string, string>
        const edits = regionEditsByClip[c.clipId] ?? []
        return {
          segmentId: 'segmentId' in anyRef ? anyRef.segmentId : undefined,
          candidateId: 'candidateId' in anyRef ? anyRef.candidateId : undefined,
          voiceId: 'voiceId' in anyRef ? anyRef.voiceId : undefined,
          trimStartMs: c.trimStartMs,
          trimEndMs: c.trimEndMs,
          fadeInMs: c.fadeInMs,
          fadeOutMs: c.fadeOutMs,
          text: c.text,
          prosodyMode: c.prosodyMode ?? 'auto',
          edits: edits.length
            ? edits.map((e): StitchPlanRegionEdit => {
                switch (e.type) {
                  case 'gain':
                    return { type: 'gain', startMs: e.startMs, endMs: e.endMs, gainDb: e.gainDb, fadeInMs: e.fadeInMs, fadeOutMs: e.fadeOutMs }
                  case 'mute':
                    return { type: 'mute', startMs: e.startMs, endMs: e.endMs, fadeInMs: e.fadeInMs, fadeOutMs: e.fadeOutMs }
                  case 'fade':
                    return { type: 'fade', startMs: e.startMs, endMs: e.endMs, fadeInMs: e.fadeInMs, fadeOutMs: e.fadeOutMs }
                  case 'delete':
                    return { type: 'delete', startMs: e.startMs, endMs: e.endMs }
                  case 'insert_silence':
                    return { type: 'insert_silence', atMs: e.atMs, durationMs: e.durationMs }
                }
              })
            : undefined,
        }
      }),
      paddingMs: paddingMs.length ? paddingMs : new Array(Math.max(0, clips.length - 1)).fill(0),
      crossfadeMs: dsp.crossfadeMs,
      segmentTargetDbfs: dsp.segmentTargetDbfs,
      finalTargetDbfs: dsp.finalTargetDbfs,
      finalCeilingDb: dsp.finalCeilingDb,
      compress: dsp.compressEnabled
        ? {
            thresholdDb: dsp.compressThresholdDb,
            ratio: dsp.compressRatio,
            attackMs: 5,
            releaseMs: 80,
          }
        : null,
      stylePreset: dsp.prosodyStylePreset,
      paceMultiplier: dsp.paceMultiplier,
      pauseOffsetMs: dsp.pauseOffsetMs,
    }
  }, [clips, paddingMs, dsp, regionEditsByClip])

  const addRegionEdit = useCallback((clipId: string, edit: RegionEdit) => {
    setRegionEditsByClip((prev) => ({
      ...prev,
      [clipId]: [...(prev[clipId] ?? []), edit],
    }))
  }, [])

  const removeRegionEdit = useCallback((clipId: string, editId: string) => {
    setRegionEditsByClip((prev) => {
      const nextEdits = (prev[clipId] ?? []).filter((edit) => edit.id !== editId)
      const next = { ...prev }
      if (nextEdits.length) next[clipId] = nextEdits
      else delete next[clipId]
      return next
    })
  }, [])

  useEffect(() => {
    const liveClipIds = new Set(clips.map((clip) => clip.clipId))
    setRegionEditsByClip((prev) => {
      let changed = false
      const next: RegionEditsByClip = {}
      for (const [clipId, edits] of Object.entries(prev)) {
        if (liveClipIds.has(clipId)) next[clipId] = edits
        else changed = true
      }
      return changed ? next : prev
    })
  }, [clips])

  const hash = useMemo(() => {
    return JSON.stringify({
      clips: clips.map((c) => [c.trimStartMs, c.trimEndMs, c.fadeInMs, c.fadeOutMs, c.text, c.prosodyMode]),
      paddingMs,
      dsp,
      regionEditsByClip,
    })
  }, [clips, paddingMs, dsp, regionEditsByClip])

  useEffect(() => {
    if (hash === lastHashRef.current || clips.length === 0) {
      if (hash !== lastHashRef.current) lastHashRef.current = hash
      return
    }
    lastHashRef.current = hash
    setStaleFlags(true)
    setPreviewError(null)

    if (debounceRef.current != null) clearTimeout(debounceRef.current)
    debounceRef.current = window.setTimeout(async () => {
      debounceRef.current = null
      const seq = ++renderSeqRef.current
      try {
        setIsRendering(true)
        const requiresServerRepair = clips.some((clip) => (clip.prosodyMode ?? 'auto') !== 'off')
        const blob = hasRegionEdits(regionEditsByClip) && !requiresServerRepair
          ? await renderEditedStitchPreview(clips, planPayload.paddingMs, dsp.crossfadeMs, regionEditsByClip)
          : await renderStitchPlan(planPayload)
        if (seq !== renderSeqRef.current) return // superseded by a newer edit
        if (previewUrl) URL.revokeObjectURL(previewUrl)
        const url = URL.createObjectURL(blob)
        setPreviewUrl(url)
        setPreviewBlob(blob)
        setStaleFlags(false)
        setPreviewError(null)
      } catch (err) {
        // Keep the last-good preview showing, but surface the failure — otherwise
        // the UI looks stuck on \"changes pending\" forever with no explanation.
        if (seq === renderSeqRef.current) {
          setPreviewError(err instanceof Error ? err.message : 'Preview render failed.')
        }
      } finally {
        if (seq === renderSeqRef.current) setIsRendering(false)
      }
    }, 500)

    return () => {
      if (debounceRef.current != null) {
        clearTimeout(debounceRef.current)
        debounceRef.current = null
      }
    }
  }, [hash, planPayload, clips, dsp.crossfadeMs, regionEditsByClip, setPreviewUrl, setPreviewBlob, setIsRendering, previewUrl])

  const handleSave = useCallback(async () => {
    renderSeqRef.current++
    if (debounceRef.current != null) {
      clearTimeout(debounceRef.current)
      debounceRef.current = null
    }
    setStaleFlags(false)
    const segments = clips.map((c) => c.text?.trim()).filter((t): t is string => !!t)
    await onSave(planPayload, segments)
  }, [planPayload, onSave, clips])

  const normalizePacing = useCallback(async () => {
    if (!clips.length) return
    setIsNormalizingPacing(true)
    setPreviewError(null)
    try {
      const result = await getStitchPacingTargets({
        transcripts: clips.map((clip) => clip.text ?? ''),
        stylePreset: dsp.prosodyStylePreset,
        paceMultiplier: dsp.paceMultiplier,
        pauseOffsetMs: dsp.pauseOffsetMs,
      })
      setPaddingMs(result.padding_ms)
      setClips((current) => current.map((clip) => ({ ...clip, prosodyMode: 'auto' })))
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : 'Could not normalize pacing.')
    } finally {
      setIsNormalizingPacing(false)
    }
  }, [clips, dsp, setClips, setPaddingMs])

  const totalMs = useMemo(() => {
    let sum = 0
    for (const c of clips) {
      sum += clipEffectiveDurationMs(c)
    }
    sum += (paddingMs || []).reduce((a, b) => a + b, 0)
    return Math.max(1, sum)
  }, [clips, paddingMs])

  return (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="text-sm font-semibold uppercase tracking-wider text-foreground">Arrange your reference clip</span>
          <span className="text-xs text-muted-foreground/70">{clips.length} clip{clips.length !== 1 ? 's' : ''}</span>
          <button
            type="button"
            onClick={normalizePacing}
            disabled={!clips.length || isNormalizingPacing}
            className="inline-flex items-center gap-1 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1 text-[10px] font-medium text-cyan-300 hover:bg-cyan-500/15 disabled:opacity-50"
            title="Set seam targets from the shared pacing engine and auto-repair internal blended boundaries"
          >
            {isNormalizingPacing ? <Loader2 className="size-3 animate-spin" /> : <Gauge className="size-3" />}
            Normalize pacing
          </button>
          {staleFlags && !previewError && (
            <span className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2 py-0.5 text-[10px] font-medium text-warning">
              changes pending
            </span>
          )}
          {previewError && (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-destructive/10 px-2 py-0.5 text-[10px] font-medium text-destructive"
              title={previewError}
            >
              preview failed — showing last good render
            </span>
          )}
        </div>
        {onClose && (
          <button type="button" onClick={onClose} className="rounded-full p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground" title="Close editor">
            <X className="size-4" />
          </button>
        )}
      </div>

      <StitchTimeline
        totalDurationMs={totalMs}
        isPreviewStale={staleFlags}
        library={library}
        onInsertFromLibrary={onInsertFromLibrary}
        regionEditsByClip={regionEditsByClip}
        onAddRegionEdit={addRegionEdit}
        onRemoveRegionEdit={removeRegionEdit}
        voiceLibrary={voiceLibrary}
        onInsertVoiceFromLibrary={onInsertVoiceFromLibrary}
      />
      <StitchDspControls open={showDsp} onToggle={() => setShowDsp((v) => !v)} />

      {clips.length > 0 && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase text-muted-foreground">Live preview</span>
              {isRendering && (
                <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                  <Loader2 className="size-3 animate-spin" />
                  rendering…
                </span>
              )}
            </div>
          </div>
          {previewUrl ? (
            <PreviewPlayer src={previewUrl} />
          ) : (
            <div className="flex h-10 items-center px-3 text-xs text-muted-foreground">
              Generating preview…
            </div>
          )}
        </div>
      )}

      <div className="mt-1 flex items-center justify-between border-t border-border/60 pt-3">
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            data-testid="stitch-save-voice"
            onClick={handleSave}
            disabled={isRendering || clips.length === 0}
            className="btn-brand inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-medium"
            title="This will be used as a reusable cloning source for text-to-speech."
          >
            Save as reference voice
          </button>
        </div>
        <div className="text-[10px] text-muted-foreground">{(totalMs / 1000).toFixed(1)}s total</div>
      </div>
    </>
  )
}

export function StitchEditorPanel(props: StitchEditorBodyProps & { onClose: () => void }) {
  return createPortal(
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) props.onClose()
      }}
    >
      <motion.div
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 12, scale: 0.98 }}
        className="flex max-h-[88vh] w-full max-w-5xl flex-col gap-4 overflow-y-auto rounded-2xl border border-border bg-background px-6 py-5 shadow-2xl"
      >
        <StitchEditorBody {...props} />
      </motion.div>
    </motion.div>,
    document.body,
  )
}

// Plain page content, no portal/backdrop/close button — used by the standalone Stitch Studio
// page, which is the editor's home rather than something popping over another workflow.
export function StitchEditorInline(props: Omit<StitchEditorBodyProps, 'onClose'>) {
  return (
    <div className="flex min-w-0 flex-col gap-4 rounded-2xl border border-border bg-background/50 px-6 py-5">
      <StitchEditorBody {...props} />
    </div>
  )
}

/* ---------- minimal preview player ---------- */

function PreviewPlayer({ src }: { src: string }) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const a = audioRef.current
    if (!a) return
    const onEnd = () => { setPlaying(false); setProgress(0) }
    const onTimeUpdate = () => {
      if (a.duration && isFinite(a.duration)) setProgress(a.currentTime / a.duration)
    }
    a.addEventListener('ended', onEnd)
    a.addEventListener('timeupdate', onTimeUpdate)
    return () => {
      a.removeEventListener('ended', onEnd)
      a.removeEventListener('timeupdate', onTimeUpdate)
    }
  }, [src])

  const togglePlay = async () => {
    const a = audioRef.current
    if (!a) return
    if (playing) a.pause()
    else await a.play()
    setPlaying(!playing)
  }

  return (
    <div className="flex items-center gap-2">
      <button type="button" onClick={togglePlay} className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground hover:text-foreground">
        {playing
          ? <div className="flex gap-[3px]"><div className="h-3 w-[2px] bg-current" /><div className="h-3 w-[2px] bg-current" /></div>
          : <Play className="size-3" />}
      </button>
      <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-black/40">
        <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-cyan-500/50 to-fuchsia-500/40" style={{ width: `${progress * 100}%` }} />
      </div>
      <audio ref={audioRef} src={src} preload="auto" />
    </div>
  )
}

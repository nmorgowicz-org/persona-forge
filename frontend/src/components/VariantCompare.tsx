import { useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { computePeaks } from '@/lib/waveform'
import { generateSpeechWithMetrics, listVoices, type ReferenceMetrics, type VoiceMeta } from '@/lib/api'
import { AudioStatsStrip } from './waveform/AudioStatsStrip'
import { WaveformLane } from './waveform/WaveformLane'

interface CompareResult {
  audioUrl: string
  metrics: ReferenceMetrics
  peaks: number[]
  durationMs: number
}

function groupVoicesByFamily(voices: VoiceMeta[]) {
  const families = new Map<string, VoiceMeta[]>()
  for (const voice of voices) {
    const key = voice.family_id ?? voice.voice_id
    const existing = families.get(key) ?? []
    existing.push(voice)
    families.set(key, existing)
  }
  return Array.from(families.entries()).map(([familyId, members]) => ({
    familyId,
    displayName: members[0].display_name ?? familyId,
    members,
  }))
}

export function VariantCompare() {
  const [text, setText] = useState('The quick brown fox jumps over the lazy dog.')
  const [voices, setVoices] = useState<VoiceMeta[]>([])
  const [voiceA, setVoiceA] = useState('')
  const [voiceB, setVoiceB] = useState('')
  const [loading, setLoading] = useState(false)
  const [resultA, setResultA] = useState<CompareResult | null>(null)
  const [resultB, setResultB] = useState<CompareResult | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)

  const audioARef = useRef<HTMLAudioElement | null>(null)
  const audioBRef = useRef<HTMLAudioElement | null>(null)
  const objectUrlsRef = useRef<string[]>([])

  useEffect(() => {
    listVoices()
      .then(setVoices)
      .catch((err) => console.error('Failed to load voices for compare picker', err))
  }, [])

  const families = useMemo(() => groupVoicesByFamily(voices), [voices])

  const decodeAudio = async (blob: Blob) => {
    const arrayBuffer = await blob.arrayBuffer()
    const AudioContextCtor =
      window.AudioContext ||
      (window as Window & typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!AudioContextCtor) throw new Error('Audio decoding is not supported in this browser')
    const ctx = new AudioContextCtor()
    try {
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0))
      return audioBuffer.duration
    } finally {
      void ctx.close()
    }
  }

  const fetchAudio = async (voiceId: string): Promise<CompareResult> => {
    const { blob, metrics } = await generateSpeechWithMetrics({ text, voiceId })
    const [peaks, durationSeconds] = await Promise.all([computePeaks(blob), decodeAudio(blob)])
    const audioUrl = URL.createObjectURL(blob)
    objectUrlsRef.current.push(audioUrl)

    return {
      audioUrl,
      metrics: { duration_seconds: durationSeconds, ...metrics },
      peaks,
      durationMs: Math.round(durationSeconds * 1000),
    }
  }

  const handleCompare = async () => {
    if (!voiceA || !voiceB || !text) return
    setLoading(true)
    try {
      objectUrlsRef.current.forEach((url) => URL.revokeObjectURL(url))
      objectUrlsRef.current = []
      const [a, b] = await Promise.all([fetchAudio(voiceA), fetchAudio(voiceB)])
      setResultA(a)
      setResultB(b)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const togglePlayback = () => {
    const next = !isPlaying
    setIsPlaying(next)
    if (next) {
      void audioARef.current?.play()
      void audioBRef.current?.play()
    } else {
      audioARef.current?.pause()
      audioBRef.current?.pause()
    }
  }

  const handleTimeUpdate = (event: React.SyntheticEvent<HTMLAudioElement, Event>) => {
    setCurrentTime(event.currentTarget.currentTime)
  }

  useEffect(() => {
    if (audioARef.current && audioBRef.current) {
      audioARef.current.currentTime = currentTime
      audioBRef.current.currentTime = currentTime
    }
  }, [currentTime])

  useEffect(() => {
    return () => {
      objectUrlsRef.current.forEach((url) => URL.revokeObjectURL(url))
      objectUrlsRef.current = []
    }
  }, [])

  return (
    <div className="flex flex-col gap-6 rounded-xl border border-border bg-card p-4 text-card-foreground shadow-sm">
      <div className="flex flex-col gap-4 rounded-lg border border-border bg-muted/30 p-4">
        <div className="grid grid-cols-1 items-end gap-4 md:grid-cols-3">
          <div className="space-y-2">
            <label className="text-sm font-medium">Test Text</label>
            <Input value={text} onChange={(event) => setText(event.target.value)} />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Variant A</label>
            <Select value={voiceA} onValueChange={setVoiceA}>
              <SelectTrigger>
                <SelectValue placeholder="Choose a voice or variant" />
              </SelectTrigger>
              <SelectContent>
                {families.map((family) => (
                  <SelectGroup key={family.familyId}>
                    <SelectLabel>{family.displayName}</SelectLabel>
                    {family.members.map((member) => (
                      <SelectItem key={member.voice_id} value={member.voice_id}>
                        {member.variant_name ?? member.display_name ?? member.voice_id}
                        {member.source ? ` — ${member.source}` : ''}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Variant B</label>
            <Select value={voiceB} onValueChange={setVoiceB}>
              <SelectTrigger>
                <SelectValue placeholder="Choose a voice or variant" />
              </SelectTrigger>
              <SelectContent>
                {families.map((family) => (
                  <SelectGroup key={family.familyId}>
                    <SelectLabel>{family.displayName}</SelectLabel>
                    {family.members.map((member) => (
                      <SelectItem key={member.voice_id} value={member.voice_id}>
                        {member.variant_name ?? member.display_name ?? member.voice_id}
                        {member.source ? ` — ${member.source}` : ''}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <Button onClick={handleCompare} disabled={loading || !voiceA || !voiceB}>
          {loading ? 'Generating...' : 'Compare Variants'}
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        {(['A', 'B'] as const).map((side) => {
          const res = side === 'A' ? resultA : resultB
          const ref = side === 'A' ? audioARef : audioBRef
          if (!res) {
            return (
              <div key={side} className="flex h-32 items-center justify-center italic opacity-50">
                No data
              </div>
            )
          }

          return (
            <div key={side} className="flex flex-col gap-2">
              <div className="flex items-center justify-between px-2 text-xs font-semibold uppercase opacity-60">
                <span>Variant {side}</span>
              </div>
              <div className="relative h-16 overflow-hidden rounded-md border border-border bg-muted/20">
                <WaveformLane
                  peaks={res.peaks}
                  durMs={res.durationMs}
                  trimStartMs={0}
                  trimEndMs={0}
                  fadeInMs={0}
                  fadeOutMs={0}
                  pauseIntervals={res.metrics.pause_intervals}
                />
                <audio ref={ref} src={res.audioUrl} onTimeUpdate={handleTimeUpdate} className="hidden" />
              </div>
              <AudioStatsStrip
                metrics={res.metrics}
                diff={
                  side === 'B' && resultA
                    ? {
                        duration_diff: res.durationMs / 1000 - resultA.durationMs / 1000,
                        speech_rate_diff: (res.metrics.speech_rate_proxy || 0) - (resultA.metrics.speech_rate_proxy || 0),
                        lufs_diff: (res.metrics.lufs_integrated || 0) - (resultA.metrics.lufs_integrated || 0),
                        pause_ratio_diff: (res.metrics.pause_ratio || 0) - (resultA.metrics.pause_ratio || 0),
                      }
                    : null
                }
              />
            </div>
          )
        })}
      </div>

      {resultA && resultB && (
        <div className="flex justify-center">
          <Button
            onClick={togglePlayback}
            variant="outline"
            className="w-40"
            aria-label={isPlaying ? 'Pause synchronized playback' : 'Play synchronized playback'}
          >
            {isPlaying ? 'Pause Sync' : 'Play Sync'}
          </Button>
        </div>
      )}
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { AudioStatsStrip } from './waveform/AudioStatsStrip'
import { WaveformLane } from './waveform/WaveformLane'

interface CompareResult {
  audioUrl: string
  metrics: {
    duration_seconds?: number
    speech_rate_proxy?: number
    lufs_integrated?: number | null
    peak_dbfs?: number
    pause_ratio?: number
    pause_count?: number
    pause_intervals?: [number, number][]
  }
  peaks: number[]
  durationMs: number
}

export function VariantCompare() {
  const [text, setText] = useState('The quick brown fox jumps over the lazy dog.')
  const [voiceA, setVoiceA] = useState('')
  const [voiceB, setVoiceB] = useState('')
  const [loading, setLoading] = useState(false)
  const [resultA, setResultA] = useState<CompareResult | null>(null)
  const [resultB, setResultB] = useState<CompareResult | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)

  const audioARef = useRef<HTMLAudioElement | null>(null)
  const audioBRef = useRef<HTMLAudioElement | null>(null)

  const fetchAudio = async (voiceId: string): Promise<CompareResult> => {
    const res = await fetch('/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice_id: voiceId }),
    })
    if (!res.ok) throw new Error(`Failed to generate for ${voiceId}`)
    const data = await res.json()

    return {
      audioUrl: data.audio_url,
      metrics: data.metrics,
      peaks: data.peaks,
      durationMs: data.duration_ms,
    }
  }

  const handleCompare = async () => {
    if (!voiceA || !voiceB || !text) return
    setLoading(true)
    try {
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

  return (
    <div className="flex flex-col gap-6 rounded-xl border border-border bg-card p-4 text-card-foreground shadow-sm">
      <div className="flex flex-col gap-4 rounded-lg border border-border bg-muted/30 p-4">
        <div className="grid grid-cols-1 items-end gap-4 md:grid-cols-3">
          <div className="space-y-2">
            <label className="text-sm font-medium">Test Text</label>
            <Input value={text} onChange={(event) => setText(event.target.value)} />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Voice A (ID)</label>
            <Input value={voiceA} onChange={(event) => setVoiceA(event.target.value)} placeholder="vd_..." />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Voice B (ID)</label>
            <Input value={voiceB} onChange={(event) => setVoiceB(event.target.value)} placeholder="vd_..." />
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

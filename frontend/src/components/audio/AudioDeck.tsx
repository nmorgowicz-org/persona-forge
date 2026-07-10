import { useEffect, useMemo, useRef, useState, type ComponentProps } from 'react'
import { Download, Gauge, Pause, Play, Repeat, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Waveform } from '@/components/Waveform'
import { computePeaks } from '@/lib/waveform'
import { cn } from '@/lib/utils'
import { LevelMeter } from './LevelMeter'
import { SpectralAccent } from './SpectralAccent'
import { AudioStatsStrip } from '../waveform/AudioStatsStrip'

interface AudioDeckProps {
  src: string
  blob?: Blob | null
  className?: string
  autoPlay?: boolean
  compact?: boolean
  title?: string
  seed?: number | null
  metrics?: ComponentProps<typeof AudioStatsStrip>['metrics']
  rtf?: number | null
  downloadName?: string
}

export function AudioDeck({
  src,
  blob,
  className,
  autoPlay = true,
  compact = false,
  title = 'Audio result',
  seed = null,
  metrics = null,
  rtf = null,
  downloadName,
}: AudioDeckProps) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [peaks, setPeaks] = useState<number[] | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState<number | null>(null)
  const [isLooping, setIsLooping] = useState(false)
  const [playbackRate, setPlaybackRate] = useState(1)

  const currentLevel = useMemo(() => {
    if (!peaks || peaks.length === 0) return 0
    const index = Math.max(0, Math.min(peaks.length - 1, Math.floor(progress * peaks.length)))
    return peaks[index] ?? 0
  }, [peaks, progress])

  const peakLevel = useMemo(() => Math.max(...(peaks ?? [0])), [peaks])

  useEffect(() => {
    setPeaks(null)
    setProgress(0)
    setIsPlaying(false)
    if (!blob) return
    let cancelled = false
    computePeaks(blob).then((p) => {
      if (!cancelled) setPeaks(p)
    })
    return () => {
      cancelled = true
    }
  }, [blob])

  useEffect(() => {
    if (!blob || duration == null || !isFinite(duration)) return
    let cancelled = false
    computePeaks(blob, Math.max(24, Math.min(120, Math.round(duration * 24)))).then((p) => {
      if (!cancelled) setPeaks(p)
    })
    return () => {
      cancelled = true
    }
  }, [blob, duration])

  useEffect(() => {
    if (!autoPlay) return
    const audio = audioRef.current
    if (!audio) return
    audio.play().catch(() => {})
  }, [autoPlay, src])

  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.loop = isLooping
      audioRef.current.playbackRate = playbackRate
    }
  }, [isLooping, playbackRate])

  function togglePlay() {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) {
      audio.play()
    } else {
      audio.pause()
    }
  }

  function handleSeek(pct: number) {
    const audio = audioRef.current
    if (!audio || duration == null) return
    audio.currentTime = pct * duration
  }

  function download() {
    const a = document.createElement('a')
    a.href = src
    a.download = downloadName ?? `generated-audio-${Date.now()}.mp3`
    a.click()
  }

  return (
    <section
      className={cn(
        'rounded-lg border border-border bg-card/95 text-card-foreground shadow-sm ring-1 ring-white/5',
        compact ? 'p-2' : 'p-3',
        className,
      )}
      aria-label={title}
    >
      <audio
        ref={audioRef}
        src={src}
        onLoadedMetadata={(e) => {
          const d = e.currentTarget.duration
          if (d != null && isFinite(d)) setDuration(d)
        }}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onEnded={() => {
          setIsPlaying(false)
          setProgress(0)
        }}
        onTimeUpdate={(e) => {
          const audio = e.currentTarget
          if (audio.duration) setProgress(audio.currentTime / audio.duration)
        }}
        className="hidden"
      />

      <div className={cn('grid gap-3', compact ? 'grid-cols-[auto_1fr_auto]' : 'grid-cols-[auto_1fr] md:grid-cols-[auto_1fr_9rem]')}>
        <div className="flex items-center gap-1.5">
          <Button
            type="button"
            size={compact ? 'icon-sm' : 'icon'}
            variant="secondary"
            className="rounded-full"
            onClick={togglePlay}
            aria-label={isPlaying ? 'Pause audio' : 'Play audio'}
          >
            {isPlaying ? <Pause className="size-4" /> : <Play className="size-4 translate-x-px" />}
          </Button>
          {!compact && (
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              onClick={() => {
                const audio = audioRef.current
                if (audio) audio.currentTime = 0
                setProgress(0)
              }}
              aria-label="Restart audio"
            >
              <RotateCcw className="size-3.5" />
            </Button>
          )}
        </div>

        <div className="min-w-0">
          <Waveform
            peaks={peaks ?? Array(64).fill(0.15)}
            progress={progress}
            duration={compact ? null : duration}
            className={compact ? 'h-10' : undefined}
            onClick={handleSeek}
          />
          {!compact && <SpectralAccent peaks={peaks} className="mt-2" />}
        </div>

        <div className={cn('flex items-center gap-1', compact ? '' : 'justify-end md:flex-col md:items-stretch')}>
          {!compact && <LevelMeter level={currentLevel} peak={peakLevel} />}
          <div className="flex items-center justify-end gap-1">
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              onClick={() => setIsLooping(!isLooping)}
              title="Toggle loop"
              aria-label="Toggle loop"
            >
              <Repeat className={cn('size-3.5', isLooping ? 'text-primary' : 'text-muted-foreground')} />
            </Button>
            {!compact && (
              <Select value={playbackRate.toString()} onValueChange={(v) => setPlaybackRate(Number(v))}>
                <SelectTrigger className="h-7 w-20 px-2 text-[10px]" aria-label="Playback speed">
                  <Gauge className="size-3 text-muted-foreground" />
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="0.5">0.5x</SelectItem>
                  <SelectItem value="0.75">0.75x</SelectItem>
                  <SelectItem value="1">1.0x</SelectItem>
                  <SelectItem value="1.25">1.25x</SelectItem>
                  <SelectItem value="1.5">1.5x</SelectItem>
                  <SelectItem value="2">2.0x</SelectItem>
                </SelectContent>
              </Select>
            )}
            <Button type="button" size="icon-sm" variant="ghost" onClick={download} title="Download" aria-label="Download audio">
              <Download className="size-3.5 text-muted-foreground" />
            </Button>
          </div>
        </div>
      </div>

      {!compact && (metrics || seed != null || typeof rtf === 'number') && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border/70 pt-2">
          {metrics && <AudioStatsStrip metrics={metrics} className="min-h-7 flex-1 rounded border border-border/70" />}
          {seed != null && <span className="rounded border border-border px-2 py-1 text-[10px] font-mono text-muted-foreground">seed {seed}</span>}
          {typeof rtf === 'number' && <span className="rounded border border-border px-2 py-1 text-[10px] font-mono text-muted-foreground">RTF {rtf.toFixed(2)}x</span>}
        </div>
      )}
    </section>
  )
}

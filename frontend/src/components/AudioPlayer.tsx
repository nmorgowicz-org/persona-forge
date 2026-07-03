import { useEffect, useRef, useState } from 'react'
import { Pause, Play } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Waveform } from './Waveform'
import { computePeaks } from '@/lib/waveform'

interface AudioPlayerProps {
  src: string
  blob?: Blob | null
  className?: string
  /** Auto-play as soon as src is (re)set. Defaults to true; pass false for list items where
   * several players render at once (candidate takes, locked segments, library browser) — auto-
   * playing every one of those simultaneously would be jarring. */
  autoPlay?: boolean
}

export function AudioPlayer({ src, blob, className, autoPlay = true }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [peaks, setPeaks] = useState<number[] | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState<number | null>(null)

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
    // Only re-trigger on src change — toggling autoPlay itself shouldn't restart playback.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src])

  function togglePlay() {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) {
      audio.play()
    } else {
      audio.pause()
    }
  }

  return (
    <div className={className}>
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
          // Keep duration so time axis remains visible
        }}
        onTimeUpdate={(e) => {
          const audio = e.currentTarget
          if (audio.duration) setProgress(audio.currentTime / audio.duration)
        }}
        className="hidden"
      />
      <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/30 px-3 py-2">
        <Button
          type="button"
          size="icon"
          variant="secondary"
          className="shrink-0 rounded-full"
          onClick={togglePlay}
        >
          {isPlaying ? <Pause className="size-4" /> : <Play className="size-4" />}
        </Button>
        <Waveform
          peaks={peaks ?? Array(64).fill(0.15)}
          progress={progress}
          duration={duration}
          className="flex-1"
        />
      </div>
    </div>
  )
}

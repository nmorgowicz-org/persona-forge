import { useEffect, useRef, useState } from 'react'
import { Pause, Play } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Waveform } from './Waveform'
import { computePeaks } from '@/lib/waveform'

interface AudioPlayerProps {
  src: string
  blob?: Blob | null
  className?: string
}

export function AudioPlayer({ src, blob, className }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [peaks, setPeaks] = useState<number[] | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [progress, setProgress] = useState(0)

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
    const audio = audioRef.current
    if (!audio) return
    audio.play().catch(() => {})
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
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onEnded={() => setIsPlaying(false)}
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
        <Waveform peaks={peaks ?? Array(64).fill(0.15)} progress={progress} className="flex-1" />
      </div>
    </div>
  )
}

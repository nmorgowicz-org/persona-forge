import { useEffect, useId, useMemo, useRef, useState, type ComponentProps } from 'react'
import { Download, Gauge, Pause, Play, Repeat, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Waveform } from '@/components/Waveform'
import { claimPlayback, releasePlayback } from '@/lib/playbackFocus'
import { computePeaks } from '@/lib/waveform'
import { cn } from '@/lib/utils'
import { LevelMeter } from './LevelMeter'
import { SpectralAccent } from './SpectralAccent'
import { AudioStatsStrip } from '../waveform/AudioStatsStrip'
import { useDragScrubValue, parseNumericText } from '@/hooks/useDragScrubValue'
// 0.1-increment speed control, styled to match the segment Duration input in
// SegmentRackRow.tsx so the two "adjust after generation" controls read as a matched pair.
// A-1: drag-scrub + click-to-type + double-click reset to 1.0 + opt-in wheel nudge via the
// shared useDragScrubValue gesture.
function SpeedStepper({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const roundStep = (v: number) => Math.round(Math.max(0.5, Math.min(2, v)) * 10) / 10
  const {
    editing,
    draftText,
    setDraftText,
    commitEdit,
    displayValue,
    beginScrub,
    handleKeyDown,
    handleDoubleClick,
    wheelTargetRef,
  } = useDragScrubValue({
    value,
    min: 0.5,
    max: 2,
    dragScale: 0.01,
    step: 0.1,
    onChange,
    dragThreshold: 2,
    shiftStep: 0.5,
    parse: parseNumericText,
    format: (v) => v.toFixed(1),
    round: roundStep,
    defaultValue: 1,
    wheel: true,
  })
  return (
    <div
      data-testid="deck-speed"
      data-speed={displayValue}
      ref={(node) => { wheelTargetRef.current = node }}
      className="flex shrink-0 cursor-ew-resize touch-none select-none items-center gap-0.5"
      onPointerDown={(e) => { if (!(e.target as HTMLElement).closest('button, input')) beginScrub(e.nativeEvent, e.currentTarget, { openEditorOnRelease: true }) }}
      onDoubleClick={handleDoubleClick}
      title="Playback speed"
    >
      <Gauge className="size-3 text-muted-foreground" />
      {editing ? (
        <input
          type="text"
          inputMode="decimal"
          value={draftText}
          aria-label="Playback speed"
          onChange={(e) => setDraftText(e.target.value)}
          onBlur={commitEdit}
          onKeyDown={handleKeyDown}
          className="w-10 rounded-md border border-input bg-transparent px-1 py-0.5 text-[9px] outline-none transition-colors focus-visible:border-ring"
          autoFocus
        />
      ) : (
        <span className="font-mono tabular-nums text-[9px] text-foreground">{displayValue.toFixed(1)}</span>
      )}
      <span className="text-[9px] text-muted-foreground">x</span>
    </div>
  )
}

interface AudioDeckProps {
  src: string
  blob?: Blob | null
  className?: string
  autoPlay?: boolean
  compact?: boolean
  // 'stacked' gives the waveform its own full-width row (taller, easier to read) with
  // playback controls collapsed into a toolbar underneath — used by the OmniVoice candidate
  // rack, where the waveform is the primary thing being judged. 'inline' (default) keeps the
  // original single-row layout used by SpeakPage's result player.
  layout?: 'inline' | 'stacked'
  showSpectralAccent?: boolean
  title?: string
  seed?: number | null
  metrics?: ComponentProps<typeof AudioStatsStrip>['metrics']
  rtf?: number | null
  downloadName?: string
  // Initial value for the SpeedStepper (e.g. a previously persisted tempo choice for this
  // clip). Uncontrolled beyond that — onSpeedChange is how the caller finds out about
  // further nudges to persist as a real time-stretch, not just local preview.
  initialSpeed?: number
  onSpeedChange?: (speed: number) => void
}

export function AudioDeck({
  src,
  blob,
  className,
  autoPlay = true,
  compact = false,
  layout = 'inline',
  showSpectralAccent = true,
  title = 'Audio result',
  seed = null,
  metrics = null,
  rtf = null,
  downloadName,
  initialSpeed = 1,
  onSpeedChange,
}: AudioDeckProps) {
  const audioRef = useRef<HTMLAudioElement>(null)
  // Identifies this deck instance in the playback-focus registry (N6).
  const playbackFocusId = useId()
  const [peaks, setPeaks] = useState<number[] | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState<number | null>(null)
  const [isLooping, setIsLooping] = useState(false)
  const [playbackRate, setPlaybackRate] = useState(initialSpeed)

  function changeSpeed(v: number) {
    setPlaybackRate(v)
    onSpeedChange?.(v)
  }
  // A drag-selected slice (0..1 fractions) to audition on repeat; overrides whole-clip loop.
  const [region, setRegion] = useState<{ start: number; end: number } | null>(null)

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

  // Alt-drag scrub: move the playhead with the pointer. `progress` is mirrored immediately
  // (a paused element does not reliably emit timeupdate on seek) so the deck's playhead
  // tracks the gesture even when nothing is playing.
  function handleScrub(pct: number) {
    const audio = audioRef.current
    if (!audio || duration == null) return
    audio.currentTime = pct * duration
    setProgress(pct)
  }

  // A drag on the waveform selects a slice, then plays it; a click clears any slice.
  function handleSelectRegion(next: { start: number; end: number } | null) {
    setRegion(next)
    const audio = audioRef.current
    if (!next || !audio || duration == null) return
    audio.currentTime = next.start * duration
    audio.play().catch(() => {})
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
        onPlay={() => {
          setIsPlaying(true)
          // One claim per deck (N6): starting any deck silences whichever was sounding.
          claimPlayback(playbackFocusId, () => audioRef.current?.pause())
        }}
        onPause={() => {
          setIsPlaying(false)
          releasePlayback(playbackFocusId)
        }}
        onEnded={() => {
          setIsPlaying(false)
          setProgress(0)
          releasePlayback(playbackFocusId)
        }}
        onTimeUpdate={(e) => {
          const audio = e.currentTarget
          if (!audio.duration) return
          // Loop the selected slice on repeat until the user pauses or clears it.
          if (region && audio.currentTime / audio.duration >= region.end) {
            audio.currentTime = region.start * audio.duration
          }
          setProgress(audio.currentTime / audio.duration)
        }}
        className="hidden"
      />

      {layout === 'stacked' ? (
        <div className="flex flex-col gap-2">
          <Waveform
            peaks={peaks ?? Array(64).fill(0.15)}
            progress={progress}
            duration={duration}
            className="h-28"
            onClick={handleSeek}
            selection={region}
            onSelectRegion={handleSelectRegion}
            onScrub={handleScrub}
            testId="deck-waveform"
          />
          <div className="flex flex-wrap items-center gap-1">
            <Button
              type="button"
              size="icon-sm"
              variant="secondary"
              className="rounded-full"
              onClick={togglePlay}
              aria-label={isPlaying ? 'Pause audio' : 'Play audio'}
            >
              {isPlaying ? <Pause className="size-3.5" /> : <Play className="size-3.5 translate-x-px" />}
            </Button>
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
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              onClick={() => setIsLooping(!isLooping)}
              tooltip="Toggle loop"
              aria-label="Toggle loop"
            >
              <Repeat className={cn('size-3.5', isLooping ? 'text-primary' : 'text-muted-foreground')} />
            </Button>
            <LevelMeter level={currentLevel} peak={peakLevel} />
            <SpeedStepper value={playbackRate} onChange={changeSpeed} />
            <Button type="button" size="icon-sm" variant="ghost" onClick={download} tooltip="Download" aria-label="Download audio">
              <Download className="size-3.5 text-muted-foreground" />
            </Button>
          </div>
        </div>
      ) : (
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
              selection={region}
              onSelectRegion={handleSelectRegion}
              onScrub={handleScrub}
              testId="deck-waveform"
            />
            {!compact && showSpectralAccent && <SpectralAccent peaks={peaks} className="mt-2" />}
          </div>

          <div className={cn('flex items-center gap-1', compact ? '' : 'justify-end md:flex-col md:items-stretch')}>
            {!compact && <LevelMeter level={currentLevel} peak={peakLevel} />}
            <div className="flex items-center justify-end gap-1">
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                onClick={() => setIsLooping(!isLooping)}
                tooltip="Toggle loop"
                aria-label="Toggle loop"
              >
                <Repeat className={cn('size-3.5', isLooping ? 'text-primary' : 'text-muted-foreground')} />
              </Button>
              {!compact && (
                <SpeedStepper value={playbackRate} onChange={changeSpeed} />
              )}
              <Button type="button" size="icon-sm" variant="ghost" onClick={download} tooltip="Download" aria-label="Download audio">
                <Download className="size-3.5 text-muted-foreground" />
              </Button>
            </div>
          </div>
        </div>
      )}

      {!compact && (metrics || seed != null || typeof rtf === 'number') && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border/70 pt-2">
          {metrics && <AudioStatsStrip metrics={metrics} className="flex-1 rounded border border-border/70" />}
          {seed != null && <span className="rounded border border-border px-2 py-1 text-[10px] font-mono text-muted-foreground">seed {seed}</span>}
          {typeof rtf === 'number' && <span className="rounded border border-border px-2 py-1 text-[10px] font-mono text-muted-foreground">RTF {rtf.toFixed(2)}x</span>}
        </div>
      )}
    </section>
  )
}

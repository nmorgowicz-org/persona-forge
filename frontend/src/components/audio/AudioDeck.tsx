import { useEffect, useMemo, useRef, useState, type ComponentProps } from 'react'
import { Download, Gauge, Pause, Play, Repeat, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Waveform } from '@/components/Waveform'
import { useAudioSource } from '@/hooks/useAudioTransport'
import { envelopeFromChannels, type AudioEnvelope } from '@/lib/waveform'
import { getLoudness, type Loudness } from '@/lib/spectrogram'
import { CLIP_DBFS } from '@/lib/signal'
import { SpectrogramCanvas } from '@/components/waveform/SpectrogramCanvas'
import { setSignalView, useSignalView } from '@/lib/spectrogram'
import { cn } from '@/lib/utils'
import { LevelMeter } from './LevelMeter'
import { AudioStatsStrip } from '../waveform/AudioStatsStrip'
import { useDragScrubValue, parseNumericText } from '@/hooks/useDragScrubValue'
import { useShortcutScope, type ShortcutCommand } from '@/hooks/useGlobalShortcuts'
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
  title = 'Audio result',
  seed = null,
  metrics = null,
  rtf = null,
  downloadName,
  initialSpeed = 1,
  onSpeedChange,
}: AudioDeckProps) {
  const audioRef = useRef<HTMLAudioElement>(null)
  // The deck is one audio source among several (T1): starting it silences whichever was
  // sounding, and it reports its position to the coordinator.
  const source = useAudioSource('audio-deck', 'Audio deck')
  const [envelope, setEnvelope] = useState<AudioEnvelope | null>(null)
  const [decodeFailed, setDecodeFailed] = useState(false)
  // Clip stats (P4 / D5): peak, RMS and BS.1770-4 integrated loudness for the whole file.
  const [stats, setStats] = useState<Loudness | null>(null)
  const [clipCleared, setClipCleared] = useState(false)
  // Session-wide, so switching to Spectrum and coming back to the page does not undo it.
  const view = useSignalView()
  const [isPlaying, setIsPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState<number | null>(null)
  const [isLooping, setIsLooping] = useState(false)
  const [playbackRate, setPlaybackRate] = useState(initialSpeed)

  // The deck's transport joins the shared command registry (M4) so it is discoverable from the
  // palette and documented in the `?` keymap alongside the rest of the app. It keeps its own
  // keys to itself -- the deck has never had keyboard bindings, and adding them is not this
  // card's job. The commands read live closures through a ref so their identity never churns
  // (a re-registration per render would notify every registry subscriber).
  const deckActionsRef = useRef({ togglePlay: () => {}, restart: () => {}, toggleLoop: () => {}, download: () => {} })
  deckActionsRef.current = {
    togglePlay,
    restart: () => {
      const audio = audioRef.current
      if (audio) audio.currentTime = 0
      setProgress(0)
    },
    toggleLoop: () => setIsLooping((looping) => !looping),
    download,
  }
  const deckCommands = useMemo<ShortcutCommand[]>(
    () => [
      { id: 'deck.playPause', label: 'Play or pause this clip', run: () => deckActionsRef.current.togglePlay() },
      { id: 'deck.restart', label: 'Restart this clip', run: () => deckActionsRef.current.restart() },
      { id: 'deck.loop', label: 'Toggle looping for this clip', run: () => deckActionsRef.current.toggleLoop() },
      { id: 'deck.download', label: 'Download this clip', run: () => deckActionsRef.current.download() },
    ],
    [],
  )
  useShortcutScope('deck', title, deckCommands)

  function changeSpeed(v: number) {
    setPlaybackRate(v)
    onSpeedChange?.(v)
  }
  // A drag-selected slice (0..1 fractions) to audition on repeat; overrides whole-clip loop.
  const [region, setRegion] = useState<{ start: number; end: number } | null>(null)

  // The clip LED latches on the file's own sample peak and stays latched until cleared -- it is
  // a record that something clipped, not a live indicator that would blink away.
  const clipped = !clipCleared && stats != null && stats.peakDbfs >= CLIP_DBFS

  useEffect(() => {
    setEnvelope(null)
    setStats(null)
    setClipCleared(false)
    setDecodeFailed(false)
    setProgress(0)
    setIsPlaying(false)
    if (!blob) return
    let cancelled = false
    // One decode feeds both analyses: the waveform envelope (P2) and the loudness stats (P4),
    // the second computed off-thread by the P3 worker.
    const run = async () => {
      try {
        const ctx = new AudioContext()
        const buffer = await ctx.decodeAudioData(await blob.arrayBuffer())
        const samples = buffer.getChannelData(0)
        const nextEnvelope = envelopeFromChannels([samples], buffer.sampleRate)
        const nextStats = await getLoudness(`loudness:deck:${src}:${blob.size}`, samples, buffer.sampleRate)
        void ctx.close()
        if (cancelled) return
        setEnvelope(nextEnvelope)
        setStats(nextStats)
      } catch {
        if (!cancelled) setDecodeFailed(true)
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [blob, src])

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
          // One claim per deck: starting any deck silences whichever was sounding.
          source.claim(() => audioRef.current?.pause())
        }}
        onPause={() => {
          setIsPlaying(false)
          source.release()
        }}
        onEnded={() => {
          setIsPlaying(false)
          setProgress(0)
          source.release()
        }}
        onTimeUpdate={(e) => {
          const audio = e.currentTarget
          if (!audio.duration) return
          // Loop the selected slice on repeat until the user pauses or clears it.
          if (region && audio.currentTime / audio.duration >= region.end) {
            audio.currentTime = region.start * audio.duration
          }
          source.report(audio.currentTime, audio.duration)
          setProgress(audio.currentTime / audio.duration)
        }}
        className="hidden"
      />

      {/* Clip stats (P4 / D5): peak, RMS and integrated loudness of the file itself. These are
          properties of the audio, not of the playback, so they never move. */}
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="micro-label">Clip</span>
        <span className="readout" data-testid="deck-peak-readout">
          {stats ? (stats.peakDbfs === -Infinity ? '−∞' : stats.peakDbfs.toFixed(1)) : '—'}
          <span className="readout-unit">dBFS peak</span>
        </span>
        <span className="readout" data-testid="deck-lufs-readout">
          {stats ? (stats.lufs === -Infinity ? '−∞' : stats.lufs.toFixed(1)) : '—'}
          <span className="readout-unit">LUFS</span>
        </span>
        <button
          type="button"
          data-testid="deck-clip-led"
          data-state={clipped ? 'on' : 'off'}
          onClick={() => setClipCleared(true)}
          title={clipped ? 'This clip reached full scale. Click to clear.' : 'No sample reached full scale.'}
          className={cn(
            'rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wide uppercase transition-colors',
            clipped
              ? 'border-destructive/60 bg-destructive/20 text-destructive'
              : 'border-border/60 text-muted-foreground/60',
          )}
        >
          Clip
        </button>
      </div>

      {layout === 'stacked' ? (
        <div data-testid="transport-strip" className="flex flex-col gap-2">
          <div className="flex items-center gap-1">
            {(['wave', 'spectrum'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                data-testid={mode === 'wave' ? 'view-wave' : 'view-spectrum'}
                aria-pressed={view === mode}
                onClick={() => setSignalView(mode)}
                className={cn(
                  'rounded-full border px-2 py-0.5 text-[10px] font-medium transition-colors',
                  view === mode
                    ? 'border-border bg-background text-foreground'
                    : 'border-transparent text-muted-foreground hover:text-foreground',
                )}
              >
                {mode === 'wave' ? 'Wave' : 'Spectrum'}
              </button>
            ))}
          </div>
          {view === 'spectrum' ? (
            <SpectrogramCanvas
              blob={blob ?? null}
              cacheKey={src ? `spectrogram:deck:${src}:${blob?.size ?? 0}` : null}
              mediaRef={audioRef}
              playing={isPlaying}
              className="h-28 rounded-md"
              testId="deck-spectrogram"
            />
          ) : (
            <Waveform
              envelope={envelope}
              failed={decodeFailed}
              mediaRef={audioRef}
              playing={isPlaying}
              progress={progress}
              duration={duration}
              className="h-28"
              onClick={handleSeek}
              selection={region}
              onSelectRegion={handleSelectRegion}
              onScrub={handleScrub}
              testId="deck-waveform"
            />
          )}
          <div className="flex flex-wrap items-center gap-1">
            <Button
              type="button"
              size="icon"
              variant="secondary"
              className="rounded-full"
              onClick={togglePlay}
              aria-label={isPlaying ? 'Pause audio' : 'Play audio'}
            >
              {isPlaying ? <Pause className="size-4" /> : <Play className="size-4 translate-x-px" />}
            </Button>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              onClick={() => {
                const audio = audioRef.current
                if (audio) audio.currentTime = 0
                setProgress(0)
              }}
              aria-label="Restart audio"
            >
              <RotateCcw className="size-4" />
            </Button>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              onClick={() => setIsLooping(!isLooping)}
              tooltip="Toggle loop"
              aria-label="Toggle loop"
            >
              <Repeat className={cn('size-4', isLooping ? 'text-primary' : 'text-muted-foreground')} />
            </Button>
            <LevelMeter
              envelope={envelope}
              mediaRef={audioRef}
              playing={isPlaying}
              progress={progress}
              className="flex-1"
            />
            <span className="micro-label">Speed</span>
            <SpeedStepper value={playbackRate} onChange={changeSpeed} />
            <Button type="button" size="icon" variant="ghost" onClick={download} tooltip="Download" aria-label="Download audio">
              <Download className="size-4 text-muted-foreground" />
            </Button>
          </div>
        </div>
      ) : (
        <div data-testid="transport-strip" className={cn('grid gap-3', compact ? 'grid-cols-[auto_1fr_auto]' : 'grid-cols-[auto_1fr] md:grid-cols-[auto_1fr_9rem]')}>
          <div className="flex items-center gap-1.5">
            <Button
              type="button"
              size="icon"
              variant="secondary"
              className="rounded-full"
              onClick={togglePlay}
              aria-label={isPlaying ? 'Pause audio' : 'Play audio'}
            >
              {isPlaying ? <Pause className="size-4" /> : <Play className="size-4 translate-x-px" />}
            </Button>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              onClick={() => {
                const audio = audioRef.current
                if (audio) audio.currentTime = 0
                setProgress(0)
              }}
              aria-label="Restart audio"
            >
              <RotateCcw className="size-4" />
            </Button>
            {!compact && (
              <div className="flex items-center gap-1">
                {(['wave', 'spectrum'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    data-testid={mode === 'wave' ? 'view-wave' : 'view-spectrum'}
                    aria-pressed={view === mode}
                    onClick={() => setSignalView(mode)}
                    className={cn(
                      'rounded-full border px-2 py-0.5 text-[10px] font-medium transition-colors',
                      view === mode
                        ? 'border-border bg-background text-foreground'
                        : 'border-transparent text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {mode === 'wave' ? 'Wave' : 'Spectrum'}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="min-w-0">
            {view === 'spectrum' && !compact ? (
              // 112 px, not the waveform's 40: the log axis needs room before formants are
              // readable, and this is the height the stacked deck already gives a signal view.
              // Owner decision, 2026-09-23, from the three-way comparison in
              // docs/screenshots/artifacts/_gates/B-P3/heights/.
              <SpectrogramCanvas
                blob={blob ?? null}
                cacheKey={src ? `spectrogram:deck:${src}:${blob?.size ?? 0}` : null}
                mediaRef={audioRef}
                playing={isPlaying}
                className="h-28 rounded-md"
                testId="deck-spectrogram"
              />
            ) : (
            <Waveform
              envelope={envelope}
              failed={decodeFailed}
              mediaRef={audioRef}
              playing={isPlaying}
              progress={progress}
              duration={compact ? null : duration}
              className={compact ? 'h-10' : undefined}
              onClick={handleSeek}
              selection={region}
              onSelectRegion={handleSelectRegion}
              onScrub={handleScrub}
              testId="deck-waveform"
            />
            )}
          </div>

          <div className={cn('flex items-center gap-1', compact ? '' : 'justify-end md:flex-col md:items-stretch')}>
            <LevelMeter
              envelope={envelope}
              mediaRef={audioRef}
              playing={isPlaying}
              progress={progress}
              className={compact ? 'min-w-20' : undefined}
            />
            <div className="flex items-center justify-end gap-1">
              <Button
                type="button"
                size="icon"
                variant="ghost"
                onClick={() => setIsLooping(!isLooping)}
                tooltip="Toggle loop"
                aria-label="Toggle loop"
              >
                <Repeat className={cn('size-4', isLooping ? 'text-primary' : 'text-muted-foreground')} />
              </Button>
              {!compact && (
                <SpeedStepper value={playbackRate} onChange={changeSpeed} />
              )}
              <Button type="button" size="icon" variant="ghost" onClick={download} tooltip="Download" aria-label="Download audio">
                <Download className="size-4 text-muted-foreground" />
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

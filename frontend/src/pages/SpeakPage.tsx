import { useEffect, useRef, useState } from 'react'
import { motion } from 'motion/react'
import {
  AlertCircle,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Dice5,
  Loader2,
  Settings2,
  Square,
} from 'lucide-react'
import {
  classifyGenerateError,
  generateAsync,
  getGenerateJobProgress,
  cancelGenerate,
  listBuiltInVoices,
  listVoices,
  warmVoice,
  type BuiltInVoiceMeta,
} from '@/lib/api'
import { useAppStore } from '@/store'
import { cn } from '@/lib/utils'
import { VoiceSelector } from '@/components/VoiceSelector'
import { AudioPlayer } from '@/components/AudioPlayer'
import { InfoIcon } from '@/components/InfoIcon'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { AdvancedDrawer } from '@/components/audio/AdvancedDrawer'




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

function StructuredError({ error }: { error: string }) {
  const info = classifyGenerateError(error, null)
  const [expanded, setExpanded] = useState(false)
  const isStrong = info.type === 'TOO_LONG' || info.type === 'TIMEOUT'


  return (
    <div
      data-testid="speak-error"
      className={
        'flex flex-col gap-1 rounded-lg border px-3 py-2 text-xs ' +
        (isStrong
          ? 'border-warning/40 bg-warning/10 text-warning'
          : 'border-destructive/40 bg-destructive/10 text-destructive')
      }
    >
      <div className="flex items-start gap-2">
        {isStrong ? (
          <AlertTriangle className="mt-[2px] size-3.5 shrink-0" />
        ) : (
          <AlertCircle className="mt-[2px] size-3.5 shrink-0" />
        )}
        <div className="flex flex-col">
          <span className="text-[11px] font-medium">{info.headline}</span>
          <span className="text-[10px] opacity-90">{info.detail}</span>
        </div>
      </div>

      {/* Expandable raw error */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 self-start text-[10px] underline decoration-dotted underline-offset-2 opacity-70 hover:opacity-100"
      >
        {expanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
        Details
      </button>

      {expanded && (
        <pre className="max-h-32 overflow-auto whitespace-pre-wrap text-[10px] opacity-80">
          {error}
        </pre>
      )}
    </div>
  )
}

function formatEta(seconds: number | null): string {
  if (seconds == null) return 'Estimating…'
  if (seconds <= 0) return 'Finishing…'
  if (seconds < 60) return `About ${Math.ceil(seconds)}s remaining`
  return `About ${Math.ceil(seconds / 60)}m remaining`
}

const POLISH_OPTIONS = [
  { id: 'off', label: 'Off' },
  { id: 'Neutral', label: 'Neutral' },
  { id: 'Clean', label: 'Clean' },
  { id: 'Broadcast', label: 'Broadcast' },
  { id: 'Calm', label: 'Calm' },
  { id: 'Energetic', label: 'Energetic' },
  { id: 'Storyteller', label: 'Storyteller' },
] as const

interface SpeakResultMeta {
  jobId: string | null
  backend: string | null
  stylePreset: string | null
  appliedSteps: string[]
  rtf: number | null
  audioSeconds: number | null
}

export function SpeakPage() {
  const reducedMotion = useReducedMotion()
  const {
    text,
    setText,
    voiceId,
    setVoiceId,
    voices,
    setVoices,
    speakAudioUrl,
    setSpeakAudioUrl,
    speakIsGenerating,
    setSpeakIsGenerating,
    speakError,
    setSpeakError,
    speakJobId,
    setSpeakJobId,
    speakJobProgress,
    setSpeakJobProgress,
    speakLastSeed,
    setSpeakLastSeed,
    speakAudioBlob,
    setSpeakAudioBlob,
    serviceStarted,
  } = useAppStore()
  const [language, setLanguage] = useState('English')
  const [stylePreset, setStylePreset] = useState<(typeof POLISH_OPTIONS)[number]['id']>('off')
  const [seedInput, setSeedInput] = useState('')
  const [builtInVoices, setBuiltInVoices] = useState<BuiltInVoiceMeta[]>([])
  const [resultMeta, setResultMeta] = useState<SpeakResultMeta | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const runtimeTtsBackend = useAppStore((s) => s.runtimeTtsBackend)
  const isPocketBackend = runtimeTtsBackend === 'pocket_tts'


  async function refreshVoices() {
    try {
      setVoices(await listVoices())
    } catch {
      // Non-fatal
    }
  }

  useEffect(() => {
    refreshVoices()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!isPocketBackend) {
      setBuiltInVoices([])
      if (voiceId?.startsWith('pocket:')) setVoiceId(null)
      return
    }
    listBuiltInVoices()
      .then(setBuiltInVoices)
      .catch(() => setBuiltInVoices([]))
  }, [isPocketBackend, setVoiceId, voiceId])

  // Cleanup poll timer on unmount
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    }
  }, [])

  function startPoll(jobId: string) {
    // Clear any existing timer
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current)

    const poll = async () => {
      try {
        const p = await getGenerateJobProgress(jobId)
        setSpeakJobProgress(p)

        if (p.status === 'completed') {
          // Download audio and capture seed if present
          try {
            const audioRes = await fetch(
              `/generate/job/${encodeURIComponent(jobId)}/audio?response_format=mp3`,
            )
            if (!audioRes.ok) throw new Error('Failed to fetch audio')
            const blob = await audioRes.blob()
            const existing = useAppStore.getState().speakAudioUrl
            if (existing) URL.revokeObjectURL(existing)
            setSpeakAudioBlob(blob)
            setSpeakAudioUrl(URL.createObjectURL(blob))
            const seedHeader = audioRes.headers.get('X-Seed')
            if (seedHeader) setSpeakLastSeed(Number(seedHeader))
            const rtfHeader = audioRes.headers.get('X-RTF')
            const audioSecondsHeader = audioRes.headers.get('X-Audio-Seconds')
            const appliedStepsHeader = audioRes.headers.get('X-Applied-Steps')
            setResultMeta({
              jobId,
              backend: runtimeTtsBackend,
              stylePreset: audioRes.headers.get('X-Style-Preset'),
              appliedSteps: appliedStepsHeader
                ? appliedStepsHeader.split(',').map((step) => step.trim()).filter(Boolean)
                : [],
              rtf: rtfHeader ? Number(rtfHeader) : p.rtf ?? null,
              audioSeconds: audioSecondsHeader ? Number(audioSecondsHeader) : p.audio_seconds ?? null,
            })
          } catch {
            setSpeakError('Failed to download generated audio')
          }
          setSpeakIsGenerating(false)
          setSpeakJobId(null)
          setSpeakJobProgress(null)
          return
        }

        if (p.status === 'failed') {
          const msg = p.message || 'Generation failed'
          const info = classifyGenerateError(msg, null)
          setSpeakError(info.headline + (info.detail ? '\n' + info.detail : ''))
          setSpeakIsGenerating(false)
          setSpeakJobId(null)
          setSpeakJobProgress(null)
          return
        }

        if (p.status === 'cancelled') {
          setSpeakError('Generation was cancelled')
          setSpeakIsGenerating(false)
          setSpeakJobId(null)
          setSpeakJobProgress(null)
          return
        }

        // Still running: schedule next poll
        pollTimerRef.current = setTimeout(poll, 400)
      } catch {
        // On transient error, keep polling
        pollTimerRef.current = setTimeout(poll, 600)
      }
    }

    poll()
  }

  async function handleGenerate() {
    if (!text.trim() || speakIsGenerating) return
    setSpeakIsGenerating(true)
    setSpeakError(null)
    setSpeakJobProgress(null)
    setResultMeta(null)
    try {
      const seed = seedInput.trim() ? Number(seedInput) : undefined
      const { job_id } = await generateAsync({
        text,
        language,
        voiceId,
        stylePreset: stylePreset === 'off' ? undefined : stylePreset,
        seed,
        responseFormat: 'mp3',
      })
      setSpeakJobId(job_id)
      startPoll(job_id)
    } catch (err) {
      setSpeakError(err instanceof Error ? err.message : String(err))
      setSpeakIsGenerating(false)
    }
  }

  async function handleStop() {
    if (!speakJobId) return
    try {
      await cancelGenerate(speakJobId)
    } catch {
      // Best-effort; server may already be stopping it.
    }
    // Let the poller detect cancelled status
  }

  function handleVoiceChange(nextVoiceId: string | null) {
    setVoiceId(nextVoiceId)
    const builtIn = builtInVoices.find((voice) => voice.voice_id === nextVoiceId)
    if (builtIn?.language) setLanguage(builtIn.language)
    // Bounce the runtime to actually load/cache this voice's clone state now, so the
    // next Generate click doesn't pay a cold-load or first-time voice-state-build cost.
    if (nextVoiceId && !nextVoiceId.startsWith('pocket:')) {
      warmVoice(nextVoiceId).catch(() => {
        // Best-effort; get_pocket_tts_voice_state re-resolves on generate anyway.
      })
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <motion.div 
        initial={{ opacity: 0, y: reducedMotion ? 0 : -8 }} 
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-2xl font-semibold tracking-tight">Speak</h1>
         <p className="text-sm text-muted-foreground">
           Type text, pick a curated Pocket voice or clone your own, and hear it spoken.
         </p>
      </motion.div>

      <motion.div
        className="flex flex-col gap-5 rounded-xl border border-border bg-card p-6 text-card-foreground shadow-sm"
        initial={{ opacity: 0, y: reducedMotion ? 0 : 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
      >
         <textarea
           data-testid="speak-text-input"
           aria-label="Text to synthesize"
           className="min-h-48 resize-y rounded-lg border border-input bg-transparent p-4 text-base outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
           placeholder="Say something..."
           value={text}
           onChange={(e) => setText(e.target.value)}
         />


        {/* Character count + length hint */}
        {text.length > 0 && (
          <div className="flex flex-col gap-0.5">
            <p className="text-[10px] text-muted-foreground tabular-nums">
              {text.length} / 2000
            </p>
            {text.length > 1500 && (
              <p className="text-[10px] text-warning">
                Very long texts may fail or time out. Consider breaking into shorter pieces.
              </p>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <VoiceSelector
            voices={voices}
            builtInVoices={isPocketBackend ? builtInVoices : []}
            voiceId={voiceId}
            onChange={handleVoiceChange}
          />

          <Select value={language} onValueChange={setLanguage}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="English">English</SelectItem>
              <SelectItem value="Chinese">Chinese</SelectItem>
              <SelectItem value="French">French</SelectItem>
              <SelectItem value="German">German</SelectItem>
              <SelectItem value="Italian">Italian</SelectItem>
              <SelectItem value="Portuguese">Portuguese</SelectItem>
              <SelectItem value="Spanish">Spanish</SelectItem>
            </SelectContent>
          </Select>

          <Select value={stylePreset} onValueChange={(value) => setStylePreset(value as typeof stylePreset)}>
            <SelectTrigger className="w-44">
              <SelectValue placeholder="Tone / polish" />
            </SelectTrigger>
            <SelectContent>
              {POLISH_OPTIONS.map((option) => (
                <SelectItem key={option.id} value={option.id}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

           <InfoIcon 
             text="Tone / polish applies real post-processing after generation. Voice variants still control the performance; polish only finishes the rendered audio." 
             className="size-3.5 shrink-0 text-muted-foreground" 
           />


          <div className="flex items-center gap-1">
            <input
              type="number"
              inputMode="numeric"
              placeholder="Random seed"
              value={seedInput}
              onChange={(e) => setSeedInput(e.target.value)}
              className="h-9 w-32 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            />
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label="Randomize seed"
                  onClick={() => setSeedInput('')}
                  className="flex size-9 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
                >
                  <Dice5 className="size-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="top">
                Clear to use a fresh random seed next generation
              </TooltipContent>
            </Tooltip>
          </div>

          {speakIsGenerating && speakJobId ? (
            // Stop button (secondary)
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleStop}
              className="h-9 gap-1.5"
            >
              <Square className="size-3" />
              Stop
            </Button>
          ) : null}

          <Button
            type="button"
            data-testid="speak-generate-button"
            onClick={handleGenerate}
            disabled={!text.trim() || speakIsGenerating || !serviceStarted}
            title={serviceStarted ? undefined : 'Model is still loading'}
            className={cn(
              'transition-all duration-200',
              !speakIsGenerating &&
                text.trim() &&
                serviceStarted &&
                'shadow-[0_4px_20px_-6px_color-mix(in_oklch,var(--primary),transparent_35%)] hover:shadow-[0_6px_24px_-6px_color-mix(in_oklch,var(--primary),transparent_20%)]',
            )}
          >
            {speakIsGenerating ? (
              <span className="flex items-center gap-1.5">
                <Loader2 className="size-4 animate-spin" />
                Generating…
              </span>
            ) : (
              'Generate'
            )}
          </Button>
        </div>

        {/* Progress + ETA while generating */}
        {speakIsGenerating && speakJobProgress && (
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <motion.div
                  className="h-full bg-primary"
                  animate={{
                     width: `${Math.min(100, Math.max(3, speakJobProgress.progress_pct))}%`,
                  }}
                  transition={{ ease: 'easeOut', duration: 0.3 }}
                />
              </div>
               {typeof speakJobProgress.progress_pct === 'number' && (
                 <span className="shrink-0 text-[10px] text-muted-foreground tabular-nums">
                   {Math.round(speakJobProgress.progress_pct)}%
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground">
              {speakJobProgress.status === 'cancelled'
                ? 'Cancelling…'
                : formatEta(speakJobProgress.eta_seconds)}
              {typeof speakJobProgress.audio_seconds_generated === 'number' && speakJobProgress.audio_seconds_generated > 0 && (
                <span className="ml-2 text-[10px] text-muted-foreground/70">
                  · {speakJobProgress.audio_seconds_generated.toFixed(1)}s generated
                </span>
              )}
              {typeof speakJobProgress.live_rtf_estimate === 'number' && (
                <span className="ml-2 text-[10px] text-primary/80 font-mono">
                  · RTF: {speakJobProgress.live_rtf_estimate.toFixed(2)}x
                </span>
              )}
               {speakJobProgress.elapsed_seconds > 0 && (
                 <span className="ml-2 text-[10px] text-muted-foreground/70">
                   · {Math.round(speakJobProgress.elapsed_seconds)}s elapsed
                </span>
              )}
               {speakJobProgress.elapsed_seconds >= 30 &&
                 speakJobProgress.elapsed_seconds < 60 &&
                 speakJobProgress.status !== 'cancelled' && (
                   <span className="ml-2 text-[10px] text-warning">
                     This is taking longer than usual.
                   </span>
                 )}
               {speakJobProgress.elapsed_seconds >= 60 &&
                 speakJobProgress.status !== 'cancelled' && (
                   <span className="ml-2 text-[10px] text-warning">
                     Generation is in progress; this may take several minutes for longer texts.
                   </span>
                 )}
            </p>
          </div>
        )}

        {/* Structured error display */}
        {speakError && <StructuredError error={speakError} />}

        {speakAudioUrl && (
          <div data-testid="speak-result" className="flex flex-col gap-2">
            <AudioPlayer
              src={speakAudioUrl}
              blob={speakAudioBlob}
              seed={speakLastSeed}
              rtf={resultMeta?.rtf ?? null}
              metrics={resultMeta?.audioSeconds ? { duration_seconds: resultMeta.audioSeconds } : null}
              showSpectralAccent={false}
            />
            {speakLastSeed !== null && (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>
                    Seed: <span className="font-mono text-foreground">{speakLastSeed}</span>
                  </span>
                  {seedInput !== String(speakLastSeed) && (
                    <button
                      type="button"
                      onClick={() => setSeedInput(String(speakLastSeed))}
                      className="underline decoration-dotted hover:text-foreground"
                    >
                      Lock this seed
                    </button>
                  )}
                </div>


              </div>
            )}

            <AdvancedDrawer
              title="Advanced Diagnostics"
              description="Detailed backend metadata for debugging and consistency checks."
              trigger={
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 gap-1 px-2 text-[10px]"
                >
                  <Settings2 className="size-3" />
                  Advanced
                </Button>
              }
            >
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[10px] font-mono">
                <div className="flex justify-between items-center gap-2">
                  <span className="opacity-60">Job ID:</span>
                  <span className="max-w-[120px] truncate">{speakJobId || 'n/a'}</span>
                  <InfoIcon text="Unique backend identifier for this generation job." className="size-3 shrink-0 text-muted-foreground" />
                </div>
                <div className="flex justify-between items-center gap-2">
                  <span className="opacity-60">Backend:</span>
                   <span className="capitalize">{runtimeTtsBackend?.replace('_', ' ') ?? 'unknown'}</span>
                  <InfoIcon text="Accelerated by Intel OpenVINO for faster CPU inference." className="size-3 shrink-0 text-muted-foreground" />
                </div>
                <div className="flex justify-between items-center gap-2">
                  <span className="opacity-60">Seed:</span>
                  <span className="tabular-nums">{speakLastSeed ?? 'N/A'}</span>
                  <InfoIcon text="Symmetric seed used to control randomness." className="size-3 shrink-0 text-muted-foreground" />
                </div>
                <div className="flex justify-between items-center gap-2">
                  <span className="opacity-60">Status:</span>
                  <span className="text-success">Completed</span>
                  <InfoIcon text="Audio successfully generated and downloaded." className="size-3 shrink-0 text-muted-foreground" />
                </div>
              </div>
            </AdvancedDrawer>


          </div>
        )}
      </motion.div>
    </div>
  )
}

import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2, Wand2, X } from 'lucide-react'
import {
  cancelVoicePreparation,
  getVoiceEngineBindings,
  prepareVoiceOnEngine,
  TranscriptReviewRequired,
  type VoiceEngineBinding,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { chipExplanation, chipText, shortEngineLabel } from '@/lib/voiceEngines'

function chipTone(binding: VoiceEngineBinding): string {
  if (binding.status === 'ready') return 'border-success/40 bg-success/10 text-success'
  if (binding.status === 'failed') return 'border-destructive/40 bg-destructive/10 text-destructive'
  if (binding.status === 'preparing') return 'border-cyan-500/40 bg-cyan-500/10 text-cyan-400'
  if (binding.status === 'unsupported' || !binding.installed) return 'border-border bg-muted/30 text-muted-foreground'
  return 'border-border bg-background text-foreground hover:bg-muted'
}

interface ReviewState {
  engine: VoiceEngineBinding
  reason: 'missing' | 'unreviewed'
  /** null = follow the stored transcript (e.g. after Whisper filled it in). */
  draft: string | null
}

/**
 * The My voices "Engines" row (plan §5.4): one chip per engine saying whether this saved voice is
 * ready there, with Prepare, inline progress, a transcript review step for engines that clone with
 * the words, and a plain explanation on hover, focus or tap. Keyboard accessible: every chip is a
 * button.
 */
export function VoiceEnginesRow({
  voiceId,
  transcript,
  refreshToken,
  onTranscribe,
  onTranscriptSaved,
  onOpenEngines,
  className,
}: {
  voiceId: string
  /** The voice's stored transcript, shown for confirmation or editing. */
  transcript: string
  /** Changes whenever the voice (its transcript or audio) may have changed, to refetch status. */
  refreshToken: string | number
  /** Whisper transcription for a voice with no transcript (the card's existing action). */
  onTranscribe?: () => Promise<boolean>
  /** Called after a reviewed transcript was saved, so the card shows the new words. */
  onTranscriptSaved?: () => void | Promise<void>
  onOpenEngines: () => void
  className?: string
}) {
  const [bindings, setBindings] = useState<VoiceEngineBinding[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [explain, setExplain] = useState<string | null>(null)
  const [review, setReview] = useState<ReviewState | null>(null)
  const [busyEngine, setBusyEngine] = useState<string | null>(null)
  const [whisperBusy, setWhisperBusy] = useState(false)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const reload = useCallback(async () => {
    try {
      const next = await getVoiceEngineBindings(voiceId)
      if (mounted.current) {
        setBindings(next)
        setError(null)
      }
      return next
    } catch (err) {
      if (mounted.current) setError(String((err as Error)?.message || err))
      return null
    }
  }, [voiceId])

  useEffect(() => {
    let current = true
    getVoiceEngineBindings(voiceId)
      .then((next) => {
        if (current && mounted.current) {
          setBindings(next)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (current && mounted.current) setError(String((err as Error)?.message || err))
      })
    return () => {
      current = false
    }
    // refreshToken is the "refetch now" signal from the library.
  }, [voiceId, refreshToken])

  // Poll only while something is being prepared.
  const anyPreparing = bindings?.some((binding) => binding.status === 'preparing') ?? false
  useEffect(() => {
    if (!anyPreparing) return
    const timer = window.setInterval(() => void reload(), 1000)
    return () => window.clearInterval(timer)
  }, [anyPreparing, reload])

  async function start(binding: VoiceEngineBinding, reviewed?: { transcript?: string; transcriptConfirmed?: boolean }) {
    setBusyEngine(binding.engine)
    setError(null)
    try {
      await prepareVoiceOnEngine(voiceId, binding.engine, reviewed)
      setReview(null)
      if (reviewed) await onTranscriptSaved?.()
      await reload()
    } catch (err) {
      if (err instanceof TranscriptReviewRequired) {
        setReview({ engine: binding, reason: err.reason, draft: err.transcript || null })
        setExplain(null)
      } else {
        setError(String((err as Error)?.message || err))
      }
    } finally {
      if (mounted.current) setBusyEngine(null)
    }
  }

  function activate(binding: VoiceEngineBinding) {
    if (binding.status === 'preparing') {
      setExplain(explain === binding.engine ? null : binding.engine)
      return
    }
    if (binding.status === 'unsupported') {
      setExplain(explain === binding.engine ? null : binding.engine)
      return
    }
    if (!binding.installed) {
      onOpenEngines()
      return
    }
    if (binding.status === 'needs_preparation' || binding.status === 'failed') {
      if (binding.blocker === 'transcript_missing' || binding.blocker === 'transcript_unreviewed') {
        // Resolve the words here, before anything runs: never at request time.
        setReview({
          engine: binding,
          reason: binding.blocker === 'transcript_missing' ? 'missing' : 'unreviewed',
          draft: null,
        })
        setExplain(null)
        return
      }
      void start(binding)
      return
    }
    setExplain(explain === binding.engine ? null : binding.engine)
  }

  async function cancel(binding: VoiceEngineBinding) {
    try {
      await cancelVoicePreparation(voiceId, binding.engine)
    } catch (err) {
      setError(String((err as Error)?.message || err))
    }
    await reload()
  }

  async function submitReview() {
    if (!review) return
    const words = (review.draft ?? transcript).trim()
    if (!words) return
    const changed = words !== transcript.trim()
    await start(review.engine, changed ? { transcript: words } : { transcriptConfirmed: true })
  }

  async function whisper() {
    if (!onTranscribe) return
    setWhisperBusy(true)
    try {
      await onTranscribe()
      // The card now holds the Whisper words; reload the review draft from the refreshed voice.
      setReview((current) => (current ? { ...current, draft: null } : current))
    } finally {
      if (mounted.current) setWhisperBusy(false)
    }
  }

  const draft = review?.draft ?? transcript
  const explained = bindings?.find((binding) => binding.engine === explain) ?? null

  return (
    <div
      data-testid="voice-engines-row"
      role="group"
      aria-label="Engines this voice can be used with"
      className={cn('rounded-control border border-border/60 bg-muted/20 p-2', className)}
    >
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Engines</p>
      {bindings === null ? (
        <p className="text-xs text-muted-foreground">{error ?? 'Checking engines…'}</p>
      ) : (
        <ul className="flex flex-wrap gap-1.5">
          {bindings.map((binding) => (
            <li key={binding.engine} className="flex items-center gap-0.5">
              <button
                type="button"
                data-testid={`engine-chip-${binding.engine}`}
                data-status={binding.status}
                data-installed={binding.installed}
                title={chipExplanation(binding)}
                aria-label={`${chipText(binding)}. ${chipExplanation(binding)}`}
                aria-disabled={busyEngine !== null}
                disabled={busyEngine === binding.engine}
                onClick={() => activate(binding)}
                className={cn(
                  'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring',
                  chipTone(binding),
                )}
              >
                {binding.status === 'preparing' && <Loader2 className="size-3 animate-spin" aria-hidden />}
                <span>{chipText(binding)}</span>
              </button>
              {binding.status === 'preparing' && (
                <Button
                  type="button"
                  size="icon-xs"
                  variant="ghost"
                  aria-label={`Cancel preparing for ${shortEngineLabel(binding)}`}
                  tooltip="Cancel"
                  onClick={() => void cancel(binding)}
                >
                  <X />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      {explained && (
        <p role="status" data-testid="engine-chip-explanation" className="mt-1.5 text-[11px] text-muted-foreground">
          {chipExplanation(explained)}
        </p>
      )}

      {bindings?.some((binding) => binding.status === 'failed') && (
        <p role="alert" className="mt-1.5 text-[11px] text-destructive">
          {bindings
            .filter((binding) => binding.status === 'failed')
            .map((binding) => `${shortEngineLabel(binding)}: ${binding.error}`)
            .join(' · ')}
        </p>
      )}

      {error && bindings !== null && (
        <p role="alert" className="mt-1.5 text-[11px] text-destructive">
          {error}
        </p>
      )}

      {review && (
        <div
          data-testid="transcript-review"
          className="mt-2 flex flex-col gap-1.5 rounded border border-warning/30 bg-warning/5 p-2"
        >
          <label htmlFor={`review-${voiceId}`} className="text-[11px] font-medium">
            {review.engine.label} clones with the transcript.{' '}
            {review.reason === 'missing'
              ? 'This voice has none: type what is said in the recording, or generate it with Whisper.'
              : 'The speech check disagreed with the stored words: confirm them or fix them.'}{' '}
            They must match the audio exactly.
          </label>
          <textarea
            id={`review-${voiceId}`}
            value={draft}
            rows={3}
            onChange={(event) => setReview({ ...review, draft: event.target.value })}
            className="w-full resize-y rounded border border-border bg-background px-2 py-1 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <div className="flex flex-wrap items-center gap-1.5">
            <Button
              type="button"
              size="xs"
              disabled={!draft.trim() || busyEngine !== null}
              onClick={() => void submitReview()}
            >
              {draft.trim() === transcript.trim() && transcript.trim()
                ? 'Confirm and prepare'
                : 'Save words and prepare'}
            </Button>
            {onTranscribe && (
              <Button type="button" size="xs" variant="outline" disabled={whisperBusy} onClick={() => void whisper()}>
                <Wand2 /> {whisperBusy ? 'Transcribing…' : 'Generate with Whisper'}
              </Button>
            )}
            <Button type="button" size="xs" variant="ghost" onClick={() => setReview(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import {
  AlertTriangle,
  AudioWaveform,
  CheckCircle2,
  Layers,
  Loader2,
  Mic2,
  Pencil,
  Plus,
  Scissors,
  Sparkles,
  Star,
  Trash2,
  Shuffle,
  Wand2,
} from 'lucide-react'
import {
  deleteOmniVoiceSegment,
  deleteVoice,
  getVoice,
  listOmniVoiceSegments,
  listVoices,
  normalizeVoiceReference,
  setDefaultVoiceVariant,
  trimVoiceReferenceSilence,
  updateVoiceSampleText,
  type SegmentMeta,
  type VoiceMeta,
} from '@/lib/api'
import { hasChipSelections, type ChipSelections } from '@/lib/voiceDesignChips'
import { MiniAudioDeck } from '@/components/audio/MiniAudioDeck'
import { Button } from '@/components/ui/button'
import { createStitchClipFromSegment } from '@/lib/stitchClips'
import { useAppStore, type StitchPlanClip } from '@/store'
import { VariantCompare } from '@/components/VariantCompare'
import { cn } from '@/lib/utils'
import { InfoIcon } from '@/components/InfoIcon'

const MOUNTED_REF_SOURCE = 'mounted_ref_audio' as const

interface VoiceReferenceMetrics {
  duration_seconds?: number | null
  sample_rate?: number | null
  lufs_integrated?: number | null
  peak_dbfs?: number | null
  true_peak_dbtp?: number | null
  true_peak_dbfs?: number | null
  rms_dbfs?: number | null
  speech_rate_proxy?: number | null
  words_per_second?: number | null
  pause_count?: number | null
  pause_total_seconds?: number | null
  pause_ratio?: number | null
  median_pause_ms?: number | null
  longest_pause_ms?: number | null
}

type VoiceWithReferenceMeta = VoiceMeta & {
  metrics?: VoiceReferenceMetrics | null
  source_model?: string | null
  source_prompt?: string | null
  source_generation_params?: Record<string, unknown> | null
  source_use_case?: string | null
  use_case?: string | null
  use_cases?: string[] | null
}

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

function isMountedRef(voice: VoiceMeta): boolean {
  return (voice as VoiceMeta & { source?: string }).source === MOUNTED_REF_SOURCE
}

// needs_review is set from the audio quality gate (quality_warnings) for regular saves and
// from ASR severity for the mounted reference voice -- keep the transcript badge scoped to
// ASR only so a clipping/SNR warning doesn't get mislabeled as "review the transcript".
function voiceTranscriptNeedsReview(voice: VoiceMeta): boolean {
  const severity = voice.asr?.severity
  return Boolean(
    severity === 'warn' || severity === 'fail' || severity === 'no_speech' || severity === 'error',
  )
}

function isClippingWarning(warning: string): boolean {
  return /clipping/i.test(warning)
}

function isTooLongWarning(warning: string): boolean {
  return /too long/i.test(warning)
}

// Only clipping (fixable by re-normalizing peak/loudness) and excess duration (often
// trailing/leading silence, fixable by trimming) have an automatic remedy today. Low SNR
// and "too short" require a fresh recording, so no fix action is offered for those.
function getFixableQualityWarnings(
  voice: VoiceMeta,
): { warning: string; action: 'normalize' | 'trim' }[] {
  const warnings = voice.quality_warnings ?? []
  const fixable: { warning: string; action: 'normalize' | 'trim' }[] = []
  const clipping = warnings.find(isClippingWarning)
  if (clipping) fixable.push({ warning: clipping, action: 'normalize' })
  const tooLong = warnings.find(isTooLongWarning)
  if (tooLong) fixable.push({ warning: tooLong, action: 'trim' })
  return fixable
}


function QualityGatePanel({
  voice,
  busy,
  onNormalize,
  onTrimSilence,
  onFixAll,
}: {
  voice: VoiceMeta
  busy: boolean
  onNormalize: () => void
  onTrimSilence: () => void
  onFixAll: () => void
}) {
  const [isAdvanced, setIsAdvanced] = useState(false)
  const warnings = voice.quality_warnings ?? []
  if (warnings.length === 0) return null
  const score = voice.quality_score
  const scoreColor =
    score === undefined
      ? 'text-muted-foreground'
      : score >= 80
        ? 'text-emerald-400'
        : score >= 50
          ? 'text-amber-400'
          : 'text-red-400'
  const fixable = getFixableQualityWarnings(voice)
  
  return (
    <div className="rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
      <div className="mb-1 flex items-center justify-between gap-2">
        <p className="flex items-center gap-1 font-semibold uppercase tracking-wide text-[10px]">
          <AlertTriangle className="size-3" />
          Reference quality
        </p>
        <div className="flex items-center gap-2">
          {score !== undefined && (
            <span className={cn('font-mono text-[11px]', scoreColor)}>{Math.round(score)}/100</span>
          )}
          <button 
            onClick={() => setIsAdvanced(!isAdvanced)}
            className="text-[10px] opacity-60 hover:opacity-100 underline underline-offset-2"
          >
            {isAdvanced ? 'Simple' : 'Advanced'}
          </button>
        </div>
      </div>
      <ul className="list-disc space-y-0.5 pl-4">
        {warnings.map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
      {fixable.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {!isAdvanced ? (
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1.5 border-amber-500/40 bg-transparent text-amber-100 hover:bg-amber-500/20"
              disabled={busy}
              onClick={onFixAll}
            >
              <Wand2 className="size-3.5" />
              Auto-fix: {fixable.length > 1 ? 'Trim & Normalize' : fixable[0].action === 'normalize' ? 'Normalize loudness' : 'Trim silence'}
            </Button>
          ) : (
            <>
              {fixable.some(f => f.action === 'normalize') && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1.5 border-amber-500/40 bg-transparent text-amber-100 hover:bg-amber-500/20"
                  disabled={busy}
                  onClick={onNormalize}
                >
                  <Wand2 className="size-3.5" />
                  Normalize
                </Button>
              )}
              {fixable.some(f => f.action === 'trim') && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1.5 border-amber-500/40 bg-transparent text-amber-100 hover:bg-amber-500/20"
                  disabled={busy}
                  onClick={onTrimSilence}
                >
                  <Scissors className="size-3.5" />
                  Trim
                </Button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}


function voiceTranscriptSource(voice: VoiceMeta): string {
  if (voice.sample_text_source === 'whisper') return 'Whisper draft'
  if (voice.sample_text_source === 'env') return 'Startup override'
  if (voice.sample_text_source === 'user') return 'User edited'
  return 'Transcript'
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function formatNumber(value: unknown, digits = 1, suffix = ''): string {
  const numeric = finiteNumber(value)
  if (numeric === null) return '--'
  return `${numeric.toFixed(digits)}${suffix}`
}

function formatPercent(value: unknown): string {
  const numeric = finiteNumber(value)
  if (numeric === null) return '--'
  return `${Math.round(numeric * 100)}%`
}

function formatDuration(value: unknown): string {
  const numeric = finiteNumber(value)
  if (numeric === null) return '--'
  if (numeric < 60) return `${numeric.toFixed(1)}s`
  const minutes = Math.floor(numeric / 60)
  const seconds = Math.round(numeric % 60)
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

function labelFromToken(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function sourceLabel(source: string | null | undefined): string | null {
  if (!source) return null
  const normalized = source.toLowerCase()
  if (normalized === MOUNTED_REF_SOURCE) return 'Mounted reference'
  if (normalized.includes('omnivoice')) return 'OmniVoice'
  if (normalized.includes('voice_design')) return 'VoiceDesign'
  if (normalized.includes('qwen')) return 'Qwen'
  if (normalized.includes('pocket')) return 'Pocket'
  if (normalized.includes('upload')) return 'Upload'
  if (normalized.includes('external')) return 'External'
  return labelFromToken(source)
}

function getVoiceMetrics(voice: VoiceMeta): VoiceReferenceMetrics | null {
  const metrics = (voice as VoiceWithReferenceMeta).metrics
  if (!metrics) return null
  return Object.values(metrics).some((value) => finiteNumber(value) !== null) ? metrics : null
}

function getSpeechRate(metrics: VoiceReferenceMetrics): number | null {
  return finiteNumber(metrics.words_per_second) ?? finiteNumber(metrics.speech_rate_proxy)
}

function getTruePeak(metrics: VoiceReferenceMetrics): number | null {
  return finiteNumber(metrics.true_peak_dbtp) ?? finiteNumber(metrics.true_peak_dbfs)
}

function getUseCaseBadges(voice: VoiceMeta): string[] {
  const v = voice as VoiceWithReferenceMeta
  const params = v.source_generation_params ?? {}
  const raw = [
    v.variant_name,
    v.variant_kind,
    v.source_use_case,
    v.use_case,
    ...(Array.isArray(v.use_cases) ? v.use_cases : []),
    typeof params.use_case === 'string' ? params.use_case : null,
    typeof params.delivery_variant === 'string' ? params.delivery_variant : null,
    typeof params.style_preset === 'string' ? params.style_preset : null,
  ]

  const seen = new Set<string>()
  return raw
    .filter((value): value is string => Boolean(value && value.trim()))
    .map(labelFromToken)
    .filter((label) => {
      const key = label.toLowerCase()
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .slice(0, 3)
}

function getSourceBadges(voice: VoiceMeta): string[] {
  const v = voice as VoiceWithReferenceMeta
  const labels = [
    sourceLabel(v.source),
    sourceLabel(v.source_model ?? undefined),
    isMountedRef(voice) ? 'Mounted reference' : null,
  ].filter((value): value is string => Boolean(value))

  const seen = new Set<string>()
  return labels.filter((label) => {
    const key = label.toLowerCase()
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function metricLevel(value: number | null, min: number, max: number): number {
  if (value === null || max <= min) return 0
  return Math.max(0.08, Math.min(1, (value - min) / (max - min)))
}

function VoiceSourceBadges({ voice }: { voice: VoiceMeta }) {
  const sourceBadges = getSourceBadges(voice)
  const useCaseBadges = getUseCaseBadges(voice)

  if (sourceBadges.length === 0 && useCaseBadges.length === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {sourceBadges.map((label) => (
        <span
          key={`source-${label}`}
          className="inline-flex items-center rounded-full border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-cyan-300"
        >
          {label}
        </span>
      ))}
      {useCaseBadges.map((label) => (
        <span
          key={`use-${label}`}
          className="inline-flex items-center rounded-full border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-emerald-300"
        >
          {label}
        </span>
      ))}
    </div>
  )
}

function FingerprintBar({
  label,
  value,
  title,
  className,
}: {
  label: string
  value: number
  title: string
  className?: string
}) {
  return (
    <div className="flex min-w-0 items-center gap-1" title={title}>
      <span className="w-10 shrink-0 text-[9px] uppercase tracking-wide text-muted-foreground/70">
        {label}
      </span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted/70">
        <div
          className={cn('h-full rounded-full', className)}
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </div>
    </div>
  )
}

function VoiceFingerprint({ metrics }: { metrics: VoiceReferenceMetrics }) {
  const speechRate = getSpeechRate(metrics)
  const pauseRatio = finiteNumber(metrics.pause_ratio)
  const lufs = finiteNumber(metrics.lufs_integrated)
  const peak = finiteNumber(metrics.peak_dbfs)

  return (
    <div
      className="grid gap-1"
      aria-label={[
        `Speech rate ${formatNumber(speechRate, 2)} words per second`,
        `Pause ratio ${formatPercent(pauseRatio)}`,
        `Loudness ${formatNumber(lufs, 1, ' LUFS')}`,
        `Peak ${formatNumber(peak, 1, ' dBFS')}`,
      ].join(', ')}
    >
      <FingerprintBar
        label="Pace"
        value={metricLevel(speechRate, 1, 4)}
        title="Speech rate from reference analysis"
        className="bg-gradient-to-r from-cyan-500 to-sky-300"
      />
      <FingerprintBar
        label="Pause"
        value={metricLevel(pauseRatio, 0, 0.45)}
        title="Share of the reference detected as pauses"
        className="bg-gradient-to-r from-amber-500 to-yellow-300"
      />
      <FingerprintBar
        label="LUFS"
        value={metricLevel(lufs, -34, -14)}
        title="Integrated loudness; farther right is louder"
        className="bg-gradient-to-r from-fuchsia-500 to-pink-300"
      />
      <FingerprintBar
        label="Peak"
        value={metricLevel(peak, -18, 0)}
        title="Peak level; farther right is closer to digital maximum"
        className="bg-gradient-to-r from-emerald-500 to-lime-300"
      />
    </div>
  )
}

function VoiceMetricChip({
  label,
  value,
  help,
}: {
  label: string
  value: string
  help?: string
}) {
  return (
    <div className="min-w-0 rounded-md border border-border/60 bg-background/50 px-2 py-1">
      <div className="flex items-center gap-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
        {help && <InfoIcon text={help} className="size-3" />}
      </div>
      <div className="truncate font-mono text-[11px] text-foreground">{value}</div>
    </div>
  )
}

function VoiceMetricsPanel({ metrics }: { metrics: VoiceReferenceMetrics | null }) {
  if (!metrics) return null

  const speechRate = getSpeechRate(metrics)
  const pauseCount = finiteNumber(metrics.pause_count)
  const truePeak = getTruePeak(metrics)

  return (
    <div className="rounded-lg border border-border/60 bg-muted/20 p-2">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Reference fingerprint
          </p>
          <InfoIcon
            text="Measured from the saved reference clip. These values describe the voice asset, not a live generation."
            className="size-3.5"
          />
        </div>
        {finiteNumber(metrics.sample_rate) !== null && (
          <span className="font-mono text-[10px] text-muted-foreground">
            {formatNumber(metrics.sample_rate, 0, ' Hz')}
          </span>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_8rem]">
        <div className="grid grid-cols-2 gap-1.5">
          <VoiceMetricChip label="Duration" value={formatDuration(metrics.duration_seconds)} />
          <VoiceMetricChip
            label="Speech rate"
            value={`${formatNumber(speechRate, 2)} w/s`}
            help="Approximate words per second from transcript-aware analysis when available."
          />
          <VoiceMetricChip
            label="Pause"
            value={`${formatPercent(metrics.pause_ratio)} (${formatNumber(pauseCount, 0)} gaps)`}
            help="How much of the reference is silence or low-energy gaps, plus detected pause count."
          />
          <VoiceMetricChip
            label="LUFS"
            value={formatNumber(metrics.lufs_integrated, 1, ' LUFS')}
            help="Integrated perceived loudness. More negative values are quieter."
          />
          <VoiceMetricChip
            label="Peak"
            value={formatNumber(metrics.peak_dbfs, 1, ' dBFS')}
            help="Highest sample peak in the reference."
          />
          <VoiceMetricChip
            label="True peak"
            value={formatNumber(truePeak, 1, ' dBTP')}
            help="Estimated inter-sample peak when available."
          />
        </div>
        <VoiceFingerprint metrics={metrics} />
      </div>
    </div>
  )
}

// Shape persisted by /omnivoice/save into voice.selections -- see app.py's omnivoice_save
// handler. stitch_plan is the raw (snake_case) editor payload, kept verbatim so a voice
// assembled in Stitch Studio can later be reopened there instead of only existing as a
// flattened audio blob (candidate_id-only clips are the exception: those reference the
// ephemeral in-memory audition cache and can't be recovered once it's evicted/restarted).
interface OmniVoiceSelections {
  engine?: string
  stitch_plan?: {
    clips?: {
      segment_id?: string
      candidate_id?: string
      voice_id?: string
      trim_start_ms?: number
      trim_end_ms?: number
      fade_in_ms?: number
      fade_out_ms?: number
    }[]
    padding_ms?: number[]
    crossfade_ms?: number
    segment_target_dbfs?: number
    final_target_dbfs?: number
    final_ceiling_db?: number
    compress?: { threshold_db: number; ratio: number } | null
  } | null
}

function toBase64FromUrl(url: string): Promise<string> {
  return fetch(url)
    .then((r) => {
      if (!r.ok) throw new Error(`Failed to fetch audio (${r.status}): ${url}`)
      return r.arrayBuffer()
    })
    .then((buf) => {
      const bytes = new Uint8Array(buf)
      let binary = ''
      for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
      return btoa(binary)
    })
}

function ClipPlayerUrl({ segmentId, className }: { segmentId: string; className?: string }) {
  const url = `/omnivoice/segments/${encodeURIComponent(segmentId)}/audio`
  const [blob, setBlob] = useState<Blob | null>(null)
  const [src, setSrc] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`Failed to fetch audio (${r.status}): ${url}`)
        return r.blob()
      })
      .then((b) => {
        if (!cancelled) {
          setBlob(b)
          setSrc(URL.createObjectURL(b))
        }
      })
      .catch(() => {
        if (!cancelled) setSrc(url)
      })
    return () => {
      cancelled = true
    }
  }, [url])

  useEffect(() => {
    const u = src
    return () => {
      if (u && u.startsWith('blob:')) URL.revokeObjectURL(u)
    }
  }, [src])

  if (!src) return null

  return <MiniAudioDeck src={src} blob={blob} className={className} autoPlay={false} />
}

// Auto-loads (but does not auto-play) a saved voice's reference audio without a
// "Load preview" click, mirroring the saved-segment cards below (ClipPlayerUrl).
function VoiceAudioAutoPlayer({ voiceId }: { voiceId: string }) {
  const [state, setState] = useState<{ url: string; blob: Blob } | 'loading' | 'error'>('loading')

  useEffect(() => {
    let cancelled = false
    setState('loading')
    getVoice(voiceId)
      .then((full) => {
        if (cancelled) return
        if (!full.audio_base64) {
          setState('error')
          return
        }
        const bytes = Uint8Array.from(atob(full.audio_base64), (c) => c.charCodeAt(0))
        const blob = new Blob([bytes], { type: 'audio/wav' })
        setState({ url: URL.createObjectURL(blob), blob })
      })
      .catch(() => {
        if (!cancelled) setState('error')
      })
    return () => {
      cancelled = true
    }
  }, [voiceId])

  useEffect(() => {
    return () => {
      if (state !== 'loading' && state !== 'error') URL.revokeObjectURL(state.url)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voiceId])

  if (state === 'loading') {
    return (
      <div className="flex h-9 items-center gap-1.5 text-xs text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" />
        Loading waveform…
      </div>
    )
  }
  if (state === 'error') {
    return <p className="text-xs text-muted-foreground">Couldn't load audio.</p>
  }
  return <MiniAudioDeck src={state.url} blob={state.blob} autoPlay={false} />
}

function VoiceCard({
  voice,
  busy,
  onUse,
  onDesignFrom,
  onReopenInStitchStudio,
  onDelete,
  onSaveSampleText,
  onNormalize,
  onTrimSilence,
  onSetDefault,
}: {
  voice: VoiceMeta
  busy: boolean
  onUse: () => void
  onDesignFrom: (() => void) | null
  onReopenInStitchStudio: (() => void) | null
  onDelete: () => void
  onSaveSampleText: (text: string) => Promise<void>
  onNormalize: () => void
  onTrimSilence: () => void
  onSetDefault: (() => void) | null
}) {
  const reducedMotion = useReducedMotion()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(voice.sample_text)
  const [saving, setSaving] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const needsReview = voiceNeedsReview(voice)
  const transcriptSource = voiceTranscriptSource(voice)
  const whisperTranscript = (voice.asr?.whisper_transcript || '').trim()
  const metrics = getVoiceMetrics(voice)
  const reviewMessage =
    voice.asr?.suggestion ||
    (needsReview
      ? 'Review the transcript before using Qwen backends.'
      : 'Transcript is ready for Qwen backends.')

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  const commit = async () => {
    const trimmed = draft.trim()
    setEditing(false)
    if (!trimmed || trimmed === voice.sample_text) {
      setDraft(voice.sample_text)
      return
    }
    setSaving(true)
    try {
      await onSaveSampleText(trimmed)
    } finally {
      setSaving(false)
    }
  }

  return (
    <motion.div
      data-testid="voice-card"
      initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: reducedMotion ? 0 : 0 }}
      whileHover={reducedMotion ? {} : { y: -2 }}
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 text-card-foreground shadow-sm transition-shadow duration-200 hover:border-border/80 hover:shadow-lg"
    >

      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <p className="min-w-0 break-all text-sm font-medium">{voice.voice_id}</p>
          {voice.family_id && (
            <span className="inline-flex items-center rounded-full border border-purple-500/30 bg-purple-500/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-purple-400">
              Family: {voice.family_id}
            </span>
          )}
          {voice.is_default && (
            <span className="inline-flex items-center gap-1 rounded-full border border-yellow-500/30 bg-yellow-500/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-yellow-400">
              <Star className="size-3 fill-current" />
              Default
            </span>
          )}
          {isMountedRef(voice) && (
            <span className="inline-flex items-center rounded-full border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-cyan-400">
              Mounted reference
            </span>
          )}
          <span
            className={
              'inline-flex items-center gap-1 rounded-full border px-1.5 py-px text-[9px] font-medium uppercase tracking-wide ' +
              (needsReview
                ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300')
            }
            title={reviewMessage}
          >
            {needsReview ? <AlertTriangle className="size-3" /> : <CheckCircle2 className="size-3" />}
            {needsReview ? 'Review text' : transcriptSource}
          </span>
        </div>
        <p className="line-clamp-2 text-xs text-muted-foreground">{voice.description}</p>
        <VoiceSourceBadges voice={voice} />
      </div>

      {needsReview && (
        <div className="rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          {reviewMessage}
        </div>
      )}

      <div className="rounded-lg border border-border/60 bg-muted/20 p-2">
        <div className="mb-1 flex items-center justify-between gap-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Reference text
          </p>
          <span className="shrink-0 text-[10px] text-muted-foreground">{transcriptSource}</span>
        </div>
        {editing ? (
          <textarea
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                commit()
              } else if (e.key === 'Escape') {
                e.preventDefault()
                setDraft(voice.sample_text)
                setEditing(false)
              }
            }}
            rows={2}
            className="w-full resize-none rounded border border-cyan-500/40 bg-background px-2 py-1 text-xs text-foreground outline-none"
          />
        ) : (
          <p
            className="cursor-text text-xs text-foreground hover:text-cyan-400"
            title="Click to edit — this is the cloning transcript, so it must match the audio"
            onClick={() => {
              setDraft(voice.sample_text)
              setEditing(true)
            }}
          >
            {voice.sample_text || '(no reference text — click to add)'}
            {saving && ' (saving…)'}
          </p>
        )}
        {whisperTranscript && whisperTranscript !== voice.sample_text && (
          <p className="mt-2 border-t border-border/60 pt-2 text-[11px] text-muted-foreground">
            Whisper heard: "{whisperTranscript}"
          </p>
        )}
      </div>

      <VoiceMetricsPanel metrics={metrics} />

      <VoiceAudioAutoPlayer voiceId={voice.voice_id} />

      <div className="flex gap-2">
        <Button size="sm" className="flex-1" onClick={onUse}>
          Use in Speak
        </Button>
        {onDesignFrom && (
          <Button
            size="sm"
            variant="outline"
            aria-label="Design a new voice from this one"
            title="Design a new voice from this one's chip settings"
            disabled={busy}
            onClick={onDesignFrom}
          >
            <Sparkles className="size-4" />
          </Button>
        )}
        {onReopenInStitchStudio && (
          <Button
            size="sm"
            variant="outline"
            aria-label="Reopen in Stitch Studio"
            title="Reopen the clips this voice was assembled from in Stitch Studio"
            disabled={busy}
            onClick={onReopenInStitchStudio}
          >
            <Layers className="size-4" />
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          aria-label="Edit reference text"
          title="Edit reference text"
          disabled={busy}
          onClick={() => {
            setDraft(voice.sample_text)
            setEditing(true)
          }}
        >
          <Pencil className="size-4" />
        </Button>
        <Button
          size="sm"
          variant="outline"
          aria-label="Normalize reference audio (-20 LUFS, -1dBTP)"
          title="Normalize reference audio (-20 LUFS, -1dBTP)"
          disabled={busy}
          onClick={onNormalize}
        >
          <Wand2 className="size-4" />
        </Button>
        <Button
          size="sm"
          variant="outline"
          aria-label="Trim leading/trailing silence"
          title="Trim leading/trailing silence"
          disabled={busy}
          onClick={onTrimSilence}
        >
          <Scissors className="size-4" />
        </Button>
        {onSetDefault && (
          <Button
            size="sm"
            variant="outline"
            aria-label="Set as default variant for this family"
            title="Set as default variant for this family"
            disabled={busy || voice.is_default}
            onClick={onSetDefault}
          >
            <Star className={cn('size-4', voice.is_default && 'fill-current text-yellow-400')} />
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          aria-label="Delete this voice"
          title="Delete this voice"
          disabled={busy}
          onClick={onDelete}
        >
          <Trash2 className="size-4" />
        </Button>
      </div>
    </motion.div>
  )
}

export function VoiceLibraryPage() {
  const reducedMotion = useReducedMotion()
  const voices = useAppStore((s) => s.voices)
  const segments = useAppStore((s) => s.ovLibrary)
  const storeSetVoices = useAppStore((s) => s.setVoices)
  const storeSetSegments = useAppStore((s) => s.setOvLibrary)

  const [error, setError] = useState<string | null>(null)
  const [busyVoiceId, setBusyVoiceId] = useState<string | null>(null)
  const [busySegmentId, setBusySegmentId] = useState<string | null>(null)

  const [segSearch, setSegSearch] = useState('')
  const [compareMode, setCompareMode] = useState(false)
  const setVoiceId = useAppStore((s) => s.setVoiceId)

  const setPage = useAppStore((s) => s.setPage)
  const setEditingVoice = useAppStore((s) => s.setEditingVoice)
  const setDesignEngine = useAppStore((s) => s.setDesignEngine)
  const setOvStitchEditorOpen = useAppStore((s) => s.setOvStitchEditorOpen)
  const setOvStitchPlanClips = useAppStore((s) => s.setOvStitchPlanClips)
  const setOvStitchPlanPaddingMs = useAppStore((s) => s.setOvStitchPlanPaddingMs)
  const setOvStitchPlanDsp = useAppStore((s) => s.setOvStitchPlanDsp)

  async function refresh() {
    const [v, segs] = await Promise.all([
      listVoices().catch((err) => {
        setError(err instanceof Error ? err.message : String(err))
        return [] as VoiceMeta[]
      }),
      listOmniVoiceSegments().catch(() => [] as SegmentMeta[]),
    ])
    storeSetVoices(v)
    storeSetSegments(segs)
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const filteredSegments = useMemo(() => {
    if (!segSearch.trim()) return segments
    const q = segSearch.trim().toLowerCase()
    return segments.filter((s) => {
      if (s.text.toLowerCase().includes(q)) return true
      return (s.tags ?? []).some((t) => (t ?? '').toLowerCase().includes(q))
    })
  }, [segments, segSearch])

  async function insertSegmentIntoStitchEditor(seg: SegmentMeta) {
    setError(null)
    try {
      const clip = await createStitchClipFromSegment(seg)

      setPage('voice-design')
      setDesignEngine('omnivoice')

      setOvStitchPlanClips((prev: any) => [...(prev ?? []), clip])
      setOvStitchEditorOpen(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  // Only meaningful for chip-based voices: re-opens VoiceDesignPanel pre-filled with this
  // voice's chip selections so the user can tweak and save as a NEW voice (always forks --
  // re-generates the reference audio, unlike editing reference text below). Voices built via
  // Stitch Studio/OmniVoice don't have chip selections, so this action isn't offered for them
  // (setDesignEngine('qwen') here is what was missing before, which used to route stitch-plan
  // voices into the wrong panel and crash).
  async function designFromVoice(voiceId: string) {
    setBusyVoiceId(voiceId)
    setError(null)
    try {
      const full = await getVoice(voiceId)
      setEditingVoice({
        voiceId: full.voice_id,
        description: full.description,
        sampleText: full.sample_text,
        language: full.language,
        seed: full.seed ?? null,
        selections: (full.selections as ChipSelections | null | undefined) ?? null,
      })
      setDesignEngine('qwen')
      setPage('voice-design')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyVoiceId(null)
    }
  }

  // Rebuilds a Stitch Studio timeline from a voice's saved stitch_plan (its actual assembly
  // origin -- segment/voice refs, trims, fades, padding, DSP) so it can be re-arranged and
  // re-saved, instead of only ever existing as a flattened audio blob. Re-saving always forks
  // a new voice (no in-place audio replace yet); clips that only carried an ephemeral
  // candidate_id (never locked into the segment library) can't be recovered and are skipped.
  async function reopenInStitchStudio(voice: VoiceMeta) {
    setBusyVoiceId(voice.voice_id)
    setError(null)
    try {
      const sel = (voice.selections as OmniVoiceSelections | null | undefined) ?? null
      const plan = sel?.stitch_plan
      const planClips = plan?.clips ?? []

      const rebuilt: StitchPlanClip[] = []
      let skipped = 0
      for (const [i, c] of planClips.entries()) {
        if (c.segment_id) {
          const seg = segments.find((s) => s.segment_id === c.segment_id)
          if (!seg) {
            skipped++
            continue
          }
          const b64 = await toBase64FromUrl(
            `/omnivoice/segments/${encodeURIComponent(c.segment_id)}/audio`,
          )
          rebuilt.push({
            clipId: `clip_reopen_${Date.now()}_${i}`,
            ref: { segmentId: c.segment_id },
            text: seg.text,
            sourceAudioBase64: b64,
            sampleRate: seg.sample_rate ?? 24000,
            durationMs:
              typeof seg.duration_sec === 'number' && seg.duration_sec > 0
                ? Math.round(seg.duration_sec * 1000)
                : 0,
            trimStartMs: c.trim_start_ms ?? 0,
            trimEndMs: c.trim_end_ms ?? 0,
            fadeInMs: c.fade_in_ms ?? 0,
            fadeOutMs: c.fade_out_ms ?? 0,
          })
        } else if (c.voice_id) {
          const full = await getVoice(c.voice_id)
          if (!full.audio_base64) {
            skipped++
            continue
          }
          rebuilt.push({
            clipId: `clip_reopen_${Date.now()}_${i}`,
            ref: { voiceId: c.voice_id },
            text: full.sample_text,
            sourceAudioBase64: full.audio_base64,
            sampleRate: 24000,
            durationMs: 0,
            trimStartMs: c.trim_start_ms ?? 0,
            trimEndMs: c.trim_end_ms ?? 0,
            fadeInMs: c.fade_in_ms ?? 0,
            fadeOutMs: c.fade_out_ms ?? 0,
          })
        } else {
          skipped++
        }
      }

      if (rebuilt.length === 0) {
        setError(
          "This voice's original clips are no longer available (only ephemeral audition candidates were used, not saved segments) — it can't be reopened for editing.",
        )
        return
      }

      setOvStitchPlanClips(rebuilt)
      setOvStitchPlanPaddingMs(plan?.padding_ms ?? new Array(Math.max(0, rebuilt.length - 1)).fill(0))
      setOvStitchPlanDsp({
        crossfadeMs: plan?.crossfade_ms,
        segmentTargetDbfs: plan?.segment_target_dbfs,
        finalTargetDbfs: plan?.final_target_dbfs,
        finalCeilingDb: plan?.final_ceiling_db,
        compressEnabled: plan?.compress != null,
        compressThresholdDb: plan?.compress?.threshold_db,
        compressRatio: plan?.compress?.ratio,
      })
      setDesignEngine('omnivoice')
      setPage('voice-design')
      setOvStitchEditorOpen(true)

      if (skipped > 0) {
        setError(
          `${skipped} clip(s) from the original assembly couldn't be recovered (ephemeral audition candidates) and were skipped.`,
        )
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyVoiceId(null)
    }
  }

  async function saveSampleText(voiceId: string, text: string) {
    setError(null)
    try {
      await updateVoiceSampleText(voiceId, text)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function remove(voiceId: string) {
    if (!window.confirm(`Delete voice ${voiceId}? This can't be undone.`)) return
    setBusyVoiceId(voiceId)
    setError(null)
    try {
      await deleteVoice(voiceId)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyVoiceId(null)
    }
  }

  async function normalize(voiceId: string) {
    setBusyVoiceId(voiceId)
    setError(null)
    try {
      await normalizeVoiceReference(voiceId)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyVoiceId(null)
    }
  }

  async function fixAll(voiceId: string) {
    setBusyVoiceId(voiceId)
    setError(null)
    try {
      const voice = await getVoice(voiceId)
      if (!voice) return
      const fixable = getFixableQualityWarnings(voice)
      for (const fix of fixable) {
        if (fix.action === 'normalize') {
          await normalize(voiceId)
        } else if (fix.action === 'trim') {
          await trimSilence(voiceId)
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyVoiceId(null)
    }
  }

  async function setDefault(voiceId: string) {
    setBusyVoiceId(voiceId)
    setError(null)
    try {
      await setDefaultVoiceVariant(voiceId)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyVoiceId(null)
    }
  }

  async function removeSegment(segmentId: string) {
    if (!window.confirm('Delete this segment? This can’t be undone.')) return
    setBusySegmentId(segmentId)
    setError(null)
    try {
      await deleteOmniVoiceSegment(segmentId)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusySegmentId(null)
    }
  }

  const formatSegmentMeta = (m: SegmentMeta) => {
    const parts: string[] = []
    const tags = m.tags?.join(', ')
    if (tags) parts.push(tags)
    if (typeof m.duration_sec === 'number' && m.duration_sec > 0)
      parts.push(`${m.duration_sec.toFixed(1)}s`)
    if (m.created_at) {
      const d = new Date(m.created_at * 1000)
      parts.push(d.toLocaleDateString('en-GB', { month: 'short', day: '2-digit' }))
    }
    return parts.join(' · ')
  }

  return (
    <div className="flex flex-col gap-6">
        <motion.div
          initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: reducedMotion ? 0 : 0 }}
          className="flex flex-col gap-1"
        >

         <div className="flex items-center justify-between">
           <h1 className="text-2xl font-semibold tracking-tight">Voice Library</h1>
           <Button
             variant="outline"
             size="sm"
             onClick={() => setCompareMode(!compareMode)}
             className={cn(
               "gap-2 transition-all",
               compareMode ? "bg-primary text-primary-foreground border-primary" : ""
             )}
           >
            <Shuffle className="size-3.5" />
             {compareMode ? 'Exit Compare' : 'Compare Variants'}
           </Button>
         </div>
         <p className="text-sm text-muted-foreground">
           Voices you've designed and saved, ready to use in Speak or over the API.
         </p>
       </motion.div>

     {compareMode && (
        <motion.div
          initial={reducedMotion ? { opacity: 0 } : { opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          className="mb-8"
        >
          <VariantCompare />
        </motion.div>

     )}


      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* Voices */}
      {voices.length === 0 && segments.length === 0 && !error ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border py-16 text-center">
          <Mic2 className="size-6 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">No voices saved yet.</p>
          <Button size="sm" variant="secondary" onClick={() => setPage('voice-design')}>
            Design your first voice
          </Button>
        </div>
      ) : (
        <>
          {voices.length > 0 && (
            <section className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold tracking-tight">
                  Saved voices ({voices.length})
                </h2>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {voices.map((voice) => (
                  <VoiceCard
                    key={voice.voice_id}
                    voice={voice}
                    busy={busyVoiceId === voice.voice_id}
                    onUse={() => {
                      setVoiceId(voice.voice_id)
                      setPage('speak')
                    }}
                    onDesignFrom={
                      hasChipSelections(voice.selections) ? () => designFromVoice(voice.voice_id) : null
                    }
                    onReopenInStitchStudio={
                      (voice.selections as OmniVoiceSelections | null | undefined)?.stitch_plan?.clips
                        ?.length
                        ? () => reopenInStitchStudio(voice)
                        : null
                    }
                    onDelete={() => remove(voice.voice_id)}
                    onSaveSampleText={(text) => saveSampleText(voice.voice_id, text)}
                    onNormalize={() => normalize(voice.voice_id)}
                    onTrimSilence={() => trimSilence(voice.voice_id)}
                    onSetDefault={voice.family_id ? () => setDefault(voice.voice_id) : null}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Saved segments */}
          <section className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold tracking-tight">
                  Saved segments ({segments.length})
                </h2>
                <p className="text-[10px] text-muted-foreground">
                  Individual takes you can hear, reuse, and insert into the stitch editor.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <div className="relative">
                  <input
                    type="text"
                    placeholder="Search segments…"
                    value={segSearch}
                    onChange={(e) => setSegSearch(e.target.value)}
                    className="h-8 w-48 rounded-md border border-border bg-muted/20 px-3 text-xs outline-none ring-0 focus:border-ring"
                  />
                </div>
              </div>
            </div>

            {segments.length === 0 && (
              <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border py-10 text-center">
                  <AudioWaveform className="size-5 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  No saved segments yet.
                </p>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setPage('voice-design')
                    setDesignEngine('omnivoice')
                  }}
                >
                  Generate segments with OmniVoice
                </Button>
              </div>
            )}

            {filteredSegments.length > 0 ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {filteredSegments.map((seg, i) => (
                        <motion.div
                          key={seg.segment_id}
                          initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: reducedMotion ? 0 : 0 }}
                          transition={{ delay: i * 0.02 }}
                          whileHover={reducedMotion ? {} : { y: -1 }}
                          className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3 text-card-foreground shadow-sm transition-shadow hover:shadow-lg"
                        >

                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1">
                        <p className="text-xs">{seg.text}</p>
                        <p className="mt-1 text-[10px] text-muted-foreground">
                          {formatSegmentMeta(seg)}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="self-start"
                        aria-label="Delete segment"
                        title="Delete segment"
                        disabled={busySegmentId === seg.segment_id}
                        onClick={() => removeSegment(seg.segment_id)}
                      >
                        <Trash2 className="size-3.5 text-muted-foreground" />
                      </Button>
                    </div>

                    <div className="flex items-center gap-2">
                      <div className="flex-1">
                        <ClipPlayerUrl
                          segmentId={seg.segment_id}
                          className="w-full"
                        />
                      </div>
                      <Button
                        size="sm"
                        className="gap-1"
                        onClick={() => insertSegmentIntoStitchEditor(seg)}
                      >
                        <Plus className="size-3.5" />
                        Insert into stitch editor
                      </Button>
                    </div>
                  </motion.div>
                ))}
              </div>
            ) : segSearch.trim() ? (
              <p className="text-xs text-muted-foreground">
                No segments match your search.
              </p>
            ) : null}
          </section>
        </>
      )}
    </div>
  )
}

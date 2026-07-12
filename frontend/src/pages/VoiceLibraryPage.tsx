import { useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import {
  AlertTriangle,
  AudioWaveform,
  Check,
  CheckCircle2,
  ChevronDown,
  Copy,
  FoldHorizontal,
  Info,
  Layers,
  Loader2,
  Mic2,
  MoreHorizontal,
  Pencil,
  Plus,
  Play,
  Radio,
  Scissors,
  SlidersHorizontal,
  Sparkles,
  Star,
  Trash2,
  Shuffle,
  Undo2,
  Wand2,
  RefreshCcw,
  LayoutGrid,
  Rows,
  Columns2,
  Columns3,
} from 'lucide-react'
import {
  activateVoiceForApi,
  analyzeVoiceReference,
  adjustVoiceReferencePauses,
  applyVoiceReferenceRegionEdits,
  deleteOmniVoiceSegment,
  deleteVoice,
  duplicateVoice,
  getVoice,
  getVoiceVariants,
  listOmniVoiceSegments,
  listVoices,
  normalizeVoiceReference,
  setActiveVoiceVariant,
  setDefaultVoiceVariant,
  trimVoiceReferenceSilence,
  updateVoiceSampleText,
  undoVoiceReferenceEdit,
  type SegmentMeta,
  type StitchPlanRegionEdit,
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
import { RegionEditor } from '@/components/waveform/RegionEditor'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

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
  pause_intervals?: [number, number][] | null
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

const STYLE_DESCRIPTIONS: Record<string, string> = {
  Neutral: 'Standard natural pacing and pauses for balanced speech.',
  Storyteller: 'Slower, more dramatic pacing with extended pauses for narrative effect.',
  Calm: 'Relaxed, steady pace with longer, soothing gaps between phrases.',
  Energetic: 'Fast-paced, tight gaps and rapid delivery for a high-energy feel.',
  Broadcast: 'Professional, clear pacing typical of news or radio announcements.',
  Clean: 'Tight, efficient pacing that removes unnecessary gaps for a crisp result.',
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
        ? 'text-success'
        : score >= 50
          ? 'text-warning'
          : 'text-destructive'
  const fixable = getFixableQualityWarnings(voice)

  return (
    <div className="rounded border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
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
              className="h-7 gap-1.5 border-warning/40 bg-transparent text-warning hover:bg-warning/20"
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
                  className="h-7 gap-1.5 border-warning/40 bg-transparent text-warning hover:bg-warning/20"
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
                  className="h-7 gap-1.5 border-warning/40 bg-transparent text-warning hover:bg-warning/20"
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
    voice.auto_fixed ? 'Auto peak-limited' : null,
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
  return Math.min(1, Math.max(0, (value - min) / (max - min)))
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
          className="inline-flex items-center rounded-full border border-success/30 bg-success/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-success"
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
        className="bg-gradient-to-r from-warning to-warning"
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
        className="bg-gradient-to-r from-success to-lime-300"
      />
    </div>
  )
}

function VoiceMetricChip({
  label,
  value,
  previewValue,
  delta,
  help,
}: {
  label: string
  value: string
  previewValue?: string
  delta?: { value: string; isPositive: boolean } | null
  help?: string
}) {
  return (
    <div className="min-w-0 rounded-md border border-border/60 bg-background/50 px-2 py-1">
      <div className="flex items-center justify-between text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">
        <div className="flex items-center gap-1">
          {label}
          {help && <InfoIcon text={help} className="size-3" />}
        </div>
      </div>
      <div className="flex items-center justify-between gap-2 mt-1">
        <span className="truncate font-mono text-[10px] text-muted-foreground/60">{value}</span>
        <div className="flex items-center gap-2">
          {delta && (
            <span className={cn('font-mono text-[10px] font-medium', delta.isPositive ? 'text-success' : 'text-destructive')}>
              {delta.value}
            </span>
          )}
          {previewValue && (
            <span className="truncate font-mono text-[11px] font-bold text-foreground">{previewValue}</span>
          )}
        </div>
      </div>
    </div>
  )
}

function VoiceMetricsPanel({ metrics, busy, onAnalyze, expanded, onToggle, previewMetrics, layoutMode }: { metrics: VoiceReferenceMetrics | null; busy: boolean; onAnalyze: () => void; expanded: boolean; onToggle: () => void; previewMetrics: VoiceReferenceMetrics | null; layoutMode: string }) {
  if (!metrics) return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-dashed border-border/60 bg-muted/10 p-3">
      <div><p className="text-xs font-medium">Reference analysis unavailable</p><p className="text-[10px] text-muted-foreground">Analyze this saved WAV to add duration, pacing, pause, loudness, and peak data.</p></div>
      <Button size="sm" variant="outline" disabled={busy} onClick={onAnalyze}>Analyze reference</Button>
    </div>
  )

  const speechRate = getSpeechRate(metrics)
  const pauseCount = finiteNumber(metrics.pause_count)
  const truePeak = getTruePeak(metrics)

  const getDelta = (ref: number | null | undefined, prev: number | null | undefined, unit = '', digits = 2, inverse = false) => {
    if (ref === null || ref === undefined || prev === null || prev === undefined) return null
    const diff = prev - ref
    if (diff === 0) return null
    const sign = diff > 0 ? '+' : ''
    const isPositive = inverse ? diff < 0 : diff > 0
    return { value: `${sign}${diff.toFixed(digits)}${unit}`, isPositive }
  }

  const deltas = previewMetrics ? {
    duration: getDelta(metrics.duration_seconds, previewMetrics.duration_seconds, 's', 2),
    rate: getDelta(metrics.speech_rate_proxy ?? metrics.words_per_second, previewMetrics.speech_rate_proxy ?? previewMetrics.words_per_second, ' w/s', 2),
    pause: getDelta(metrics.pause_ratio, previewMetrics.pause_ratio, '%', 1, true),
    lufs: getDelta(metrics.lufs_integrated, previewMetrics.lufs_integrated, ' LUFS', 1),
    peak: getDelta(metrics.peak_dbfs, previewMetrics.peak_dbfs, ' dBFS', 1),
  } : null

  const pVals = previewMetrics ? {
    duration: formatDuration(previewMetrics.duration_seconds),
    rate: `${formatNumber(previewMetrics.speech_rate_proxy ?? previewMetrics.words_per_second, 2)} w/s`,
    pause: `${formatPercent(previewMetrics.pause_ratio)} (${formatNumber(previewMetrics.pause_count, 0)} gaps)`,
    lufs: formatNumber(previewMetrics.lufs_integrated, 1, ' LUFS'),
    peak: formatNumber(previewMetrics.peak_dbfs, 1, ' dBFS'),
  } : null


  return (
    <div className="border-y border-border/60 py-2">
      <button type="button" className="flex w-full items-center justify-between gap-3 text-left" onClick={onToggle} aria-expanded={expanded}>
        <span className="min-w-0 truncate font-mono text-[11px] text-muted-foreground">
          {formatDuration(metrics.duration_seconds)} · {formatNumber(speechRate, 2)} w/s · {formatPercent(metrics.pause_ratio)} pauses · {formatNumber(metrics.lufs_integrated, 1, ' LUFS')} · {formatNumber(metrics.peak_dbfs, 1, ' dBFS')}
        </span>
        <span className="inline-flex shrink-0 items-center gap-1 text-[10px] font-medium text-foreground">Audio analysis <ChevronDown className={cn('size-3.5 transition-transform', expanded && 'rotate-180')} /></span>
      </button>
      {expanded && <div className="mt-3 rounded-lg bg-muted/20 p-2">
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

        <div className={cn(
          "grid gap-3 sm:grid-cols-[minmax(0,1fr)_8rem]",
          layoutMode === 'list' && "grid-cols-1",
          layoutMode === 'grid-3' && "max-w-sm mx-auto"
        )}>
          <div className="grid grid-cols-2 gap-1.5">
            <VoiceMetricChip label="Duration" value={formatDuration(metrics.duration_seconds)} delta={deltas?.duration} previewValue={pVals?.duration} />
            <VoiceMetricChip
              label="Speech rate"
              value={`${formatNumber(speechRate, 2)} w/s`}
              delta={deltas?.rate}
              previewValue={pVals?.rate}
              help="Approximate words per second from transcript-aware analysis when available."
            />
            <VoiceMetricChip
              label="Pause"
              value={`${formatPercent(metrics.pause_ratio)} (${formatNumber(pauseCount, 0)} gaps)`}
              delta={deltas?.pause}
              previewValue={pVals?.pause}
              help="How much of the reference is silence or low-energy gaps, plus detected pause count."
            />
            <VoiceMetricChip
              label="LUFS"
              value={formatNumber(metrics.lufs_integrated, 1, ' LUFS')}
              delta={deltas?.lufs}
              previewValue={pVals?.lufs}
              help="Integrated perceived loudness. More negative values are quieter."
            />
            <VoiceMetricChip
              label="Peak"
              value={formatNumber(metrics.peak_dbfs, 1, ' dBFS')}
              delta={deltas?.peak}
              previewValue={pVals?.peak}
              help="Highest sample peak in the reference."
            />


            <VoiceMetricChip
              label="True peak"
              value={formatNumber(truePeak, 1, ' dBTP')}
              help="Estimated inter-sample peak when available."
            />
          </div>
          <div className="flex flex-col gap-2">
            <VoiceFingerprint metrics={metrics} />
          </div>
        </div>

      </div>}
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
  layoutMode,
  onUse,
  onDesignFrom,
  onReopenInStitchStudio,
  onDelete,
  onDuplicate,
  onSaveSampleText,
  onNormalize,
  onTrimSilence,
  onFixAll,
  onSetDefault,
  onAdjustPauses,
  onActivateForApi,
  onApplyReferenceEdits,
  onAnalyze,
  onUndo,
}: {
  voice: VoiceMeta
  busy: boolean
  layoutMode: string
  onUse: () => void
  onDesignFrom: (() => void) | null
  onReopenInStitchStudio: (() => void) | null
  onDelete: () => void
  onDuplicate: () => Promise<VoiceMeta | null>
  onSaveSampleText: (text: string) => Promise<void>
  onNormalize: (voiceId: string) => Promise<void>
  onTrimSilence: (voiceId: string) => Promise<void>
  onFixAll: () => void
  onSetDefault: (() => void) | null
  onAdjustPauses: (voiceId: string, stylePreset: string, paceMultiplier: number, pauseOffset: number) => Promise<void>
  onActivateForApi: () => void
  onApplyReferenceEdits: (voiceId: string, edits: StitchPlanRegionEdit[]) => Promise<void>
  onAnalyze: () => void
  onUndo: () => void
}) {

  const reducedMotion = useReducedMotion()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(voice.sample_text)
  const [saving, setSaving] = useState(false)
  const [editingAudio, setEditingAudio] = useState(false)
  const [editorAudio, setEditorAudio] = useState<string | null>(null)
  const [regionEdits, setRegionEdits] = useState<StitchPlanRegionEdit[]>([])
  const [stylePreset, setStylePreset] = useState('Neutral')
  const [paceMultiplier, setPaceMultiplier] = useState(1.0)
  const [pauseOffset, setPauseOffset] = useState(0)
  const [variants, setVariants] = useState<string[]>([])
  const [activeVariant, setActiveVariant] = useState<string | null>(null)
  const [prosodyBusy, setProsodyBusy] = useState(false)
  const [previewBusy, setPreviewBusy] = useState(false)
  const [previewAudio, setPreviewAudio] = useState<{ url: string; blob: Blob } | null>(null)
  const [previewMetrics, setPreviewMetrics] = useState<VoiceReferenceMetrics | null>(null)
  const [analysisExpanded, setAnalysisExpanded] = useState(() => localStorage.getItem('voice-library-analysis-expanded') !== 'false')
  const [preserveOriginal, setPreserveOriginal] = useState(true)
  const [editorVoiceId, setEditorVoiceId] = useState(voice.voice_id)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const needsReview = voiceTranscriptNeedsReview(voice)
  const transcriptSource = voiceTranscriptSource(voice)
  const whisperTranscript = (voice.asr?.whisper_transcript || '').trim()
  const metrics = getVoiceMetrics(voice)
  const reviewMessage =
    voice.asr?.suggestion ||
    (needsReview
      ? 'Review the transcript before using Qwen backends.'
      : 'Transcript is ready for Qwen backends.')

  useEffect(() => {
    async function loadVariants() {
      try {
        const data = await getVoiceVariants(voice.voice_id)
        setVariants(data.variants)
        setActiveVariant(data.active_variant)
      } catch (err) {
        console.error(`Failed to load variants for ${voice.voice_id}:`, err)
      }
    }
    loadVariants()
  }, [voice.voice_id])

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

  const mutationVoiceId = async () => {
    if (!preserveOriginal) return voice.voice_id
    const copy = await onDuplicate()
    return copy?.voice_id ?? null
  }

  const openAudioEditor = async () => {
    const targetId = await mutationVoiceId()
    if (!targetId) return
    const detail = await getVoice(targetId)
    setEditorVoiceId(targetId)
    setEditorAudio(detail.audio_base64 ?? null)
    setRegionEdits([])
    setEditingAudio(true)
  }

  const runMutation = async (action: (voiceId: string) => Promise<void>) => {
    const targetId = await mutationVoiceId()
    if (targetId) await action(targetId)
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
        <div className="flex flex-col gap-2 overflow-hidden rounded-lg border border-border/60 bg-muted/10 p-2">
         <div className="flex items-center justify-between px-1">
           <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Prosody Variants</p>
           <div className="flex items-center gap-1">
             {variants.length === 0 ? <span className="text-[10px] text-muted-foreground/50">None</span> : <span className="text-[10px] text-muted-foreground">{variants.length} total</span>}
           </div>
         </div>
         <div className="max-h-24 overflow-y-auto space-y-1 px-1">
           {variants.map(v => (
             <div key={v} className="flex items-center justify-between group">
               <button
                 onClick={async () => {
                   try {
                     await setActiveVoiceVariant(voice.voice_id, v)
                     setActiveVariant(v)
                   } catch (err) { console.error(err) }
                 }}
                 className={cn(
                   "text-left truncate text-[11px] py-0.5 px-1 rounded transition-colors",
                   activeVariant === v ? "bg-cyan-500/20 text-cyan-300" : "text-muted-foreground hover:bg-muted/40"
                 )}
               >
                 {v}
               </button>
               {activeVariant === v && <Check className="size-3 text-cyan-400" />}
             </div>
           ))}
         </div>
       </div>

       <div className="flex flex-wrap items-center gap-2">
          <p className="min-w-0 break-all text-sm font-medium">{voice.voice_id}</p>
          {voice.family_id && (
            <span className="inline-flex items-center rounded-full border border-purple-500/30 bg-purple-500/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-purple-400">
              Family: {voice.family_id}
            </span>
          )}
          {voice.is_default && (
            <span className="inline-flex items-center gap-1 rounded-full border border-warning/30 bg-warning/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-warning">
              <Star className="size-3 fill-current" />
              Default
            </span>
          )}
          {voice.api_active && (
            <span className="inline-flex items-center gap-1 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-px text-[9px] font-medium uppercase text-cyan-400">
              <Radio className="size-3" /> API default
            </span>
          )}
          <span
            className={
              'inline-flex items-center gap-1 rounded-full border px-1.5 py-px text-[9px] font-medium uppercase tracking-wide ' +
              (needsReview
                ? 'border-warning/30 bg-warning/10 text-warning'
                : 'border-success/30 bg-success/10 text-success')
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
        <div className="rounded border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
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

       <QualityGatePanel
         voice={voice}
         busy={busy}
         onNormalize={() => { void runMutation(onNormalize) }}
         onTrimSilence={() => { void runMutation(onTrimSilence) }}
         onFixAll={onFixAll}
       />

          <VoiceMetricsPanel metrics={metrics} busy={busy} onAnalyze={onAnalyze} expanded={analysisExpanded} onToggle={() => setAnalysisExpanded((value) => { localStorage.setItem('voice-library-analysis-expanded', String(!value)); return !value })} previewMetrics={previewMetrics} layoutMode={layoutMode} />




        <div className="relative group space-y-1">
          {previewAudio ? (
            <div className="relative space-y-1">
            <div className="relative group/original opacity-40 grayscale">
              <div className="absolute -top-2 left-2 z-10 rounded bg-muted px-1 py-px text-[9px] font-bold text-muted-foreground">ORIGINAL</div>
              <VoiceAudioAutoPlayer voiceId={voice.voice_id} />
            </div>

              <div className="relative">
                <div className="absolute -top-2 left-2 z-10 rounded bg-cyan-500 px-1 py-px text-[9px] font-bold text-white">PREVIEW</div>
                <MiniAudioDeck src={previewAudio.url} blob={previewAudio.blob} autoPlay={false} />
              </div>
            </div>
          ) : (
            <VoiceAudioAutoPlayer voiceId={voice.voice_id} />
          )}
          {previewAudio && (
            <button
              onClick={() => {
                URL.revokeObjectURL(previewAudio.url)
                setPreviewAudio(null)
              }}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded bg-background/80 p-1 text-[10px] hover:bg-background opacity-0 group-hover:opacity-100 transition-opacity"
            >
              Clear
            </button>
          )}
        </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" className="min-w-32" onClick={onUse}>
          Use in Speak
        </Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={openAudioEditor}><SlidersHorizontal /> Edit audio</Button>
         <Popover>
           <PopoverTrigger asChild>
             <Button size="sm" variant="outline" disabled={busy}>
               <FoldHorizontal /> Adjust prosody <ChevronDown />
             </Button>
           </PopoverTrigger>
           <PopoverContent align="start" className="w-72">
             <p className="text-xs font-medium mb-2">Prosody Settings</p>
             <div className="space-y-3">
                <div className="flex flex-col gap-1.5">
                  <label className="text-[10px] uppercase tracking-wide text-muted-foreground">Style Preset</label>
                   <Select 
                     value={stylePreset} 
                     onValueChange={(val) => {
                       setStylePreset(val)
                       setPreviewAudio(null)
                     }}
                   >
                     <SelectTrigger size="sm" className="w-full h-7 px-2 text-xs">
                       <SelectValue />
                     </SelectTrigger>
                     <SelectContent>
                       <SelectGroup>
                         {Object.keys(STYLE_DESCRIPTIONS).map(s => (
                           <SelectItem key={s} value={s}>
                             <div className="flex flex-col text-left">
                               <span className="font-medium">{s}</span>
                               <span className="text-[10px] opacity-60 leading-tight">{STYLE_DESCRIPTIONS[s]}</span>
                             </div>
                           </SelectItem>
                         ))}
                       </SelectGroup>
                     </SelectContent>
                   </Select>
                    <div className="flex gap-2 rounded bg-muted/50 p-2 text-[10px] text-muted-foreground border border-border">
                      <Info className="size-3 shrink-0 mt-0.5" />
                      <span className="italic leading-tight">
                        {STYLE_DESCRIPTIONS[stylePreset]}
                      </span>
                    </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <div className="flex justify-between items-center">
                    <label className="text-[10px] uppercase tracking-wide text-muted-foreground">Global Pace Scale</label>
                    <span className="font-mono text-[10px]">{paceMultiplier.toFixed(1)}x</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground italic leading-tight mb-1">
                    Scales all pauses proportionally (e.g., 1.2x increases all gaps by 20%).
                  </p>
                  <input
                    type="range" min="0.5" max="2.0" step="0.1"
                    value={paceMultiplier}
                    onChange={(e) => setPaceMultiplier(parseFloat(e.target.value))}
                    className="w-full accent-cyan-500"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <div className="flex justify-between items-center">
                    <label className="text-[10px] uppercase tracking-wide text-muted-foreground">Pause Offset</label>
                    <span className="font-mono text-[10px]">{pauseOffset > 0 ? `+${pauseOffset}` : pauseOffset}ms</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground italic leading-tight mb-1">
                    Shifts all gaps by a flat amount (e.g., +100ms adds 100ms to every pause).
                  </p>
                  <input
                    type="range" min="-500" max="500" step="10"
                    value={pauseOffset}
                    onChange={(e) => setPauseOffset(parseInt(e.target.value))}
                    className="w-full accent-cyan-500"
                  />
                </div>
                <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy || prosodyBusy || previewBusy}
                       onClick={async () => {
                         setPreviewBusy(true)
                         try {
                           const response = await fetch(`/voices/${voice.voice_id}/preview-prosody?style_preset=${encodeURIComponent(stylePreset)}&pace_multiplier=${paceMultiplier}&pause_offset=${pauseOffset}`)
                           if (!response.ok) throw new Error('Preview fetch failed')
                           const data = await response.json()
                           const blob = new Blob([Uint8Array.from(atob(data.audio_base64), c => c.charCodeAt(0))], { type: 'audio/wav' })
                           const url = URL.createObjectURL(blob)
                           setPreviewAudio({ url, blob })
                           setPreviewMetrics(data.metrics)
                         } catch (err) {
                           console.error('Prosody preview failed:', err)
                         } finally {
                           setPreviewBusy(false)
                         }
                       }}
                    >
                      {previewAudio ? <Undo2 className="size-3.5" /> : <Play className="size-3.5" />} {previewAudio ? 'Reset Preview' : 'Preview'}
                    </Button>
                   <Button
                     size="sm"
                     variant="outline"
                     disabled={busy || prosodyBusy || previewBusy}
                     onClick={async () => {
                       setProsodyBusy(true)
                       try {
                         await onAdjustPauses(voice.voice_id, stylePreset, paceMultiplier, pauseOffset)
                         const data = await getVoiceVariants(voice.voice_id)
                         setVariants(data.variants)
                         setActiveVariant(data.active_variant)
                       } finally {
                         setProsodyBusy(false)
                       }
                     }}
                   >
                     <Wand2 className="size-3.5" /> Save as Variant
                   </Button>
                 </div>


             </div>
           </PopoverContent>
         </Popover>

        <Popover><PopoverTrigger asChild><Button size="icon-sm" variant="outline" aria-label="More voice actions" tooltip="More voice actions"><MoreHorizontal /></Button></PopoverTrigger><PopoverContent align="end" className="w-64 gap-1 p-1.5">
          <label className="mb-1 flex items-center gap-2 rounded bg-muted/30 p-2 text-xs"><input type="checkbox" checked={preserveOriginal} onChange={(event) => setPreserveOriginal(event.target.checked)} /> Edit audio operations on a copy</label>
          <Button size="sm" variant="ghost" className="w-full justify-start" onClick={onDuplicate}><Copy /> Duplicate voice</Button>
          <Button size="sm" variant="ghost" className="w-full justify-start" disabled={voice.api_active} onClick={onActivateForApi}><Radio /> Activate for API</Button>
          {onDesignFrom && <Button size="sm" variant="ghost" className="w-full justify-start" onClick={onDesignFrom}><Sparkles /> Design from voice</Button>}
          {onReopenInStitchStudio && <Button size="sm" variant="ghost" className="w-full justify-start" onClick={onReopenInStitchStudio}><Layers /> Open in Stitch Studio</Button>}
          <Button size="sm" variant="ghost" className="w-full justify-start" onClick={() => setEditing(true)}><Pencil /> Edit transcript</Button>
          <Button size="sm" variant="ghost" className="w-full justify-start" onClick={() => runMutation(onNormalize)}><Wand2 /> Normalize loudness</Button>
          <Button size="sm" variant="ghost" className="w-full justify-start" onClick={() => runMutation(onTrimSilence)}><Scissors /> Trim boundary silence</Button>
          {onSetDefault && <Button size="sm" variant="ghost" className="w-full justify-start" disabled={voice.is_default} onClick={onSetDefault}><Star /> Set family default</Button>}
          {voice.undo_available && <Button size="sm" variant="ghost" className="w-full justify-start" onClick={onUndo}><Undo2 /> Undo last audio edit</Button>}
           <Button size="sm" variant="ghost" className="w-full justify-start" onClick={onAnalyze}><RefreshCcw className="size-3.5" /> Refresh analysis</Button>
           <div className="my-1 border-t border-border" />
           <Button size="sm" variant="ghost" className="w-full justify-start text-destructive hover:text-destructive" onClick={onDelete}><Trash2 /> Delete voice</Button>

        </PopoverContent></Popover>
      </div>
      {editingAudio && editorAudio && (
        <RegionEditor audioBase64={editorAudio} edits={regionEdits} pauseIntervals={metrics?.pause_intervals as [number, number][] | undefined} onChange={setRegionEdits} busy={busy} onClose={() => setEditingAudio(false)} onApply={async () => {
          await onApplyReferenceEdits(editorVoiceId, regionEdits)
          setEditingAudio(false)
        }} />
      )}
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
  const [layoutMode, setLayoutMode] = useState(() => {
    if (typeof window === 'undefined') return 'grid-1'
    return localStorage.getItem('voice-library-layout') || 'grid-1'
  })
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

  useEffect(() => {
    localStorage.setItem('voice-library-layout', layoutMode)
  }, [layoutMode])

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

// fixAll is currently not used in the main render loop
  async function fixAll(voiceId: string) {
    // Currently unused in favor of explicit fixes
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
          await trimVoiceReferenceSilence(voiceId)
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

  async function adjustPauses(voiceId: string, stylePreset: string, paceMultiplier: number, pauseOffset: number) {
    setBusyVoiceId(voiceId)
    setError(null)
    try {
      await adjustVoiceReferencePauses(voiceId, stylePreset, paceMultiplier, pauseOffset)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyVoiceId(null)
    }
  }

  async function activateForApi(voiceId: string) {
    setBusyVoiceId(voiceId)
    setError(null)
    try {
      await activateVoiceForApi(voiceId)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyVoiceId(null)
    }
  }

  async function applyReferenceEdits(voiceId: string, edits: StitchPlanRegionEdit[]) {
    setBusyVoiceId(voiceId)
    setError(null)
    try {
      await applyVoiceReferenceRegionEdits(voiceId, edits)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyVoiceId(null)
    }
  }

  async function duplicate(voiceId: string): Promise<VoiceMeta | null> {
    setBusyVoiceId(voiceId)
    setError(null)
    try {
      const copy = await duplicateVoice(voiceId)
      await refresh()
      return copy
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      return null
    } finally {
      setBusyVoiceId(null)
    }
  }

  async function analyze(voiceId: string) {
    setBusyVoiceId(voiceId)
    setError(null)
    try {
      await analyzeVoiceReference(voiceId)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyVoiceId(null)
    }
  }

  async function undoAudioEdit(voiceId: string) {
    setBusyVoiceId(voiceId)
    setError(null)
    try {
      await undoVoiceReferenceEdit(voiceId)
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
                 <div className="flex items-center gap-1 rounded-lg bg-muted/50 p-1">
                   <Button
                     variant={layoutMode === 'grid-1' ? 'secondary' : 'ghost'}
                     size="icon-sm"
                     onClick={() => setLayoutMode('grid-1')}
                     title="Single column"
                   >
                     <LayoutGrid className="size-3.5" />
                   </Button>
                   <Button
                     variant={layoutMode === 'grid-2' ? 'secondary' : 'ghost'}
                     size="icon-sm"
                     onClick={() => setLayoutMode('grid-2')}
                     title="Two columns"
                   >
                     <Columns2 className="size-3.5" />
                   </Button>
                   <Button
                     variant={layoutMode === 'grid-3' ? 'secondary' : 'ghost'}
                     size="icon-sm"
                     onClick={() => setLayoutMode('grid-3')}
                     title="Three columns"
                   >
                     <Columns3 className="size-3.5" />
                   </Button>
                   <Button
                     variant={layoutMode === 'list' ? 'secondary' : 'ghost'}
                     size="icon-sm"
                     onClick={() => setLayoutMode('list')}
                     title="List view"
                   >
                     <Rows className="size-3.5" />
                   </Button>
                 </div>
               </div>


            <div className={cn(
              "grid gap-4",
              layoutMode === 'grid-1' && "grid-cols-1 max-w-4xl mx-auto",
              layoutMode === 'grid-2' && "grid-cols-1 sm:grid-cols-2",
              layoutMode === 'grid-3' && "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
              layoutMode === 'list' && "grid-cols-1"
            )}>
              {voices.map((voice) => (
                <VoiceCard
                  key={voice.voice_id}
                  voice={voice}
                  busy={busyVoiceId === voice.voice_id}
                  layoutMode={layoutMode}
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
                  onDuplicate={() => duplicate(voice.voice_id)}
                   onSaveSampleText={(text) => saveSampleText(voice.voice_id, text)}
                   onNormalize={(voiceId) => normalize(voiceId)}
                   onTrimSilence={async (voiceId) => { await trimVoiceReferenceSilence(voiceId); await refresh() }}
                   onFixAll={() => fixAll(voice.voice_id)}
                   onSetDefault={voice.family_id ? () => setDefault(voice.voice_id) : null}
                    onAdjustPauses={(voiceId, stylePreset, paceMultiplier, pauseOffset) => adjustPauses(voiceId, stylePreset, paceMultiplier, pauseOffset)}

                   onActivateForApi={() => activateForApi(voice.voice_id)}
                  onApplyReferenceEdits={(voiceId, edits) => applyReferenceEdits(voiceId, edits)}
                  onAnalyze={() => analyze(voice.voice_id)}
                  onUndo={() => undoAudioEdit(voice.voice_id)}
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

                     <div className="flex flex-col gap-2">
                       <div>
                         <ClipPlayerUrl
                           segmentId={seg.segment_id}
                           className="w-full"
                         />
                       </div>
                       <Button
                         size="sm"
                         className="gap-1 w-full"
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

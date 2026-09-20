import { useCallback, useEffect, useRef, useState } from 'react'
import {
  adjustVoiceReferencePauses,
  cancelVoiceAlignment,
  deleteVoiceVariant,
  getVoiceAlignmentStatus,
  getVoiceVariantAudio,
  getVoiceVariantMetrics,
  getVoiceVariants,
  previewVoiceProsody,
  saveVoiceProsodyVariant,
  setActiveVoiceVariant,
  startVoiceAlignment,
  type AlignmentBoundary,
  type ProsodyMode,
  type ProsodyPausePlanEntry,
  type ReferenceMetrics,
  type VoiceMeta,
  type VoiceVariantEntry,
} from '@/lib/api'

// Project targets ES2023; Promise.withResolvers needs ES2024 lib typings, so this stays
// on the executor form.
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export interface ProsodyPreviewState {
  url: string
  blob: Blob
  audioBase64: string
  sampleCount: number
  plan: ProsodyPausePlanEntry[]
}

// The minimum voice shape the editor needs: full VoiceMeta from Voice Library, or a
// lightweight stand-in from any caller that only knows the id (e.g. a fresh selection
// before the full record has loaded).
export type ProsodyEditorVoice = Pick<VoiceMeta, 'voice_id' | 'sample_text' | 'sha256' | 'api_active'>

/**
 * Single source of truth for one voice's prosody editing session: style/pace/pause
 * controls, forced-alignment boundaries, per-boundary nudges, the adjusted-audio
 * preview, and the variant list (preview/promote/fork/delete). Shared verbatim by
 * Voice Library's compact popover and the Voice Edit page.
 */

export interface ProsodyEditor {
  stylePreset: string
  setStylePreset: (value: string) => void
  paceMultiplier: number
  setPaceMultiplier: (value: number) => void
  pauseOffset: number
  setPauseOffset: (value: number) => void
  mode: ProsodyMode
  setMode: (value: ProsodyMode) => void
  hasTranscript: boolean
  resolvedPrecise: boolean
  setAutoTriagePrecise: (value: boolean) => void
  entries: VoiceVariantEntry[]
  activeFilename: string
  alignBusy: boolean
  alignBoundaries: AlignmentBoundary[] | null
  alignError: string | null
  alignWarning: string | null
  preview: ProsodyPreviewState | null
  previewMetrics: ReferenceMetrics | null
  previewBusy: boolean
  targetOverrides: Record<string, number>
  nudgeTarget: (key: string, deltaMs: number) => void
  resetTarget: (key: string) => void
  togglePreview: () => Promise<void>
  clearPreview: () => void
  previewingVariant: string | null
  variantBusy: string | null
  savingVariantBusy: boolean
  promoteBusy: boolean
  previewVariant: (entry: VoiceVariantEntry) => Promise<void>
  promoteVariant: (entry: VoiceVariantEntry) => Promise<void>
  forkVariant: ((entry: VoiceVariantEntry) => Promise<void>) | undefined
  deleteVariant: (entry: VoiceVariantEntry) => Promise<void>
  saveVariant: () => Promise<void>
  savePromote: () => Promise<void>
  busy: boolean
  error: string | null
}
export function useProsodyEditor(
  voice: ProsodyEditorVoice,
  onChanged?: () => Promise<void> | void,
  onFork?: (entry: VoiceVariantEntry) => Promise<unknown> | void,
): ProsodyEditor {
  const voiceId = voice.voice_id

  const [stylePreset, setStylePreset] = useState('Neutral')
  const [paceMultiplier, setPaceMultiplier] = useState(1)
  const [pauseOffset, setPauseOffset] = useState(0)
  const [mode, setMode] = useState<ProsodyMode>('auto')

  const [entries, setEntries] = useState<VoiceVariantEntry[]>([])
  const [activeFilename, setActiveFilename] = useState('original.wav')

  const [alignBusy, setAlignBusy] = useState(false)
  const [alignBoundaries, setAlignBoundaries] = useState<AlignmentBoundary[] | null>(null)
  const [alignError, setAlignError] = useState<string | null>(null)
  const [alignWarning, setAlignWarning] = useState<string | null>(null)
  const alignJobRef = useRef<{ jobId: string; cancelled: boolean } | null>(null)

  const [previewBusy, setPreviewBusy] = useState(false)
  const [preview, setPreview] = useState<ProsodyPreviewState | null>(null)
  const [previewMetrics, setPreviewMetrics] = useState<ReferenceMetrics | null>(null)
  const [targetOverrides, setTargetOverrides] = useState<Record<string, number>>({})

  const [previewingVariant, setPreviewingVariant] = useState<string | null>(null)
  const variantPreviewAudioRef = useRef<HTMLAudioElement | null>(null)
  const [variantBusy, setVariantBusy] = useState<string | null>(null)
  const [savingVariantBusy, setSavingVariantBusy] = useState(false)
  const [promoteBusy, setPromoteBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const hasTranscript = Boolean((voice.sample_text || '').trim())

  const refresh = useCallback(async () => {
    const data = await getVoiceVariants(voiceId)
    setEntries(data.entries)
    setActiveFilename(data.active_filename)
  }, [voiceId])

  useEffect(() => {
    setPreview(null)
    setPreviewMetrics(null)
    setTargetOverrides({})
    setError(null)
    void refresh().catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [refresh])

  // Reset any cached boundaries when the clip identity or its transcript changes — the
  // old alignment no longer describes this audio/text.
  useEffect(() => {
    setAlignBoundaries(null)
    setAlignError(null)
    setAlignWarning(null)
  }, [voiceId, voice.sample_text, voice.sha256])

  useEffect(() => () => {
    variantPreviewAudioRef.current?.pause()
    variantPreviewAudioRef.current = null
  }, [voiceId])

  // Whether Auto mode should resolve to Precise for this clip. Voice Library derives
  // this from its own triage heuristic and reports it in; callers that don't have a
  // triage signal simply never call the setter, leaving Auto's default behavior alone.
  const [autoTriagePrecise, setAutoTriagePrecise] = useState(false)
  const resolvedPrecise = mode === 'precise' || (mode === 'auto' && autoTriagePrecise)

  const runAlignment = useCallback(async () => {
    if (!hasTranscript || alignBusy) return
    setAlignBusy(true)
    setAlignError(null)
    setAlignWarning(null)
    try {
      const job = await startVoiceAlignment(voiceId)
      alignJobRef.current = { jobId: job.job_id, cancelled: false }
      let current = job
      while (current.status === 'queued' || current.status === 'running') {
        if (alignJobRef.current?.cancelled) return
        await sleep(500)
        if (alignJobRef.current?.cancelled) return
        current = await getVoiceAlignmentStatus(voiceId, job.job_id)
      }
      if (alignJobRef.current?.cancelled) return
      if (current.status === 'completed') {
        setAlignBoundaries(current.result?.boundaries ?? [])
        if (current.within_latency_budget === false) {
          setAlignWarning(
            `Alignment took ${current.duration_seconds?.toFixed(1) ?? '?'}s, above the ${current.latency_budget_seconds.toFixed(1)}s budget. The result is usable; consider a faster provider or shorter clip.`,
          )
        }
      } else if (current.status === 'failed') {
        setAlignError(current.error || 'Alignment failed')
        setAlignBoundaries([])
      }
    } catch (err) {
      setAlignError(err instanceof Error ? err.message : String(err))
    } finally {
      alignJobRef.current = null
      setAlignBusy(false)
    }
  }, [alignBusy, hasTranscript, voiceId])

  // Trigger alignment lazily the first time Precise resolves for this clip, and cancel
  // any in-flight job on unmount / clip change.
  useEffect(() => {
    if (resolvedPrecise && hasTranscript && alignBoundaries === null && !alignBusy) {
      void runAlignment()
    }
    return () => {
      const inflight = alignJobRef.current
      if (inflight && !inflight.cancelled) {
        inflight.cancelled = true
        void cancelVoiceAlignment(voiceId, inflight.jobId).catch(() => {})
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedPrecise, hasTranscript, alignBoundaries])

  // One place to render a prosody preview, so the Preview button and per-marker nudges
  // stay in sync. Passing an explicit overrides map avoids stale-state races on rapid drags.
  const runPreview = useCallback(async (overrides: Record<string, number>) => {
    setPreviewBusy(true)
    try {
      const data = await previewVoiceProsody(voiceId, stylePreset, paceMultiplier, pauseOffset, mode, overrides)
      const blob = new Blob([Uint8Array.from(atob(data.audio_base64), (c) => c.charCodeAt(0))], { type: 'audio/wav' })
      const url = URL.createObjectURL(blob)
      setPreview((prev) => {
        if (prev) URL.revokeObjectURL(prev.url)
        return { url, blob, audioBase64: data.audio_base64, sampleCount: data.sample_count, plan: data.plan }
      })
      setPreviewMetrics(data.metrics)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setPreviewBusy(false)
    }
  }, [mode, paceMultiplier, pauseOffset, stylePreset, voiceId])

  // Preview and Reset Preview are the same action — both re-render from the current
  // sliders and clear any per-marker nudges, giving a clean baseline either way.
  const togglePreview = useCallback(() => {
    setTargetOverrides({})
    return runPreview({})
  }, [runPreview])

  const clearPreview = useCallback(() => {
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev.url)
      return null
    })
    setPreviewMetrics(null)
    setTargetOverrides({})
  }, [])

  // Merge an incremental target delta for one boundary and immediately re-preview.
  const nudgeTarget = useCallback((key: string, deltaMs: number) => {
    setTargetOverrides((prev) => {
      const next = { ...prev, [key]: (prev[key] ?? 0) + deltaMs }
      void runPreview(next)
      return next
    })
  }, [runPreview])

  const resetTarget = useCallback((key: string) => {
    setTargetOverrides((prev) => {
      if (!(key in prev)) return prev
      const next = { ...prev }
      delete next[key]
      void runPreview(next)
      return next
    })
  }, [runPreview])

  const saveVariant = useCallback(async () => {
    setSavingVariantBusy(true)
    setError(null)
    try {
      await saveVoiceProsodyVariant(voiceId, stylePreset, paceMultiplier, pauseOffset, mode, targetOverrides)
      await refresh()
      await onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSavingVariantBusy(false)
    }
  }, [mode, onChanged, paceMultiplier, pauseOffset, refresh, stylePreset, targetOverrides, voiceId])

  // Bake this take and immediately promote it to the primary variant served by the API.
  const savePromote = useCallback(async () => {
    setPromoteBusy(true)
    setError(null)
    try {
      await adjustVoiceReferencePauses(voiceId, stylePreset, paceMultiplier, pauseOffset, mode)
      await refresh()
      await onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setPromoteBusy(false)
    }
  }, [mode, onChanged, paceMultiplier, pauseOffset, refresh, stylePreset, voiceId])

  // Explicit, first-class "promote to API reference". Confirms first when this voice_id
  // is also the persisted global API default, since the swap changes the live default
  // immediately.
  const promoteVariant = useCallback(async (entry: VoiceVariantEntry) => {
    if (voice.api_active) {
      const ok = window.confirm(
        'This voice is the live API default. Promoting this variant will change what the ' +
        'default API voice sounds like immediately. Continue?',
      )
      if (!ok) return
    }
    setVariantBusy(entry.filename)
    setError(null)
    try {
      await setActiveVoiceVariant(voiceId, entry.filename)
      setActiveFilename(entry.filename)
      await onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setVariantBusy(null)
    }
  }, [onChanged, voice.api_active, voiceId])

  // Also reflects the previewed take's stats via previewMetrics, so clicking a
  // variant/Original compares against whatever is currently active.
  const previewVariant = useCallback(async (entry: VoiceVariantEntry) => {
    if (previewingVariant === entry.filename) {
      variantPreviewAudioRef.current?.pause()
      variantPreviewAudioRef.current = null
      setPreviewingVariant(null)
      setPreviewMetrics(null)
      return
    }
    variantPreviewAudioRef.current?.pause()
    setVariantBusy(entry.filename)
    setError(null)
    try {
      const [{ audio_base64 }, metricsResult] = await Promise.all([
        getVoiceVariantAudio(voiceId, entry.filename),
        getVoiceVariantMetrics(voiceId, entry.filename).catch(() => null),
      ])
      const bytes = Uint8Array.from(atob(audio_base64), (c) => c.charCodeAt(0))
      const url = URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }))
      const el = new Audio(url)
      variantPreviewAudioRef.current = el
      setPreviewingVariant(entry.filename)
      if (metricsResult) setPreviewMetrics(metricsResult.metrics)
      el.addEventListener('ended', () => setPreviewingVariant(null))
      await el.play()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setPreviewingVariant(null)
    } finally {
      setVariantBusy(null)
    }
  }, [previewingVariant, voiceId])

  const forkVariant = useCallback(async (entry: VoiceVariantEntry) => {
    if (!onFork) return
    setVariantBusy(entry.filename)
    try {
      await onFork(entry)
    } finally {
      setVariantBusy(null)
    }
  }, [onFork])

  const deleteVariant = useCallback(async (entry: VoiceVariantEntry) => {
    if (!window.confirm(`Delete variant "${entry.label}"? This cannot be undone.`)) return
    setVariantBusy(entry.filename)
    setError(null)
    try {
      await deleteVoiceVariant(voiceId, entry.filename)
      await refresh()
      await onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setVariantBusy(null)
    }
  }, [onChanged, refresh, voiceId])

  return {
    stylePreset, setStylePreset, paceMultiplier, setPaceMultiplier, pauseOffset, setPauseOffset,
    mode, setMode, hasTranscript, resolvedPrecise, setAutoTriagePrecise,
    entries, activeFilename,
    alignBusy, alignBoundaries, alignError, alignWarning,
    preview, previewMetrics, previewBusy, targetOverrides, nudgeTarget, resetTarget,
    togglePreview, clearPreview,
    previewingVariant, variantBusy, savingVariantBusy, promoteBusy,
    previewVariant, promoteVariant, forkVariant: onFork ? forkVariant : undefined, deleteVariant,
    saveVariant, savePromote,
    busy: previewBusy || savingVariantBusy || promoteBusy,
    error,
  }
}

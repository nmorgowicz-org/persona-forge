import { useCallback, useEffect, useRef, useState } from 'react'
import { useAudioSource } from '@/hooks/useAudioTransport'
import { useAppStore } from '@/store'
import {
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
  variantsReady: boolean
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
  // Latest voiceId, readable from async continuations whose closure captured a stale
  // value across a voice switch (alignment commits, preview responses).
  const voiceIdRef = useRef(voiceId)
  const previewSeq = useRef(0)
  const [variantsReady, setVariantsReady] = useState(false)
  useEffect(() => {
    voiceIdRef.current = voiceId
  }, [voiceId])

  const [previewingVariant, setPreviewingVariant] = useState<string | null>(null)
  const variantPreviewAudioRef = useRef<HTMLAudioElement | null>(null)
  // This editor's identity in the playback-focus registry (N6): previewing a variant
  // silences whatever else is sounding, and vice versa.
  // The variant preview is one audio source among several (T1).
  const source = useAudioSource('prosody-preview', 'Prosody preview')
  const variantPreviewUrlRef = useRef<string | null>(null)
  const [variantBusy, setVariantBusy] = useState<string | null>(null)
  const [savingVariantBusy, setSavingVariantBusy] = useState(false)
  const [promoteBusy, setPromoteBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const hasTranscript = Boolean((voice.sample_text || '').trim())

  const refresh = useCallback(async () => {
    const data = await getVoiceVariants(voiceId)
    setEntries(data.entries)
    setActiveFilename(data.active_filename)
    setVariantsReady(true)
  }, [voiceId])

  useEffect(() => {
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev.url)
      return null
    })
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

  // Voice switch / unmount: stop any variant preview playback and release its object
  // URL, drop the main preview (revoking its URL), and reset the per-variant state that
  // would otherwise linger as a phantom "playing" row or stale busy flag.
  useEffect(() => () => {
    variantPreviewAudioRef.current?.pause()
    variantPreviewAudioRef.current = null
    if (variantPreviewUrlRef.current) {
      URL.revokeObjectURL(variantPreviewUrlRef.current)
      variantPreviewUrlRef.current = null
    }
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev.url)
      return null
    })
    setPreviewingVariant(null)
    setVariantBusy(null)
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
    let inflight: { jobId: string; cancelled: boolean } | null = null
    try {
      const job = await startVoiceAlignment(voiceId)
      // Capture this poller's own record: a later trigger (voice switch, re-run)
      // overwrites alignJobRef, and polling the live ref would hide this poller's
      // cancel flag.
      inflight = { jobId: job.job_id, cancelled: false }
      alignJobRef.current = inflight
      let current = job
      while (current.status === 'queued' || current.status === 'running') {
        if (inflight.cancelled) return
        await sleep(500)
        if (inflight.cancelled) return
        current = await getVoiceAlignmentStatus(voiceId, job.job_id)
      }
      if (inflight.cancelled) return
      // The session may have moved to another voice while we polled (the start
      // response can land after the switch already ran) — never commit a result
      // that no longer describes the current voice.
      if (current.voice_id !== voiceIdRef.current) return
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
      if (voiceIdRef.current === voiceId) {
        setAlignError(err instanceof Error ? err.message : String(err))
      }
    } finally {
      // Only clear the shared ref if it still points at this poller — a newer one
      // may have taken it over in the meantime.
      if (inflight && alignJobRef.current === inflight) alignJobRef.current = null
      setAlignBusy(false)
    }
  }, [alignBusy, hasTranscript, voiceId])

  // Trigger alignment lazily the first time Precise resolves for this clip, and cancel
  // any in-flight job on unmount / clip change. Keyed on voiceId so a switch cancels
  // the previous voice's job under its own id and re-evaluates for the new voice;
  // keyed on alignBusy so a switch mid-alignment re-triggers once the superseded
  // poller releases its busy flag.
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
  }, [resolvedPrecise, hasTranscript, alignBoundaries, voiceId, alignBusy])

  // One place to render a prosody preview, so the Preview button and per-marker nudges
  // stay in sync. Passing an explicit overrides map avoids stale-state races on rapid drags.
  const runPreview = useCallback(async (overrides: Record<string, number>) => {
    // A newer preview request or a voice switch supersedes this one; its response
    // must not write state or allocate object URLs in the current session.
    const seq = ++previewSeq.current
    const capturedVoiceId = voiceId
    setPreviewBusy(true)
    try {
      const data = await previewVoiceProsody(capturedVoiceId, stylePreset, paceMultiplier, pauseOffset, mode, overrides)
      if (previewSeq.current !== seq || voiceIdRef.current !== capturedVoiceId) return
      const blob = new Blob([Uint8Array.from(atob(data.audio_base64), (c) => c.charCodeAt(0))], { type: 'audio/wav' })
      const url = URL.createObjectURL(blob)
      setPreview((prev) => {
        if (prev) URL.revokeObjectURL(prev.url)
        return { url, blob, audioBase64: data.audio_base64, sampleCount: data.sample_count, plan: data.plan }
      })
      setPreviewMetrics(data.metrics)
    } catch (err) {
      if (previewSeq.current !== seq || voiceIdRef.current !== capturedVoiceId) return
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      if (previewSeq.current === seq) setPreviewBusy(false)
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
  // The next map is computed here rather than inside the updater — React 18 dev
  // double-invokes updaters, which would double the preview request.
  const nudgeTarget = useCallback((key: string, deltaMs: number) => {
    const next = { ...targetOverrides, [key]: (targetOverrides[key] ?? 0) + deltaMs }
    setTargetOverrides(next)
    void runPreview(next)
  }, [runPreview, targetOverrides])

  const resetTarget = useCallback((key: string) => {
    if (!(key in targetOverrides)) return
    const next = { ...targetOverrides }
    delete next[key]
    setTargetOverrides(next)
    void runPreview(next)
  }, [runPreview, targetOverrides])

  const saveVariant = useCallback(async () => {
    const capturedVoiceId = voiceId
    setSavingVariantBusy(true)
    setError(null)
    try {
      await saveVoiceProsodyVariant(voiceId, stylePreset, paceMultiplier, pauseOffset, mode, targetOverrides)
      if (voiceIdRef.current !== capturedVoiceId) return
      useAppStore.getState().announce('Prosody variant saved — it is listed with this voice.')
      await refresh()
      await onChanged?.()
    } catch (err) {
      if (voiceIdRef.current === capturedVoiceId) {
        setError(err instanceof Error ? err.message : String(err))
      }
    } finally {
      if (voiceIdRef.current === capturedVoiceId) setSavingVariantBusy(false)
    }
  }, [mode, onChanged, paceMultiplier, pauseOffset, refresh, stylePreset, targetOverrides, voiceId])
  const savePromote = useCallback(async () => {
    const capturedVoiceId = voiceId
    setPromoteBusy(true)
    setError(null)
    let stage: 'save' | 'promote' | 'done' = 'save'
    try {
      const created = await saveVoiceProsodyVariant(voiceId, stylePreset, paceMultiplier, pauseOffset, mode, targetOverrides)
      if (voiceIdRef.current !== capturedVoiceId) return
      stage = 'promote'
      const variantFilename = `prosody_${created.variant_slug}.wav`
      await setActiveVoiceVariant(voiceId, variantFilename)
      stage = 'done'
      useAppStore.getState().announce('Variant saved and promoted — it is what the API serves now.')
      await refresh()
      await onChanged?.()
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      if (voiceIdRef.current !== capturedVoiceId) return
      setError(
        stage === 'promote'
          ? `Saved as a variant, but promotion failed: ${message} — you can promote it from the Prosody Variants list.`
          : message,
      )
    } finally {
      if (voiceIdRef.current === capturedVoiceId) setPromoteBusy(false)
    }
  }, [mode, onChanged, paceMultiplier, pauseOffset, refresh, stylePreset, targetOverrides, voiceId])

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
    const capturedVoiceId = voiceId
    setVariantBusy(entry.filename)
    setError(null)
    try {
      await setActiveVoiceVariant(voiceId, entry.filename)
      if (voiceIdRef.current !== capturedVoiceId) return
      setActiveFilename(entry.filename)
      await onChanged?.()
    } catch (err) {
      if (voiceIdRef.current === capturedVoiceId) {
        setError(err instanceof Error ? err.message : String(err))
      }
    } finally {
      if (voiceIdRef.current === capturedVoiceId) setVariantBusy(null)
    }
  }, [onChanged, voice.api_active, voiceId])

  // Also reflects the previewed take's stats via previewMetrics, so clicking a
  // variant/Original compares against whatever is currently active.
  const previewVariant = useCallback(async (entry: VoiceVariantEntry) => {
    if (previewingVariant === entry.filename) {
      variantPreviewAudioRef.current?.pause()
      variantPreviewAudioRef.current = null
      source.release()
      if (variantPreviewUrlRef.current) {
        URL.revokeObjectURL(variantPreviewUrlRef.current)
        variantPreviewUrlRef.current = null
      }
      setPreviewingVariant(null)
      setPreviewMetrics(null)
      return
    }
    const capturedVoiceId = voiceId
    variantPreviewAudioRef.current?.pause()
    if (variantPreviewUrlRef.current) {
      URL.revokeObjectURL(variantPreviewUrlRef.current)
      variantPreviewUrlRef.current = null
    }
    setVariantBusy(entry.filename)
    setError(null)
    try {
      const [{ audio_base64 }, metricsResult] = await Promise.all([
        getVoiceVariantAudio(voiceId, entry.filename),
        getVoiceVariantMetrics(voiceId, entry.filename).catch(() => null),
      ])
      // Voice switched while fetching — don't start playback or allocate an object
      // URL in the new session.
      if (voiceIdRef.current !== capturedVoiceId) return
      const bytes = Uint8Array.from(atob(audio_base64), (c) => c.charCodeAt(0))
      const url = URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }))
      variantPreviewUrlRef.current = url
      const el = new Audio(url)
      variantPreviewAudioRef.current = el
      setPreviewingVariant(entry.filename)
      setPreviewMetrics(metricsResult ? metricsResult.metrics : null)
      source.claim(() => {
        el.pause()
        setPreviewingVariant(null)
      })
      el.addEventListener('ended', () => {
        setPreviewingVariant(null)
        source.release()
        if (variantPreviewUrlRef.current === url) {
          URL.revokeObjectURL(url)
          variantPreviewUrlRef.current = null
        }
      })
      await el.play()
    } catch (err) {
      if (voiceIdRef.current !== capturedVoiceId) return
      setError(err instanceof Error ? err.message : String(err))
      setPreviewingVariant(null)
    } finally {
      if (voiceIdRef.current === capturedVoiceId) setVariantBusy(null)
    }
  }, [previewingVariant, voiceId, source])

  const forkVariant = useCallback(async (entry: VoiceVariantEntry) => {
    if (!onFork) return
    const capturedVoiceId = voiceId
    setVariantBusy(entry.filename)
    try {
      await onFork(entry)
    } finally {
      if (voiceIdRef.current === capturedVoiceId) setVariantBusy(null)
    }
  }, [onFork, voiceId])

  const deleteVariant = useCallback(async (entry: VoiceVariantEntry) => {
    if (!window.confirm(`Delete variant "${entry.label}"? This cannot be undone.`)) return
    const capturedVoiceId = voiceId
    setVariantBusy(entry.filename)
    setError(null)
    try {
      await deleteVoiceVariant(voiceId, entry.filename)
      if (voiceIdRef.current !== capturedVoiceId) return
      await refresh()
      await onChanged?.()
    } catch (err) {
      if (voiceIdRef.current === capturedVoiceId) {
        setError(err instanceof Error ? err.message : String(err))
      }
    } finally {
      if (voiceIdRef.current === capturedVoiceId) setVariantBusy(null)
    }
  }, [onChanged, refresh, voiceId])

  return {
    stylePreset, setStylePreset, paceMultiplier, setPaceMultiplier, pauseOffset, setPauseOffset,
    mode, setMode, hasTranscript, resolvedPrecise, setAutoTriagePrecise,
    entries, activeFilename, variantsReady,
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

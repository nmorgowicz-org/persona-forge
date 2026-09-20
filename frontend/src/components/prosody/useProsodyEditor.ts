import { useCallback, useEffect, useState } from 'react'
import {
  getVoiceVariants,
  previewVoiceProsody,
  saveVoiceProsodyVariant,
  setActiveVoiceVariant,
  type ProsodyMode,
  type ProsodyPreview,
  type VoiceVariantEntry,
} from '@/lib/api'

export function useProsodyEditor(voiceId: string | null, onChanged?: () => Promise<void> | void) {
  const [stylePreset, setStylePreset] = useState('Neutral')
  const [paceMultiplier, setPaceMultiplier] = useState(1)
  const [pauseOffset, setPauseOffset] = useState(0)
  const [mode, setMode] = useState<ProsodyMode>('auto')
  const [entries, setEntries] = useState<VoiceVariantEntry[]>([])
  const [activeFilename, setActiveFilename] = useState('original.wav')
  const [preview, setPreview] = useState<ProsodyPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!voiceId) return
    const data = await getVoiceVariants(voiceId)
    setEntries(data.entries)
    setActiveFilename(data.active_filename)
  }, [voiceId])

  useEffect(() => {
    setPreview(null)
    setError(null)
    void refresh().catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [refresh])

  const run = useCallback(async (action: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try {
      await action()
      await refresh()
      await onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }, [onChanged, refresh])

  const previewProsody = useCallback(() => run(async () => {
    if (!voiceId) return
    setPreview(await previewVoiceProsody(voiceId, stylePreset, paceMultiplier, pauseOffset, mode))
  }), [mode, paceMultiplier, pauseOffset, run, stylePreset, voiceId])

  const saveVariant = useCallback(async () => {
    if (!voiceId) return
    setBusy(true)
    setError(null)
    try {
      const saved = await saveVoiceProsodyVariant(voiceId, stylePreset, paceMultiplier, pauseOffset, mode)
      await refresh()
      setEntries((current) => current.some((entry) => entry.id === saved.variant_id) ? current : [
        ...current,
        { id: saved.variant_id, filename: saved.variant_slug, label: saved.variant_slug, slug: saved.variant_slug, is_original: false },
      ])
      await onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }, [mode, onChanged, paceMultiplier, pauseOffset, refresh, stylePreset, voiceId])

  const promoteVariant = useCallback((filename: string) => run(async () => {
    if (!voiceId) return
    await setActiveVoiceVariant(voiceId, filename)
  }), [run, voiceId])

  return {
    stylePreset, setStylePreset, paceMultiplier, setPaceMultiplier, pauseOffset, setPauseOffset,
    mode, setMode, entries, activeFilename, preview, busy, error, previewProsody, saveVariant, promoteVariant,
  }
}

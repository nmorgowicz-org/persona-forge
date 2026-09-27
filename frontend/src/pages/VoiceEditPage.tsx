import { useCallback, useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { SavedVoicePicker } from '@/components/voice/SavedVoicePicker'
import { ProsodyEditorPanel } from '@/components/prosody/ProsodyEditorPanel'
import { PageHeader } from '@/components/ui/page-header'
import { listVoices, type VoiceMeta } from '@/lib/api'
import { useAppStore } from '@/store'

export function VoiceEditPage() {
  const setVoices = useAppStore((state) => state.setVoices)
  const deepLinkVoiceId = useAppStore((state) => state.deepLinkProsodyVoiceId)
  const consumeDeepLink = useAppStore((state) => state.setDeepLinkProsodyVoiceId)
  const [voices, setLocalVoices] = useState<VoiceMeta[]>(() => useAppStore.getState().voices)
  const [selection, setSelection] = useState(() => ({
    deepLinkId: deepLinkVoiceId,
    selectedId: deepLinkVoiceId,
  }))
  if (deepLinkVoiceId && selection.deepLinkId !== deepLinkVoiceId) {
    setSelection({ deepLinkId: deepLinkVoiceId, selectedId: deepLinkVoiceId })
  }
  const selectedId = selection.selectedId
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const refresh = useCallback(async (): Promise<void> => {
    const next = await listVoices()
    setLocalVoices(next)
    setVoices(next)
  }, [setVoices])

  useEffect(() => {
    const load = async () => {
      try {
        await refresh()
        setLoadError(null)
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : String(err))
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [refresh])

  // Keep the one-shot deep-link in the store only until its target voice is available.
  useEffect(() => {
    if (deepLinkVoiceId && voices.some((voice) => voice.voice_id === deepLinkVoiceId)) {
      consumeDeepLink(null)
    }
  }, [consumeDeepLink, deepLinkVoiceId, voices])

  const effectiveSelectedId =
    selectedId && voices.some((voice) => voice.voice_id === selectedId)
      ? selectedId
      : voices[0]?.voice_id ?? null
  const selectedVoice = voices.find((voice) => voice.voice_id === effectiveSelectedId) ?? null

  return (
    <div data-testid="voice-edit-page" className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title="Voice Edit"
        description="Create, compare, and promote prosody variants without leaving the voice workflow."
      />
      {loadError && (
        <p data-testid="voice-edit-load-error" className="status-badge status-tone-danger px-3 py-1.5 text-xs font-medium">
          {loadError}
        </p>
      )}
      <SavedVoicePicker
        voices={voices}
        selectedId={effectiveSelectedId}
        onChange={(nextId) => setSelection((current) => ({ ...current, selectedId: nextId }))}
        search={search}
        onSearchChange={setSearch}
      />
      {selectedVoice ? (
        <ProsodyEditorPanel voice={selectedVoice} layout="page" onChanged={refresh} />
      ) : loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading voices…
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Save a reference voice before editing its prosody.</p>
      )}
    </div>
  )
}

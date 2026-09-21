import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { SavedVoicePicker } from '@/components/voice/SavedVoicePicker'
import { ProsodyEditorPanel } from '@/components/prosody/ProsodyEditorPanel'
import { listVoices, type VoiceMeta } from '@/lib/api'
import { useAppStore } from '@/store'

export function VoiceEditPage() {
  const setVoices = useAppStore((state) => state.setVoices)
  const deepLinkVoiceId = useAppStore((state) => state.deepLinkProsodyVoiceId)
  const consumeDeepLink = useAppStore((state) => state.setDeepLinkProsodyVoiceId)
  const [voices, setLocalVoices] = useState<VoiceMeta[]>(() => useAppStore.getState().voices)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const refresh = async (): Promise<void> => {
    const next = await listVoices()
    setLocalVoices(next)
    setVoices(next)
  }

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
  }, [])

  // Deep link and auto-select share one effect so the deep-linked voice always wins:
  // two effects in the same commit raced on setSelectedId, and the auto-select
  // (voices[0]) clobbered the deep link before it was consumed.
  useEffect(() => {
    if (deepLinkVoiceId && voices.some((voice) => voice.voice_id === deepLinkVoiceId)) {
      setSelectedId(deepLinkVoiceId)
      consumeDeepLink(null)
    } else if (!selectedId && !deepLinkVoiceId && voices.length) {
      setSelectedId(voices[0].voice_id)
    }
  }, [consumeDeepLink, deepLinkVoiceId, selectedId, voices])

  const selectedVoice = voices.find((voice) => voice.voice_id === selectedId) ?? null

  return (
    <div data-testid="voice-edit-page" className="flex min-w-0 flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Voice Edit</h1>
        <p className="text-sm text-muted-foreground">Create, compare, and promote prosody variants without leaving the voice workflow.</p>
      </header>
      {loadError && (
        <p data-testid="voice-edit-load-error" className="status-badge status-tone-danger px-3 py-1.5 text-xs font-medium">
          {loadError}
        </p>
      )}
      <SavedVoicePicker voices={voices} selectedId={selectedId} onChange={setSelectedId} search={search} onSearchChange={setSearch} />
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

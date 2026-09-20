import { useEffect, useState } from 'react'
import { SavedVoicePicker } from '@/components/voice/SavedVoicePicker'
import { ProsodyEditorPanel } from '@/components/prosody/ProsodyEditorPanel'
import { listVoices, type VoiceMeta } from '@/lib/api'
import { useAppStore } from '@/store'

export function VoiceEditPage() {
  const storeVoices = useAppStore((state) => state.voices)
  const setVoices = useAppStore((state) => state.setVoices)
  const deepLinkVoiceId = useAppStore((state) => state.deepLinkProsodyVoiceId)
  const consumeDeepLink = useAppStore((state) => state.setDeepLinkProsodyVoiceId)
  const [voices, setLocalVoices] = useState<VoiceMeta[]>(storeVoices)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const refresh = async (): Promise<void> => {
    const next = await listVoices()
    setLocalVoices(next)
    setVoices(next)
  }

  useEffect(() => { void refresh() }, [])

  useEffect(() => {
    if (!deepLinkVoiceId || !voices.some((voice) => voice.voice_id === deepLinkVoiceId)) return
    setSelectedId(deepLinkVoiceId)
    consumeDeepLink(null)
  }, [consumeDeepLink, deepLinkVoiceId, voices])

  useEffect(() => {
    if (!selectedId && voices.length) setSelectedId(voices[0].voice_id)
  }, [selectedId, voices])

  const selectedVoice = voices.find((voice) => voice.voice_id === selectedId) ?? null

  return (
    <div data-testid="voice-edit-page" className="flex min-w-0 flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Voice Edit</h1>
        <p className="text-sm text-muted-foreground">Create, compare, and promote prosody variants without leaving the voice workflow.</p>
      </header>
      <SavedVoicePicker voices={voices} selectedId={selectedId} onChange={setSelectedId} search={search} onSearchChange={setSearch} />
      {selectedVoice ? <ProsodyEditorPanel voice={selectedVoice} layout="page" onChanged={refresh} /> : <p className="text-sm text-muted-foreground">Save a reference voice before editing its prosody.</p>}
    </div>
  )
}

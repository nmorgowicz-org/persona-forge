import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Mic2, Pencil, Trash2 } from 'lucide-react'
import { deleteVoice, getVoice, listVoices, type VoiceMeta } from '@/lib/api'
import type { ChipSelections } from '@/lib/voiceDesignChips'
import { AudioPlayer } from '@/components/AudioPlayer'
import { Button } from '@/components/ui/button'
import { useAppStore } from '@/store'

export function VoiceLibraryPage() {
  const [voices, setVoices] = useState<VoiceMeta[]>([])
  const [error, setError] = useState<string | null>(null)
  const [playing, setPlaying] = useState<Record<string, { url: string; blob: Blob }>>({})
  const [busyVoiceId, setBusyVoiceId] = useState<string | null>(null)
  const setVoiceId = useAppStore((s) => s.setVoiceId)
  const setPage = useAppStore((s) => s.setPage)
  const setEditingVoice = useAppStore((s) => s.setEditingVoice)

  function refresh() {
    return listVoices()
      .then(setVoices)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function preview(voiceId: string) {
    if (playing[voiceId]) return
    try {
      const full = await getVoice(voiceId)
      if (!full.audio_base64) return
      const bytes = Uint8Array.from(atob(full.audio_base64), (c) => c.charCodeAt(0))
      const blob = new Blob([bytes], { type: 'audio/wav' })
      setPlaying((prev) => ({ ...prev, [voiceId]: { url: URL.createObjectURL(blob), blob } }))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function edit(voiceId: string) {
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
      setPage('voice-design')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyVoiceId(null)
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

  return (
    <div className="flex flex-col gap-6">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-semibold tracking-tight">Voice Library</h1>
        <p className="text-sm text-muted-foreground">
          Voices you've designed and saved, ready to use in Speak or over the API.
        </p>
      </motion.div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {voices.length === 0 && !error && (
        <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border py-16 text-center">
          <Mic2 className="size-6 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">No voices saved yet.</p>
          <Button size="sm" variant="secondary" onClick={() => setPage('voice-design')}>
            Design your first voice
          </Button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {voices.map((voice, i) => (
          <motion.div
            key={voice.voice_id}
            data-testid="voice-card"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.03 }}
            className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 text-card-foreground shadow-sm"
          >
            <div>
              <p className="text-sm font-medium">{voice.voice_id}</p>
              <p className="line-clamp-2 text-xs text-muted-foreground">{voice.description}</p>
            </div>

            {playing[voice.voice_id] ? (
              <AudioPlayer src={playing[voice.voice_id].url} blob={playing[voice.voice_id].blob} />
            ) : (
              <Button size="sm" variant="outline" onClick={() => preview(voice.voice_id)}>
                Load preview
              </Button>
            )}

            <div className="flex gap-2">
              <Button
                size="sm"
                className="flex-1"
                onClick={() => {
                  setVoiceId(voice.voice_id)
                  setPage('speak')
                }}
              >
                Use in Speak
              </Button>
              <Button
                size="sm"
                variant="outline"
                aria-label="Tune this voice"
                title="Tune this voice"
                disabled={busyVoiceId === voice.voice_id}
                onClick={() => edit(voice.voice_id)}
              >
                <Pencil className="size-4" />
              </Button>
              <Button
                size="sm"
                variant="outline"
                aria-label="Delete this voice"
                title="Delete this voice"
                disabled={busyVoiceId === voice.voice_id}
                onClick={() => remove(voice.voice_id)}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}

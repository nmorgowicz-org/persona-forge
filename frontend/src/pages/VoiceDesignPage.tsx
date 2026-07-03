import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { VoiceDesignPanel } from '@/components/VoiceDesignPanel'
import { PersonaForgePanel } from '@/components/PersonaForgePanel'
import { EngineSelector, type DesignEngine } from '@/components/EngineSelector'
import { useAppStore, type EditingVoice } from '@/store'
import { listVoices } from '@/lib/api'

export function VoiceDesignPage() {
  const setVoiceId = useAppStore((s) => s.setVoiceId)
  const setVoices = useAppStore((s) => s.setVoices)
  const setPage = useAppStore((s) => s.setPage)
  const editingVoice = useAppStore((s) => s.editingVoice)
  const setEditingVoice = useAppStore((s) => s.setEditingVoice)
  const [engine, setEngine] = useState<DesignEngine>('qwen')

  // Capture the queued edit once on mount, then clear it from the store — a plain later visit
  // to this page (e.g. via the sidebar) should start fresh, not silently reuse stale edit state.
  const [initial] = useState<EditingVoice | null>(editingVoice)
  useEffect(() => {
    if (editingVoice) setEditingVoice(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function refreshVoices() {
    try {
      setVoices(await listVoices())
    } catch {
      // Non-fatal — voice library may be empty or briefly unavailable during a swap.
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-semibold tracking-tight">Voice Design</h1>
        <p className="text-sm text-muted-foreground">
          Compose a voice from traits, preview it, and save it to the library.
        </p>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}>
        <EngineSelector value={engine} onChange={setEngine} />
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} key={engine}>
        {engine === 'qwen' ? (
          <VoiceDesignPanel
            key={initial?.voiceId ?? 'new'}
            initial={initial}
            onVoiceCreated={(newVoiceId) => {
              setVoiceId(newVoiceId)
              refreshVoices()
              setPage('speak')
            }}
          />
        ) : (
          <PersonaForgePanel />
        )}
      </motion.div>
    </div>
  )
}

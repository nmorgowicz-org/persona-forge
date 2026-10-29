import { useEffect, useState } from 'react'

export interface SpeakEngineModel {
  id: string
  label: string
  installed?: boolean
  active?: boolean
  capabilities: { clone?: boolean; seed?: boolean; speed?: boolean }
}
export interface PresetVoice {
  voice_id: string
  engine: string | null
  kind: 'library' | 'preset'
  display_name: string
}

/** Loads installed engines and their preset voices once. */
export function useSpeakEngines() {
  const [models, setModels] = useState<SpeakEngineModel[]>([])
  const [presets, setPresets] = useState<PresetVoice[]>([])
  useEffect(() => {
    Promise.all([fetch('/v1/models').then((r) => r.json()), fetch('/v1/audio/voices').then((r) => r.json())])
      .then(([m, v]) => {
        setModels((m.data ?? []).filter((e: SpeakEngineModel) => e.installed !== false))
        setPresets((v.data ?? []).filter((x: PresetVoice) => x.kind === 'preset'))
      })
      .catch(() => undefined)
  }, [])
  return { models, presets }
}


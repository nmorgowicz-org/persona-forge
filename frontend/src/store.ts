import { create } from 'zustand'
import type { VoiceMeta } from './lib/api'
import { applyTheme, loadStoredTheme, type Theme } from './lib/theme'
import type { ChipSelections } from './lib/voiceDesignChips'

export type Page = 'speak' | 'voice-design' | 'voice-library' | 'integrations' | 'runtime'

// A voice queued up from the Voice Library's "Edit" action, to be consumed once by
// VoiceDesignPage and cleared — see VoiceDesignPage.tsx. Editing forks a new voice on save
// (there's no in-place update), so this only ever pre-fills the design panel.
export interface EditingVoice {
  voiceId: string
  description: string
  sampleText: string
  language: string
  seed: number | null
  selections: ChipSelections | null
}

interface AppState {
  page: Page
  theme: Theme
  text: string
  voiceId: string | null
  voices: VoiceMeta[]
  audioUrl: string | null
  isGenerating: boolean
  error: string | null
  editingVoice: EditingVoice | null
  setPage: (page: Page) => void
  setTheme: (theme: Theme) => void
  setText: (text: string) => void
  setVoiceId: (voiceId: string | null) => void
  setVoices: (voices: VoiceMeta[]) => void
  setAudioUrl: (url: string | null) => void
  setGenerating: (isGenerating: boolean) => void
  setError: (error: string | null) => void
  setEditingVoice: (voice: EditingVoice | null) => void
}

const initialTheme = loadStoredTheme()
applyTheme(initialTheme)

export const useAppStore = create<AppState>((set) => ({
  page: 'speak',
  theme: initialTheme,
  text: '',
  voiceId: null,
  voices: [],
  audioUrl: null,
  isGenerating: false,
  error: null,
  editingVoice: null,
  setPage: (page) => set({ page }),
  setTheme: (theme) => {
    applyTheme(theme)
    set({ theme })
  },
  setText: (text) => set({ text }),
  setVoiceId: (voiceId) => set({ voiceId }),
  setVoices: (voices) => set({ voices }),
  setAudioUrl: (audioUrl) => set({ audioUrl }),
  setGenerating: (isGenerating) => set({ isGenerating }),
  setError: (error) => set({ error }),
  setEditingVoice: (editingVoice) => set({ editingVoice }),
}))

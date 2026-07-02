import { create } from 'zustand'

interface AppState {
  text: string
  voiceId: string | null
  audioUrl: string | null
  isGenerating: boolean
  error: string | null
  setText: (text: string) => void
  setVoiceId: (voiceId: string | null) => void
  setAudioUrl: (url: string | null) => void
  setGenerating: (isGenerating: boolean) => void
  setError: (error: string | null) => void
}

export const useAppStore = create<AppState>((set) => ({
  text: '',
  voiceId: null,
  audioUrl: null,
  isGenerating: false,
  error: null,
  setText: (text) => set({ text }),
  setVoiceId: (voiceId) => set({ voiceId }),
  setAudioUrl: (audioUrl) => set({ audioUrl }),
  setGenerating: (isGenerating) => set({ isGenerating }),
  setError: (error) => set({ error }),
}))

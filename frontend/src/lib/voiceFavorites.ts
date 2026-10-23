import { getPref, setPref, subscribePrefs } from './uiPreferences'

/** Favorited voice IDs, shared by the catalog and the Speak picker. */
export function readFavoriteVoiceIds(): string[] {
  const value = getPref<string[]>('voiceFavorites', [])
  return Array.isArray(value) ? value.filter((id) => typeof id === 'string') : []
}

export function toggleFavoriteVoice(voiceId: string): string[] {
  const current = readFavoriteVoiceIds()
  const next = current.includes(voiceId)
    ? current.filter((id) => id !== voiceId)
    : [...current, voiceId]
  setPref('voiceFavorites', next)
  return next
}

export function subscribeFavoriteVoices(callback: () => void): () => void {
  return subscribePrefs(callback)
}

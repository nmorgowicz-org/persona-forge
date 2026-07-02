export const THEMES = ['violet', 'teal', 'amber', 'rose'] as const
export type Theme = (typeof THEMES)[number]

const STORAGE_KEY = 'qwen3-tts-theme'
const DEFAULT_THEME: Theme = 'violet'

export function loadStoredTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY)
  return (THEMES as readonly string[]).includes(stored ?? '') ? (stored as Theme) : DEFAULT_THEME
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  localStorage.setItem(STORAGE_KEY, theme)
}

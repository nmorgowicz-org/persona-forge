import { getPref } from './uiPreferences'

export const THEMES = ['violet', 'teal', 'amber', 'rose'] as const
export type Theme = (typeof THEMES)[number]

const STORAGE_KEY = 'persona-forge-theme'
const DEFAULT_THEME: Theme = 'violet'

export function loadStoredTheme(): Theme {
  return getPref<Theme>('theme', DEFAULT_THEME)
}

// Local first-paint copy only. Persistence to the server happens in the store's setTheme
// (a user action) — boot-time calls must not POST, or they race the preference sync.
export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  localStorage.setItem(STORAGE_KEY, theme)
}

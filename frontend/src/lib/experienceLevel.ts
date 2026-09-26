import { getPref } from './uiPreferences'

export const EXPERIENCE_LEVELS = ['guided', 'expert'] as const
export type ExperienceLevel = (typeof EXPERIENCE_LEVELS)[number]

const STORAGE_KEY = 'persona-forge-experience-level'
const DEFAULT_LEVEL: ExperienceLevel = 'guided'

export function loadStoredExperienceLevel(): ExperienceLevel {
  return getPref<ExperienceLevel>('experienceLevel', DEFAULT_LEVEL)
}

// Local first-paint copy only; the store's setUiExperienceLevel persists to the server.
export function storeExperienceLevel(level: ExperienceLevel) {
  localStorage.setItem(STORAGE_KEY, level)
}

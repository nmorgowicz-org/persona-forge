export const EXPERIENCE_LEVELS = ['guided', 'expert'] as const
export type ExperienceLevel = (typeof EXPERIENCE_LEVELS)[number]

const STORAGE_KEY = 'persona-forge-experience-level'
const DEFAULT_LEVEL: ExperienceLevel = 'guided'

export function loadStoredExperienceLevel(): ExperienceLevel {
  const stored = localStorage.getItem(STORAGE_KEY)
  return (EXPERIENCE_LEVELS as readonly string[]).includes(stored ?? '')
    ? (stored as ExperienceLevel)
    : DEFAULT_LEVEL
}

export function storeExperienceLevel(level: ExperienceLevel) {
  localStorage.setItem(STORAGE_KEY, level)
}

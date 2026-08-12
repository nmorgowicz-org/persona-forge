import { useAppStore } from '@/store'

export function useExperienceLevel() {
  return useAppStore((s) => s.uiExperienceLevel)
}

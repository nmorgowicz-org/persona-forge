import type { BuiltInVoiceMeta, VoiceEngineBinding } from '@/lib/api'
import { shortEngineLabel } from '@/lib/voiceEngines'

export type ReadinessTone = 'ready' | 'warn' | 'error' | 'info' | 'muted'

export interface ReadinessBadge {
  text: string
  tone: ReadinessTone
}

/**
 * Readiness of one entry in the Speak picker (plan §5.6). Saved voices report where a pack
 * cloning engine can run them (from /voices/engines bindings); presets report whether their
 * engine is installed. Pocket's own presets and Pocket cloning are always ready, so Pocket
 * presets get the plain "Ready" badge and saved voices carry no Pocket badge.
 */
export function savedVoiceBadges(bindings: VoiceEngineBinding[] | undefined): ReadinessBadge[] {
  if (!bindings) return []
  const badges: ReadinessBadge[] = []
  for (const binding of bindings) {
    if (!binding.supported || binding.engine === 'pocket-tts') continue
    const name = shortEngineLabel(binding)
    if (binding.status === 'ready') badges.push({ text: `Ready on ${name}`, tone: 'ready' })
    else if (binding.status === 'preparing') badges.push({ text: `Preparing for ${name}…`, tone: 'info' })
    else if (binding.status === 'failed') badges.push({ text: `${name} prepare failed`, tone: 'error' })
    else if (!binding.installed) badges.push({ text: `Install ${name}`, tone: 'muted' })
    else badges.push({ text: `Prepare ${name} first`, tone: 'warn' })
  }
  return badges
}

export function presetReadinessBadge(preset: BuiltInVoiceMeta): ReadinessBadge {
  if (preset.installed === false) {
    return { text: `Install ${preset.engine_label ?? preset.engine ?? 'engine'}`, tone: 'muted' }
  }
  return { text: 'Ready', tone: 'ready' }
}

export const READINESS_BADGE_CLASSES: Record<ReadinessTone, string> = {
  ready: 'border-success/30 bg-success/10 text-success',
  warn: 'border-warning/30 bg-warning/10 text-warning',
  error: 'border-destructive/30 bg-destructive/10 text-destructive',
  info: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-400',
  muted: 'border-border bg-muted/30 text-muted-foreground',
}

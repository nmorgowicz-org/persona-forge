import type { VoiceEngineBinding } from '@/lib/api'

const SHORT_LABELS: Record<string, string> = {
  'pocket-tts': 'Pocket',
  'pocket-lite': 'Pocket Lite',
  kitten2: 'Kitten 2',
  'phonon-31m': 'Phonon',
  kokoro: 'Kokoro',
}

export function shortEngineLabel(binding: Pick<VoiceEngineBinding, 'engine' | 'label'>): string {
  return SHORT_LABELS[binding.engine] ?? binding.label
}

/** What the chip says, e.g. "Kitten 2 • Prepare" or "Phonon — not supported (no local cloning)". */
export function chipText(binding: VoiceEngineBinding): string {
  const name = shortEngineLabel(binding)
  if (binding.status === 'unsupported') return `${name} — not supported (${binding.reason ?? 'no local cloning'})`
  if (!binding.installed) return `${name} · Install to use`
  switch (binding.status) {
    case 'ready':
      return `${name} ✓ Ready`
    case 'preparing':
      return `${name} … Preparing`
    case 'failed':
      return `${name} ! Failed, retry`
    default:
      return `${name} • Prepare`
  }
}

export function chipExplanation(binding: VoiceEngineBinding): string {
  const name = shortEngineLabel(binding)
  switch (binding.status) {
    case 'unsupported':
      return `${binding.label} cannot clone a saved voice (${binding.reason ?? 'no local cloning'}). Use one of its built-in voices instead.`
    case 'ready':
      return binding.engine === 'pocket-tts'
        ? `${name} clones this voice on every request; nothing to prepare.`
        : `${name} has prepared this voice from its current reference audio${binding.needs_transcript ? ' and transcript' : ''}. Editing either makes it need preparing again.`
    case 'preparing':
      return `Preparing this voice for ${name}…`
    case 'failed':
      return `Preparing for ${name} failed: ${binding.error ?? 'unknown error'}. Choose it again to retry.`
    default:
      return !binding.installed
        ? `${binding.label} is not installed. Install it under Runtime → Speech engines to use this voice with it.`
        : `Prepare this voice for ${name} now, instead of at its first use.${binding.needs_transcript ? ' It clones with the transcript, so you will confirm the words first.' : ''}`
  }
}

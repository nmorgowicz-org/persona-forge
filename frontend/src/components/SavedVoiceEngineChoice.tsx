import type { VoiceEngineBinding } from '@/lib/api'
import { shortEngineLabel } from '@/lib/voiceEngines'

interface Props {
  /** Binding status of the selected saved voice, from GET /voices/{id}/engines. */
  bindings: VoiceEngineBinding[] | undefined
  /** The current engine choice ('' = the active engine, served by the old job path). */
  engine: string
  onEngine: (engine: string) => void
}

/** A binding this voice can actually run on: installed, cloning-capable, and ready or preparable. */
function runnable(binding: VoiceEngineBinding): boolean {
  return (
    binding.supported &&
    binding.installed &&
    binding.engine !== 'pocket-tts' &&
    (binding.status === 'ready' || binding.status === 'needs_preparation')
  )
}

/**
 * Engine dropdown for a selected saved voice (plan §5.6: "for saved voices an engine dropdown
 * lists prepared engines"). Pocket is always there (it clones per request); each pack engine the
 * voice can run on is labelled with its binding status. Choosing one drives the same
 * /v1/audio/speech path as the Engine selector.
 */
export function SavedVoiceEngineChoice({ bindings, engine, onEngine }: Props) {
  const options = (bindings ?? []).filter(runnable)
  if (options.length === 0) return null
  // An engine that cannot run this voice (or cannot clone at all) must not sit in the box.
  const current = engine === '' || options.some((b) => b.engine === engine) ? engine : ''
  return (
    <div className="flex flex-col gap-1">
      <span className="micro-label">Runs on</span>
      <select
        data-testid="saved-voice-engine"
        aria-label="Engine for this voice"
        className="h-9 max-w-52 rounded-md border border-input bg-transparent px-2 text-sm"
        value={current}
        onChange={(event) => onEngine(event.target.value)}
      >
        <option value="">Pocket (active engine)</option>
        {options.map((binding) => (
          <option key={binding.engine} value={binding.engine}>
            {`${shortEngineLabel(binding)} — ${binding.status === 'ready' ? 'Ready' : 'prepare first'}`}
          </option>
        ))}
      </select>
    </div>
  )
}

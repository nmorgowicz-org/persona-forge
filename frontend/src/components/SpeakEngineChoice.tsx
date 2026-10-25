import type { PresetVoice, SpeakEngineModel } from '@/lib/speakEngines'

interface Props {
  models: SpeakEngineModel[]
  presets: PresetVoice[]
  engine: string
  preset: string
  onEngine: (engine: string) => void
  onPreset: (preset: string) => void
}

/**
 * Engine and preset voice for Speak. The empty engine means "the active engine" and keeps the
 * existing generate path. Any other engine is served beside the active one through the
 * OpenAI-compatible endpoint, so choosing it never unloads or swaps anything.
 */
export function SpeakEngineChoice({ models, presets, engine, preset, onEngine, onPreset }: Props) {
  const active = models.find((m) => m.active)
  const chosen = models.find((m) => m.id === engine)
  const engineVoices = presets.filter((v) => v.engine === engine)
  if (models.length < 2) return null
  return (
    <div className="flex flex-col gap-1" data-testid="speak-engine-choice">
      <span className="micro-label">Engine</span>
      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="Engine"
          className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
          value={engine}
          onChange={(event) => {
            onEngine(event.target.value)
            onPreset('')
          }}
        >
          <option value="">Active engine{active ? ` (${active.label})` : ''}</option>
          {models
            .filter((m) => !m.active)
            .map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
        </select>
        {chosen && (
          <select
            aria-label="Engine voice"
            className="h-9 max-w-52 rounded-md border border-input bg-transparent px-2 text-sm"
            value={preset}
            onChange={(event) => onPreset(event.target.value)}
          >
            {chosen.capabilities.clone && <option value="">Selected voice (cloned)</option>}
            {engineVoices.map((v) => (
              <option key={v.voice_id} value={v.voice_id}>
                {v.display_name}
              </option>
            ))}
          </select>
        )}
      </div>
      {chosen && (
        <span className="max-w-72 text-[10px] text-muted-foreground">
          {chosen.label} runs beside {active?.label ?? 'the active engine'}; nothing is unloaded.
          {!chosen.capabilities.seed && ` ${chosen.label} doesn't support seeds.`} Post-processing applies to the
          active engine only.
        </span>
      )}
    </div>
  )
}

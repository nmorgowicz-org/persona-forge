import { motion } from 'framer-motion'
import { Sparkles, Wand2 } from 'lucide-react'
import { cn } from '@/lib/utils'

export type DesignEngine = 'qwen' | 'omnivoice'

interface EngineOption {
  id: DesignEngine
  label: string
  description: string
  icon: typeof Sparkles
}

const ENGINE_OPTIONS: EngineOption[] = [
  {
    id: 'qwen',
    label: 'Qwen VoiceDesign',
    description: 'Free-form description, best for tone/persona — not accent-precise.',
    icon: Sparkles,
  },
  {
    id: 'omnivoice',
    label: 'Persona Forge (OmniVoice)',
    description: 'Fixed trait chips, genuinely accent-capable — audition, cherry-pick, stitch.',
    icon: Wand2,
  },
]

interface EngineSelectorProps {
  value: DesignEngine
  onChange: (engine: DesignEngine) => void
}

export function EngineSelector({ value, onChange }: EngineSelectorProps) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {ENGINE_OPTIONS.map((option) => {
        const selected = value === option.id
        return (
          <button
            key={option.id}
            type="button"
            data-testid={`engine-${option.id}`}
            onClick={() => onChange(option.id)}
            className={cn(
              'relative flex items-start gap-3 rounded-xl border p-4 text-left transition-colors',
              selected
                ? 'border-primary bg-primary/5'
                : 'border-border bg-card hover:bg-accent/40',
            )}
          >
            {selected && (
              <motion.div
                layoutId="engine-selector-highlight"
                className="pointer-events-none absolute inset-0 rounded-xl border border-primary"
                transition={{ type: 'spring', stiffness: 500, damping: 40 }}
              />
            )}
            <option.icon
              className={cn('mt-0.5 size-4 shrink-0', selected ? 'text-primary' : 'text-muted-foreground')}
            />
            <div>
              <p className="text-sm font-medium leading-none">{option.label}</p>
              <p className="mt-1 text-xs text-muted-foreground">{option.description}</p>
            </div>
          </button>
        )
      })}
    </div>
  )
}

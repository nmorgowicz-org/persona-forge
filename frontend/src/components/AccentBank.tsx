import { motion } from 'motion/react'
import { Play } from 'lucide-react'
import { ACCENT_BANK, type AccentBankEntry } from '@/lib/accentBank'
import { cn } from '@/lib/utils'

interface AccentBankProps {
  selectedId: string | null
  onSelect: (entry: AccentBankEntry) => void
}

export function AccentBank({ selectedId, onSelect }: AccentBankProps) {
  return (
    <div className="flex flex-wrap gap-3">
      {ACCENT_BANK.map((entry) => {
        const selected = entry.id === selectedId
        return (
          <motion.button
            key={entry.id}
            type="button"
            data-testid={`accent-bank-${entry.id}`}
            onClick={() => onSelect(entry)}
            whileTap={{ scale: 0.97 }}
            className={cn(
              'flex w-56 flex-col gap-2 rounded-xl border p-3 text-left transition-colors',
              selected ? 'border-primary bg-primary/5' : 'border-border bg-card hover:bg-accent/40',
            )}
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">{entry.label}</p>
              <span
                className={cn(
                  'flex size-6 items-center justify-center rounded-full',
                  entry.previewAudioUrl
                    ? 'bg-primary/10 text-primary'
                    : 'bg-muted text-muted-foreground/50',
                )}
                title={entry.previewAudioUrl ? 'Play preview' : 'Preview not curated yet'}
              >
                <Play className="size-3" />
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground">{entry.instruct}</p>
            <p className="text-[11px] text-muted-foreground/70">
              {entry.showcaseSentences.length} showcase sentence
              {entry.showcaseSentences.length === 1 ? '' : 's'}
            </p>
          </motion.button>
        )
      })}
    </div>
  )
}

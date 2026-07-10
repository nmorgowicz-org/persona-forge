import { HelpCircle } from 'lucide-react'
import { TooltipProvider } from '@/components/ui/tooltip'
import * as Tooltip from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store'
import { GLOSSARY } from '@/lib/glossary'

export function InfoIcon({ text, className }: { text: string; className?: string }) {
  const setGlossaryOpen = useAppStore((s) => s.setGlossaryOpen)
  const glossaryEntry = GLOSSARY[text]

  return (
    <TooltipProvider delayDuration={60} skipDelayDuration={0}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span
            className={cn(
              'inline-flex size-4 cursor-help items-center justify-center rounded-full text-muted-foreground/70 transition-colors hover:text-foreground',
              className,
            )}
            aria-label={text}
          >
            <HelpCircle className="size-3.5" />
          </span>
        </Tooltip.Trigger>
        <Tooltip.Content side="top" align="start" className="max-w-64 p-2">
          <div className="flex flex-col gap-1">
            <p className="text-xs">{glossaryEntry ? glossaryEntry.definition : text}</p>
            {glossaryEntry && (
              <button
                type="button"
                onClick={() => setGlossaryOpen(true)}
                className="text-[10px] text-primary underline opacity-80 hover:opacity-100"
              >
                Learn more in Glossary
              </button>
            )}
          </div>
        </Tooltip.Content>
      </Tooltip.Root>
    </TooltipProvider>
  )
}


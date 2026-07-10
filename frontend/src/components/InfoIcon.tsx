import { HelpCircle } from 'lucide-react'
import { TooltipProvider } from '@/components/ui/tooltip'
import * as Tooltip from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

export function InfoIcon({ text, className }: { text: string; className?: string }) {
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
        <Tooltip.Content side="top" align="start">
          {text}
        </Tooltip.Content>
      </Tooltip.Root>
    </TooltipProvider>
  )
}

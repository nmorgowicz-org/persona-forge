import { TooltipProvider } from '@/components/ui/tooltip'
import * as Tooltip from '@/components/ui/tooltip'

export function InfoIcon({ text }: { text: string }) {
  return (
    <TooltipProvider delayDuration={60} skipDelayDuration={0}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span
            className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full border border-muted-foreground/40 text-[10px] font-medium text-muted-foreground/70 transition-colors hover:border-muted-foreground hover:text-muted-foreground cursor-help"
          >
            ?
          </span>
        </Tooltip.Trigger>
        <Tooltip.Content side="top" align="start">
          {text}
        </Tooltip.Content>
      </Tooltip.Root>
    </TooltipProvider>
  )
}

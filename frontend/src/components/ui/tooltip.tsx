import * as React from 'react'
import * as Radix from 'radix-ui'
import { cn } from '@/lib/utils'

const T = Radix.Tooltip

export const TooltipRoot = T.Root
export const TooltipTrigger = T.Trigger
export const TooltipProvider = T.Provider

export function TooltipContent({
  children,
  side = 'top',
  align = 'center',
  className,
}: {
  children: React.ReactNode
  side?: 'top' | 'bottom' | 'left' | 'right'
  align?: 'center' | 'start' | 'end'
  className?: string
}) {
  return (
    <T.Portal>
      <T.Content
        side={side}
        align={align}
        sideOffset={6}
        className={cn(
          'z-50 max-w-[240px] rounded-lg border border-border/90 bg-popover px-2.5 py-1.5',
          'text-[11px] leading-snug text-popover-foreground shadow-lg',
          'animate-in fade-in-0 zoom-in-95 duration-150',
          className,
        )}
      >
        {children}
      </T.Content>
    </T.Portal>
  )
}

// Convenience wrapper: <Tooltip.Root><Tooltip.Trigger/><Tooltip.Content/></Tooltip.Root>
export const Tooltip = {
  Root: TooltipRoot,
  Trigger: TooltipTrigger,
  Content: TooltipContent,
}

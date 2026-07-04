import * as React from 'react'
import * as TooltipPrimitive from 'radix-ui/Tooltip'
import { cn } from '@/lib/utils'

const TooltipProvider = TooltipPrimitive.Provider
const TooltipRoot = TooltipPrimitive.Root
const TooltipTrigger = TooltipPrimitive.Trigger

export function Tooltip({
  children,
  side = 'top',
  delayDuration = 150,
}: {
  children: React.ReactNode
  side?: 'top' | 'bottom' | 'left' | 'right'
  delayDuration?: number
}) {
  return (
    <TooltipProvider delayDuration={delayDuration}>
      <TooltipRoot>
        {children}
      </TooltipRoot>
    </TooltipProvider>
  )
}

export const TooltipTriggerBase = ({
  asChild = false,
  children,
}: {
  asChild?: boolean
  children: React.ReactNode
}) => (
  <TooltipPrimitive.Trigger asChild={asChild}>
    {children}
  </TooltipPrimitive.Trigger>
)

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
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
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
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  )
}

// Simple wrapper that matches previous usage where Tooltip wraps Trigger + Content.
// For PersonaForgePanel-style usage, we'll wire with the primitives directly where needed.

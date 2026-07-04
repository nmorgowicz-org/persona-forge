import * as React from 'react'
import * as Radix from 'radix-ui'
import { cn } from '@/lib/utils'

const T = Radix.Tooltip

export function TooltipProvider({
  delayDuration = 150,
  skipDelayDuration = 0,
  children,
}: {
  delayDuration?: number
  skipDelayDuration?: number
  children: React.ReactNode
}) {
  return (
    <T.Provider delayDuration={delayDuration} skipDelayDuration={skipDelayDuration}>
      {children}
    </T.Provider>
  )
}

export function Root({ children }: { children: React.ReactNode }) {
  return <T.Root>{children}</T.Root>
}

export function Trigger({
  children,
  asChild,
  className,
  ...props
}: React.ComponentProps<typeof T.Trigger> & { className?: string }) {
  return (
    <T.Trigger asChild={asChild} className={cn('relative inline-flex', className)} {...props}>
      {children}
    </T.Trigger>
  )
}

export function Content({
  children,
  side = 'top',
  align = 'center',
  hidden,
  className,
}: {
  children: React.ReactNode
  side?: 'top' | 'bottom' | 'left' | 'right'
  align?: 'center' | 'start' | 'end'
  hidden?: boolean
  className?: string
}) {
  if (hidden) return null

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

// Backwards-compatible names
export const Tooltip = Root
export const TooltipTrigger = Trigger
export const TooltipContent = Content

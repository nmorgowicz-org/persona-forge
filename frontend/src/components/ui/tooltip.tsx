import * as React from 'react'
import * as Radix from 'radix-ui'
import { cn } from '@/lib/utils'

const T = Radix.Tooltip

export function Tooltip({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <T.Provider delayDuration={150}>
      <T.Root defaultOpen={false}>
        {children}
      </T.Root>
    </T.Provider>
  )
}

export function TooltipTrigger({
  children,
  asChild,
  ...props
}: {
  children: React.ReactNode
  asChild?: boolean
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <T.Trigger asChild={asChild} {...props}>
      {children}
    </T.Trigger>
  )
}

export function TooltipContent({
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

import { createContext, useContext, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Slot } from 'radix-ui'
import { cn } from '@/lib/utils'

type Side = 'top' | 'bottom' | 'left' | 'right'

interface TooltipContextValue {
  open: boolean
  setOpen: (v: boolean) => void
  side: Side
}

const TooltipContext = createContext<TooltipContextValue | null>(null)

function useTooltipContext() {
  const ctx = useContext(TooltipContext)
  if (!ctx) throw new Error('TooltipContent/TooltipTrigger must be inside Tooltip')
  return ctx
}

export function Tooltip({
  children,
  side = 'top',
}: {
  children: React.ReactNode
  side?: Side
}) {
  const [open, setOpen] = useState(false)

  const value = useMemo(
    () => ({ open, setOpen, side }),
    [open, side],
  )

  return (
    <TooltipContext.Provider value={value}>
      {children}
    </TooltipContext.Provider>
  )
}

export function TooltipTrigger({
  children,
  asChild,
  className,
  ...props
}: {
  children: React.ReactNode
  asChild?: boolean
  className?: string
}) {
  const { setOpen } = useTooltipContext()

  const hoverProps = {
    onMouseEnter: () => setOpen(true),
    onMouseLeave: () => setOpen(false),
  }

  if (asChild) {
    return (
      <Slot.Root
        {...props}
        {...hoverProps}
        className={cn('relative inline-flex', className)}
      >
        {children}
      </Slot.Root>
    )
  }

  return (
    <span
      className={cn('relative inline-flex', className)}
      {...hoverProps}
      {...props}
    >
      {children}
    </span>
  )
}

export function TooltipContent({
  children,
  side,
  align,
  hidden,
  className,
}: {
  children: React.ReactNode
  side?: Side
  align?: string
  hidden?: boolean
  className?: string
}) {
  if (hidden) return null
  const ctx = useTooltipContext()
  const resolvedSide = side ?? ctx.side

  const posClass = useMemo(() => {
    switch (resolvedSide) {
      case 'top':
        return 'bottom-full left-1/2 mb-1.5 -translate-x-1/2'
      case 'bottom':
        return 'top-full left-1/2 mt-1.5 -translate-x-1/2'
      case 'left':
        return 'right-full top-1/2 mr-1.5 -translate-y-1/2'
      case 'right':
        return 'left-full top-1/2 ml-1.5 -translate-y-1/2'
    }
  }, [resolvedSide])

  return (
    <AnimatePresence>
      {ctx.open && (
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.97 }}
          transition={{ duration: 0.12, ease: 'easeOut' }}
          className={cn(
            'absolute z-50 whitespace-nowrap rounded-lg border border-border/80 bg-popover px-2 py-1 text-[10px] leading-tight text-popover-foreground shadow-lg',
            posClass,
            align === 'start' && 'left-0 -translate-x-0',
            align === 'end' && 'right-0',
            className,
          )}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export const TooltipProvider = ({ children }: { children: React.ReactNode }) => children

import { Progress as ProgressPrimitive } from 'radix-ui'
import { cn } from '@/lib/utils'

interface ProgressProps {
  /** 0-100, or null when the backend has not measured anything yet (indeterminate). */
  value: number | null
  /** Accessible name. A progressbar with no name announces only a number. */
  label: string
  testId?: string
  className?: string
}

/**
 * B-P9: the one progress primitive, on radix's `Progress` so the `progressbar` role,
 * `aria-valuenow/min/max` and the indeterminate case are the library's problem, not each
 * caller's. Rendered as a bar; callers put their own readout (percentage, ETA) beside it.
 */
export function Progress({ value, label, testId, className }: ProgressProps) {
  return (
    <ProgressPrimitive.Root
      value={value}
      max={100}
      aria-label={label}
      data-testid={testId}
      className={cn('relative h-2 w-full overflow-hidden rounded-full bg-muted', className)}
    >
      <ProgressPrimitive.Indicator
        className="h-full w-full flex-1 bg-primary transition-transform"
        style={{ transform: `translateX(-${100 - (value ?? 0)}%)` }}
      />
    </ProgressPrimitive.Root>
  )
}

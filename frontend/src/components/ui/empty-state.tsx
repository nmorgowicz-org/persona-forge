import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/**
 * B-P9: the empty/instrument motif -- the same geometry as the startup field, drawn as a
 * quiet line: a waveform converging onto a seam, the seam, and the signal leaving it as an
 * open arc. It is a line illustration, never artwork behind controls.
 */
export function EmptyStateMotif({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 240 64"
      aria-hidden="true"
      focusable="false"
      className={cn('h-16 w-60 shrink-0', className)}
    >
      <g fill="none" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round">
        {/* the waveform converging onto the seam */}
        <path d="M4 32 C14 18 22 46 32 32 C42 18 50 46 60 32 C70 22 76 42 86 32 C94 25 99 39 107 32 L118 32" opacity="0.55" />
        {/* the seam */}
        <path d="M121 13 L121 51" opacity="0.35" />
        {/* the signal leaving it */}
        <path d="M136 21 C146 26 146 38 136 43" opacity="0.7" />
        <path d="M150 13 C166 23 166 41 150 51" opacity="0.45" />
        <path d="M172 32 C182 21 191 43 201 32 C209 23 215 40 223 32 L237 32" opacity="0.55" />
      </g>
    </svg>
  )
}

interface EmptyStateProps {
  title: string
  description?: string
  /** Exactly one next action: an empty surface must never be a dead end. */
  actionLabel: string
  onAction: () => void
  /** Extra content below the action (e.g. a secondary affordance a surface already had). */
  children?: ReactNode
  testId?: string
  className?: string
}

export function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
  children,
  testId = 'empty-state',
  className,
}: EmptyStateProps) {
  return (
    <div
      data-testid={testId}
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-panel border border-dashed border-border px-6 py-10 text-center',
        className,
      )}
    >
      <EmptyStateMotif className="text-primary/40" />
      <div className="flex flex-col gap-1">
        <p className="text-sm font-medium text-foreground">{title}</p>
        {description && <p className="max-w-md text-xs text-muted-foreground">{description}</p>}
      </div>
      <Button size="sm" variant="secondary" data-testid="empty-state-action" onClick={onAction}>
        {actionLabel}
      </Button>
      {children}
    </div>
  )
}

// The page header (B-P6). Every page opens with the same band: a `.display` title, an optional
// context line, and a right-aligned slot for the page's primary action.
//
// The content is exactly what each page already had -- this is one *form*, not new
// information. Before it, every page hand-rolled an <h1> at its own size (text-2xl on four
// pages, text-lg on another) with its own spacing, which is the kind of drift that makes an app
// feel assembled rather than designed.
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export interface PageHeaderProps {
  title: string
  description?: string
  /** Context readouts (counts, states) shown as `.micro-label` chips beside the title. */
  context?: ReactNode
  /** The page's primary action, aligned right. */
  actions?: ReactNode
  className?: string
}

export function PageHeader({ title, description, context, actions, className }: PageHeaderProps) {
  return (
    <header
      data-testid="page-header"
      className={cn('flex flex-wrap items-start justify-between gap-x-6 gap-y-3', className)}
    >
      <div className="min-w-0">
        <h1 data-testid="page-title" className="display">
          {title}
        </h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {(context || actions) && (
        <div className="flex shrink-0 flex-wrap items-center gap-3">
          {context}
          {actions}
        </div>
      )}
    </header>
  )
}

import * as React from 'react'
import { createPortal } from 'react-dom'
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

/**
 * Drop-in replacement for a native `title=` on an icon button: wraps the child in the shared
 * Radix tooltip so every hover hint across the app looks and times identically to the nav icons
 * (the app-wide TooltipProvider in App.tsx sets the 150ms delay). Keep an `aria-label` on the
 * child for screen readers — this only handles the visual hint.
 */
export function IconTooltip({
  label,
  children,
  side = 'top',
  align = 'center',
}: {
  label: string
  children: React.ReactNode
  side?: 'top' | 'bottom' | 'left' | 'right'
  align?: 'center' | 'start' | 'end'
}) {
  return (
    <Root>
      <Trigger asChild>{children}</Trigger>
      <Content side={side} align={align}>
        {label}
      </Content>
    </Root>
  )
}

/** Converts legacy/native title attributes into the same fast styled tooltip presentation. */
export function TitleTooltipBridge() {
  const [tip, setTip] = React.useState<{ label: string; x: number; y: number } | null>(null)
  const timer = React.useRef<number | null>(null)

  React.useEffect(() => {
    const convert = (root: ParentNode) => {
      const elements = root instanceof Element && root.hasAttribute('title') ? [root] : []
      elements.push(...Array.from(root.querySelectorAll?.('[title]') ?? []))
      for (const element of elements) {
        const title = element.getAttribute('title')
        if (!title) continue
        element.setAttribute('data-app-tooltip', title)
        element.removeAttribute('title')
      }
    }
    convert(document)
    const observer = new MutationObserver((records) => records.forEach((record) => {
      if (record.type === 'attributes') convert(record.target as Element)
      record.addedNodes.forEach((node) => { if (node instanceof Element) convert(node) })
    }))
    observer.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['title'] })

    const show = (target: Element) => {
      const label = target.getAttribute('data-app-tooltip')
      if (!label) return
      const rect = target.getBoundingClientRect()
      if (timer.current) window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => setTip({ label, x: rect.left + rect.width / 2, y: rect.top - 8 }), 150)
    }
    const enter = (event: Event) => { const target = (event.target as Element | null)?.closest?.('[data-app-tooltip]'); if (target) show(target) }
    const leave = () => { if (timer.current) window.clearTimeout(timer.current); timer.current = null; setTip(null) }
    document.addEventListener('mouseover', enter)
    document.addEventListener('focusin', enter)
    document.addEventListener('mouseout', leave)
    document.addEventListener('focusout', leave)
    return () => { observer.disconnect(); leave(); document.removeEventListener('mouseover', enter); document.removeEventListener('focusin', enter); document.removeEventListener('mouseout', leave); document.removeEventListener('focusout', leave) }
  }, [])

  return tip ? createPortal(
    <div className="pointer-events-none fixed z-[100] max-w-[240px] -translate-x-1/2 -translate-y-full rounded-lg border border-border/90 bg-popover px-2.5 py-1.5 text-[11px] leading-snug text-popover-foreground shadow-lg animate-in fade-in-0 zoom-in-95 duration-150" style={{ left: tip.x, top: tip.y }} role="tooltip">
      {tip.label}
    </div>, document.body,
  ) : null
}

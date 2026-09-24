// Right-click menu primitive. There was none in components/ui, so this wraps the
// **already-installed** unified `radix-ui` package's ContextMenu (same pattern as
// tooltip.tsx) -- zero dependency changes. Radix gives us the hard parts for free:
// portal positioning that survives scroll/zoom, roving focus, typeahead, Escape, and
// the keyboard triggers (Shift+F10 and the dedicated context-menu key), which is what
// makes every menu in the app reachable without a pointer.
import * as React from 'react'
import * as Radix from 'radix-ui'
import { cn } from '@/lib/utils'

const M = Radix.ContextMenu

export function Root({ children }: { children: React.ReactNode }) {
  return <M.Root>{children}</M.Root>
}

/** Opens the menu anchored at an element's own box, by dispatching the same `contextmenu`
 * event the pointer path produces -- Radix positions the content from that event's client
 * coordinates, so a keyboard open lands in the same place a right-click would. */
function openAtElement(element: HTMLElement) {
  const rect = element.getBoundingClientRect()
  element.dispatchEvent(
    new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      clientX: rect.left + Math.min(24, rect.width / 2),
      clientY: rect.top + Math.min(24, rect.height / 2),
    }),
  )
}

/** `asChild` renders the child itself -- no extra DOM node, so wrapping a draggable or
 * pointer-driven surface cannot change its layout or its gesture handling. Radix composes
 * (not replaces) the child's own handlers, so a right-click that opens the menu still lets
 * the element see the event.
 *
 * Radix's own trigger listens for `contextmenu` only and leans on the browser to synthesize
 * that event from Shift+F10 / the context-menu key -- which macOS Chromium never does, so
 * keyboard parity would silently be a platform feature rather than ours. The trigger handles
 * those two keys explicitly and reuses the pointer path. */
export function Trigger({
  children,
  asChild,
  className,
  onKeyDown,
  ...props
}: React.ComponentProps<typeof M.Trigger> & { className?: string }) {
  const handleKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    onKeyDown?.(event)
    if (event.defaultPrevented) return
    if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
      event.preventDefault()
      openAtElement(event.currentTarget)
    }
  }
  return (
    <M.Trigger asChild={asChild} className={className} onKeyDown={handleKeyDown} {...props}>
      {children}
    </M.Trigger>
  )
}

export function Content({
  children,
  className,
  ...props
}: React.ComponentProps<typeof M.Content> & { className?: string }) {
  return (
    <M.Portal>
      <M.Content
        className={cn(
          'z-50 min-w-[196px] rounded-control border border-border/90 bg-popover p-1',
          'text-[11px] leading-snug text-popover-foreground shadow-lg',
          'animate-in fade-in-0 zoom-in-95 duration-100',
          className,
        )}
        {...props}
      >
        {children}
      </M.Content>
    </M.Portal>
  )
}

export function Item({
  children,
  className,
  danger,
  ...props
}: React.ComponentProps<typeof M.Item> & { className?: string; danger?: boolean }) {
  return (
    <M.Item
      className={cn(
        'flex cursor-default select-none items-center gap-2 rounded px-2 py-1 outline-none',
        'data-[highlighted]:bg-muted data-[disabled]:pointer-events-none data-[disabled]:opacity-40',
        danger && 'text-destructive',
        className,
      )}
      {...props}
    >
      {children}
    </M.Item>
  )
}

/** Right-aligned hint inside an Item (a shortcut or a value the action would apply). */
export function Hint({ children }: { children: React.ReactNode }) {
  return <span className="ml-auto shrink-0 font-mono text-[10px] text-muted-foreground/70">{children}</span>
}

export function Label({ children }: { children: React.ReactNode }) {
  return <M.Label className="px-2 py-1 text-[10px] uppercase tracking-wide text-muted-foreground/70">{children}</M.Label>
}

export function Separator() {
  return <M.Separator className="my-1 h-px bg-border/70" />
}

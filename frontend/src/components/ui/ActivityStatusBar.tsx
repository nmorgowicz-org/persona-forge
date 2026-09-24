import * as React from 'react'
import { Info, Loader2, StopCircle, Timer } from 'lucide-react'
import { useAppStore } from '@/store'
import { useSidebar } from '@/components/ui/sidebar-context'
import { cn } from '@/lib/utils'

// The info view (CP0 decision D6). Any control can carry a `data-help` string; hovering or
// focusing it puts that string in this strip, the way a plugin's help line works. It is also
// where genuine product knowledge lives now, instead of paragraphs in the panel that the user
// reads before they have made any choice.
let helpText: string | null = null
const helpListeners = new Set<() => void>()

export function setHelpText(next: string | null): void {
  if (helpText === next) return
  helpText = next
  for (const listener of helpListeners) listener()
}

function subscribeHelp(listener: () => void): () => void {
  helpListeners.add(listener)
  return () => {
    helpListeners.delete(listener)
  }
}

function useHelpText(): string | null {
  return React.useSyncExternalStore(
    subscribeHelp,
    () => helpText,
    () => null,
  )
}

function formatEta(s: number) {
  const total = Math.round(s)
  if (total <= 0 || !isFinite(total)) return ''
  const m = Math.floor(total / 60)
  const sec = total % 60
  if (m <= 0) return `~${sec}s`
  return `~${m}m ${sec < 10 ? '0' + sec : sec}s`
}

function adaptiveMessage(active: boolean, progress: number, eta: number | null) {
  if (!active) return ''
  if (progress >= 0.85) return 'Almost there… finalizing audio.'
  if (progress >= 0.5) return 'Comparing candidates… this won’t interrupt you.'
  if (eta && eta <= 30) return 'Generating speech… nearly done.'
  return 'Generating speech in the background.'
}

export function ActivityStatusBar() {
  const status = useAppStore((s) => s.activityStatus)
  const { open: sidebarOpen } = useSidebar()
  const [hovered, setHovered] = React.useState(false)
  const [countdown, setCountdown] = React.useState<number | null>(
    status?.etaSeconds != null ? Math.round(status.etaSeconds) : null
  )

  const active = !!status

  React.useEffect(() => {
    if (!active || status?.etaSeconds == null) {
      setCountdown(null)
      return
    }
    setCountdown(Math.round(status.etaSeconds))
  }, [active, status?.etaSeconds])

  React.useEffect(() => {
    if (!active || countdown == null || countdown <= 0) return
    const id = setInterval(() => {
      setCountdown((prev) => {
        if (prev == null || prev <= 1) {
          clearInterval(id)
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(id)
  }, [active, countdown])

  const help = useHelpText()

  // The strip exists to say something: activity, or an explanation of whatever the pointer is
  // on. With neither, it stays out of the way rather than holding a permanent empty bar.
  const activity = active && status ? status : null
  if (!help && !activity) return null

  const title = activity?.title
  const message = activity
    ? activity.message || adaptiveMessage(true, activity.progress, countdown)
    : ''
  const detail = activity?.detail
  const onCancel = activity?.onCancel
  const progress =
    typeof activity?.progress === 'number' && activity.progress >= 0
      ? Math.min(1, activity.progress)
      : 0
  const etaDisplay =
    countdown != null && countdown >= 5 && countdown <= 1800
      ? formatEta(countdown)
      : null

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-50"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div
        className={cn(
          'w-full border-t border-border/70 bg-surface-1/95 backdrop-blur-xl transition-[margin,width] duration-200 ease-linear',
          sidebarOpen
            ? 'md:ml-64 md:w-[calc(100%-16rem)]'
            : 'md:ml-12 md:w-[calc(100%-3rem)]',
        )}
      >
        {/* Gradient progress bar */}
        <div className="h-[2px] bg-neutral-900/80 overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-primary via-primary/90 to-primary/60"
            style={{
              width: `${Math.max(5, Math.min(100, progress * 100))}%`,
              transition: 'width 0.7s ease-out',
              animation: 'pulse-subtle 2.4s ease-in-out infinite',
            }}
          />
        </div>

        <div className="relative">
          {/* Primary row */}
          {activity && (
          <div className="flex items-center gap-2.5 px-4 py-1.5 text-[10px] text-muted-foreground">
            <Loader2 className="size-3 shrink-0 animate-spin text-primary" />

            <span className="font-medium text-foreground">
              {title}
            </span>

            {etaDisplay && (
              <span className="flex shrink-0 items-center gap-1 rounded-full bg-primary/15 px-2 py-0.5 text-[11px] font-semibold text-primary tabular-nums">
                <Timer className="size-3" />
                {etaDisplay}
              </span>
            )}

            {message && (
              <span className="truncate">
                {message}
              </span>
            )}

            {detail && (
              <span className={cn(!onCancel && 'ml-auto', 'shrink-0')}>
                {detail}
              </span>
            )}

            {onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="ml-auto flex shrink-0 items-center gap-1 rounded-full border border-destructive/40 bg-destructive/10 px-2 py-0.5 text-[11px] font-semibold text-destructive transition-colors hover:bg-destructive/20"
              >
                <StopCircle className="size-3" />
                Stop
              </button>
            )}
          </div>
          )}

          {/* Info view (D6): whatever control the pointer or focus is on, explained in place. */}
          {help && (
            <div
              data-testid="info-strip"
              role="status"
              aria-live="polite"
              className="flex items-center gap-2 px-4 py-1.5 text-[11px] text-muted-foreground"
            >
              <Info className="size-3 shrink-0 text-primary" />
              <span className="truncate">{help}</span>
            </div>
          )}

          {/* Secondary row: appears on hover if there's extra detail */}
          {hovered && (
            <div className="absolute inset-x-0 -bottom-5 flex items-center gap-2 px-4 text-[9px] text-muted-foreground">
              <span>You can keep working; changes appear as they complete.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

import * as React from 'react'
import { Loader2 } from 'lucide-react'
import { useAppStore } from '@/store'

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

  if (!active || !status) return null

  const title = status.title
  const message =
    status.message || adaptiveMessage(true, status.progress, countdown)
  const detail = status.detail
  const progress =
    typeof status.progress === 'number' && status.progress >= 0
      ? Math.min(1, status.progress)
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
      <div className="ml-14 w-full border-t border-border/70 bg-[#0B0B0F]/96 backdrop-blur-xl">
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
          <div className="flex items-center gap-2 px-4 py-1.5 text-[10px] text-muted-foreground">
            <Loader2 className="size-3 shrink-0 animate-spin text-primary" />

            <span className="font-medium text-foreground">
              {title}
            </span>

            {message && (
              <span className="truncate">
                {message}
              </span>
            )}

            {detail && (
              <span className="shrink-0">
                {detail}
              </span>
            )}

            {etaDisplay && (
              <span className="ml-auto shrink-0 text-foreground">
                {etaDisplay} remaining
              </span>
            )}
          </div>

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

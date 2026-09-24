import { useEffect, useState } from 'react'
import { useAppStore } from '@/store'
import markUrl from '@/assets/mark.svg'
import startupFieldUrl from '@/assets/startup-field.png'

/** The cold boot's steps. A model load reports no percentage we can trust before the service
 * answers at all, so the readout is stepped by elapsed time rather than invented. */
const STEPS = [
  { at: 0, label: 'Starting the service' },
  { at: 8, label: 'Loading the model' },
  { at: 25, label: 'Warming up the first voices' },
] as const

/**
 * B-P9: the initial-load window. While the backend is still answering 503 on /health the app
 * knows nothing at all, so it shows this instead of the work surfaces -- the Signal Crucible
 * mark at 72px over the startup field, dimmed, with a stepped load readout.
 *
 * Replaces the content rather than overlaying it: a splash that leaves the controls mounted
 * behind it is a splash a keyboard can still reach.
 */
export function StartupState() {
  const loadingMessage = useAppStore((s) => s.loadingMessage)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => window.clearInterval(timer)
  }, [])

  let step = 0
  for (let i = 0; i < STEPS.length; i++) {
    if (elapsed >= STEPS[i].at) step = i
  }
  const label = loadingMessage || STEPS[step].label

  return (
    <div
      data-testid="startup-state"
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-8 overflow-hidden bg-background"
    >
      {/* The field, dimmed. It is a backdrop, not a control surface: nothing sits on top of
          it except the mark and the readout. */}
      <img
        src={startupFieldUrl}
        alt=""
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 size-full object-cover opacity-[0.22]"
      />

      <div className="relative flex flex-col items-center gap-6">
        <img src={markUrl} alt="" width={72} height={72} className="size-[72px]" />

        <div className="flex flex-col items-center gap-2">
          <p className="text-sm font-medium text-foreground">{label}</p>
          <p className="text-[11px] tabular-nums text-muted-foreground">
            {elapsed}s elapsed
          </p>
        </div>

        {/* Stepped readout: which step of the boot we are in, and how many there are. */}
        <div
          role="progressbar"
          aria-label="Startup progress"
          aria-valuemin={1}
          aria-valuemax={STEPS.length}
          aria-valuenow={step + 1}
          aria-valuetext={label}
          data-testid="startup-steps"
          className="flex items-center gap-1.5"
        >
          {STEPS.map((entry, index) => (
            <span
              key={entry.label}
              className={
                index <= step
                  ? 'h-1 w-8 rounded-full bg-primary transition-colors'
                  : 'h-1 w-8 rounded-full bg-muted transition-colors'
              }
            />
          ))}
        </div>
      </div>
    </div>
  )
}

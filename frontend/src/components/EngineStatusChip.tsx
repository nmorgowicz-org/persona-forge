import { Loader2 } from 'lucide-react'
import {
  chooseChipEngine,
  deriveChipState,
  ENGINE_CHIP_WORD,
  useEngineLoadStatus,
} from '@/lib/engineStatus'
import { useAppStore } from '@/store'
import { IconTooltip } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

// A load an API request started outside this tab must still reach the chip. The hook already
// re-reads every 2 s while a load is in flight; this is the slow steady-state re-read.
const IDLE_POLL_MS = 10_000

const CHIP_HELP = 'The engine serving speech right now, with its state and device. Click to manage engines.'

/** The shell header's engine status chip (plan §5.1): name, state, device — on every page. */
export function EngineStatusChip() {
  const setPage = useAppStore((s) => s.setPage)
  const loadingMessage = useAppStore((s) => s.loadingMessage)
  const healthStatus = useAppStore((s) => s.healthStatus)
  const healthError = useAppStore((s) => s.healthError)
  const healthDevice = useAppStore((s) => s.healthDevice)
  const { cards } = useEngineLoadStatus({ idleIntervalMs: IDLE_POLL_MS })

  const card = chooseChipEngine(cards)
  // No engine information, no chip: a wrong state is worse than no state.
  if (!card) return null

  const { state, reason } = deriveChipState(card, { loadingMessage, healthStatus, healthError })
  // A pack engine reports the device its worker measured at install time; the active
  // backend's device comes from /health. Either may be missing — the chip then omits it.
  const device = card.install_check?.device || healthDevice || null

  const serving =
    card.api_default
      ? `${card.label} serves the API default.`
      : `${card.label} is the active engine.`
  const statusLine =
    reason ??
    (state === 'ready' ? `Ready${device ? ` on ${device}` : ''}.` : `${ENGINE_CHIP_WORD[state]}.`)

  return (
    <>
      <IconTooltip label={`${serving} ${statusLine}`}>
        <button
          type="button"
          data-testid="engine-status-chip"
          data-chip-state={state}
          data-help={CHIP_HELP}
          onClick={() => setPage('runtime')}
          aria-label={`Engine status: ${card.label}. ${serving} Open Runtime.`}
          className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-border bg-background px-2 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          {state === 'loading' ? (
            <Loader2 aria-hidden="true" className="size-3.5 shrink-0 animate-spin text-primary" />
          ) : (
            <span
              aria-hidden="true"
              className={cn(
                'size-2 shrink-0 rounded-full',
                state === 'ready' && 'bg-success',
                state === 'warming' && 'animate-pulse bg-warning',
                state === 'error' && 'bg-destructive',
              )}
            />
          )}
          <span
            data-testid="engine-status-label"
            className="min-w-0 max-w-24 truncate min-[420px]:max-w-40 sm:max-w-52"
          >
            {card.label}
          </span>
          <span
            data-testid="engine-status-state"
            className={cn(
              'shrink-0 font-medium',
              state === 'ready' && 'text-success',
              state === 'warming' && 'text-warning',
              state === 'loading' && 'text-primary',
              state === 'error' && 'text-destructive',
            )}
          >
            {ENGINE_CHIP_WORD[state]}
          </span>
          {device && (
            <span data-testid="engine-status-device" className="hidden shrink-0 md:inline">
              {device}
            </span>
          )}
        </button>
      </IconTooltip>
      {/* State changes are announced politely here; the button's accessible name stays stable
          (engine and role only), so a transition never re-reads the whole control. */}
      <span data-testid="engine-status-live" aria-live="polite" className="sr-only">
        {`${card.label}: ${ENGINE_CHIP_WORD[state]}`}
      </span>
    </>
  )
}

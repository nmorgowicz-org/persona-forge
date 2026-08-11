import { FlaskConical } from 'lucide-react'
import * as Tooltip from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

// Surfaces the ASR (Whisper) transcript + match-score confidence the backend computed for a
// take, plus its flag status. The match score renders inline (not just on hover) so a low-
// confidence take is visible at a glance, not just buried in a tooltip.
export function TakeDebugButton({
  lines,
  matchScore,
}: {
  lines: string[]
  matchScore?: number | null
}) {
  const scoreColor =
    matchScore == null
      ? 'text-muted-foreground'
      : matchScore >= 0.9
        ? 'text-success'
        : matchScore >= 0.7
          ? 'text-warning'
          : 'text-destructive'
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <button
          type="button"
          className={cn(
            'ml-auto flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[9px] transition-colors hover:bg-muted/60',
            scoreColor,
          )}
        >
          <FlaskConical className="size-2.5" />
          {matchScore != null && <span className="font-mono">{matchScore.toFixed(2)}</span>}
        </button>
      </Tooltip.Trigger>
      <Tooltip.Content side="top" align="end">
        <div className="flex flex-col gap-0.5 text-[9px]">
          {lines.map((l, i) => (
            <div key={i}>{l}</div>
          ))}
        </div>
      </Tooltip.Content>
    </Tooltip.Root>
  )
}

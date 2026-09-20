// Visual duration rail for one segment-browser row. List metadata never includes audio (payload
// size), so an unauditioned row shows a truthful neutral rail -- never a fake waveform -- and
// only gets real peaks with a moving playhead once the row has actually been auditioned.
import { cn } from '@/lib/utils'

const NEUTRAL_BAR_COUNT = 24

export function SegmentPreviewRail({
  peaks,
  progress,
  isPlaying,
}: {
  peaks: number[] | null
  progress: number
  isPlaying: boolean
}) {
  if (!peaks || peaks.length === 0) {
    return (
      <div className="flex h-5 flex-1 items-center gap-px" aria-hidden="true">
        {Array.from({ length: NEUTRAL_BAR_COUNT }).map((_, i) => (
          <div key={i} className="h-1.5 flex-1 rounded-sm bg-muted-foreground/20" />
        ))}
      </div>
    )
  }
  return (
    <div className="flex h-5 flex-1 items-center gap-px" aria-hidden="true">
      {peaks.map((p, i) => (
        <div
          key={i}
          className={cn(
            'flex-1 rounded-sm transition-colors',
            isPlaying && i / peaks.length <= progress ? 'bg-cyan-400' : 'bg-cyan-500/30',
          )}
          style={{ height: `${Math.max(15, p * 100)}%` }}
        />
      ))}
    </div>
  )
}

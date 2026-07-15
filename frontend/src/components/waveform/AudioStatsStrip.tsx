import { memo } from 'react'
import { cn } from '@/lib/utils'
import { InfoIcon } from '@/components/InfoIcon'

interface AudioStatsStripProps {
  metrics: {
    duration_seconds?: number
    speech_rate_proxy?: number
    lufs_integrated?: number | null
    peak_dbfs?: number
    pause_ratio?: number
    pause_count?: number
  } | null
  diff?: {
    duration_diff: number
    speech_rate_diff: number
    lufs_diff: number
    pause_ratio_diff?: number
  } | null
  className?: string
}

function formatValue(value: number | null | undefined, unit = '') {
  if (value === undefined || value === null || Number.isNaN(value)) return '--'
  return `${value.toFixed(2)}${unit}`
}

function formatDiff(value: number, unit = '') {
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}${unit}`
}

export const AudioStatsStrip = memo(function AudioStatsStrip({
  metrics,
  diff,
  className,
}: AudioStatsStripProps) {
  if (!metrics) {
    return (
      <div className={cn('flex h-8 items-center justify-center px-2 text-[10px] text-muted-foreground/40', className)}>
        no metrics available
      </div>
    )
  }

  return (
    <div
      className={cn(
        'flex h-8 items-center gap-4 border-y border-border bg-background/50 px-3 text-[11px] font-mono text-muted-foreground/80',
        className,
      )}
    >
      <div className="flex items-center gap-1">
        <span className="opacity-50">DUR:</span>
        <span className="text-foreground/90">{formatValue(metrics.duration_seconds, 's')}</span>
        {diff && <div>{formatDiff(diff.duration_diff, 's')}</div>}
      </div>
      <div className="flex items-center gap-1">
        <div className="flex items-center gap-1 opacity-50">
          WPS
          <InfoIcon text="Words Per Second: Average speed of speech. Higher values indicate faster speaking." />
        </div>
        <span>{formatValue(metrics.speech_rate_proxy)}</span>
        {diff && <div>{formatDiff(diff.speech_rate_diff)}</div>}
      </div>
      <div className="flex items-center gap-1">
        <div className="flex items-center gap-1 opacity-50">
          LUFS
          <InfoIcon text="Loudness Units relative to Full Scale: A measure of perceived loudness. -23 LUFS is a common broadcast standard." />
        </div>
        <span>{formatValue(metrics.lufs_integrated, 'dB')}</span>
        {diff && <div>{formatDiff(diff.lufs_diff, 'dB')}</div>}
      </div>
      <div className="flex items-center gap-1">
        <div className="flex items-center gap-1 opacity-50">
          PEAK
          <InfoIcon text="Peak Amplitude: The maximum volume level in the clip. 0 dBFS is the digital maximum." />
        </div>
        <span>{formatValue(metrics.peak_dbfs, 'dB')}</span>
      </div>
      <div className="flex items-center gap-1">
        <div className="flex items-center gap-1 opacity-50">
          PAUSE
          <InfoIcon text="Pause Ratio: Percentage of the audio that consists of silence or low-energy gaps." />
        </div>
        <span>{formatValue((metrics.pause_ratio ?? 0) * 100, '%')}</span>
        <span className="ml-1 opacity-50">({metrics.pause_count ?? 0})</span>
        {diff && diff.pause_ratio_diff !== undefined && (
          <div>{formatDiff(diff.pause_ratio_diff * 100, '%')}</div>
        )}
      </div>
    </div>
  )
})

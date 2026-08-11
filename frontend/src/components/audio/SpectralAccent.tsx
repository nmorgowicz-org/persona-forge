import { memo } from 'react'
import { cn } from '@/lib/utils'

interface SpectralAccentProps {
  peaks?: number[] | null
  className?: string
}

export const SpectralAccent = memo(function SpectralAccent({ peaks, className }: SpectralAccentProps) {
  const source = peaks && peaks.length > 0 ? peaks : Array.from({ length: 48 }, (_, i) => 0.25 + 0.18 * Math.sin(i / 4))
  const cells = source.slice(0, 72)

  return (
    <div
      className={cn('grid h-8 grid-flow-col auto-cols-fr gap-px overflow-hidden rounded bg-background/70 p-px ring-1 ring-border/70', className)}
      aria-hidden="true"
    >
      {cells.map((peak, index) => {
        const intensity = Math.max(0.08, Math.min(1, peak))
        return (
          <span
            key={index}
            className="rounded-[1px]"
            style={{
              opacity: 0.22 + intensity * 0.68,
              background: `linear-gradient(180deg, hsl(${188 + intensity * 130} 86% ${42 + intensity * 20}%), hsl(${38 + intensity * 26} 92% 54% / .28))`,
              transform: `scaleY(${0.35 + intensity * 0.65})`,
            }}
          />
        )
      })}
    </div>
  )
})

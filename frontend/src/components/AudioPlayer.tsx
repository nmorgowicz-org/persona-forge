import { AudioDeck } from './audio/AudioDeck'

interface AudioPlayerProps {
  src: string
  blob?: Blob | null
  className?: string
  autoPlay?: boolean
  seed?: number | null
  metrics?: Parameters<typeof AudioDeck>[0]['metrics']
  rtf?: number | null
  downloadName?: string
  layout?: 'inline' | 'stacked'
  showSpectralAccent?: boolean
  initialSpeed?: number
  onSpeedChange?: (speed: number) => void
}

export function AudioPlayer({
  src,
  blob,
  className,
  autoPlay = true,
  seed = null,
  metrics = null,
  rtf = null,
  downloadName,
  layout,
  showSpectralAccent,
  initialSpeed,
  onSpeedChange,
}: AudioPlayerProps) {
  return (
    <AudioDeck
      src={src}
      blob={blob}
      className={className}
      autoPlay={autoPlay}
      seed={seed}
      metrics={metrics}
      rtf={rtf}
      downloadName={downloadName}
      layout={layout}
      showSpectralAccent={showSpectralAccent}
      initialSpeed={initialSpeed}
      onSpeedChange={onSpeedChange}
    />
  )
}

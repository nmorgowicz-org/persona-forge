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
    />
  )
}

import { AudioDeck } from './audio/AudioDeck'

interface AudioPlayerProps {
  src: string
  blob?: Blob | null
  className?: string
  autoPlay?: boolean
}

export function AudioPlayer({ src, blob, className, autoPlay = true }: AudioPlayerProps) {
  return <AudioDeck src={src} blob={blob} className={className} autoPlay={autoPlay} />
}

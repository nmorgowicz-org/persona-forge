import { useEffect, useState } from 'react'
import { AudioPlayer } from '@/components/AudioPlayer'
import { base64ToBlob } from '@/lib/utils'

export function ClipPlayer({
  audioBase64,
  audioUrl,
  className,
  autoPlay = false,
}: {
  audioBase64?: string
  audioUrl?: string
  className?: string
  autoPlay?: boolean
}) {
  const [blob, setBlob] = useState<Blob | null>(null)
  const [src, setSrc] = useState<string | null>(null)

  useEffect(() => {
    if (audioBase64 && !audioUrl) {
      const b = base64ToBlob(audioBase64)
      setBlob(b)
      setSrc(`data:audio/wav;base64,${audioBase64}`)
      return
    }
    if (audioUrl) {
      let cancelled = false
      fetch(audioUrl)
        .then((r) => {
          if (!r.ok || cancelled) return
          return r.blob()
        })
        .then((b) => {
          if (b && !cancelled) {
            setBlob(b)
            setSrc(URL.createObjectURL(b))
          }
        })
        .catch(() => {
          if (!cancelled) setSrc(audioUrl)
        })
      return () => {
        cancelled = true
      }
    }
  }, [audioBase64, audioUrl])

  useEffect(() => {
    const url = src
    return () => {
      if (url && url.startsWith('blob:')) URL.revokeObjectURL(url)
    }
  }, [src])

  if (!src) return null

  return (
    <AudioPlayer
      src={src}
      blob={blob}
      autoPlay={autoPlay}
      className={className}
    />
  )
}

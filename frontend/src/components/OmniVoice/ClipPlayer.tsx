import { useEffect, useMemo, useState } from 'react'
import { AudioPlayer } from '@/components/AudioPlayer'
import { base64ToBlob } from '@/lib/utils'

export function ClipPlayer({
  audioBase64,
  audioUrl,
  className,
  autoPlay = false,
  layout,
  initialSpeed,
  onSpeedChange,
}: {
  audioBase64?: string
  audioUrl?: string
  className?: string
  autoPlay?: boolean
  layout?: 'inline' | 'stacked'
  initialSpeed?: number
  onSpeedChange?: (speed: number) => void
}) {
  const base64Blob = useMemo(
    () => (audioBase64 && !audioUrl ? base64ToBlob(audioBase64) : null),
    [audioBase64, audioUrl],
  )
  const base64Src = audioBase64 && !audioUrl
    ? `data:audio/wav;base64,${audioBase64}`
    : null
  const [fetched, setFetched] = useState<{
    audioUrl: string
    src: string
    blob: Blob | null
  } | null>(null)

  useEffect(() => {
    if (!audioUrl) return
    let cancelled = false
    let objectUrl: string | null = null
    fetch(audioUrl)
      .then((response) => {
        if (!response.ok) throw new Error('Failed to fetch audio')
        return response.blob()
      })
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setFetched({ audioUrl, src: objectUrl, blob })
      })
      .catch(() => {
        if (!cancelled) setFetched({ audioUrl, src: audioUrl, blob: null })
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [audioUrl])

  const hasFetchedAudio = fetched !== null && fetched.audioUrl === audioUrl
  const src = base64Src ?? (hasFetchedAudio ? fetched.src : null)
  const blob = base64Blob ?? (hasFetchedAudio ? fetched.blob : null)

  if (!src) return null

  return (
    <AudioPlayer
      src={src}
      blob={blob}
      autoPlay={autoPlay}
      className={className}
      layout={layout}
      initialSpeed={initialSpeed}
      onSpeedChange={onSpeedChange}
    />
  )
}

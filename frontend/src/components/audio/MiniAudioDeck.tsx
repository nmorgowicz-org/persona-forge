import { AudioDeck } from './AudioDeck'
import type { ComponentProps } from 'react'

type MiniAudioDeckProps = Omit<ComponentProps<typeof AudioDeck>, 'compact'>

export function MiniAudioDeck(props: MiniAudioDeckProps) {
  return <AudioDeck {...props} compact autoPlay={props.autoPlay ?? false} />
}

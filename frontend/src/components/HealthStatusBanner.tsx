import { useAppStore } from '@/store'
import { Loader2 } from 'lucide-react'

export function HealthStatusBanner() {
  const modelLoaded = useAppStore((s) => s.modelLoaded)
  const loadingMessage = useAppStore((s) => s.loadingMessage)
  const page = useAppStore((s) => s.page)
  const designEngine = useAppStore((s) => s.designEngine)

  if (modelLoaded) return null
  // model_loaded only tracks the Base/VoiceDesign slot — OmniVoice (Persona Forge) loads
  // independently and never touches it, so this banner would otherwise show "Initializing
  // TTS model" on Persona Forge even when nothing is loading there.
  const needsBase = page === 'speak' || (page === 'voice-design' && designEngine === 'qwen')
  if (!needsBase) return null

  return (
    <div className="flex items-center justify-between gap-2 border-b border-border bg-muted/30 px-4 py-1.5 text-xs text-muted-foreground">
      <div className="flex items-center gap-2">
        <Loader2 className="size-3 animate-spin text-muted-foreground" />
        <span>
          {loadingMessage || 'Initializing TTS model…'}
        </span>
      </div>
      <span className="shrink-0 opacity-70">
        Speak and Voice Design will be available shortly.
      </span>
    </div>
  )
}

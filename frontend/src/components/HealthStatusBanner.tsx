import { useAppStore } from '@/store'
import { AlertTriangle, Loader2 } from 'lucide-react'

export function HealthStatusBanner() {
  const serviceStarted = useAppStore((s) => s.serviceStarted)
  const loadingMessage = useAppStore((s) => s.loadingMessage)
  const page = useAppStore((s) => s.page)
  const designEngine = useAppStore((s) => s.designEngine)
  const refTextValidation = useAppStore((s) => s.refTextValidation)

  // service_started stays true forever after the first successful load — later idle-unload
  // cycles reload lazily/transparently on the next request, so there's nothing to "wait" for
  // and no banner should show. Only a true cold boot (never started) blocks anything.
  if (serviceStarted) {
    // REF_TEXT mismatch warning on Speak page
    if (
      page === 'speak' &&
      refTextValidation &&
      (refTextValidation.severity === 'fail' ||
        refTextValidation.severity === 'warn')
    ) {
      const isFail = refTextValidation.severity === 'fail'

      return (
        <div
          className={
            'flex items-center gap-2 border-b px-4 py-1.5 text-xs ' +
            (isFail
              ? 'border-rose-500/30 bg-rose-500/10 text-rose-300'
              : 'border-amber-500/30 bg-amber-500/10 text-amber-300')
          }
        >
          <AlertTriangle className="size-3 shrink-0" />
          <div className="min-w-0 flex-1">
            <span className="inline-block truncate">
              {isFail
                ? 'The reference text does not match the reference audio. This will degrade speech quality.'
                : 'Reference text may need review; speech quality can be affected.'}
            </span>
          </div>
          {isFail && (
            <span className="shrink-0 text-[10px] opacity-70">
              Review it in Voice Library.
            </span>
          )}
        </div>
      )
    }

    return null
  }

  // model_loaded/service_started only track the Base/VoiceDesign slot — OmniVoice loads
  // independently and never touches it, so this banner would otherwise show "Initializing
  // TTS model" on the OmniVoice panel even when nothing is loading there.
  const needsBase =
    page === 'speak' || (page === 'voice-design' && designEngine === 'qwen')
  if (!needsBase) return null

  return (
    <div className="flex items-center justify-between gap-2 border-b border-border bg-muted/30 px-4 py-1.5 text-xs text-muted-foreground">
      <div className="min-w-0 flex items-center gap-2">
        <Loader2 className="size-3 shrink-0 animate-spin text-muted-foreground" />
        <span className="truncate">{loadingMessage || 'Initializing TTS model…'}</span>
      </div>
      <span className="shrink-0 opacity-70 hidden sm:inline">
        Speak and Voice Design will be available shortly.
      </span>
    </div>
  )
}

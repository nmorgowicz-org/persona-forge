import { useAppStore } from '@/store'
import { AlertTriangle, ArrowRight, Info, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AppBanner } from '@/components/ui/app-banner'

export function HealthStatusBanner() {
  const serviceStarted = useAppStore((s) => s.serviceStarted)
  const loadingMessage = useAppStore((s) => s.loadingMessage)
  const healthStatus = useAppStore((s) => s.healthStatus)
  const healthError = useAppStore((s) => s.healthError)
  const page = useAppStore((s) => s.page)
  const designEngine = useAppStore((s) => s.designEngine)
  const refTextValidation = useAppStore((s) => s.refTextValidation)
  const setPage = useAppStore((s) => s.setPage)
  const setVoiceLibraryFocusVoiceId = useAppStore((s) => s.setVoiceLibraryFocusVoiceId)

  // Any in-flight model load (cold boot, post-boot swap-back, or OmniVoice load) gets the
  // top notification bar, on any page, until the server stops reporting loadingMessage.
  // A startup failure (health status "error") resolves into a persistent error bar instead
  // of spinning "Loading model…" forever.
  if (loadingMessage) {
    if (healthStatus === 'error') {
      return (
        <AppBanner tone="danger" icon={<AlertTriangle className="size-3 shrink-0" />}>
          <span className="inline-block truncate">
            {loadingMessage}
            {healthError ? `: ${healthError}` : ''}
          </span>
        </AppBanner>
      )
    }
    return (
      <AppBanner tone="neutral" icon={<Loader2 className="size-3 shrink-0 animate-spin" />}>
        <span className="truncate">{loadingMessage}</span>
      </AppBanner>
    )
  }

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
      const voiceId = refTextValidation.voiceId
      const activeApiVoiceId = refTextValidation.activeApiVoiceId
      const activeVoiceDiffers = Boolean(
        activeApiVoiceId && voiceId && activeApiVoiceId !== voiceId,
      )
      const affectsActiveGeneration = !activeVoiceDiffers
      const textSource = refTextValidation.textSource
      const audioPath = refTextValidation.audioPath
      const configuredText = refTextValidation.configuredText
      const mismatchDetail = voiceId && activeVoiceDiffers
        ? `Mounted reference configuration needs review for ${voiceId}.`
        : voiceId
          ? `Reference text does not match the mounted audio for ${voiceId}.`
          : 'Reference text may not match the mounted reference audio.'

      return (
        <AppBanner
          tone={affectsActiveGeneration ? (isFail ? 'danger' : 'warning') : 'neutral'}
          icon={
            affectsActiveGeneration ? (
              <AlertTriangle className="size-3 shrink-0" />
            ) : (
              <Info className="size-3 shrink-0" />
            )
          }
          detail={
            (audioPath || configuredText || refTextValidation.whisperTranscript) && (
              <span title={configuredText || undefined}>
                {audioPath && `Audio: ${audioPath}`}
                {textSource && ` · Text source: ${textSource === 'env' ? 'REF_TEXT' : textSource}`}
                {configuredText && ` · Configured: “${configuredText}”`}
                {refTextValidation.whisperTranscript &&
                  ` · Whisper heard: “${refTextValidation.whisperTranscript}”`}
              </span>
            )
          }
          actions={
            voiceId && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                data-testid="health-review-voice"
                className="h-6 shrink-0 gap-1 px-1.5 text-[10px] underline underline-offset-2"
                onClick={() => {
                  setVoiceLibraryFocusVoiceId(voiceId)
                  setPage('voice-library')
                }}
              >
                Review {voiceId}
                <ArrowRight className="size-3" />
              </Button>
            )
          }
        >
          <span className="font-medium">{mismatchDetail}</span>{' '}
          <span className="opacity-80">
            {activeVoiceDiffers
              ? `It is not the active API voice, so current no-voice generation uses ${activeApiVoiceId}.`
              : textSource === 'env'
                ? 'The configured REF_TEXT belongs to different audio.'
                : 'Review or regenerate the transcript before cloning.'}
          </span>
        </AppBanner>
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
    <AppBanner
      tone="neutral"
      icon={<Loader2 className="size-3 shrink-0 animate-spin" />}
      actions={
        <span className="hidden shrink-0 opacity-70 sm:inline">
          Speak and Voice Design will be available shortly.
        </span>
      }
    >
      <span className="truncate">{loadingMessage || 'Initializing TTS model…'}</span>
    </AppBanner>
  )
}

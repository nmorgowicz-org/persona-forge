import { useCallback, useEffect, useRef, useState } from 'react'
import { useAppStore } from '@/store'
import { StitchEditorInline } from '@/components/StitchTimeline'
import { StitchABBar } from '@/components/stitch/StitchABBar'
import { useStoreStitchPlanSession } from '@/hooks/useStitchPlanSession'
import {
  activateVoiceForApi,
  listOmniVoiceSegments,
  listVoices,
  saveOmniVoice,
  type SegmentMeta,
  type StitchPlanPayload,
  type VoiceMeta,
} from '@/lib/api'
import { insertSegmentsIntoStitchTimeline, insertVoicesIntoStitchTimeline, suggestedStitchVoiceName } from '@/lib/stitchClips'

const DELIVERY_VARIANTS = [
  { kind: 'natural', name: 'Natural', hint: 'Conversational and neutral' },
  { kind: 'calm', name: 'Calm', hint: 'Slower and steadier' },
  { kind: 'energetic', name: 'Energetic', hint: 'Brighter and tighter' },
  { kind: 'broadcast', name: 'Broadcast', hint: 'Clear and projected' },
  { kind: 'storyteller', name: 'Storyteller', hint: 'Warm and expressive' },
] as const

type DeliveryVariantKind = (typeof DELIVERY_VARIANTS)[number]['kind']

// A second, more direct entry point into the same stitch editor used inside the OmniVoice
// flow — lets a user jump straight to arranging saved segments/voices into a
// reference voice without first running an audition. Shares the same store-backed stitch
// plan, so switching between this page and OmniVoice's editor doesn't lose the timeline.
export function StitchStudioPage() {
  const voices = useAppStore((s) => s.voices)
  const setVoices = useAppStore((s) => s.setVoices)

  const savedVoiceId = useAppStore((s) => s.ovSavedVoiceId)
  const setSavedVoiceId = useAppStore((s) => s.setOvSavedVoiceId)
  const setDeepLinkProsodyVoiceId = useAppStore((s) => s.setDeepLinkProsodyVoiceId)
  const setPage = useAppStore((s) => s.setPage)
  const clips = useAppStore((s) => s.ovStitchPlanClips)

  const [library, setLibrary] = useState<SegmentMeta[]>([])
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [isActivating, setIsActivating] = useState(false)
  const [deliveryVariantKind, setDeliveryVariantKind] =
    useState<DeliveryVariantKind>('natural')
  const [useAsApiDefault, setUseAsApiDefault] = useState(false)
  const [activationError, setActivationError] = useState<string | null>(null)
  const nameInputRef = useRef<HTMLInputElement>(null)
  const namePristineRef = useRef(true)
  const previousClipCountRef = useRef(clips.length)
  const sourceName = clips[0] ? suggestedStitchVoiceName(clips[0]) : ''

  const deliveryVariant = DELIVERY_VARIANTS.find(
    (variant) => variant.kind === deliveryVariantKind,
  ) ?? DELIVERY_VARIANTS[0]

  useEffect(() => {
    listOmniVoiceSegments().then(setLibrary).catch(() => {})
    listVoices().then(setVoices).catch(() => {})
  }, [setVoices])

  useEffect(() => {
    if (
      previousClipCountRef.current === 0
      && clips.length === 1
      && namePristineRef.current
      && sourceName
    ) {
      setName(sourceName)
    }
    previousClipCountRef.current = clips.length
  }, [clips.length, sourceName])

  const session = useStoreStitchPlanSession()

  const insertFromLibrary = useCallback((segs: SegmentMeta[], afterClipId: string | null) => {
    void insertSegmentsIntoStitchTimeline(segs, session, setError, afterClipId)
  }, [session])

  const insertVoiceFromLibrary = useCallback((voices: VoiceMeta[], afterClipId: string | null) => {
    void insertVoicesIntoStitchTimeline(voices, session, setError, afterClipId)
  }, [session])

  const handleSave = useCallback(
    async (plan: StitchPlanPayload, segments: string[]) => {
      if (!name.trim()) {
        setError('Give this voice a name before saving.')
        nameInputRef.current?.focus()
        return
      }
      try {
        setIsSaving(true)
        setError(null)
        const result = await saveOmniVoice({
          instruct: name.trim(),
          segments: segments.length ? segments : [name.trim()],
          stitchPlan: plan,
          familyId: useAppStore.getState().targetFamilyId,
          variantName: deliveryVariant.name,
          variantKind: deliveryVariant.kind,
        })
        setSavedVoiceId(result.voice_id)
        setDeepLinkProsodyVoiceId(result.voice_id)
        if (useAsApiDefault) {
          try {
            await activateVoiceForApi(result.voice_id)
            setActivationError(null)
          } catch (activationErr) {
            setActivationError(activationErr instanceof Error ? activationErr.message : String(activationErr))
          }
        } else {
          setActivationError(null)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setIsSaving(false)
      }
    },
    [name, setSavedVoiceId, deliveryVariant, setDeepLinkProsodyVoiceId, useAsApiDefault],
  )
  const retryActivation = useCallback(async () => {
    if (!savedVoiceId) return
    try {
      setIsActivating(true)
      await activateVoiceForApi(savedVoiceId)
      setActivationError(null)
    } catch (activationErr) {
      setActivationError(activationErr instanceof Error ? activationErr.message : String(activationErr))
    } finally {
      setIsActivating(false)
    }
  }, [savedVoiceId])
  const handleStartOver = useCallback(() => {
    setName('')
    namePristineRef.current = true
    previousClipCountRef.current = 0
    setError(null)
    setActivationError(null)
    setUseAsApiDefault(false)
    setSavedVoiceId(null)
  }, [setSavedVoiceId])

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-foreground">Stitch Studio</h1>
        <p className="text-sm text-muted-foreground">
          Arrange saved segments or voice-library entries into a timeline and save the result as a
          new reference voice — no audition required first.
        </p>
      </div>

      <div className="flex max-w-md flex-col gap-1.5">
        <div className="flex items-center justify-between gap-2">
          <label htmlFor="stitch-voice-name" className="text-xs font-medium text-muted-foreground">Name this voice</label>
          {sourceName && (
            <span className="text-[10px] text-muted-foreground">
              Suggested from first clip
              {name !== sourceName && (
                <button
                  type="button"
                  data-testid="stitch-revert-source-name"
                  onClick={() => setName(sourceName)}
                  className="ml-2 font-medium text-primary hover:underline"
                >
                  Revert to suggestion
                </button>
              )}
            </span>
          )}
        </div>
        <input
          ref={nameInputRef}
          id="stitch-voice-name"
          type="text"
          data-testid="stitch-voice-name"
          value={name}
          onChange={(e) => {
            namePristineRef.current = false
            setName(e.target.value)
          }}
          placeholder="e.g. Narrator — warm AU accent"
          className="rounded-md border border-border bg-muted/40 px-3 py-1.5 text-sm text-foreground outline-none focus:border-cyan-500/50"
        />
      </div>

      <DeliveryVariantSelector
        value={deliveryVariantKind}
        onChange={setDeliveryVariantKind}
      />

      <label className="flex max-w-md items-start gap-2 text-xs text-muted-foreground">
        <input
          type="checkbox"
          data-testid="stitch-use-as-api-default"
          checked={useAsApiDefault}
          onChange={(event) => setUseAsApiDefault(event.currentTarget.checked)}
          className="mt-0.5 size-3.5 accent-primary"
        />
        <span>
          Use as default for API calls
          <span className="block text-[10px]">Saves the reference first, then activates it for API requests.</span>
        </span>
      </label>

      {error && <p className="text-xs text-destructive">{error}</p>}
      {isSaving && <p className="text-xs text-muted-foreground">Saving…</p>}

      <StitchABBar />

      <StitchEditorInline
        surface="studio"
        session={session}
        library={library}
        onInsertFromLibrary={insertFromLibrary}
        voiceLibrary={voices}
        onInsertVoiceFromLibrary={insertVoiceFromLibrary}
        onSave={handleSave}
        onStartOver={handleStartOver}
        name={name}
        saveLabel={useAsApiDefault ? 'Save & use as API default' : 'Save as reference voice'}
        isSaving={isSaving}
        isActivating={isActivating}
        onFocusName={() => nameInputRef.current?.focus()}
      />

      {savedVoiceId && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <p>
            {activationError ? 'Saved, not activated' : 'Saved to voice library as'}{' '}
            <span className="font-mono text-foreground">{savedVoiceId}</span>.
          </p>
          <button
            type="button"
            data-testid="stitch-adjust-prosody"
            onClick={() => { setDeepLinkProsodyVoiceId(savedVoiceId); setPage('voice-edit') }}
            className="font-medium text-primary hover:underline"
          >
            Adjust prosody
          </button>
          {activationError && (
            <button
              type="button"
              data-testid="stitch-retry-api-activation"
              onClick={() => void retryActivation()}
              className="font-medium text-primary hover:underline"
            >
              Retry activation
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function DeliveryVariantSelector({
  value,
  onChange,
}: {
  value: DeliveryVariantKind
  onChange: (value: DeliveryVariantKind) => void
}) {
  return (
    <div className="flex max-w-3xl flex-col gap-1">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Delivery variant
      </p>
      <div className="flex flex-wrap gap-1.5">
        {DELIVERY_VARIANTS.map((variant) => (
          <button
            key={variant.kind}
            type="button"
            title={variant.hint}
            onClick={() => onChange(variant.kind)}
            className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition ${
              value === variant.kind
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-input bg-background text-muted-foreground hover:bg-accent hover:text-foreground'
            }`}
          >
            {variant.name}
          </button>
        ))}
      </div>
    </div>
  )
}

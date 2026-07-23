import { useCallback, useEffect, useState } from 'react'
import { useAppStore } from '@/store'
import { StitchEditorInline } from '@/components/StitchTimeline'
import {
  listOmniVoiceSegments,
  listVoices,
  saveOmniVoice,
  type SegmentMeta,
  type StitchPlanPayload,
  type VoiceMeta,
} from '@/lib/api'
import { insertSegmentIntoStitchTimeline, insertVoiceIntoStitchTimeline } from '@/lib/stitchClips'

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

  const [library, setLibrary] = useState<SegmentMeta[]>([])
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [deliveryVariantKind, setDeliveryVariantKind] =
    useState<DeliveryVariantKind>('natural')

  const deliveryVariant = DELIVERY_VARIANTS.find(
    (variant) => variant.kind === deliveryVariantKind,
  ) ?? DELIVERY_VARIANTS[0]

  useEffect(() => {
    listOmniVoiceSegments().then(setLibrary).catch(() => {})
    listVoices().then(setVoices).catch(() => {})
  }, [setVoices])

  const insertFromLibrary = useCallback(async (seg: SegmentMeta) => {
    await insertSegmentIntoStitchTimeline(seg, setError)
  }, [])

  const insertVoiceFromLibrary = useCallback(async (voice: VoiceMeta) => {
    await insertVoiceIntoStitchTimeline(voice, setError)
  }, [])

  const handleSave = useCallback(
    async (plan: StitchPlanPayload, segments: string[]) => {
      if (!name.trim()) {
        setError('Give this voice a name before saving.')
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
        setPage('voice-library')
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setIsSaving(false)
      }
    },
    [name, setSavedVoiceId, deliveryVariant, setDeepLinkProsodyVoiceId, setPage],
  )

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-foreground">Stitch Studio</h1>
        <p className="text-sm text-muted-foreground">
          Arrange saved segments or voice-library entries into a timeline and save the result as a
          new reference voice — no audition required first.
        </p>
      </div>

      <div className="flex flex-col gap-1.5 max-w-md">
        <label className="text-xs font-medium text-muted-foreground">Name this voice</label>
        <input
          type="text"
          data-testid="stitch-voice-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Narrator — warm AU accent"
          className="rounded-md border border-border bg-muted/40 px-3 py-1.5 text-sm text-foreground outline-none focus:border-cyan-500/50"
        />
      </div>

      <DeliveryVariantSelector
        value={deliveryVariantKind}
        onChange={setDeliveryVariantKind}
      />

      {error && <p className="text-xs text-destructive">{error}</p>}
      {isSaving && <p className="text-xs text-muted-foreground">Saving…</p>}

      <StitchEditorInline
        library={library}
        onInsertFromLibrary={insertFromLibrary}
        voiceLibrary={voices}
        onInsertVoiceFromLibrary={insertVoiceFromLibrary}
        onSave={handleSave}
      />

      {savedVoiceId && (
        <p className="text-xs text-muted-foreground">
          Saved to voice library as <span className="font-mono text-foreground">{savedVoiceId}</span>.
        </p>
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

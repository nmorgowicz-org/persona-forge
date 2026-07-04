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

// A second, more direct entry point into the same stitch editor used inside Persona Forge's
// OmniVoice flow — lets a user jump straight to arranging saved segments/voices into a
// reference voice without first running an audition. Shares the same store-backed stitch
// plan, so switching between this page and Persona Forge's editor doesn't lose the timeline.
export function StitchStudioPage() {
  const voices = useAppStore((s) => s.voices)
  const setVoices = useAppStore((s) => s.setVoices)

  const savedVoiceId = useAppStore((s) => s.ovSavedVoiceId)
  const setSavedVoiceId = useAppStore((s) => s.setOvSavedVoiceId)

  const [library, setLibrary] = useState<SegmentMeta[]>([])
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

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
        })
        setSavedVoiceId(result.voice_id)
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setIsSaving(false)
      }
    },
    [name, setSavedVoiceId],
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
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Narrator — warm AU accent"
          className="rounded-md border border-border bg-muted/40 px-3 py-1.5 text-sm text-foreground outline-none focus:border-cyan-500/50"
        />
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}
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

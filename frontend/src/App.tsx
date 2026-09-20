import { useCallback, useState } from 'react'
import { TitleTooltipBridge, TooltipProvider } from '@/components/ui/tooltip'
import { AppShell } from '@/components/AppShell'
import { useAppStore } from '@/store'
import { PersonaWizardPage } from '@/pages/PersonaWizardPage'
import { SpeakPage } from '@/pages/SpeakPage'
import { VoiceDesignPage } from '@/pages/VoiceDesignPage'
import { VoiceLibraryPage } from '@/pages/VoiceLibraryPage'
import { StitchStudioPage } from '@/pages/StitchStudioPage'
import { VoiceEditPage } from '@/pages/VoiceEditPage'
import { IntegrationsPage } from '@/pages/IntegrationsPage'
import { RuntimeConfigPage } from '@/pages/RuntimeConfigPage'
import { Glossary } from '@/components/audio/Glossary'
import { StitchEditorPanel } from '@/components/StitchTimeline'
import { useDraftStitchPlanSession } from '@/hooks/useStitchPlanSession'
import { insertSegmentsIntoStitchTimeline, insertVoicesIntoStitchTimeline } from '@/lib/stitchClips'
import type { StitchPlanState } from '@/lib/stitchPlan'
import type { SegmentMeta, VoiceMeta } from '@/lib/api'

// The one quick-insert modal instance for the whole app (Decision B: hoist the render, not
// the flag -- previously OmniVoicePanel's own mount trapped it inside the Voice Design page,
// so opening it from Voice Library first forced a navigation to Voice Design just to have
// somewhere to render it). Mounted only while open, so the draft session below re-clones the
// current store plan fresh on every opening.
function QuickInsertStitchEditor() {
  const incomingClip = useAppStore((s) => s.ovStitchEditorIncomingClip)
  const storeClips = useAppStore((s) => s.ovStitchPlanClips)
  const storePaddingMs = useAppStore((s) => s.ovStitchPlanPaddingMs)
  const storeDsp = useAppStore((s) => s.ovStitchPlanDsp)
  const storeRegionEdits = useAppStore((s) => s.ovStitchRegionEditsByClip)
  const replaceOvStitchPlan = useAppStore((s) => s.replaceOvStitchPlan)
  const closeOvStitchEditor = useAppStore((s) => s.closeOvStitchEditor)
  const setPage = useAppStore((s) => s.setPage)
  const library = useAppStore((s) => s.ovLibrary)
  const voiceLibrary = useAppStore((s) => s.voices)

  const initial: StitchPlanState = incomingClip
    ? {
        clips: [...storeClips, incomingClip],
        paddingMs: storeClips.length > 0 ? [...storePaddingMs, 0] : storePaddingMs,
        dsp: storeDsp,
        regionEditsByClip: storeRegionEdits,
      }
    : { clips: storeClips, paddingMs: storePaddingMs, dsp: storeDsp, regionEditsByClip: storeRegionEdits }

  const session = useDraftStitchPlanSession(initial)

  const handleCommitDraft = useCallback((plan: StitchPlanState, destination: 'caller' | 'studio') => {
    replaceOvStitchPlan(plan)
    closeOvStitchEditor()
    if (destination === 'studio') setPage('stitch-studio')
  }, [replaceOvStitchPlan, closeOvStitchEditor, setPage])

  const handleCancelDraft = useCallback(() => {
    closeOvStitchEditor()
  }, [closeOvStitchEditor])

  const [insertError, setInsertError] = useState<string | null>(null)
  const onInsertFromLibrary = useCallback((segs: SegmentMeta[], afterClipId: string | null) => {
    void insertSegmentsIntoStitchTimeline(segs, session, setInsertError, afterClipId)
  }, [session])
  const onInsertVoiceFromLibrary = useCallback((voices: VoiceMeta[], afterClipId: string | null) => {
    void insertVoicesIntoStitchTimeline(voices, session, setInsertError, afterClipId)
  }, [session])

  return (
    <>
      {insertError && (
        <div className="fixed inset-x-0 top-0 z-[60] bg-destructive/90 px-4 py-1.5 text-center text-xs text-destructive-foreground">
          {insertError}
        </div>
      )}
      <StitchEditorPanel
        surface="quick-insert"
        session={session}
        library={library}
        onInsertFromLibrary={onInsertFromLibrary}
        voiceLibrary={voiceLibrary}
        onInsertVoiceFromLibrary={onInsertVoiceFromLibrary}
        onCommitDraft={handleCommitDraft}
        onCancelDraft={handleCancelDraft}
      />
    </>
  )
}

export default function App() {
  const page = useAppStore((s) => s.page)
  const glossaryOpen = useAppStore((s) => s.glossaryOpen)
  const setGlossaryOpen = useAppStore((s) => s.setGlossaryOpen)
  const glossaryFocusId = useAppStore((s) => s.glossaryFocusId)
  const stitchEditorOpen = useAppStore((s) => s.ovStitchEditorOpen)

  return (
    <TooltipProvider>
      <TitleTooltipBridge />
      <div className="relative flex min-h-screen w-full flex-col">
        <AppShell>
          {page === 'wizard' && <PersonaWizardPage />}
          {page === 'speak' && <SpeakPage />}
          {page === 'voice-design' && <VoiceDesignPage />}
          {page === 'voice-library' && <VoiceLibraryPage />}
          {page === 'voice-edit' && <VoiceEditPage />}
          {page === 'stitch-studio' && <StitchStudioPage />}
          {page === 'integrations' && <IntegrationsPage />}
          {page === 'runtime' && <RuntimeConfigPage />}
        </AppShell>
        <Glossary
          isOpen={glossaryOpen}
          onClose={() => setGlossaryOpen(false)}
          focusId={glossaryFocusId}
        />
        {stitchEditorOpen && <QuickInsertStitchEditor />}
      </div>
    </TooltipProvider>
  )
}

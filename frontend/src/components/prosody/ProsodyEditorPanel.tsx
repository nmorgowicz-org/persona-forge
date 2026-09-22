import { AlignmentCompare } from '@/components/waveform/AlignmentCompare'
import { ProsodyControls } from './ProsodyControls'
import { ProsodyVariantsList } from './ProsodyVariantsList'
import { useProsodyEditor, type ProsodyEditorVoice } from './useProsodyEditor'

interface ProsodyEditorPanelProps {
  voice: ProsodyEditorVoice
  layout: 'compact' | 'page'
  onChanged?: () => Promise<void> | void
}

// Full standalone prosody workspace: owns its own editor session and renders every
// piece (variants list, alignment comparison, settings form) in one page-styled block.
// Used by the Voice Edit page. Voice Library instead calls `useProsodyEditor` itself and
// composes `ProsodyControls`/`ProsodyVariantsList` inline, so its always-visible variant
// strip and alignment preview can live outside the settings popover.
export function ProsodyEditorPanel({ voice, layout, onChanged }: ProsodyEditorPanelProps) {
  const editor = useProsodyEditor(voice, onChanged)
  return (
    <section data-testid="prosody-editor-panel" data-layout={layout} className={layout === 'page' ? 'mx-auto flex w-full max-w-5xl flex-col gap-5' : 'flex flex-col gap-3'}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Prosody editor</h2>
          <p className="text-xs text-muted-foreground">Preview pacing, save variants, then promote the one you want served.</p>
        </div>
      </div>
      <ProsodyVariantsList editor={editor} layout={layout} />
      {/* Mounted unconditionally: with no preview yet this renders the ORIGINAL lane
          alone (waveform, transport, word labels), so the workspace is a waveform
          surface from the moment a voice is selected instead of only after Preview.
          Matches VoiceLibraryPage's always-visible strip. */}
      <AlignmentCompare
        voiceId={voice.voice_id}
        adjustedBase64={editor.preview?.audioBase64 ?? null}
        adjustedSampleCount={editor.preview?.sampleCount ?? null}
        boundaryPlan={editor.preview?.plan ?? []}
        boundaries={editor.alignBoundaries}
        overrides={editor.targetOverrides}
        onNudgeTarget={editor.previewBusy ? undefined : editor.nudgeTarget}
        onResetTarget={editor.previewBusy ? undefined : editor.resetTarget}
        stylePreset={editor.preview ? editor.stylePreset : undefined}
      />
      <ProsodyControls editor={editor} layout={layout} />
    </section>
  )
}

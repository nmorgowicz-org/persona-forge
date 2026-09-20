import { Play, Star, Wand2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AlignmentCompare } from '@/components/waveform/AlignmentCompare'
import { useProsodyEditor } from './useProsodyEditor'

interface ProsodyEditorPanelProps {
  voiceId: string
  layout: 'compact' | 'page'
  onChanged?: () => Promise<void> | void
}

export function ProsodyEditorPanel({ voiceId, layout, onChanged }: ProsodyEditorPanelProps) {
  const editor = useProsodyEditor(voiceId, onChanged)
  return (
    <section data-testid="prosody-editor-panel" className={layout === 'page' ? 'mx-auto flex w-full max-w-5xl flex-col gap-5' : 'flex flex-col gap-3'}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Prosody editor</h2>
          <p className="text-xs text-muted-foreground">Preview pacing, save variants, then promote the one you want served.</p>
        </div>
        <Button data-testid="voice-edit-save-variant" size="sm" disabled={editor.busy} onClick={() => void editor.saveVariant()}>
          <Wand2 /> Save as Variant
        </Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Style preset
          <select value={editor.stylePreset} onChange={(event) => editor.setStylePreset(event.currentTarget.value)} className="h-9 rounded border border-border bg-background px-2 text-sm text-foreground">
            {['Neutral', 'Storyteller', 'Calm', 'Energetic', 'Broadcast', 'Clean'].map((preset) => <option key={preset}>{preset}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Pace {editor.paceMultiplier.toFixed(1)}×
          <input type="range" min="0.5" max="2" step="0.1" value={editor.paceMultiplier} onChange={(event) => editor.setPaceMultiplier(Number(event.currentTarget.value))} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Pause offset {editor.pauseOffset}ms
          <input type="range" min="-500" max="500" step="10" value={editor.pauseOffset} onChange={(event) => editor.setPauseOffset(Number(event.currentTarget.value))} />
        </label>
      </div>
      <div className="flex flex-wrap gap-2">
        {(['auto', 'natural', 'precise'] as const).map((mode) => <Button key={mode} size="sm" variant={editor.mode === mode ? 'default' : 'outline'} onClick={() => editor.setMode(mode)}>{mode}</Button>)}
        <Button size="sm" variant="outline" disabled={editor.busy} onClick={() => void editor.previewProsody()}><Play /> Preview</Button>
      </div>
      {editor.error && <p className="text-sm text-destructive">{editor.error}</p>}
      {editor.preview && <AlignmentCompare voiceId={voiceId} adjustedBase64={editor.preview.audio_base64} adjustedSampleCount={editor.preview.sample_count} boundaryPlan={editor.preview.plan} boundaries={null} stylePreset={editor.stylePreset} />}
      <div className="rounded-lg border border-border/60 p-3">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Prosody variants</p>
        <div className="space-y-2">
          {editor.entries.map((entry) => <div key={entry.id} data-testid="voice-edit-variant" className="flex items-center justify-between gap-2 text-sm">
            <span>{entry.label}{editor.activeFilename === entry.filename ? ' — Primary' : ''}</span>
            {editor.activeFilename !== entry.filename && <Button size="sm" variant="outline" disabled={editor.busy} onClick={() => void editor.promoteVariant(entry.filename)}><Star /> Promote</Button>}
          </div>)}
        </div>
      </div>
    </section>
  )
}

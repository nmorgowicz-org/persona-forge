import { AlertTriangle, AudioWaveform, Loader2, Play, Star, Undo2, Wand2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { ProsodyMode } from '@/lib/api'
import type { ProsodyEditor } from './useProsodyEditor'

export const STYLE_DESCRIPTIONS: Record<string, string> = {
  Neutral: 'Standard natural pacing and pauses for balanced speech.',
  Storyteller: 'Slower, more dramatic pacing with extended pauses for narrative effect.',
  Calm: 'Relaxed, steady pace with longer, soothing gaps between phrases.',
  Energetic: 'Fast-paced, tight gaps and rapid delivery for a high-energy feel.',
  Broadcast: 'Professional, clear pacing typical of news or radio announcements.',
  Clean: 'Tight, efficient pacing that removes unnecessary gaps for a crisp result.',
}

// Optional triage-derived hint about whether Auto mode will resolve to Precise for this
// clip. Voice Library computes this from its own reference-analysis triage; other
// callers (e.g. Voice Edit) simply omit it and lose only the decorative hint text.
export interface ProsodyTriageHint {
  mode?: string | null
  reasons?: string[] | null
  gapsDetected?: number | null
  boundariesExpected?: number | null
}

interface ProsodyControlsProps {
  editor: ProsodyEditor
  layout: 'compact' | 'page'
  triage?: ProsodyTriageHint | null
}

const MODE_TITLES: Record<ProsodyMode, (hasTranscript: boolean) => string> = {
  precise: (hasTranscript) =>
    hasTranscript
      ? 'Force forced-alignment-directed surgical pauses'
      : 'Add reference text to enable forced alignment',
  natural: () => 'Fast energy path — never re-aligns',
  auto: () => 'Let triage decide: align blended clips, keep clean clips fast',
}

// The prosody settings form — mode, style, pace, pause, and the preview/save/promote
// actions. Shared verbatim between Voice Library's compact popover and the Voice Edit
// page; the surrounding variants list and alignment comparison are composed by the caller
// so each surface can place them where its layout needs.
export function ProsodyControls({ editor, layout, triage }: ProsodyControlsProps) {
  const sentenceBoundaries = (editor.alignBoundaries ?? []).filter((b) => b.kind === 'sentence_split')
  const clauseBoundaries = (editor.alignBoundaries ?? []).filter((b) => b.kind !== 'sentence_split' && b.owns_clause)
  const shapedBoundaryCount = sentenceBoundaries.length + clauseBoundaries.length

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <label className="text-[10px] uppercase tracking-wide text-muted-foreground">Processing mode</label>
          {triage?.mode && (
            <span className="text-[9px] text-muted-foreground" title={(triage.reasons ?? []).filter(Boolean).join('\n')}>
              triage: {triage.mode}
            </span>
          )}
        </div>
        <div className="grid grid-cols-3 gap-1">
          {(['auto', 'natural', 'precise'] as const).map((m) => {
            const disabled = m === 'precise' && !editor.hasTranscript
            return (
              <Button
                key={m}
                size="sm"
                variant={editor.mode === m ? 'default' : 'outline'}
                disabled={disabled}
                className="h-7 px-1 text-[10px] capitalize"
                title={MODE_TITLES[m](editor.hasTranscript)}
                onClick={() => editor.setMode(m)}
              >
                {m}
              </Button>
            )
          })}
        </div>
        {/* Latency masking + boundary badge: only meaningful when the resolved mode
            actually aligns. */}
        {editor.resolvedPrecise && (
          editor.alignBusy ? (
            <div className="flex items-center gap-1.5 text-[10px] text-cyan-400">
              <Loader2 className="size-3 animate-spin" />
              Finding linguistic boundaries…
            </div>
          ) : editor.alignError ? (
            <div className="flex items-center gap-1 text-[10px] text-warning" title={editor.alignError}>
              <AlertTriangle className="size-3" /> Alignment unavailable — using safe fallback
            </div>
          ) : editor.alignWarning ? (
            <div className="flex items-center gap-1 text-[10px] text-warning" title={editor.alignWarning}>
              <AlertTriangle className="size-3" /> Alignment exceeded latency budget
            </div>
          ) : editor.alignBoundaries !== null ? (
            shapedBoundaryCount > 0 ? (
              <div
                className="flex items-center gap-1"
                title={[
                  `${sentenceBoundaries.length} sentence boundary${sentenceBoundaries.length === 1 ? '' : 'ies'} (manufactured sentence-end pauses)`,
                  `${clauseBoundaries.length} clause boundary${clauseBoundaries.length === 1 ? '' : 'ies'} (comma-scale pauses)`,
                ].join('\n')}
              >
                <Badge variant="outline" className="h-4 gap-1 px-1.5 text-[9px] font-medium text-cyan-400 border-cyan-500/40">
                  <AudioWaveform className="size-2.5" />
                  Aligned · {shapedBoundaryCount} boundar{shapedBoundaryCount === 1 ? 'y' : 'ies'}
                </Badge>
              </div>
            ) : (
              <div className="text-[10px] text-muted-foreground">Aligned · no surgical pauses needed</div>
            )
          ) : null
        )}
        <p className="text-[10px] text-muted-foreground italic leading-tight">
          {!editor.hasTranscript
            ? 'No transcript on this clip — Precise (forced alignment) needs reference text.'
            : triage?.mode === 'precise'
              ? `${triage.gapsDetected ?? '?'} gaps detected, ${triage.boundariesExpected ?? '?'} sentence boundaries expected → blended speech; Auto escalates to alignment.`
              : triage?.mode === 'natural'
                ? 'Gaps line up with sentence boundaries → clean; Auto keeps the fast energy path.'
                : 'Auto follows triage: blended clips escalate to forced alignment, clean clips keep the fast path.'}
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-[10px] uppercase tracking-wide text-muted-foreground">Style Preset</label>
        <Select value={editor.stylePreset} onValueChange={(val) => { editor.setStylePreset(val); editor.clearPreview() }}>
          <SelectTrigger size="sm" className="w-full h-7 px-2 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {Object.keys(STYLE_DESCRIPTIONS).map((s) => (
                <SelectItem key={s} value={s}>
                  <div className="flex flex-col text-left">
                    <span className="font-medium">{s}</span>
                    <span className="text-[10px] opacity-60 leading-tight">{STYLE_DESCRIPTIONS[s]}</span>
                  </div>
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex justify-between items-center">
          <label className="text-[10px] uppercase tracking-wide text-muted-foreground">Global Pace Scale</label>
          <span className="font-mono text-[10px]">{editor.paceMultiplier.toFixed(1)}x</span>
        </div>
        <p className="text-[10px] text-muted-foreground italic leading-tight mb-1">
          Scales all pauses proportionally (e.g., 1.2x increases all gaps by 20%).
        </p>
        <input
          type="range" min="0.5" max="2.0" step="0.1"
          value={editor.paceMultiplier}
          onChange={(e) => editor.setPaceMultiplier(parseFloat(e.target.value))}
          className="w-full accent-cyan-500"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex justify-between items-center">
          <label className="text-[10px] uppercase tracking-wide text-muted-foreground">Pause Offset</label>
          <span className="font-mono text-[10px]">{editor.pauseOffset > 0 ? `+${editor.pauseOffset}` : editor.pauseOffset}ms</span>
        </div>
        <p className="text-[10px] text-muted-foreground italic leading-tight mb-1">
          Shifts all gaps by a flat amount (e.g., +100ms adds 100ms to every pause).
        </p>
        <input
          type="range" min="-500" max="500" step="10"
          value={editor.pauseOffset}
          onChange={(e) => editor.setPauseOffset(parseInt(e.target.value, 10))}
          className="w-full accent-cyan-500"
        />
      </div>

      {editor.error && <p className="text-xs text-destructive">{editor.error}</p>}

      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={editor.busy}
          onClick={() => void editor.togglePreview()}
        >
          {editor.preview ? <Undo2 className="size-3.5" /> : <Play className="size-3.5" />} {editor.preview ? 'Reset Preview' : 'Preview'}
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={editor.busy}
          title="Bake and save this take as a new, independently-addressable variant — does not change what's currently served"
          onClick={() => void editor.saveVariant()}
          data-testid="voice-edit-save-variant"
        >
          <Wand2 className="size-3.5" /> Save as Variant
        </Button>
        <Button
          size="sm"
          variant={layout === 'page' ? 'default' : 'outline'}
          disabled={editor.busy}
          title="Bake this take and immediately promote it to the primary variant served by the API"
          onClick={() => void editor.savePromote()}
        >
          <Star className="size-3.5" /> Save &amp; Promote
        </Button>
      </div>
    </div>
  )
}

import { Check, GitFork, Loader2, Pause, Play, Star, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ProsodyEditor } from './useProsodyEditor'

interface ProsodyVariantsListProps {
  editor: ProsodyEditor
  layout: 'compact' | 'page'
}

// Original + every saved prosody variant, in one selectable list — the master reference
// is a first-class, always-visible row, not hidden behind a separate action. Shared by
// Voice Library's compact card and the Voice Edit page.
export function ProsodyVariantsList({ editor, layout }: ProsodyVariantsListProps) {
  const rowTestId = layout === 'page' ? 'voice-edit-variant' : undefined
  return (
    <div className={cn('flex flex-col overflow-hidden rounded-lg border border-border/60 bg-muted/10', layout === 'page' ? 'p-3' : 'p-2')}>
      <div className="flex items-center justify-between px-1">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Prosody Variants</p>
        <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
          {editor.entries.length === 0 && !editor.variantsReady && !editor.error && <Loader2 className="size-3 animate-spin" />}
          {editor.entries.length} total{editor.entries.length > 1 ? ` (${editor.entries.length - 1} variant${editor.entries.length - 1 === 1 ? '' : 's'})` : ''}
        </span>
      </div>
      <div className={cn('space-y-1 px-1', layout === 'compact' && 'max-h-28 overflow-y-auto')}>
        {editor.entries.map((entry) => (
          <div key={entry.id} data-testid={rowTestId} className="flex items-center justify-between gap-1">
            <span
              className={cn(
                'min-w-0 flex-1 truncate text-[11px] py-0.5 px-1 rounded',
                editor.activeFilename === entry.filename ? 'bg-cyan-500/20 text-cyan-300' : 'text-muted-foreground',
              )}
              title={entry.id}
            >
              {entry.label}
            </span>
            {editor.activeFilename === entry.filename && (
              <span className="flex shrink-0 items-center gap-0.5 text-[9px] font-medium uppercase tracking-wide text-cyan-400">
                <Check className="size-3" /> Primary
              </span>
            )}
            <div className="flex shrink-0 items-center gap-0.5">
              {editor.activeFilename !== entry.filename && (
                <button
                  onClick={() => void editor.promoteVariant(entry)}
                  disabled={editor.variantBusy === entry.filename}
                  title="Make this the primary variant — served by the API and shown as the main waveform for this voice_id"
                  aria-label="Make this the primary variant"
                  className="rounded p-0.5 text-muted-foreground hover:bg-cyan-500/20 hover:text-cyan-300"
                >
                  <Star className="size-3" />
                </button>
              )}
              <button
                onClick={() => void editor.previewVariant(entry)}
                disabled={editor.variantBusy === entry.filename && editor.previewingVariant !== entry.filename}
                title={editor.previewingVariant === entry.filename ? 'Stop preview' : 'Preview this variant'}
                aria-label={editor.previewingVariant === entry.filename ? 'Stop preview' : 'Preview this variant'}
                className="rounded p-0.5 text-muted-foreground hover:bg-muted/40 hover:text-foreground"
              >
                {editor.previewingVariant === entry.filename ? <Pause className="size-3" /> : <Play className="size-3" />}
              </button>
              {!entry.is_original && (
                <>
                  {editor.forkVariant && (
                    <button
                      onClick={() => void editor.forkVariant?.(entry)}
                      disabled={editor.variantBusy === entry.filename}
                      title="Fork this variant to an independent voice_id"
                      aria-label="Fork this variant to an independent voice_id"
                      className="rounded p-0.5 text-muted-foreground hover:bg-muted/40 hover:text-foreground"
                    >
                      <GitFork className="size-3" />
                    </button>
                  )}
                  <button
                    onClick={() => void editor.deleteVariant(entry)}
                    disabled={editor.variantBusy === entry.filename}
                    title="Delete this variant"
                    aria-label="Delete this variant"
                    className="rounded p-0.5 text-muted-foreground hover:bg-destructive/20 hover:text-destructive"
                  >
                    <Trash2 className="size-3" />
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

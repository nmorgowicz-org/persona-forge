import { Download, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { AutoCheckStatus } from '@/lib/compareAutoCheck'
import { AUTO_CHECK_DISCLAIMER, SIMILARITY_MODEL, WER_MODEL, type CheckState } from '@/components/voices/useAutoCheck'

/** The explicit opt-in. Off by default: shows what would be downloaded and how big it is. */
export function AutoCheckSetup({
  status,
  statusError,
  needsSimilarity,
  onDownload,
}: {
  status: AutoCheckStatus | null
  statusError: string | null
  needsSimilarity: boolean
  onDownload: (ids: string[]) => void
}) {
  if (!status) {
    return statusError ? <p className="text-[11px] text-destructive">Auto-check unavailable: {statusError}</p> : null
  }
  const wanted = status.models.filter((m) => m.id === WER_MODEL || (needsSimilarity && m.id === SIMILARITY_MODEL))
  const missing = wanted.filter((m) => !m.available)
  const job = status.job
  if (job.state === 'running') {
    return (
      <p role="status" className="flex items-center gap-1.5 text-[11px] text-muted-foreground" data-testid="auto-check-download">
        <Loader2 className="size-3 animate-spin" />
        {job.step || 'Downloading'} ({job.step_index} of {job.step_count})
      </p>
    )
  }
  if (missing.length === 0) return null
  const sizes = Math.round(missing.reduce((sum, m) => sum + m.size_bytes, 0) / 1e6)
  return (
    <div className="flex flex-col gap-1.5 rounded-control border border-dashed border-border p-3" data-testid="auto-check-setup">
      <span className="text-xs font-medium">Auto-check (optional)</span>
      <p className="text-[11px] text-muted-foreground">
        Small hints under each clip: word error against your text
        {needsSimilarity ? ' and speaker similarity to the reference' : ''}. They run on this computer, need{' '}
        {missing.map((m) => `${m.label} (${m.size_label})`).join(' and ')} that
        {missing.length === 1 ? ' is' : ' are'} not downloaded yet, and nothing is downloaded until you ask.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="xs" variant="outline" onClick={() => onDownload(missing.map((m) => m.id))}>
          <Download />
          Enable auto-check: download {missing.length === 1 ? 'model' : 'models'} ({sizes} MB)
        </Button>
        {job.state === 'error' && job.error && (
          <span role="alert" className="text-[11px] text-destructive">{job.error}</span>
        )}
      </div>
    </div>
  )
}

/** One clip's hint line: a Check button, its result and the standing disclaimer. */
export function AutoCheckHint({
  state,
  canCheck,
  busy,
  isClone,
  onCheck,
}: {
  state: CheckState | undefined
  canCheck: boolean
  busy: boolean
  isClone: boolean
  onCheck: () => void
}) {
  return (
    <div className="flex flex-col gap-1 border-t border-border pt-1.5 text-[11px]" data-testid="auto-check">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">Auto-check (hint)</span>
        <Button
          type="button"
          size="xs"
          variant="outline"
          disabled={!canCheck || busy}
          title={canCheck ? undefined : 'Download the auto-check model first'}
          onClick={onCheck}
        >
          {state?.state === 'running' ? <Loader2 className="animate-spin" /> : null}
          {state?.state === 'done' ? 'Check again' : 'Check'}
        </Button>
        {state?.state === 'error' && <span role="alert" className="text-destructive">{state.message}</span>}
      </div>
      {state?.state === 'done' && (
        <div className="flex flex-col gap-0.5" data-testid="auto-check-result">
          <span data-testid="auto-check-wer">
            Word error:{' '}
            {state.result.wer === null
              ? 'not available'
              : `${(state.result.wer * 100).toFixed(state.result.wer > 0 && state.result.wer < 0.1 ? 1 : 0)}%`}
            {state.result.transcript !== null && (
              <span className="text-muted-foreground"> · heard “{state.result.transcript || '(nothing)'}”</span>
            )}
          </span>
          {isClone && (
            <span data-testid="auto-check-similarity">
              Speaker similarity:{' '}
              {state.result.similarity === null ? 'not available' : state.result.similarity.toFixed(2)}
              <span className="text-muted-foreground"> (1 is identical)</span>
            </span>
          )}
          {state.result.notes
            .filter((note) => /needs the|could not|no speech|too short|no words/i.test(note))
            .map((note) => (
              <span key={note} className="text-muted-foreground">{note}</span>
            ))}
        </div>
      )}
      <span className="text-muted-foreground">{AUTO_CHECK_DISCLAIMER}</span>
    </div>
  )
}

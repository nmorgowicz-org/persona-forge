import { computeStitchDurations, type StitchDurations } from '@/lib/stitchPlan'
import type { StitchPlanState } from '@/lib/stitchPlan'

type ReadinessState = 'blocked' | 'warning' | 'ideal' | 'overlong'

type GuidanceAction = 'add-clips' | 'name-it' | 'save'

function readinessState(durations: StitchDurations): ReadinessState {
  if (durations.sourceMaterialMs < 5000) return 'blocked'
  if (durations.renderedMs < 10000) return 'warning'
  if (durations.renderedMs <= 15000) return 'ideal'
  return 'overlong'
}

function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`
}

export function ReferenceReadiness({
  plan,
  name,
  isSaving,
  isActivating,
  isPreviewRendering,
  saveLabel,
  onSave,
  onFocusName,
  onAddClips,
}: {
  plan: StitchPlanState
  name: string
  isSaving: boolean
  /** API-default activation in flight: the bar shows "Activating…" but Save stays enabled. */
  isActivating?: boolean
  isPreviewRendering: boolean
  saveLabel: string
  onSave: () => void
  onFocusName: () => void
  onAddClips: () => void
}) {
  const durations = computeStitchDurations(plan)
  const state = readinessState(durations)
  const hasName = name.trim().length > 0
  const canSave = durations.sourceMaterialMs >= 5000 && hasName && !isSaving && !isPreviewRendering
  const action: GuidanceAction = durations.sourceMaterialMs < 5000 || durations.renderedMs < 10000
    ? 'add-clips'
    : hasName
      ? 'save'
      : 'name-it'

  const message = state === 'blocked'
    ? 'Add more source speech before saving. Spacing does not count toward the five-second minimum.'
    : state === 'warning'
      ? 'Add clips to reach a 10–15 second rendered reference.'
      : state === 'ideal'
        ? 'Reference length is in the recommended 10–15 second range.'
        : 'This reference is longer than 15 seconds; it remains valid but may be slower to use.'
  const stateClass = state === 'blocked'
    ? 'border-destructive/40 bg-destructive/5'
    : state === 'warning'
      ? 'border-warning/40 bg-warning/5'
      : state === 'ideal'
        ? 'border-success/40 bg-success/5'
        : 'border-info/40 bg-info/5'

  return (
    <section
      data-testid="stitch-reference-readiness"
      data-readiness-state={state}
      className={`flex flex-col gap-3 rounded-lg border px-4 py-3 ${stateClass}`}
      aria-label="Reference readiness"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div>
          <p className="text-xs font-semibold text-foreground">Reference readiness</p>
          <p className="text-xs text-muted-foreground">{message}</p>
        </div>
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
          state === 'blocked' ? 'bg-destructive/10 text-destructive'
            : state === 'warning' ? 'bg-warning/10 text-warning'
              : state === 'ideal' ? 'bg-success/10 text-success'
                : 'bg-info/10 text-info'
        }`}>
          {state}
        </span>
        <p className="text-xs font-mono tabular-nums text-foreground">
          <span data-testid="stitch-source-duration">{seconds(durations.sourceMaterialMs)} clips</span>
          {' + '}{seconds(durations.spacingMs)} spacing = <span data-testid="stitch-rendered-duration">{seconds(durations.renderedMs)} rendered</span>
        </p>
      </div>

      <ol className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        {[
          ['Add clips', action === 'add-clips'],
          ['Reach 10–15s', action === 'add-clips' && durations.sourceMaterialMs >= 5000],
          ['Name it', action === 'name-it'],
          ['Save', action === 'save'],
          ['Adjust prosody', false],
        ].map(([label, active]) => (
          <li key={label as string} className={active ? 'font-medium text-foreground' : undefined}>
            {label as string}
          </li>
        ))}
      </ol>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          data-testid="stitch-save-voice"
          onClick={onSave}
          disabled={!canSave}
          className={canSave && action === 'save'
            ? 'btn-brand inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-medium'
            : 'inline-flex items-center gap-1.5 rounded-full border border-border px-4 py-1.5 text-xs font-medium text-muted-foreground disabled:opacity-50'}
          title="This will be used as a reusable cloning source for text-to-speech."
        >
          {saveLabel}
        </button>
        {isActivating && (
          <span className="text-[10px] font-medium text-info" data-testid="stitch-activating">
            Activating…
          </span>
        )}
        {action === 'add-clips' && (
          <button type="button" data-testid="stitch-guidance-primary" onClick={onAddClips} className="btn-brand inline-flex rounded-full px-4 py-1.5 text-xs font-medium">
            {durations.sourceMaterialMs < 5000 ? 'Add clips' : 'Reach 10–15s'}
          </button>
        )}
        {action === 'name-it' && (
          <button type="button" data-testid="stitch-guidance-primary" onClick={onFocusName} className="btn-brand inline-flex rounded-full px-4 py-1.5 text-xs font-medium">
            Name it
          </button>
        )}
      </div>
    </section>
  )
}

import { useState } from 'react'
import { Check } from 'lucide-react'
import * as Tooltip from '@/components/ui/tooltip'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { lockInOmniVoiceSegment, type SegmentMeta } from '@/lib/api'
import { lookupFeatureTags } from '@/lib/accentBank'
import { ClipPlayer } from './ClipPlayer'
import { TakeDebugButton } from './TakeDebugButton'

// Per-segment duration target bounds. Was capped at 4s, but nick got successful, natural
// takes noticeably longer than that (2026-07-04) — the cap was just a UI convention, not a
// real model/backend limit (omnivoice_engine forwards `duration` straight to the model).
export const SEGMENT_DURATION_MIN_SEC = 0.5
export const SEGMENT_DURATION_MAX_SEC = 7.0

type RackCandidate = {
  candidate_id: string
  audio_base64: string
  flagged: boolean
  flag_reason: string | null
  duration_sec: number | null | undefined
  whisper_transcript: string | null
  match_score: number | null
}

interface SegmentRackRowProps {
  segIndex: number
  row: {
    segmentId: string
    text: string
    candidates: RackCandidate[]
    selectedTakeIndex: number
    previousBatches?: { durationSec: number; candidates: RackCandidate[] }[]
  }
  isRackAuditioning: boolean
  jobStatus: 'queued' | 'running' | 'completed' | 'failed' | null
  jobCurrentSegmentIndex: number | null
  autoplayTakes: boolean
  segmentDuration: number | null
  onEdit: (segmentId: string, newText: string) => void
  onRegen: (segmentId: string) => void
  onSelectTake: (segmentId: string, index: number) => void
  onSegmentDurationChange: (segmentId: string, duration: number | null) => void
  onSaveToLibrary: (segMeta: SegmentMeta) => void
  isMissingTake: boolean
  instruct: string
  accentId?: string | null
  // Per-candidate tempo choice from each take's SpeedStepper, keyed by candidate_id — lifted
  // up to OmniVoicePanel since Stitch/Save need it, not just this row's own preview.
  candidateSpeeds: Record<string, number>
  onCandidateSpeedChange: (candidateId: string, speed: number) => void
  candidatesPerSegment: number
  avgCandidateSeconds: number | null
  onSelectBatch: (segmentId: string, batchIndex: number) => void
}

const NATURAL_WORDS_PER_SEC = 3

export function SegmentRackRow({
  segIndex,
  row,
  isRackAuditioning,
  jobStatus,
  jobCurrentSegmentIndex,
  autoplayTakes,
  segmentDuration,
  onEdit,
  onRegen,
  onSelectTake,
  onSegmentDurationChange,
  onSaveToLibrary,
  isMissingTake,
  instruct,
  accentId,
  candidateSpeeds,
  onCandidateSpeedChange,
  candidatesPerSegment,
  avgCandidateSeconds,
  onSelectBatch,
}: SegmentRackRowProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(row.text)
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set())
  const isCurrent =
    jobStatus === 'running' &&
    jobCurrentSegmentIndex != null &&
    row.segmentId === `seg-${jobCurrentSegmentIndex}`

  // The box shows the user's explicit override once set; otherwise it falls back to the
  // actual length of the currently selected take, so there's always a starting point to
  // nudge from instead of an empty field.
  const selectedCandidate =
    row.selectedTakeIndex != null ? row.candidates[row.selectedTakeIndex] : undefined
  const actualDurationSec = selectedCandidate?.duration_sec ?? null
  const displayDuration = segmentDuration ?? actualDurationSec ?? null
  const isDirty =
    segmentDuration != null &&
    actualDurationSec != null &&
    Math.abs(segmentDuration - actualDurationSec) > 0.05

  // Pre-regen pacing risk: same speech_rate_proxy formula as audio_style.py (word_count /
  // duration), computed client-side against the *target* duration since this is meant to warn
  // before generation, not just report after it.
  const wordCount = row.text.trim().split(/\s+/).filter(Boolean).length
  const projectedWps =
    displayDuration && displayDuration > 0 ? wordCount / displayDuration : null
  const pacingWarning =
    projectedWps != null && projectedWps > NATURAL_WORDS_PER_SEC
      ? `~${Math.round(((projectedWps - NATURAL_WORDS_PER_SEC) / NATURAL_WORDS_PER_SEC) * 100)}% faster than natural pace — may reduce intelligibility.`
      : null

  const regenCostEstimate =
    avgCandidateSeconds && avgCandidateSeconds > 0
      ? `~${candidatesPerSegment} take${candidatesPerSegment === 1 ? '' : 's'}, ~${Math.round(avgCandidateSeconds * candidatesPerSegment)}s`
      : null

  const handleDurChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = Number(e.target.value)
    if (Number.isNaN(v)) {
      onSegmentDurationChange(row.segmentId, null)
      return
    }
    const clamped = Math.max(SEGMENT_DURATION_MIN_SEC, Math.min(SEGMENT_DURATION_MAX_SEC, v))
    onSegmentDurationChange(row.segmentId, clamped)
  }

  const handleDurBlur = (e: React.FocusEvent<HTMLInputElement>) => {
    const v = Number(e.target.value)
    if (Number.isNaN(v) || v <= 0) {
      onSegmentDurationChange(row.segmentId, segmentDuration ?? null)
      return
    }
    const clamped = Math.max(SEGMENT_DURATION_MIN_SEC, Math.min(SEGMENT_DURATION_MAX_SEC, v))
    onSegmentDurationChange(row.segmentId, clamped)
  }

  const handleDurKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      e.currentTarget.blur()
    }
  }

  return (
    <div
      key={row.segmentId}
      className={cn(
        'flex min-w-0 flex-col gap-1 rounded-md border bg-muted/30 px-2 py-1.5',
        isMissingTake ? 'border-warning/60' : 'border-border',
      )}
    >
      {/* Header */}
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="shrink-0 inline-flex h-4 w-4 items-center justify-center rounded-full bg-muted text-[9px] font-medium">
          {segIndex + 1}
        </span>

        {isCurrent && (
          <span className="shrink-0 inline-flex items-center gap-1 rounded-full border border-primary/60 bg-primary/10 px-1.5 py-0.5 text-[9px] font-semibold text-primary">
            Generating…
          </span>
        )}

        <div className="min-w-0 flex-1">
          {editing ? (
            <input
              autoFocus
              type="text"
              value={draft}
              onChange={(e) =>
                setDraft(e.target.value)
              }
              onBlur={() => {
                onEdit(row.segmentId, draft)
                setEditing(false)
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  onEdit(row.segmentId, draft)
                  setEditing(false)
                }
                if (e.key === 'Escape') {
                  setDraft(row.text)
                  setEditing(false)
                }
              }}
              className="w-full min-w-0 rounded-md border border-input bg-transparent px-2 py-0.5 text-[10px] outline-none focus-visible:border-ring"
            />
          ) : (
            <span
              onClick={() => {
                setEditing(true)
                setDraft(row.text)
              }}
              className="block cursor-text truncate text-[10px] hover:text-foreground"
              title="Click to edit"
            >
              {row.text}
            </span>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {/* Per-segment Duration */}
          <Tooltip.Root>
            <Tooltip.Trigger asChild>
              <div
                className={cn(
                  'relative flex items-center gap-1 rounded-md border px-1.5 py-0.5 transition-colors',
                  isDirty ? 'border-warning/70 bg-warning/10' : 'border-primary/30 bg-primary/5',
                )}
              >
                <span className="text-[9px] font-medium text-primary/80">
                  Duration
                </span>
                <input
                  type="number"
                  min={SEGMENT_DURATION_MIN_SEC}
                  max={SEGMENT_DURATION_MAX_SEC}
                  step={0.1}
                  value={displayDuration != null ? Math.round(displayDuration * 10) / 10 : ''}
                  onChange={handleDurChange}
                  onBlur={handleDurBlur}
                  onKeyDown={handleDurKeyDown}
                  className="w-12 rounded border border-transparent bg-transparent px-1 py-0.5 text-[9px] outline-none transition-colors focus-visible:border-ring"
                />
                <span className="text-[9px] text-muted-foreground">s</span>
                {isDirty && (
                  <span className="absolute -top-1 -right-1 size-1.5 rounded-full bg-warning" />
                )}
                {pacingWarning && (
                  <span className="absolute -top-1 -left-1 size-1.5 rounded-full bg-destructive" />
                )}
              </div>
            </Tooltip.Trigger>
            <Tooltip.Content side="top">
              {pacingWarning
                ? pacingWarning
                : isDirty
                  ? `Currently ${actualDurationSec?.toFixed(1)}s — hit Regen to retarget at ${displayDuration?.toFixed(1)}s.`
                  : 'Target duration for this segment (0.5–7s). Change it, then hit Regen to apply.'}
            </Tooltip.Content>
          </Tooltip.Root>
          {pacingWarning && (
            <span className="shrink-0 text-[9px] text-destructive/80" title={pacingWarning}>
              ⚠
            </span>
          )}

          <button
            type="button"
            onClick={() => {
              setEditing(true)
              setDraft(row.text)
            }}
            className="shrink-0 rounded px-1 py-0.5 text-[9px] text-muted-foreground underline decoration-dotted underline-offset-1 hover:text-foreground"
          >
            ✎
          </button>
          <Tooltip.Root>
            <Tooltip.Trigger asChild>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className={cn(
                  'shrink-0 h-5 px-1.5 text-[9px] transition-all',
                  isDirty && !isRackAuditioning && 'border-warning/70 text-warning hover:text-warning',
                )}
                onClick={() =>
                  onRegen(row.segmentId)
                }
                disabled={isRackAuditioning}
              >
                {isRackAuditioning
                  ? (
                      <span className="flex items-center gap-1">
                        <span className="h-2.5 w-2.5 animate-spin rounded-full border-[1.5px] border-muted-foreground/90 border-t-transparent" />
                        Regen
                      </span>
                    )
                  : 'Regen'}
              </Button>
            </Tooltip.Trigger>
            <Tooltip.Content side="left">
              {isRackAuditioning
                ? 'Regenerate this segment after current job finishes.'
                : [
                    isDirty
                      ? 'Duration changed — regenerate to apply the new target length.'
                      : 'Regenerate this segment with current settings.',
                    regenCostEstimate,
                  ]
                    .filter(Boolean)
                    .join(' ')}
            </Tooltip.Content>
          </Tooltip.Root>
          {regenCostEstimate && (
            <span className="shrink-0 text-[9px] text-muted-foreground/70">
              {regenCostEstimate}
            </span>
          )}
        </div>
      </div>

      {/* Batch selector — one pill per duration a Regen was run at, most recent first;
          lets the user flip back to a prior batch instead of it being silently discarded. */}
      {row.previousBatches != null && row.previousBatches.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="shrink-0 text-[9px] text-muted-foreground/70">Batches:</span>
          <span className="shrink-0 rounded-full border border-[hsl(190,90%,50%)]/50 bg-[hsl(190,90%,50%)]/10 px-1.5 py-0.5 text-[9px] font-medium text-[hsl(190,90%,50%)]">
            current{actualDurationSec != null ? ` (${actualDurationSec.toFixed(1)}s)` : ''}
          </span>
          {row.previousBatches.map((batch, bi) => (
            <button
              key={bi}
              type="button"
              onClick={() => onSelectBatch(row.segmentId, bi)}
              className="shrink-0 rounded-full border border-border/70 bg-muted/50 px-1.5 py-0.5 text-[9px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              {batch.durationSec.toFixed(1)}s
            </button>
          ))}
        </div>
      )}

      {/* Takes */}
      {row.candidates.length > 0 && (() => {
        const allFlagged = row.candidates.every(c => c.flagged)
        if (allFlagged) {
          return (
            <div className="flex min-w-0 items-center gap-1.5 rounded-md border border-border/70 bg-muted/40 px-1.5 py-1">
              <span className="text-[9px] text-muted-foreground">
                No usable audio generated — try again or adjust text/parameters.
              </span>
            </div>
          )
        }

        return (
          <div className="flex min-w-0 flex-col gap-1">
            {row.candidates.map((c, ci) => {
              const selected = ci === row.selectedTakeIndex
              const isFlagged = !!c.flagged

              // Simple debug info for this candidate
              const debugLines: string[] = []
              if (isFlagged) {
                debugLines.push(`Flag: ${c.flag_reason || "no-speech"}`)
              } else {
                debugLines.push("Flag: ok")
              }
              if (c.whisper_transcript) {
                debugLines.push(`Whisper: "${c.whisper_transcript}"`)
              } else {
                debugLines.push("Whisper: (no speech detected)")
              }
              if (c.match_score != null) {
                const label =
                  c.match_score >= 0.9
                    ? "Match: " + c.match_score.toFixed(2) + " (strong)"
                    : c.match_score >= 0.7
                      ? "Match: " + c.match_score.toFixed(2) + " (ok)"
                      : "Match: " + c.match_score.toFixed(2) + " (low)"
                debugLines.push(label)
              }

              if (isFlagged) {
                return (
                  <div
                    key={c.candidate_id}
                    className="flex min-w-0 items-center gap-1.5 rounded-md border border-border/60 bg-muted/40 px-1.5 py-1 opacity-70"
                  >
                    <span
                      className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground"
                    >
                      T{ci + 1}
                    </span>
                    <Tooltip.Root>
                      <Tooltip.Trigger asChild>
                        <div>
                          <span
                            className="shrink-0 rounded-full border border-warning/50 bg-warning/30 px-1 py-0.5 text-[9px] text-warning"
                          >
                            no-speech
                          </span>
                        </div>
                      </Tooltip.Trigger>
                      <Tooltip.Content side="top">
                        No speech detected after 3 attempts (ASR + quality check).
                      </Tooltip.Content>
                    </Tooltip.Root>
                    <span className="text-[9px] text-muted-foreground">
                      No usable audio (3 attempts)
                    </span>

                    <TakeDebugButton lines={debugLines} matchScore={c.match_score} />
                  </div>
                )
              }

              return (
                <div
                  key={c.candidate_id}
                  data-testid="omnivoice-candidate-take"
                  className={cn(
                    'flex min-w-0 flex-col gap-1.5 rounded-md border px-1.5 py-1.5 transition-all',
                    selected
                      ? 'border-[hsl(190,90%,50%)] bg-[hsl(190,90%,50%)]/5 shadow-[0_0_10px_rgba(34,211,238,0.12)]'
                      : 'border-border/60 bg-background',
                  )}
                >
                  <div className="flex min-w-0 items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() =>
                        onSelectTake(row.segmentId, ci)
                      }
                      className={cn(
                        'shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium transition-colors',
                        selected
                          ? 'bg-[hsl(190,90%,50%)] text-background'
                          : 'bg-muted text-muted-foreground hover:bg-muted/80',
                      )}
                    >
                      T{ci + 1}
                    </button>

                    <TakeDebugButton lines={debugLines} matchScore={c.match_score} />

                    <Tooltip.Root>
                      <Tooltip.Trigger asChild>
                        <button
                          type="button"
                          data-testid="omnivoice-lock-segment"
                          disabled={savedIds.has(c.candidate_id)}
                          onClick={async () => {
                            try {
                              const meta = await lockInOmniVoiceSegment({
                                candidateId: c.candidate_id,
                                text: row.text,
                                instruct,
                                accentId,
                                featureTags: lookupFeatureTags(accentId, row.text),
                              })
                              setSavedIds((prev) => {
                                const next = new Set(prev)
                                next.add(c.candidate_id)
                                return next
                              })
                              onSaveToLibrary(meta)
                            } catch {
                              // Non-fatal: API will show its own error at global level
                            }
                          }}
                          className={cn(
                            'ml-auto shrink-0 inline-flex h-5 w-5 items-center justify-center rounded-full border border-border bg-muted/60 text-[9px] text-muted-foreground transition-colors',
                            savedIds.has(c.candidate_id)
                              ? 'border-success/60 bg-success/10 text-success'
                              : 'hover:bg-muted hover:text-foreground disabled:opacity-60',
                          )}
                        >
                          {savedIds.has(c.candidate_id)
                            ? <Check className="size-3" />
                            : '🔖'}
                        </button>
                      </Tooltip.Trigger>
                      <Tooltip.Content side="top" align="end">
                        {savedIds.has(c.candidate_id)
                          ? 'Saved to segment library'
                          : 'Save this take to segment library'}
                      </Tooltip.Content>
                    </Tooltip.Root>
                  </div>

                  <ClipPlayer
                    audioBase64={c.audio_base64 || undefined}
                    audioUrl={
                      !c.audio_base64
                        ? `/omnivoice/segments/${encodeURIComponent(row.segmentId)}/audio`
                        : undefined
                    }
                    className="min-w-0"
                    autoPlay={selected && autoplayTakes && Boolean(c.audio_base64)}
                    layout="stacked"
                    showSpectralAccent={false}
                    initialSpeed={candidateSpeeds[c.candidate_id] ?? 1}
                    onSpeedChange={(speed) => onCandidateSpeedChange(c.candidate_id, speed)}
                  />
                </div>
              )
            })}
          </div>
        )
      })()}
    </div>
  )
}

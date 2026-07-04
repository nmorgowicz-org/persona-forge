import {
  useEffect,
  useMemo,
  useCallback,
  useState,
} from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { FlaskConical } from 'lucide-react'
import {
  auditionOmniVoiceStreaming,
  deleteOmniVoiceSegment,
  getOmniVoiceAuditionProgress,
  listOmniVoiceSegments,
  saveOmniVoice,
  stitchOmniVoice,
} from '@/lib/api'
import {
  ACCENT_BANK,
  type AccentBankEntry,
  type ShowcaseSentence,
} from '@/lib/accentBank'
import {
  ACCENTS,
  AGES,
  GENDERS,
  PITCHES,
  STYLE_WHISPER,
  composeInstruct,
  selectionsFromInstruct,
} from '@/lib/omnivoiceChips'
import { ChipButton } from './Chip'
import { AudioPlayer } from './AudioPlayer'
import { Button } from '@/components/ui/button'
import { base64ToBlob, cn } from '@/lib/utils'
import { useAppStore } from '@/store'
import { TooltipProvider } from '@/components/ui/tooltip'
import * as Tooltip from '@/components/ui/tooltip'

const DEFAULT_ACCENT = ACCENT_BANK[0] ?? null

const NON_VERBAL_TAGS = [
  '[laughter]',
  '[sigh]',
  '[confirmation-en]',
  '[question-en]',
  '[question-ah]',
  '[question-oh]',
  '[question-ei]',
  '[question-yi]',
  '[surprise-ah]',
  '[surprise-oh]',
  '[surprise-wa]',
  '[surprise-yo]',
  '[dissatisfaction-hnn]',
]

function formatEta(seconds: number | null): string {
  if (seconds == null) return 'estimating…'
  if (seconds < 1) return 'almost done'
  if (seconds < 60) return `~${Math.round(seconds)}s remaining`
  return `~${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s remaining`
}

function ClipPlayer({
  audioBase64,
  className,
  autoPlay = false,
}: {
  audioBase64: string
  className?: string
  autoPlay?: boolean
}) {
  const blob = useMemo(() => base64ToBlob(audioBase64), [audioBase64])
  const src = useMemo(
    () => `data:audio/wav;base64,${audioBase64}`,
    [audioBase64],
  )
  return (
    <AudioPlayer
      src={src}
      blob={blob}
      autoPlay={autoPlay}
      className={className}
    />
  )
}

function InfoIcon({ text }: { text: string }) {
  return (
    <TooltipProvider delayDuration={60} skipDelayDuration={0}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span
            className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full border border-muted-foreground/40 text-[10px] font-medium text-muted-foreground/70 transition-colors hover:border-muted-foreground hover:text-muted-foreground cursor-help"
          >
            ?
          </span>
        </Tooltip.Trigger>
        <Tooltip.Content side="top" align="start">
          {text}
        </Tooltip.Content>
      </Tooltip.Root>
    </TooltipProvider>
  )
}

interface SegmentRackRowProps {
  segIndex: number
  row: {
    segmentId: string
    text: string
    candidates: { candidate_id: string; audio_base64: string; flagged: boolean; flag_reason: string | null; duration_sec: number | null | undefined; whisper_transcript: string | null; match_score: number | null }[]
    selectedTakeIndex: number
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
}

// Surfaces the ASR (Whisper) transcript + match-score confidence the backend computed for a
// take, plus its flag status. The match score renders inline (not just on hover) so a low-
// confidence take is visible at a glance, not just buried in a tooltip.
function TakeDebugButton({
  lines,
  matchScore,
}: {
  lines: string[]
  matchScore?: number | null
}) {
  const scoreColor =
    matchScore == null
      ? 'text-muted-foreground'
      : matchScore >= 0.9
        ? 'text-emerald-400'
        : matchScore >= 0.7
          ? 'text-amber-400'
          : 'text-red-400'
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <button
          type="button"
          className={cn(
            'ml-auto flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[9px] transition-colors hover:bg-muted/60',
            scoreColor,
          )}
        >
          <FlaskConical className="size-2.5" />
          {matchScore != null && <span className="font-mono">{matchScore.toFixed(2)}</span>}
        </button>
      </Tooltip.Trigger>
      <Tooltip.Content side="top" align="end">
        <div className="flex flex-col gap-0.5 text-[9px]">
          {lines.map((l, i) => (
            <div key={i}>{l}</div>
          ))}
        </div>
      </Tooltip.Content>
    </Tooltip.Root>
  )
}

function SegmentRackRow({
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
}: SegmentRackRowProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(row.text)
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

  const handleDurChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = Number(e.target.value)
    if (Number.isNaN(v)) {
      onSegmentDurationChange(row.segmentId, null)
      return
    }
    const clamped = Math.max(0.5, Math.min(4.0, v))
    onSegmentDurationChange(row.segmentId, clamped)
  }

  const handleDurBlur = (e: React.FocusEvent<HTMLInputElement>) => {
    const v = Number(e.target.value)
    if (Number.isNaN(v) || v <= 0) {
      onSegmentDurationChange(row.segmentId, segmentDuration ?? null)
      return
    }
    const clamped = Math.max(0.5, Math.min(4.0, v))
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
      className="flex min-w-0 flex-col gap-1 rounded-md border border-border bg-muted/30 px-2 py-1.5"
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
            <span className="block truncate text-[10px]">
              {row.text}
            </span>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {/* Per-segment Duration */}
          <Tooltip.Root>
            <Tooltip.Trigger asChild>
              <div className="relative flex items-center gap-0.5">
                <span className="text-[9px] text-muted-foreground">
                  Duration
                </span>
                <input
                  type="number"
                  min={0.5}
                  max={4}
                  step={0.1}
                  value={displayDuration != null ? Math.round(displayDuration * 10) / 10 : ''}
                  onChange={handleDurChange}
                  onBlur={handleDurBlur}
                  onKeyDown={handleDurKeyDown}
                  className={cn(
                    'w-14 rounded-md border bg-transparent px-1 py-0.5 text-[9px] outline-none transition-colors focus-visible:border-ring',
                    isDirty ? 'border-amber-500/70' : 'border-input',
                  )}
                />
                {isDirty && (
                  <span className="absolute -top-1 -right-1 size-1.5 rounded-full bg-amber-500" />
                )}
              </div>
            </Tooltip.Trigger>
            <Tooltip.Content side="top">
              {isDirty
                ? `Currently ${actualDurationSec?.toFixed(1)}s — hit Regen to retarget at ${displayDuration?.toFixed(1)}s.`
                : 'Target duration for this segment (0.5–4s). Change it, then hit Regen to apply.'}
            </Tooltip.Content>
          </Tooltip.Root>

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
                  isDirty && !isRackAuditioning && 'border-amber-500/70 text-amber-500 hover:text-amber-400',
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
                : isDirty
                  ? 'Duration changed — regenerate to apply the new target length.'
                  : 'Regenerate this segment with current settings.'}
            </Tooltip.Content>
          </Tooltip.Root>
        </div>
      </div>

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
                            className="shrink-0 rounded-full border border-amber-900/50 bg-amber-950/30 px-1 py-0.5 text-[9px] text-amber-300"
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
                  className={cn(
                    'flex min-w-0 items-center gap-1 rounded-md border px-1.5 py-1 transition-all',
                    selected
                      ? 'border-[hsl(190,90%,50%)] bg-[hsl(190,90%,50%)]/5 shadow-[0_0_10px_rgba(34,211,238,0.12)]'
                      : 'border-border/60 bg-background',
                  )}
                >
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

                  <ClipPlayer
                    audioBase64={c.audio_base64}
                    className="min-w-0 flex-1"
                    autoPlay={selected && autoplayTakes}
                  />

                  <TakeDebugButton lines={debugLines} matchScore={c.match_score} />
                </div>
              )
            })}
          </div>
        )
      })()}
    </div>
  )
}

interface PersonaForgePanelProps {
  onVoiceCreated?: (voiceId: string) => void
}

export function PersonaForgePanel({ onVoiceCreated }: PersonaForgePanelProps) {
  // -- State from store --
  const selections = useAppStore((s) => s.ovSelections)
  const candidatesPerSegment = useAppStore(
    (s) => s.ovCandidatesPerSegment,
  )
  const showAdvanced = useAppStore((s) => s.ovShowAdvanced)
  const numStepInput = useAppStore((s) => s.ovNumStepInput)
  const speedInput = useAppStore((s) => s.ovSpeedInput)
  const guidanceScaleInput = useAppStore(
    (s) => s.ovGuidanceScaleInput,
  )
  const diverseCandidates = useAppStore(
    (s) => s.ovDiverseCandidates,
  )
  const scriptText = useAppStore((s) => s.ovScriptText)
  const segmentRack = useAppStore((s) => s.ovSegmentRack)
  const isRackAuditioning = useAppStore(
    (s) => s.ovIsRackAuditioning,
  )
  const lockedSegments = useAppStore((s) => s.ovLockedSegments)
  const isStitching = useAppStore((s) => s.ovIsStitching)
  const isSaving = useAppStore((s) => s.ovIsSaving)
  const modelLoaded = useAppStore((s) => s.modelLoaded)
  const error = useAppStore((s) => s.ovError)
  const stitchedUrl = useAppStore((s) => s.ovStitchedUrl)
  const stitchedBlob = useAppStore((s) => s.ovStitchedBlob)
  const savedVoiceId = useAppStore((s) => s.ovSavedVoiceId)
  const progress = useAppStore((s) => s.ovProgress)
  // Intentionally subscribed to keep Zustand batched; value used via store hooks in this component.
  useAppStore((s) => s.ovCurrentJobId)
  const jobTotalSegments = useAppStore((s) => s.ovJobTotalSegments)
  const jobStatus = useAppStore((s) => s.ovJobStatus)
  const jobSegmentsCompleted = useAppStore(
    (s) => s.ovJobSegmentsCompleted,
  )
  const jobCurrentSegmentIndex = useAppStore(
    (s) => s.ovJobCurrentSegmentIndex,
  )
  // Intentionally subscribed (Zustand batching); used in this component.
  useAppStore((s) => s.ovJobMessage)
  const jobEtaSeconds = useAppStore((s) => s.ovJobEtaSeconds)
  const jobCandidatesTotal = useAppStore((s) => s.ovJobCandidatesTotal)
  const jobCandidatesCompleted = useAppStore((s) => s.ovJobCandidatesCompleted)
  const autoplayTakes = useAppStore((s) => s.ovAutoplayTakes)
  const setAutoplayTakes = useAppStore(
    (s) => s.setOvAutoplayTakes,
  )
  const setActivityStatus = useAppStore(
    (s) => s.setActivityStatus,
  )
  const library = useAppStore((s) => s.ovLibrary)
  const libraryFilter = useAppStore((s) => s.ovLibraryFilter)
  const isLibraryOpen = useAppStore((s) => s.ovIsLibraryOpen)
  const librarySelection = useAppStore(
    (s) => s.ovLibrarySelection,
  )

  const setSelections = useAppStore((s) => s.setOvSelections)
  const setCandidatesPerSegment = useAppStore(
    (s) => s.setOvCandidatesPerSegment,
  )
  const setShowAdvanced = useAppStore(
    (s) => s.setOvShowAdvanced,
  )
  const setNumStepInput = useAppStore(
    (s) => s.setOvNumStepInput,
  )
  const setSpeedInput = useAppStore((s) => s.setOvSpeedInput)
  const setGuidanceScaleInput = useAppStore(
    (s) => s.setOvGuidanceScaleInput,
  )
  const setDiverseCandidates = useAppStore(
    (s) => s.setOvDiverseCandidates,
  )
  const setScriptText = useAppStore((s) => s.setOvScriptText)
  const setSegmentRack = useAppStore(
    (s) => s.setOvSegmentRack,
  )
  const setIsRackAuditioning = useAppStore(
    (s) => s.setOvIsRackAuditioning,
  )
  const setLockedSegments = useAppStore(
    (s) => s.setOvLockedSegments,
  )
  const setIsStitching = useAppStore((s) => s.setOvIsStitching)
  const setIsSaving = useAppStore((s) => s.setOvIsSaving)
  const setError = useAppStore((s) => s.setOvError)
  const setStitchedUrl = useAppStore((s) => s.setOvStitchedUrl)
  const setStitchedBlob = useAppStore(
    (s) => s.setOvStitchedBlob,
  )
  const setSavedVoiceId = useAppStore(
    (s) => s.setOvSavedVoiceId,
  )
  const setProgress = useAppStore((s) => s.setOvProgress)
  const setCurrentJobId = useAppStore(
    (s) => s.setOvCurrentJobId,
  )
  const setJobTotalSegments = useAppStore(
    (s) => s.setOvJobTotalSegments,
  )
  const setJobStatus = useAppStore(
    (s) => s.setOvJobStatus,
  )
  const setJobSegmentsCompleted = useAppStore(
    (s) => s.setOvJobSegmentsCompleted,
  )
  const setJobCurrentSegmentIndex = useAppStore(
    (s) => s.setOvJobCurrentSegmentIndex,
  )
  const setJobMessage = useAppStore(
    (s) => s.setOvJobMessage,
  )
  const setJobEtaSeconds = useAppStore(
    (s) => s.setOvJobEtaSeconds,
  )
  const setJobCandidatesTotal = useAppStore(
    (s) => s.setOvJobCandidatesTotal,
  )
  const setJobCandidatesCompleted = useAppStore(
    (s) => s.setOvJobCandidatesCompleted,
  )
  const setJobCurrentCandidateIndex = useAppStore(
    (s) => s.setOvJobCurrentCandidateIndex,
  )
  const setLibrary = useAppStore((s) => s.setOvLibrary)
  const setLibraryFilter = useAppStore(
    (s) => s.setOvLibraryFilter,
  )
  const setIsLibraryOpen = useAppStore(
    (s) => s.setOvIsLibraryOpen,
  )
  const setLibrarySelection = useAppStore(
    (s) => s.setOvLibrarySelection,
  )

  // -- Init --
  const initRef = useMemo(() => ({ done: false }), [])

  if (!initRef.done) {
    initRef.done = true
    if (
      DEFAULT_ACCENT &&
      selections.gender == null &&
      selections.age == null &&
      selections.accent == null
    ) {
      setSelections(selectionsFromInstruct(DEFAULT_ACCENT.instruct))
    }
  }

  // Load library on mount
  useEffect(() => {
    const load = async () => {
      try {
        setLibrary(await listOmniVoiceSegments())
      } catch {
        // Non-fatal
      }
    }
    load()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // -- Derived --
  const instruct = useMemo(
    () => composeInstruct(selections),
    [selections],
  )

  const matchedAccentBankEntry = useMemo(
    () =>
      ACCENT_BANK.find(
        (entry) =>
          selectionsFromInstruct(entry.instruct).accent ===
          selections.accent,
      ) ?? null,
    [selections.accent],
  )

  const lines = scriptText
    .split(/\n/)
    .map((l) => l.trim())
    .filter(Boolean)

  const scriptWordCount = scriptText
    .trim()
    ? scriptText.trim().split(/\s+/).length
    : 0

  const hasLongLines =
    lines.some(
      (l) => l.length > 120 || l.split(/\s+/).length > 15,
    )

  const filteredLibrary = libraryFilter.trim()
    ? library.filter((m) =>
        m.tags.some((t) =>
          t
            .toLowerCase()
            .includes(
              libraryFilter.trim().toLowerCase(),
            ),
        ),
      )
    : library

  const activeShowcaseSentences =
    matchedAccentBankEntry?.showcaseSentences ?? []

  // -- Script composer state --
  const [scriptRef, setScriptRef] = useState<HTMLTextAreaElement | null>(null)
  const [tagsOpen, setTagsOpen] = useState(false)
  const [examplesOpen, setExamplesOpen] = useState(false)
  const [segmentDurations, setSegmentDurations] = useState<
    Record<string, number | null>
  >({})
  const [postProcess, setPostProcess] = useState(true)
  const anySegmentHasDuration = Object.values(segmentDurations).some(
    (d) => d != null,
  )



  // -- Handlers --
  const insertAtCursor = useCallback(
    (insert: string) => {
      const el = scriptRef
      if (!el) {
        setScriptText((prev) =>
          prev.trim()
            ? prev.trim() + ' ' + insert
            : insert,
        )
        return
      }
      const start = el.selectionStart
      const end = el.selectionEnd
      const before = scriptText.slice(0, start)
      const after = scriptText.slice(end)

      const needsSpaceBefore =
        before.length > 0 && !/[\s\n]/.test(before[before.length - 1])
      const needsSpaceAfter =
        after.length > 0 && !/[\s\n]/.test(after[0])

      const next =
        before +
        (needsSpaceBefore ? ' ' : '') +
        insert +
        (needsSpaceAfter ? ' ' : '') +
        after

      setScriptText(next)
      // Restore cursor
      requestAnimationFrame(() => {
        const pos =
          start +
          (needsSpaceBefore ? 1 : 0) +
          insert.length +
          (needsSpaceAfter ? 1 : 0)
        el.focus()
        el.setSelectionRange(pos, pos)
      })
    },
    [scriptRef, scriptText, setScriptText],
  )

  const insertExampleSentence = useCallback(
    (sentence: ShowcaseSentence) => {
      const insert = sentence.text
      const el = scriptRef

      if (scriptText.trim()) {
        // Insert as new line
        const newline = '\n' + insert
        if (!el) {
          setScriptText((prev) => prev.trim() + newline)
          return
        }
        const start = el.selectionStart
        const before = scriptText.slice(0, start)
        const after = scriptText.slice(start)
        const next = before + newline + after
        setScriptText(next)
        requestAnimationFrame(() => {
          const pos = start + newline.length
          el.focus()
          el.setSelectionRange(pos, pos)
        })
      } else {
        insertAtCursor(insert)
      }
    },
    [scriptRef, scriptText, setScriptText, insertAtCursor],
  )

  const insertNonVerbalTag = useCallback(
    (tag: string) => {
      insertAtCursor(tag)
    },
    [insertAtCursor],
  )
  const refreshLibrary = useCallback(async () => {
    try {
      setLibrary(await listOmniVoiceSegments())
    } catch (err) {
      setError(
        err instanceof Error ? err.message : String(err),
      )
    }
  }, [setLibrary, setError])

  const applyAccentPreset = useCallback(
    (entry: AccentBankEntry) => {
      setSelections(selectionsFromInstruct(entry.instruct))
      setLockedSegments([])
      setScriptText('')
      setSegmentRack([])
      setStitchedUrl(null)
      setSavedVoiceId(null)
      setError(null)
    },
    [
      setSelections,
      setLockedSegments,
      setScriptText,
      setSegmentRack,
      setStitchedUrl,
      setSavedVoiceId,
      setError,
    ],
  )

  const toggleSingle = useCallback(
    (
      key: 'gender' | 'age' | 'pitch' | 'accent',
      id: string,
    ) => {
      setSelections((prev) => ({
        ...prev,
        [key]: prev[key] === id ? null : id,
      }))
    },
    [setSelections],
  )

  const toggleWhisper = useCallback(() => {
    setSelections((prev) => ({
      ...prev,
      whisper: !prev.whisper,
    }))
  }, [setSelections])

  const splitScriptToSegments = useCallback(
    (text: string): string[] => {
      return text
        .split(/\n/)
        .map((l) => l.trim())
        .filter(Boolean)
        .flatMap((line) => {
          if (line.split(/\s+/).length <= 15) return [line]
          // Rough sentence-split fallback
          const parts = line
            .split(/(?<=[.!?])\s+/)
            .map((p) => p.trim())
            .filter(Boolean)
          return parts.length > 1
            ? parts
            : [line]
        })
    },
    [],
  )

  const handleBatchAudition = useCallback(async () => {
    const text = scriptText.trim()
    if (!text || !instruct || isRackAuditioning) return

    const segments = splitScriptToSegments(text)
    if (segments.length === 0) return

    setIsRackAuditioning(true)
    setError(null)
    setSegmentRack([])
    setProgress(null)
    setJobMessage(null)
    setJobStatus(null)
    setJobSegmentsCompleted([])
    setJobCurrentSegmentIndex(null)

    try {
        const durations = segments.map(
          (_, i) => segmentDurations[`seg-${i}`] ?? null,
        )

        const { job_id, total_segments } =
          await auditionOmniVoiceStreaming({
            segments,
            instruct,
            candidatesPerSegment,
            numStep: numStepInput.trim()
              ? Number(numStepInput)
              : undefined,
            speed: speedInput.trim()
              ? Number(speedInput)
              : undefined,
            guidanceScale: guidanceScaleInput.trim()
              ? Number(guidanceScaleInput)
              : undefined,
            diverseCandidates,
            durations,
            postprocessOutput: postProcess || null,
          })

        setCurrentJobId(job_id)
        setJobTotalSegments(total_segments)
        setJobStatus('running')
        setExamplesOpen(false)
        setTagsOpen(false)

        const jobDone = false
        let lastHandledCount = 0

        while (!jobDone) {
          const p = await getOmniVoiceAuditionProgress(
            job_id,
          )
          setJobStatus(p.status)
          setJobCurrentSegmentIndex(
            p.current_segment_index,
          )
          setJobSegmentsCompleted(p.segments_completed)
          setJobMessage(p.message || null)
          setJobEtaSeconds(
            p.eta ?? p.estimated_remaining_seconds ?? null,
          )
          if (typeof p.total_candidates === 'number')
            setJobCandidatesTotal(p.total_candidates)
          if (typeof p.completed_candidates === 'number')
            setJobCandidatesCompleted(p.completed_candidates)
          if (typeof p.current_candidate_index === 'number')
            setJobCurrentCandidateIndex(p.current_candidate_index)

          if (
            p.segments_completed.length >
            lastHandledCount
          ) {
            setSegmentRack((prev) => {
              const next = [...prev]
              const existingIds = new Set(
                next.map(
                  (r) => r.segmentId,
                ),
              )
              for (const s of p.segments_completed || []) {
                const segId = `seg-${s.segment_index}`
                if (!existingIds.has(segId)) {
                  const candidates =
                    Array.isArray(s.candidates)
                      ? s.candidates
                      : []
                  next.push({
                    segmentId: segId,
                    text: s.text || '',
                    candidates,
                    selectedTakeIndex:
                      candidates.length > 0
                        ? 0
                        : -1,
                  })
                }
              }
              return next
            })
            lastHandledCount =
              p.segments_completed.length
          }

        if (p.status === 'completed') {
          // Finalize: keep segment rack + completed list intact
          setIsRackAuditioning(false)
          setProgress(null)
          setCurrentJobId(null)
          setJobStatus('completed')
          setJobCurrentSegmentIndex(null)
          setJobMessage('All segments generated.')
          break
        }
        if (p.status === 'failed') {
          setError(
            p.message ||
              'OmniVoice job failed.',
          )
          break
        }
        await new Promise(
          (r) => setTimeout(r, 500),
        )
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : String(err),
      )
      // On error: fully reset
      setIsRackAuditioning(false)
      setProgress(null)
      setCurrentJobId(null)
      setJobStatus(null)
      setJobTotalSegments(0)
      setJobSegmentsCompleted([])
      setJobCurrentSegmentIndex(null)
      setJobMessage(null)
      setJobEtaSeconds(null)
      setJobCandidatesTotal(0)
      setJobCandidatesCompleted(0)
      setJobCurrentCandidateIndex(null)
    }
  }, [
    scriptText,
    instruct,
    isRackAuditioning,
    splitScriptToSegments,
    candidatesPerSegment,
    numStepInput,
    speedInput,
    guidanceScaleInput,
    diverseCandidates,
    segmentDurations,
    postProcess,
    setIsRackAuditioning,
    setError,
    setSegmentRack,
    setProgress,
    setCurrentJobId,
    setJobTotalSegments,
    setJobStatus,
    setJobSegmentsCompleted,
    setJobCurrentSegmentIndex,
    setJobMessage,
    setJobEtaSeconds,
    setJobCandidatesTotal,
    setJobCandidatesCompleted,
    setJobCurrentCandidateIndex,
  ])

  const selectTake = useCallback(
    (segmentId: string, index: number) => {
      setSegmentRack((prev) =>
        prev.map((row) => {
          if (row.segmentId !== segmentId) return row
          // Toggle: clicking the same take again deselects it
          const next = row.selectedTakeIndex === index ? -1 : index
          return { ...row, selectedTakeIndex: next }
        }),
      )
    },
    [setSegmentRack],
  )

  const editSegmentText = useCallback(
    (segmentId: string, newText: string) => {
      setSegmentRack((prev) =>
        prev.map((row) =>
          row.segmentId === segmentId
            ? { ...row, text: newText }
            : row,
        ),
      )
    },
    [setSegmentRack],
  )

  const regenerateSegment = useCallback(
    async (segmentId: string) => {
      const row = segmentRack.find(
        (r) => r.segmentId === segmentId,
      )
      if (!row || isRackAuditioning) return

      setIsRackAuditioning(true)
      setError(null)
      setProgress(null)
      setJobMessage(null)
      setJobStatus(null)
      setJobSegmentsCompleted([])
      setJobCurrentSegmentIndex(null)

      try {
        const segDuration =
          segmentDurations[row.segmentId] ?? null

        const { job_id } =
          await auditionOmniVoiceStreaming({
            segments: [row.text],
            instruct,
            candidatesPerSegment,
            numStep: numStepInput.trim()
              ? Number(numStepInput)
              : undefined,
            speed: speedInput.trim()
              ? Number(speedInput)
              : undefined,
            guidanceScale: guidanceScaleInput.trim()
              ? Number(guidanceScaleInput)
              : undefined,
            diverseCandidates,
            durations: [segDuration],
            postprocessOutput: postProcess || null,
          })

        setCurrentJobId(job_id)
        setJobTotalSegments(1)
        setJobStatus('running')
        setExamplesOpen(false)
        setTagsOpen(false)

        while (true) {
          const p = await getOmniVoiceAuditionProgress(
            job_id,
          )
          setJobStatus(p.status)
          setJobCurrentSegmentIndex(
            p.current_segment_index,
          )
          setJobSegmentsCompleted(p.segments_completed)
          setJobEtaSeconds(
            p.eta ?? p.estimated_remaining_seconds ?? null,
          )
          if (typeof p.total_candidates === 'number')
            setJobCandidatesTotal(p.total_candidates)
          if (typeof p.completed_candidates === 'number')
            setJobCandidatesCompleted(p.completed_candidates)
          if (typeof p.current_candidate_index === 'number')
            setJobCurrentCandidateIndex(p.current_candidate_index)

          if (p.status === 'completed') {
            const seg = p.segments_completed[0]
            if (seg) {
              setSegmentRack((prev) =>
                prev.map((r) =>
                  r.segmentId ===
                  segmentId
                    ? {
                        ...r,
                        candidates:
                          seg.candidates,
                        selectedTakeIndex:
                          0,
                      }
                    : r,
                ),
              )
            }
            // Clean up for single-seg regen
            setIsRackAuditioning(false)
            setProgress(null)
            setCurrentJobId(null)
            setJobStatus(null)
            setJobTotalSegments(0)
            setJobSegmentsCompleted([])
            setJobCurrentSegmentIndex(null)
            setJobMessage(null)
            setJobEtaSeconds(null)
            setJobCandidatesTotal(0)
            setJobCandidatesCompleted(0)
            setJobCurrentCandidateIndex(null)
            break
          }
          if (p.status === 'failed') {
            setError(
              p.message ||
                'OmniVoice job failed.',
            )
            break
          }
          await new Promise(
            (r) => setTimeout(r, 500),
          )
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : String(err),
        )
        setIsRackAuditioning(false)
        setProgress(null)
        setCurrentJobId(null)
        setJobStatus(null)
        setJobTotalSegments(0)
        setJobSegmentsCompleted([])
        setJobCurrentSegmentIndex(null)
        setJobMessage(null)
        setJobEtaSeconds(null)
        setJobCandidatesTotal(0)
        setJobCandidatesCompleted(0)
        setJobCurrentCandidateIndex(null)
      }
    },
    [
      segmentRack,
      isRackAuditioning,
      instruct,
      candidatesPerSegment,
      numStepInput,
      speedInput,
      guidanceScaleInput,
      diverseCandidates,
      segmentDurations,
      postProcess,
      setIsRackAuditioning,
      setError,
      setSegmentRack,
      setProgress,
      setCurrentJobId,
      setJobTotalSegments,
      setJobStatus,
      setJobSegmentsCompleted,
      setJobCurrentSegmentIndex,
      setJobMessage,
      setJobEtaSeconds,
      setJobCandidatesTotal,
      setJobCandidatesCompleted,
      setJobCurrentCandidateIndex,
    ],
  )

  const onSegmentDurationChange = useCallback(
    (segmentId: string, value: number | null) => {
      setSegmentDurations((prev) => {
        if (value == null || value <= 0) {
          const next = { ...prev }
          delete next[segmentId]
          return next
        }
        const clamped = Math.max(0.5, Math.min(4, value))
        return { ...prev, [segmentId]: clamped }
      })
    },
    [],
  )

  const handleStitch = useCallback(async () => {
    if (segmentRack.length === 0 || isStitching) return

    const selectedCandidates = segmentRack.map(
      (row) =>
        row.candidates[row.selectedTakeIndex],
    )

    if (
      selectedCandidates.some(
        (c) => !c || !c.candidate_id,
      )
    ) {
      setError('Select a take for each segment first.')
      return
    }

    setIsStitching(true)
    setError(null)
    setSavedVoiceId(null)
    try {
      const candidateIds = selectedCandidates.map(
        (c) => c.candidate_id,
      )
      const blob = await stitchOmniVoice(candidateIds)
      setStitchedUrl(URL.createObjectURL(blob))
      setStitchedBlob(blob)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : String(err),
      )
    } finally {
      setIsStitching(false)
    }
  }, [
    segmentRack,
    isStitching,
    setIsStitching,
    setError,
    setSavedVoiceId,
    setStitchedUrl,
    setStitchedBlob,
  ])

  const handleSave = useCallback(async () => {
    if (segmentRack.length === 0 || isSaving) return

    const segments = segmentRack.map((r) => r.text)

    const selectedCandidates = segmentRack.map(
      (row) =>
        row.candidates[row.selectedTakeIndex],
    )

    if (
      selectedCandidates.some(
        (c) => !c || !c.candidate_id,
      )
    ) {
      setError('Select a take for each segment first.')
      return
    }

    setIsSaving(true)
    setError(null)
    try {
      const candidateIds = selectedCandidates.map(
        (c) => c.candidate_id,
      )
      const result = await saveOmniVoice({
        selections: candidateIds,
        instruct,
        segments,
        accentId:
          matchedAccentBankEntry?.id ?? null,
      })
      setSavedVoiceId(result.voice_id)
      onVoiceCreated?.(result.voice_id)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : String(err),
      )
    } finally {
      setIsSaving(false)
    }
  }, [
    segmentRack,
    isSaving,
    instruct,
    matchedAccentBankEntry,
    onVoiceCreated,
    setIsSaving,
    setError,
    setSavedVoiceId,
  ])

  const removeLockedSegment = useCallback(
    (index: number) => {
      setLockedSegments((prev) =>
        prev.filter((_, i) => i !== index),
      )
      setStitchedUrl(null)
      setSavedVoiceId(null)
    },
    [
      setLockedSegments,
      setStitchedUrl,
      setSavedVoiceId,
    ],
  )

  const toggleLibrarySelection = useCallback(
    (segmentId: string) => {
      setLibrarySelection((prev) => {
        const next = new Set(prev)
        if (next.has(segmentId))
          next.delete(segmentId)
        else next.add(segmentId)
        return next
      })
    },
    [setLibrarySelection],
  )

  const addSelectedFromLibrary = useCallback(
    () => {
      const chosen = library.filter(
        (m) => librarySelection.has(m.segment_id),
      )
      setLockedSegments((prev) => [
        ...prev,
        ...chosen
          .filter(
            (m) =>
              !prev.some(
                (s) =>
                  s.segmentId === m.segment_id,
              ),
          )
          .map((m) => ({
            segmentId: m.segment_id,
            text: m.text,
            audioBase64:
              m.audio_base64 ?? '',
          })),
      ])
      setLibrarySelection(new Set())
      setStitchedUrl(null)
      setSavedVoiceId(null)
    },
    [
      library,
      librarySelection,
      setLockedSegments,
      setLibrarySelection,
      setStitchedUrl,
      setSavedVoiceId,
    ],
  )

  const handleDeleteFromLibrary = useCallback(
    async (segmentId: string) => {
      try {
        await deleteOmniVoiceSegment(segmentId)
        setLockedSegments((prev) =>
          prev.filter(
            (s) => s.segmentId !== segmentId,
          ),
        )
        refreshLibrary()
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : String(err),
        )
      }
    },
    [
      setLockedSegments,
      refreshLibrary,
      setError,
    ],
  )

  // -- Render: Left column --
  const leftColumn = (
    <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3 text-card-foreground shadow-sm">
      <div>
        <h2 className="text-[13px] font-semibold tracking-tight">
          Design an accent-cloned voice
        </h2>
        <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground">
          OmniVoice uses a fixed tag vocabulary — every
          option below is validated. Pick a starting
          preset, then adjust chips; the right panel
          always reflects the exact instruct string
          being sent.
        </p>
      </div>

      {ACCENT_BANK.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {ACCENT_BANK.map((entry) => (
            <Button
              key={entry.id}
              type="button"
              variant="secondary"
              size="sm"
              onClick={() =>
                applyAccentPreset(entry)
              }
              className="rounded-full"
            >
              {entry.label} starter
            </Button>
          ))}
        </div>
      )}

      <ChipSection title="Accent">
        <div className="flex flex-wrap gap-1.5">
          {ACCENTS.map((chip) => (
            <ChipButton
              key={chip.id}
              label={chip.label}
              selected={
                selections.accent ===
                chip.id
              }
              onClick={() =>
                toggleSingle(
                  'accent',
                  chip.id,
                )
              }
            />
          ))}
        </div>
        <p className="mt-2 rounded-md bg-muted/60 px-2.5 py-2 text-[10px] leading-tight text-muted-foreground">
          Only Australian has a curated showcase-sentence
          bank (validated hands-on). Other accents use the
          same closed tag set but are not yet
          quality-checked.
        </p>
      </ChipSection>

      <ChipSection title="Demographics">
        <div className="flex flex-wrap gap-1.5">
          {GENDERS.map((chip) => (
            <ChipButton
              key={chip.id}
              label={chip.label}
              selected={
                selections.gender ===
                chip.id
              }
              onClick={() =>
                toggleSingle(
                  'gender',
                  chip.id,
                )
              }
            />
          ))}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {AGES.map((chip) => (
            <ChipButton
              key={chip.id}
              label={chip.label}
              selected={
                selections.age === chip.id
              }
              onClick={() =>
                toggleSingle('age', chip.id)
              }
            />
          ))}
        </div>
      </ChipSection>

      <ChipSection title="Pitch">
        <div className="flex flex-wrap gap-1.5">
          {PITCHES.map((chip) => (
            <ChipButton
              key={chip.id}
              label={chip.label}
              selected={
                selections.pitch ===
                chip.id
              }
              onClick={() =>
                toggleSingle(
                  'pitch',
                  chip.id,
                )
              }
            />
          ))}
        </div>
        <p className="mt-1.5 text-[10px] text-muted-foreground">
          "High pitch" trends tinnier in testing —
          "moderate" is usually the safer default.
        </p>
      </ChipSection>

      <ChipSection title="Style">
        <div className="flex flex-wrap gap-1.5">
          <ChipButton
            label={STYLE_WHISPER.label}
            selected={selections.whisper}
            onClick={toggleWhisper}
          />
        </div>
        <p className="mt-1.5 text-[10px] text-muted-foreground">
          The only style tag OmniVoice documents — there's
          no "warm" or "sweet" here (that's
          VoiceDesign-only).
        </p>
      </ChipSection>
    </div>
  )

  // -- Render: Right column --
  const rightColumn = (
    <div className="flex h-fit flex-col gap-2.5 rounded-xl border border-border bg-card p-3 text-card-foreground shadow-sm lg:sticky lg:top-4">
      {/* Composed instruct */}
      <div>
        <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Composed instruct
        </p>
        <div
          data-testid="omnivoice-instruct"
          className="min-h-8 w-full rounded-md border border-input bg-muted/40 px-2.5 py-1.5 font-mono text-[10px] leading-tight text-muted-foreground"
        >
          {instruct || (
            <span className="italic">
              Pick at least one chip on the left…
            </span>
          )}
        </div>
      </div>

          {/* Script / Lines (composer-style) */}
          <div className="flex flex-col gap-1">
            {/* Script control-panel card */}
            <div className="flex flex-col rounded-lg border border-border bg-card">
              {/* Header bar */}
              <div className="flex items-center justify-between gap-2 rounded-t-lg border-b border-border bg-muted/50 px-2.5 py-1.5">
              <div className="flex items-center gap-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-foreground/90">
                  Script
                </p>
                {scriptWordCount > 0 && (
                  <span className="text-[10px] text-foreground/60">
                    {lines.length} line{lines.length !== 1 ? 's' : ''} · {scriptWordCount} word{scriptWordCount !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1.5">
                {activeShowcaseSentences.length > 0 && (
                  <Tooltip.Root>
                    <Tooltip.Trigger asChild>
                      <button
                        type="button"
                         onClick={() => {
                           setExamplesOpen((v) => !v)
                           setTagsOpen(false)
                         }}
                          className={cn(
                            "inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-[10px] font-semibold transition-colors hover:bg-accent",
                            examplesOpen
                              ? "bg-primary/10 text-primary border-primary/40"
                              : "bg-muted/90 text-foreground/90",
                          )}
                      >
                        ⚡ Examples
                      </button>
                    </Tooltip.Trigger>
                    <Tooltip.Content side="bottom">
                      Accent-specific example lines to insert.
                    </Tooltip.Content>
                  </Tooltip.Root>
                )}
                <Tooltip.Root>
                  <Tooltip.Trigger asChild>
                    <button
                       type="button"
                       onClick={() => {
                         setTagsOpen((v) => !v)
                         setExamplesOpen(false)
                       }}
                        className={cn(
                          "inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-[10px] font-semibold transition-colors hover:bg-accent",
                          tagsOpen
                            ? "bg-primary/10 text-primary border-primary/40"
                            : "bg-muted/90 text-foreground/90",
                        )}
                    >
                      <span className="mr-0.5 text-[10px] text-foreground/70">✦</span>
                      Non-Verbals
                    </button>
                  </Tooltip.Trigger>
                  <Tooltip.Content side="bottom">
                    Insert non-verbal expressions inline, e.g. "[laughter]".
                  </Tooltip.Content>
                </Tooltip.Root>
              </div>
            </div>

            {/* Tags palette */}
            <AnimatePresence initial={false}>
              {tagsOpen && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="overflow-hidden border-b border-border"
                >
                  <div className="flex flex-wrap gap-1 px-2.5 py-2">
                    {NON_VERBAL_TAGS.map((tag) => (
                      <button
                        key={tag}
                        type="button"
                        onClick={() => insertNonVerbalTag(tag)}
                        className="inline-flex items-center gap-0.5 rounded-full border border-border/90 bg-muted/70 px-1.5 py-0.5 font-mono text-[10px] text-foreground/90 transition-colors hover:bg-accent hover:text-foreground"
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Examples palette */}
            <AnimatePresence initial={false}>
              {examplesOpen && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="overflow-hidden border-b border-border"
                >
                  <div className="flex flex-wrap gap-1.5 px-2.5 py-2">
                    {activeShowcaseSentences.map((sentence) => (
                      <button
                        key={sentence.text}
                        type="button"
                        title={sentence.note}
                        onClick={() => insertExampleSentence(sentence)}
                        className="rounded-full border border-border/90 bg-muted/70 px-2.5 py-0.5 text-[10px] text-foreground/90 transition-colors hover:bg-accent hover:text-foreground"
                      >
                        {sentence.text}
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Textarea */}
            <div className="px-2.5 pt-2 pb-1">
              <textarea
                ref={setScriptRef}
                data-testid="omnivoice-script"
                placeholder="Paste or type your script (up to 10 lines recommended)…"
                rows={4}
                value={scriptText}
                onChange={(e) =>
                  setScriptText(e.target.value)
                }
                className="w-full resize-none rounded-md border border-input bg-muted/40 px-3 py-2 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40"
              />
            </div>

            {/* Guidance */}
            <div className="px-3 pb-2">
              <div className="flex flex-wrap items-center gap-x-3 text-[10px] text-muted-foreground">
                <span>
                  Recommended: 5–15 words per line.
                </span>
                <span>
                  Use Non-Verbals for [laughter], [sigh], etc.
                </span>
              </div>
              {hasLongLines && (
                <p className="mt-0.5 text-[10px] text-amber-400">
                  Some lines are long; shorter lines produce more reliable results.
                </p>
              )}
            </div>
          </div>

          {/* Language note */}
          <p className="text-[9px] text-muted-foreground">
            Best quality: English. For other languages,
            consider using a reference audio instead.
          </p>

        {/* Generate button */}
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            data-testid="omnivoice-audition-button"
            onClick={handleBatchAudition}
            disabled={
              !scriptText.trim() ||
              !instruct ||
              isRackAuditioning ||
              !modelLoaded
            }
            title={
              modelLoaded
                ? undefined
                : 'Model is still loading'
            }
            className="min-w-[160px]"
          >
            {isRackAuditioning
              ? 'Generating…'
              : 'Generate candidates'}
          </Button>
          <button
            type="button"
            onClick={() =>
              setShowAdvanced(!showAdvanced)
            }
            className="text-[10px] text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground"
          >
            {showAdvanced
              ? 'Hide advanced'
              : 'Advanced'}
          </button>
          </div>

        {/* Live hint while generating */}
        {isRackAuditioning && (
          <p className="text-[9px] text-muted-foreground">
            You can keep editing, add tags, or queue another generation; it won’t affect this run.
          </p>
        )}

        {/* Advanced controls */}
        <AnimatePresence initial={false}>
          {showAdvanced && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="flex flex-col gap-2 overflow-hidden rounded-lg border border-border/70 bg-muted/50 p-2.5"
            >
              {/* Steps */}
              <div className="flex items-center gap-3">
                <label className="flex min-w-[110px] items-center gap-1 text-[10px] text-muted-foreground">
                  <span>
                    Steps
                    <InfoIcon text="Diffusion step count (16–32). Higher is slower but can be cleaner." />
                  </span>
                </label>
                <div className="flex flex-1 items-center gap-2">
                  <input
                    type="range"
                    min={16}
                    max={32}
                    step={1}
                    value={
                      numStepInput
                        ? Number(numStepInput) || 32
                        : 32
                    }
                    onChange={(e) =>
                      setNumStepInput(
                        String(e.target.value),
                      )
                    }
                    className="flex-1 accent-primary"
                  />
                   <input
                     type="number"
                     min={16}
                     max={32}
                      value={numStepInput || 32}
                     onChange={(e) =>
                       setNumStepInput(
                         e.target.value,
                       )
                     }
                     className="w-14 rounded-md border border-input bg-transparent px-1.5 py-1 text-xs outline-none focus-visible:border-ring"
                   />
                </div>
              </div>

              {/* Guidance scale with explicit Auto */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-3">
                  <label className="flex min-w-[110px] items-center gap-1 text-[10px] text-muted-foreground">
                    <span>
                      Guidance
                      <InfoIcon text="Improves accent and voice fidelity (1.5–3.0). Higher = tighter accent but slightly less natural." />
                    </span>
                  </label>
                  <Tooltip.Root>
                    <Tooltip.Trigger asChild>
                      <button
                        type="button"
                        onClick={() =>
                          setGuidanceScaleInput(
                            guidanceScaleInput === ''
                              ? '2.0'
                              : '',
                          )
                        }
                        className={cn(
                          'ml-1 inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-[9px] font-medium transition-colors',
                          guidanceScaleInput === ''
                            ? 'border-primary/60 bg-primary/10 text-primary'
                            : 'bg-muted text-muted-foreground hover:bg-muted/80',
                        )}
                      >
                        Auto
                      </button>
                    </Tooltip.Trigger>
                    <Tooltip.Content side="top">
                      Use OmniVoice default (effective 2.0).
                    </Tooltip.Content>
                  </Tooltip.Root>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min={1.5}
                    max={3}
                    step={0.1}
                    value={
                      guidanceScaleInput
                        ? Number(guidanceScaleInput) || 2
                        : 2
                    }
                    onChange={(e) =>
                      setGuidanceScaleInput(
                        String(
                          Number(
                            e.target.value,
                          ).toFixed(1),
                        ),
                      )
                    }
                    className="flex-1 accent-primary"
                  />
                  <input
                    type="number"
                    min={1.5}
                    max={3}
                    step={0.1}
                    value={
                      guidanceScaleInput || ''
                    }
                    onChange={(e) =>
                      setGuidanceScaleInput(
                        e.target.value,
                      )
                    }
                    placeholder="2.0"
                    className="w-14 rounded-md border border-input bg-transparent px-1.5 py-1 text-xs outline-none focus-visible:border-ring"
                  />
                </div>
              </div>

              {/* Speed */}
              <div className="flex items-center gap-3">
                <label className="flex min-w-[110px] items-center gap-1 text-[10px] text-muted-foreground">
                  <span>
                    Speed
                    <InfoIcon text="Playback-rate multiplier. 0.8–1.5 recommended; server clamps 0.5–2.5." />
                  </span>
                </label>
              <input
                type="number"
                min={0.5}
                max={2.5}
                step={0.1}
                placeholder="1.0"
                value={speedInput}
                  onChange={(e) =>
                    setSpeedInput(
                      e.target.value,
                    )
                  }
                  className="w-24 rounded-md border border-input bg-transparent px-2 py-1 text-xs outline-none focus-visible:border-ring"
                />
              </div>

              {/* Diverse candidates */}
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 text-[10px] text-muted-foreground">
                  <span>
                    Diverse candidates
                    <InfoIcon text="Generates takes with different delivery and prosody by varying internal temperatures." />
                  </span>
                </label>
                <button
                  type="button"
                  role="switch"
                  aria-checked={
                    diverseCandidates
                  }
                  onClick={() =>
                    setDiverseCandidates(
                      !diverseCandidates,
                    )
                  }
                  className={cn(
                    'relative inline-flex h-5 w-9 cursor-pointer rounded-full border border-border transition-colors',
                    diverseCandidates
                      ? 'bg-primary'
                      : 'bg-muted',
                  )}
                >
                  <span
                    className={cn(
                      'absolute top-[3px] left-[3px] h-3.5 w-3.5 rounded-full bg-background shadow transition-transform',
                      diverseCandidates
                        ? 'translate-x-4'
                        : 'translate-x-0',
                    )}
                  />
                </button>
              </div>

              {/* Post-process toggle */}
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 text-[10px] text-muted-foreground">
                  <span>
                    Post-process (trim silence)
                    <InfoIcon text="On: trims trailing silence and normalizes (may shorten clips). Off: preserves raw output; use this when you set explicit durations to avoid clips being cut short." />
                  </span>
                </label>
                <button
                  type="button"
                  role="switch"
                  aria-checked={
                    postProcess
                  }
                  onClick={() =>
                    setPostProcess(
                      !postProcess,
                    )
                  }
                  className={cn(
                    'relative inline-flex h-5 w-9 cursor-pointer rounded-full border border-border transition-colors',
                    postProcess
                      ? 'bg-primary'
                      : 'bg-muted',
                  )}
                >
                  <span
                    className={cn(
                      'absolute top-[3px] left-[3px] h-3.5 w-3.5 rounded-full bg-background shadow transition-transform',
                      postProcess
                        ? 'translate-x-4'
                        : 'translate-x-0',
                    )}
                  />
                </button>
              </div>
              {anySegmentHasDuration && (
                <p className="text-[9px] leading-snug text-amber-500/90">
                  One or more segments have an explicit Duration set — post-processing is
                  automatically disabled for those segments regardless of this toggle, to
                  keep their length accurate.
                </p>
              )}

              {/* Candidates count */}
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 text-[10px] text-muted-foreground">
                  Candidates per segment
                </label>
                <input
                  type="number"
                  min={1}
                  max={6}
                  value={candidatesPerSegment}
                  onChange={(e) =>
                    setCandidatesPerSegment(
                      Number(
                        e.target.value,
                      ) || 1,
                    )
                  }
                  className="w-16 rounded-md border border-input bg-transparent px-2 py-1 text-xs outline-none focus-visible:border-ring"
                />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Progress bar + ETA (inline; no full-viewport bar) */}
      {isRackAuditioning && (
        <div
          data-testid="omnivoice-progress"
          className="flex flex-col gap-1.5"
        >
          {/* Overall progress bar based on candidates */}
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              {jobStatus === 'running' &&
              typeof jobCandidatesTotal === 'number' &&
              jobCandidatesTotal > 0 &&
              typeof jobCandidatesCompleted === 'number' ? (
                <motion.div
                  className="h-full bg-primary"
                  animate={{
                    width: `${Math.min(
                      100,
                      (jobCandidatesCompleted / jobCandidatesTotal) * 100,
                    )}%`,
                  }}
                  transition={{ ease: 'easeOut', duration: 0.3 }}
                />
              ) : (
                <motion.div
                  className="h-full bg-primary/80"
                  animate={{
                    width: ['30%', '70%', '30%'],
                  }}
                  transition={{
                    duration: 2.5,
                    repeat: Number.POSITIVE_INFINITY,
                    ease: 'easeInOut',
                  }}
                />
              )}
            </div>
            {jobStatus === 'running' &&
              typeof jobCandidatesTotal === 'number' &&
              jobCandidatesTotal > 0 &&
              typeof jobCandidatesCompleted === 'number' && (
                <span className="shrink-0 text-[9px] text-muted-foreground">
                  {jobCandidatesCompleted}/{jobCandidatesTotal}
                </span>
              )}
          </div>

          {/* Status line with segment info and ETA countdown */}
          <p className="text-[10px] text-muted-foreground">
            {(() => {
              const running = jobStatus === 'running'
              if (jobStatus === 'queued') {
                return 'Queued — waiting for model to load…'
              }

              if (running && jobTotalSegments > 0) {
                const seg = (jobCurrentSegmentIndex ?? 0) + 1
                const ready = jobSegmentsCompleted.length
                const base = `Generating segment ${seg} of ${jobTotalSegments}`

                const etaPart =
                  jobEtaSeconds != null &&
                  jobEtaSeconds >= 5 &&
                  jobEtaSeconds <= 1800
                    ? ` · Est. remaining: ${formatEta(jobEtaSeconds)}`
                    : ''

                if (ready > 0) {
                  return `${base} · ${ready}/${jobTotalSegments} ready${etaPart}`
                }
                return `${base}${etaPart}`
              }

              if (running) return 'Starting…'
              if (jobStatus === 'failed')
                return 'Job failed'
              return 'Finalizing…'
            })()}

            {progress?.phase === 'loading' &&
              ' — loading OmniVoice checkpoint…'}
          </p>

          {jobStatus === 'running' &&
            jobSegmentsCompleted.length > 0 && (
              <p className="text-[9px] text-muted-foreground">
                New segments will appear below as each
                one finishes — you can preview and
                select takes live.
              </p>
            )}
        </div>
      )}

        {/* Segment rack */}
        {segmentRack.length > 0 && (
          <div className="flex min-w-0 flex-col gap-1">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
                Segment rack
              </p>
              <button
                type="button"
                onClick={() => setAutoplayTakes(!autoplayTakes)}
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border border-border/90 px-2 py-0.5 text-[9px] font-medium transition-colors",
                  autoplayTakes
                    ? "border-primary/60 bg-primary/10 text-primary"
                    : "bg-muted/80 text-muted-foreground",
                )}
              >
                {autoplayTakes ? 'Autoplay takes: On' : 'Autoplay takes: Off'}
              </button>
            </div>

            <div className="flex min-w-0 flex-col gap-1 overflow-y-auto">
              <p className="text-[9px] text-muted-foreground">
                Click a take to select it for stitching; click again to deselect.
              </p>
              {segmentRack.map((row, segIndex) => (
                <SegmentRackRow
                  key={row.segmentId}
                  segIndex={segIndex}
                  row={row}
                  isRackAuditioning={isRackAuditioning}
                  jobStatus={jobStatus}
                  jobCurrentSegmentIndex={jobCurrentSegmentIndex}
                  autoplayTakes={autoplayTakes}
                  onEdit={editSegmentText}
                  onRegen={regenerateSegment}
                  onSelectTake={selectTake}
                  segmentDuration={
                    segmentDurations[row.segmentId] ?? null
                  }
                  onSegmentDurationChange={
                    onSegmentDurationChange
                  }
                />
              ))}
            </div>

            {/* Stitch / Save */}
            <div className="mt-0.5 flex flex-wrap gap-1.5">
              <Button
                type="button"
                data-testid="omnivoice-stitch-button"
                onClick={handleStitch}
                disabled={
                  segmentRack.length === 0 ||
                  isStitching
                }
                className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-[hsl(190,90%,50%)] to-[hsl(210,90%,45%)] px-3 py-1 text-[11px] font-medium text-background shadow-[0_4px_15px_rgba(34,211,238,0.25)] transition-all hover:scale-[1.02] hover:shadow-[0_8px_25px_rgba(34,211,238,0.35)] disabled:opacity-50 disabled:shadow-none"
              >
                {isStitching
                  ? 'Stitching…'
                  : 'Stitch all'}
              </Button>
           </div>
         </div>
       )}

      {/* Stitched preview */}
      <AnimatePresence>
        {stitchedUrl && (
          <motion.div
            data-testid="omnivoice-result"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            className="flex flex-col gap-3 rounded-xl border border-border bg-muted/50 px-4 py-3"
          >
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Stitched preview
            </p>
            <AudioPlayer
              src={stitchedUrl}
              blob={stitchedBlob}
            />
            {savedVoiceId ? (
              <p className="text-xs text-muted-foreground">
                Saved to voice library as{' '}
                <span className="font-mono text-foreground">
                  {savedVoiceId}
                </span>
                .
              </p>
            ) : (
              <Button
                type="button"
                data-testid="omnivoice-save-button"
                variant="outline"
                size="sm"
                onClick={handleSave}
                disabled={isSaving}
                className="self-start rounded-full px-3 py-1 text-[11px]"
              >
                {isSaving
                  ? 'Saving…'
                  : 'Save to voice library'}
              </Button>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Segment library */}
      <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
        <button
          type="button"
          className="flex items-center justify-between text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground"
          onClick={() =>
            setIsLibraryOpen((v) => !v)
          }
        >
          <span>
            Segment library ({library.length})
          </span>
          <span>{isLibraryOpen ? 'Hide' : 'Browse'}</span>
        </button>
        {isLibraryOpen && (
          <div className="flex flex-col gap-2">
            <input
              type="text"
              placeholder="Filter by tag…"
              value={libraryFilter}
              onChange={(e) =>
                setLibraryFilter(e.target.value)
              }
              className="w-full rounded-md border border-input bg-transparent p-2 text-xs outline-none focus-visible:border-ring"
            />
            <div className="flex max-h-48 flex-col gap-1.5 overflow-y-auto">
              {filteredLibrary.length ===
                0 && (
                <p className="text-[10px] text-muted-foreground">
                  No segments match.
                </p>
              )}
              {filteredLibrary.map((m) => (
                <div
                  key={m.segment_id}
                  className={cn(
                    'flex items-center gap-2 rounded-md border p-2',
                    librarySelection.has(
                      m.segment_id,
                    )
                      ? 'border-primary bg-primary/5'
                      : 'border-border',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={librarySelection.has(
                      m.segment_id,
                    )}
                    onChange={() =>
                      toggleLibrarySelection(
                        m.segment_id,
                      )
                    }
                  />
                  <div className="flex-1">
                    <p className="text-xs">
                      {m.text}
                    </p>
                    <p className="text-[10px] text-muted-foreground">
                      {m.tags.join(', ')}
                    </p>
                  </div>
                  {m.audio_base64 && (
                    <ClipPlayer
                      audioBase64={
                        m.audio_base64
                      }
                      className="w-40"
                    />
                  )}
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      handleDeleteFromLibrary(
                        m.segment_id,
                      )
                    }
                  >
                    Delete
                  </Button>
                </div>
              ))}
            </div>
            <Button
              type="button"
              size="sm"
              className="self-start"
              onClick={
                addSelectedFromLibrary
              }
              disabled={
                librarySelection.size === 0
              }
            >
              Add selected to locked sentences
            </Button>
          </div>
        )}
      </div>

      {/* Locked segments */}
      {lockedSegments.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Locked sentences ({lockedSegments.length})
          </p>
          {lockedSegments.map((seg, i) => (
            <div
              key={seg.segmentId}
              className="flex items-center gap-2 rounded-md border border-border bg-muted/30 p-2"
            >
              <span className="flex-1 text-xs">
                {seg.text}
              </span>
              {seg.audioBase64 && (
                <ClipPlayer
                  audioBase64={
                    seg.audioBase64
                  }
                  className="w-40"
                />
              )}
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() =>
                  removeLockedSegment(i)
                }
              >
                Remove
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <p
          data-testid="omnivoice-error"
          className="text-xs text-destructive"
        >
          {error}
        </p>
      )}
    </div>
  )

  // Feed global ActivityStatusBar from this panel's OmniVoice job state
  const showLiveStatus =
    isRackAuditioning &&
    jobStatus === 'running' &&
    jobTotalSegments > 0

  const progressFraction = (() => {
    if (!showLiveStatus || jobTotalSegments <= 0) return 0
    const segsCompleted =
      Array.isArray(jobSegmentsCompleted) ? jobSegmentsCompleted.length : 0
    const candidatesDone =
      typeof jobCandidatesCompleted === 'number'
        ? jobCandidatesCompleted
        : 0
    const candidatesAll =
      typeof jobCandidatesTotal === 'number'
        ? jobCandidatesTotal
        : 0

    const segFrac =
      jobTotalSegments > 0
        ? segsCompleted / jobTotalSegments
        : 0
    const candFrac =
      candidatesAll > 0
        ? candidatesDone / candidatesAll
        : 0

    return Math.min(1, segFrac * 0.6 + candFrac * 0.4)
  })()

  useEffect(() => {
    if (!showLiveStatus) {
      setActivityStatus(null)
      return
    }

    const segIndex = jobCurrentSegmentIndex ?? 0
    const candDone = typeof jobCandidatesCompleted === 'number' ? jobCandidatesCompleted : 0
    const candTotal = typeof jobCandidatesTotal === 'number' && jobCandidatesTotal > 0
      ? jobCandidatesTotal
      : 0

    const detail =
      candTotal > 0
        ? `Segment ${segIndex + 1}/${jobTotalSegments} · Candidate ${candDone}/${candTotal}`
        : `Segment ${segIndex + 1}/${jobTotalSegments}`

    setActivityStatus({
      active: true,
      title: 'Generating speech',
      message: '',
      detail,
      progress: progressFraction,
      etaSeconds: jobEtaSeconds,
    })
  }, [
    showLiveStatus,
    jobTotalSegments,
    jobCurrentSegmentIndex,
    jobCandidatesCompleted,
    jobCandidatesTotal,
    jobEtaSeconds,
    progressFraction,
    setActivityStatus,
  ])

  return (
    <div className="relative">
      <div
        className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,280px)_minmax(0,1fr)]"
      >
        {leftColumn}
        {rightColumn}
      </div>
    </div>
  )
}

function ChipSection({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </p>
      {children}
    </div>
  )
}

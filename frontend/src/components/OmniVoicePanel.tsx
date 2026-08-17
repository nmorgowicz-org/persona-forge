import {
  useEffect,
  useMemo,
  useCallback,
  useState,
} from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Scissors } from 'lucide-react'
import { Disclose } from './Disclose'
import {
  auditionOmniVoiceStreaming,
  cancelOmniVoiceAudition,
  deleteOmniVoiceSegment,
  getOmniVoiceAuditionProgress,
  getSegmentAudioBase64,
  listOmniVoiceSegments,
  renderStitchPlan,
  saveOmniVoice,
  type OmniVoiceCandidateSegment,
  type StitchPlanPayload,
  type SegmentMeta,
  type VoiceMeta,
} from '@/lib/api'
import {
  ACCENT_BANK,
  ESTIMATED_WORDS_PER_SECOND,
  FEATURE_INFO,
  HERO_TARGET_MAX_SEC,
  HERO_TARGET_MIN_SEC,
  buildHeroTake,
  type AccentBankEntry,
  type ShowcaseSentence,
} from '@/lib/accentBank'
import {
  composeInstruct,
  selectionsFromInstruct,
} from '@/lib/omnivoiceChips'
import { AudioPlayer } from './AudioPlayer'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useAppStore, type StitchPlanClip } from '@/store'
import * as Tooltip from '@/components/ui/tooltip'
import { StitchEditorPanel } from '@/components/StitchTimeline'
import { insertSegmentIntoStitchTimeline, insertVoiceIntoStitchTimeline } from '@/lib/stitchClips'
import { ClipPlayer } from './OmniVoice/ClipPlayer'
import { InfoIcon } from './OmniVoice/InfoIcon'
import { AccentChipPanel } from './OmniVoice/AccentChipPanel'
import {
  SegmentRackRow,
  SEGMENT_DURATION_MIN_SEC,
  SEGMENT_DURATION_MAX_SEC,
} from './OmniVoice/SegmentRackRow'

const DEFAULT_ACCENT = ACCENT_BANK[0] ?? null

const DELIVERY_VARIANTS = [
  { kind: 'natural', name: 'Natural', hint: 'Conversational and neutral' },
  { kind: 'calm', name: 'Calm', hint: 'Slower and steadier' },
  { kind: 'energetic', name: 'Energetic', hint: 'Brighter and tighter' },
  { kind: 'broadcast', name: 'Broadcast', hint: 'Clear and projected' },
  { kind: 'storyteller', name: 'Storyteller', hint: 'Warm and expressive' },
] as const

type DeliveryVariantKind = (typeof DELIVERY_VARIANTS)[number]['kind']

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

// Breadcrumb so a hard refresh mid-run can reconnect to the still-generating server-side
// job instead of losing all trace of it (the job itself keeps running independently).
const OV_ACTIVE_JOB_KEY = 'ov_active_job'

interface OvActiveJobBreadcrumb {
  jobId: string
  instruct: string
  scriptText: string
  totalSegments: number
}

function saveActiveJobBreadcrumb(breadcrumb: OvActiveJobBreadcrumb) {
  try {
    localStorage.setItem(OV_ACTIVE_JOB_KEY, JSON.stringify(breadcrumb))
  } catch {
    // Resume-after-refresh is a nice-to-have; don't fail the job over it.
  }
}

function clearActiveJobBreadcrumb() {
  try {
    localStorage.removeItem(OV_ACTIVE_JOB_KEY)
  } catch {
    // ignore
  }
}

function readActiveJobBreadcrumb(): OvActiveJobBreadcrumb | null {
  try {
    const raw = localStorage.getItem(OV_ACTIVE_JOB_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed.jobId !== 'string') return null
    return parsed as OvActiveJobBreadcrumb
  } catch {
    return null
  }
}

function formatEta(seconds: number | null): string {
  if (seconds == null) return 'estimating…'
  if (seconds < 1) return 'almost done'
  if (seconds < 60) return `~${Math.round(seconds)}s remaining`
  return `~${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s remaining`
}


interface OmniVoicePanelProps {
  onVoiceCreated?: (voiceId: string) => void
}

export function OmniVoicePanel({ onVoiceCreated }: OmniVoicePanelProps) {
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
  const minMatchScore = useAppStore(
    (s) => s.ovMinMatchScore,
  )
  const scriptText = useAppStore((s) => s.ovScriptText)
  const segmentRack = useAppStore((s) => s.ovSegmentRack)
  const isRackAuditioning = useAppStore(
    (s) => s.ovIsRackAuditioning,
  )
  const isStitching = useAppStore((s) => s.ovIsStitching)
  const isSaving = useAppStore((s) => s.ovIsSaving)
  const error = useAppStore((s) => s.ovError)
  const stitchedUrl = useAppStore((s) => s.ovStitchedUrl)
  const stitchedBlob = useAppStore((s) => s.ovStitchedBlob)
  const savedVoiceId = useAppStore((s) => s.ovSavedVoiceId)
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
  const jobMessage = useAppStore((s) => s.ovJobMessage)
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
  const setMinMatchScore = useAppStore(
    (s) => s.setOvMinMatchScore,
  )
  const setScriptText = useAppStore((s) => s.setOvScriptText)
  const setSegmentRack = useAppStore(
    (s) => s.setOvSegmentRack,
  )
  const setIsRackAuditioning = useAppStore(
    (s) => s.setOvIsRackAuditioning,
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
  const stitchEditorOpen = useAppStore(
    (s) => s.ovStitchEditorOpen,
  )
  const setStitchPlanClips = useAppStore(
    (s) => s.setOvStitchPlanClips,
  )
  const voices = useAppStore((s) => s.voices)
  const setStitchPlanPaddingAt = useAppStore(
    (s) => s.setOvStitchPlanPaddingAt,
  )
  const setStitchPlanPaddingMs = useAppStore(
    (s) => s.setOvStitchPlanPaddingMs,
  )
  const setStitchEditorOpen = useAppStore(
    (s) => s.setOvStitchEditorOpen,
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

  // Load library on mount only if the store is empty.
  useEffect(() => {
    if (library.length > 0) return
    ;(async () => {
      try {
        setLibrary(await listOmniVoiceSegments())
      } catch {
        // Non-fatal
      }
    })()
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

  // Rough estimate only (ESTIMATED_WORDS_PER_SECOND) — real duration always comes back from
  // the render itself; this just gives a live sense of "am I near the 10-15s hero target"
  // while building a script, before generating anything.
  const estimatedScriptSeconds = scriptWordCount / ESTIMATED_WORDS_PER_SECOND
  const heroMeterState: 'under' | 'in-range' | 'over' =
    estimatedScriptSeconds < HERO_TARGET_MIN_SEC
      ? 'under'
      : estimatedScriptSeconds > HERO_TARGET_MAX_SEC
        ? 'over'
        : 'in-range'

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
  // Per-candidate tempo choice from each take's SpeedStepper — carried into the Stitch/Save
  // plan as a real time-stretch (audio_post.stitch_segments' `tempos` kwarg), not just the
  // discardable local playbackRate preview AudioDeck used before this.
  const [candidateSpeeds, setCandidateSpeeds] = useState<Record<string, number>>({})
  const onCandidateSpeedChange = useCallback((candidateId: string, speed: number) => {
    setCandidateSpeeds((prev) => ({ ...prev, [candidateId]: speed }))
  }, [])
  // Rolling avg_seconds-per-candidate from the most recent job, used to give Regen a rough
  // "~Ns" cost estimate up front rather than only ever showing progress after the fact.
  const [lastAvgCandidateSeconds, setLastAvgCandidateSeconds] = useState<number | null>(null)
  const [postProcess, setPostProcess] = useState(true)
  const [deliveryVariantKind, setDeliveryVariantKind] =
    useState<DeliveryVariantKind>('natural')
  const anySegmentHasDuration = Object.values(segmentDurations).some(
    (d) => d != null,
  )

  // Running tally of the currently-selected takes across the rack — same override-or-actual
  // fallback each SegmentRackRow uses for its own duration box, summed, so there's a rough
  // preview of the final stitched length before hitting Stitch (which itself requires every
  // row to have a selection). Reuses the hero-take target band for coloring since a stitched
  // rack *is* the reference clip this whole workflow is trying to land in 10-15s.
  const segmentRackTally = useMemo(() => {
    let totalSec = 0
    let selectedCount = 0
    for (const row of segmentRack) {
      if (row.selectedTakeIndex < 0) continue
      selectedCount += 1
      const candidate = row.candidates[row.selectedTakeIndex]
      const override = segmentDurations[row.segmentId] ?? null
      const actual = candidate?.duration_sec ?? null
      totalSec += override ?? actual ?? 0
    }
    return { totalSec, selectedCount }
  }, [segmentRack, segmentDurations])

  const segmentRackTallyState: 'under' | 'in-range' | 'over' =
    segmentRackTally.totalSec < HERO_TARGET_MIN_SEC
      ? 'under'
      : segmentRackTally.totalSec > HERO_TARGET_MAX_SEC
        ? 'over'
        : 'in-range'

  const deliveryVariant = DELIVERY_VARIANTS.find(
    (variant) => variant.kind === deliveryVariantKind,
  ) ?? DELIVERY_VARIANTS[0]


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

  const applyHeroTake = useCallback(
    (entry: AccentBankEntry) => {
      const hero = buildHeroTake(entry)
      setScriptText(hero.map((s) => s.text).join('\n'))
      setSegmentRack([])
      setStitchedUrl(null)
      setSavedVoiceId(null)
      setError(null)
      setExamplesOpen(false)
    },
    [
      setScriptText,
      setSegmentRack,
      setStitchedUrl,
      setSavedVoiceId,
      setError,
    ],
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
      setScriptText('')
      setSegmentRack([])
      setStitchedUrl(null)
      setSavedVoiceId(null)
      setError(null)
    },
    [
      setSelections,
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

  // Merge in-place: a segment's candidates list grows as each candidate finishes, so
  // update existing rows instead of only appending new ones — this is what lets a take's
  // waveform/player show up as soon as it's done, without waiting for the rest of the
  // segment (or job) to finish. Shared by a fresh batch run and a resumed-after-refresh one.
  const mergeBatchSegments = useCallback(
    (segments: OmniVoiceCandidateSegment[]) => {
      setSegmentRack((prev) => {
        const next = [...prev]
        const indexBySegId = new Map(
          next.map((r, i) => [r.segmentId, i]),
        )
        for (const s of segments) {
          const segId = `seg-${s.segment_index}`
          const candidates = Array.isArray(s.candidates)
            ? s.candidates
            : []
          const existingIndex = indexBySegId.get(segId)
          if (existingIndex == null) {
            next.push({
              segmentId: segId,
              text: s.text || '',
              candidates,
              selectedTakeIndex:
                candidates.length > 0 ? 0 : -1,
            })
          } else {
            next[existingIndex] = {
              ...next[existingIndex],
              candidates,
            }
          }
        }
        return next
      })
    },
    [setSegmentRack],
  )

  // Shared poll loop: fetches progress, mirrors it into the store, forwards the segment
  // list to the caller's merge logic, and resolves once the job reaches a terminal state.
  // Used by both a freshly-started job and one resumed from a hard-refresh breadcrumb.
  const pollOmniVoiceJob = useCallback(
    async (
      jobId: string,
      onSegments: (segments: OmniVoiceCandidateSegment[]) => void,
    ): Promise<
      | { status: 'completed' }
      | { status: 'cancelled' }
      | { status: 'failed'; message: string }
    > => {
      let consecutivePollFailures = 0
      while (true) {
        let p
        try {
          p = await getOmniVoiceAuditionProgress(jobId)
          consecutivePollFailures = 0
        } catch (pollErr) {
          // A single missed poll (e.g. the server is momentarily busy servicing
          // the heavy generation request itself) doesn't mean the job died — it's
          // running as an independent background thread server-side. Only give up
          // after several consecutive misses so a transient blip can't strand the
          // UI on "Failed to fetch" while the container keeps generating fine.
          consecutivePollFailures += 1
          if (consecutivePollFailures >= 6) throw pollErr
          await new Promise((r) => setTimeout(r, 500))
          continue
        }
        setJobStatus(p.status)
        setJobCurrentSegmentIndex(p.current_segment_index)
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
        if (typeof p.avg_seconds === 'number' && p.avg_seconds > 0)
          setLastAvgCandidateSeconds(p.avg_seconds)

        onSegments(p.segments_completed || [])

        if (p.status === 'completed') return { status: 'completed' }
        if (p.status === 'failed') {
          if ((p.message || '').toLowerCase().includes('cancel')) {
            return { status: 'cancelled' }
          }
          return {
            status: 'failed',
            message: p.message || 'OmniVoice job failed.',
          }
        }
        await new Promise((r) => setTimeout(r, 500))
      }
    },
    [
      setJobStatus,
      setJobCurrentSegmentIndex,
      setJobSegmentsCompleted,
      setJobMessage,
      setJobEtaSeconds,
      setJobCandidatesTotal,
      setJobCandidatesCompleted,
      setJobCurrentCandidateIndex,
    ],
  )

  const handleBatchAudition = useCallback(async () => {
    const text = scriptText.trim()
    if (!text || !instruct || isRackAuditioning) return

    const segments = splitScriptToSegments(text)
    if (segments.length === 0) return

    setIsRackAuditioning(true)
    setError(null)
    setSegmentRack([])
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
              : 2.5,
            diverseCandidates,
            durations,
            postprocessOutput: postProcess || null,
            minMatchScore,
          })

        setCurrentJobId(job_id)
        setJobTotalSegments(total_segments)
        setJobStatus('running')
        setExamplesOpen(false)
        setTagsOpen(false)
        saveActiveJobBreadcrumb({
          jobId: job_id,
          instruct,
          scriptText: text,
          totalSegments: total_segments,
        })

        const outcome = await pollOmniVoiceJob(job_id, mergeBatchSegments)
        clearActiveJobBreadcrumb()

        if (outcome.status === 'completed') {
          // Finalize: keep segment rack + completed list intact
          setIsRackAuditioning(false)
          setCurrentJobId(null)
          setJobStatus('completed')
          setJobCurrentSegmentIndex(null)
          setJobMessage('All segments generated.')
        } else if (outcome.status === 'cancelled') {
          setJobMessage('Cancelled.')
          setIsRackAuditioning(false)
          setCurrentJobId(null)
          setJobCurrentSegmentIndex(null)
          setJobEtaSeconds(null)
        } else {
          setError(outcome.message)
        }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : String(err),
      )
      clearActiveJobBreadcrumb()
      // On error: fully reset
      setIsRackAuditioning(false)
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
    minMatchScore,
    segmentDurations,
    postProcess,
    pollOmniVoiceJob,
    mergeBatchSegments,
    setIsRackAuditioning,
    setError,
    setSegmentRack,
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

  // Resume-after-refresh: on mount, check for a breadcrumb left by a job that was still
  // running/queued when the page unloaded. Only batch runs are resumable — regen jobs are
  // short-lived and the rest of the rack is unrecoverable client-side after a hard refresh
  // anyway, so a lost regen just finishes server-side unobserved (same as before this fix).
  useEffect(() => {
    const breadcrumb = readActiveJobBreadcrumb()
    if (!breadcrumb) return

    let cancelled = false
    ;(async () => {
      let p
      try {
        p = await getOmniVoiceAuditionProgress(breadcrumb.jobId)
      } catch {
        clearActiveJobBreadcrumb()
        setError(
          "Your in-progress voice-design job couldn't be found — it may have been lost when the server restarted. Please generate again.",
        )
        return
      }
      if (cancelled) return
      if (p.status !== 'running' && p.status !== 'queued') {
        clearActiveJobBreadcrumb()
        if (p.status === 'completed') {
          setError('Your voice-design job finished while this page was closed. Reopen the rack by generating again to see the results.')
        } else if (p.status === 'failed') {
          setError(p.message || 'Your voice-design job failed while this page was closed.')
        }
        return
      }

      setScriptText(breadcrumb.scriptText)
      setSelections(selectionsFromInstruct(breadcrumb.instruct))
      setSegmentRack(
        (p.segments_completed || []).map((s) => ({
          segmentId: `seg-${s.segment_index}`,
          text: s.text || '',
          candidates: Array.isArray(s.candidates) ? s.candidates : [],
          selectedTakeIndex:
            Array.isArray(s.candidates) && s.candidates.length > 0 ? 0 : -1,
        })),
      )
      setCurrentJobId(breadcrumb.jobId)
      setJobTotalSegments(breadcrumb.totalSegments)
      setJobStatus(p.status)
      setIsRackAuditioning(true)
      setError(null)

      const outcome = await pollOmniVoiceJob(breadcrumb.jobId, mergeBatchSegments)
      clearActiveJobBreadcrumb()

      if (outcome.status === 'completed') {
        setIsRackAuditioning(false)
        setCurrentJobId(null)
        setJobStatus('completed')
        setJobCurrentSegmentIndex(null)
        setJobMessage('All segments generated.')
      } else if (outcome.status === 'cancelled') {
        setJobMessage('Cancelled.')
        setIsRackAuditioning(false)
        setCurrentJobId(null)
        setJobCurrentSegmentIndex(null)
        setJobEtaSeconds(null)
      } else {
        setError(outcome.message)
      }
    })()

    return () => {
      cancelled = true
    }
    // Only ever check for a resumable job once, right after mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  // Flips back to a previously-regenerated candidate batch instead of losing it — swaps the
  // active batch into previousBatches so it stays reachable in both directions.
  const selectCandidateBatch = useCallback(
    (segmentId: string, batchIndex: number) => {
      setSegmentRack((prev) =>
        prev.map((r) => {
          if (r.segmentId !== segmentId) return r
          const batches = r.previousBatches ?? []
          const target = batches[batchIndex]
          if (!target) return r
          const currentDuration =
            segmentDurations[r.segmentId] ??
            r.candidates[r.selectedTakeIndex]?.duration_sec ??
            0
          return {
            ...r,
            candidates: target.candidates,
            selectedTakeIndex: target.candidates.length > 0 ? 0 : -1,
            previousBatches: [
              { durationSec: currentDuration, candidates: r.candidates },
              ...batches.filter((_, i) => i !== batchIndex),
            ].slice(0, 4),
          }
        }),
      )
    },
    [setSegmentRack, segmentDurations],
  )

  const regenerateSegment = useCallback(
    async (segmentId: string) => {
      const row = segmentRack.find(
        (r) => r.segmentId === segmentId,
      )
      if (!row || isRackAuditioning) return

      // Snapshot the outgoing batch (tagged with the duration it was generated at) before
      // the streaming merge below overwrites row.candidates with fresh takes.
      if (row.candidates.length > 0) {
        const priorDurationSec =
          segmentDurations[row.segmentId] ??
          row.candidates[row.selectedTakeIndex]?.duration_sec ??
          0
        setSegmentRack((prev) =>
          prev.map((r) =>
            r.segmentId === segmentId
              ? {
                  ...r,
                  previousBatches: [
                    { durationSec: priorDurationSec, candidates: r.candidates },
                    ...(r.previousBatches ?? []),
                  ].slice(0, 4),
                }
              : r,
          ),
        )
      }

      setIsRackAuditioning(true)
      setError(null)
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
              : 2.5,
            diverseCandidates,
            durations: [segDuration],
            postprocessOutput: postProcess || null,
            minMatchScore,
          })

        setCurrentJobId(job_id)
        setJobTotalSegments(1)
        setJobStatus('running')
        setExamplesOpen(false)
        setTagsOpen(false)

        const outcome = await pollOmniVoiceJob(job_id, (segments) => {
          const regenSeg = segments[0]
          if (regenSeg && Array.isArray(regenSeg.candidates)) {
            // Merge candidates in as they stream in, so a take's waveform/player
            // appears as soon as it's rendered rather than waiting for the whole
            // regen batch to finish.
            setSegmentRack((prev) =>
              prev.map((r) =>
                r.segmentId === segmentId
                  ? {
                      ...r,
                      candidates: regenSeg.candidates,
                      // Regen always replaces candidates with fresh, unheard takes, so
                      // any previously selected index must not carry over onto them.
                      selectedTakeIndex:
                        regenSeg.candidates.length > 0 ? 0 : r.selectedTakeIndex,
                    }
                  : r,
              ),
            )
          }
        })

        if (outcome.status === 'completed') {
          // Clean up for single-seg regen
          setIsRackAuditioning(false)
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
        } else if (outcome.status === 'cancelled') {
          setIsRackAuditioning(false)
          setCurrentJobId(null)
          setJobStatus(null)
          setJobTotalSegments(0)
          setJobSegmentsCompleted([])
          setJobCurrentSegmentIndex(null)
          setJobMessage('Cancelled.')
          setJobEtaSeconds(null)
          setJobCandidatesTotal(0)
          setJobCandidatesCompleted(0)
          setJobCurrentCandidateIndex(null)
        } else {
          setError(outcome.message)
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : String(err),
        )
        setIsRackAuditioning(false)
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
      minMatchScore,
      segmentDurations,
      postProcess,
      pollOmniVoiceJob,
      setIsRackAuditioning,
      setError,
      setSegmentRack,
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
        const clamped = Math.max(SEGMENT_DURATION_MIN_SEC, Math.min(SEGMENT_DURATION_MAX_SEC, value))
        return { ...prev, [segmentId]: clamped }
      })
    },
    [],
  )

  const handleStitch = useCallback(async () => {
    if (segmentRack.length === 0 || isStitching) return

    const selectedRows = segmentRack.filter(
      (row) => row.selectedTakeIndex >= 0 && row.candidates[row.selectedTakeIndex]?.candidate_id,
    )

    if (selectedRows.length === 0) {
      setError('Select at least one take before stitching.')
      return
    }

    setIsStitching(true)
    setError(null)
    setSavedVoiceId(null)
    try {
      const plan: StitchPlanPayload = {
        clips: selectedRows.map((row) => {
          const candidate = row.candidates[row.selectedTakeIndex]
          const fromLibrary = candidate.candidate_id.startsWith('lib:')
          return {
            segmentId: fromLibrary ? row.segmentId : undefined,
            candidateId: fromLibrary ? undefined : candidate.candidate_id,
            trimStartMs: 0,
            trimEndMs: 0,
            fadeInMs: 0,
            fadeOutMs: 0,
            tempoFactor: candidateSpeeds[candidate.candidate_id] ?? 1,
            text: row.text,
            prosodyMode: 'auto',
          }
        }),
        paddingMs: new Array(Math.max(0, selectedRows.length - 1)).fill(0),
        crossfadeMs: 100,
        segmentTargetDbfs: -20,
        finalTargetDbfs: -18,
        finalCeilingDb: -1,
        compress: null,
        stylePreset: 'Neutral',
        paceMultiplier: 1,
        pauseOffsetMs: 0,
      }
      const blob = await renderStitchPlan(plan)
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
    candidateSpeeds,
  ])

  const handleSave = useCallback(async () => {
    if (segmentRack.length === 0 || isSaving) return

    const selectedRows = segmentRack.filter(
      (row) => row.selectedTakeIndex >= 0 && row.candidates[row.selectedTakeIndex]?.candidate_id,
    )

    if (selectedRows.length === 0) {
      setError('Select at least one take before saving.')
      return
    }

    const segments = selectedRows.map((r) => r.text)

    setIsSaving(true)
    setError(null)
    try {
      const plan: StitchPlanPayload = {
        clips: selectedRows.map((row) => {
          const candidate = row.candidates[row.selectedTakeIndex]
          const fromLibrary = candidate.candidate_id.startsWith('lib:')
          return {
            segmentId: fromLibrary ? row.segmentId : undefined,
            candidateId: fromLibrary ? undefined : candidate.candidate_id,
            trimStartMs: 0,
            trimEndMs: 0,
            fadeInMs: 0,
            fadeOutMs: 0,
            tempoFactor: candidateSpeeds[candidate.candidate_id] ?? 1,
            text: row.text,
            prosodyMode: 'auto',
          }
        }),
        paddingMs: new Array(Math.max(0, selectedRows.length - 1)).fill(0),
        crossfadeMs: 100,
        segmentTargetDbfs: -20,
        finalTargetDbfs: -18,
        finalCeilingDb: -1,
        compress: null,
        stylePreset: 'Neutral',
        paceMultiplier: 1,
        pauseOffsetMs: 0,
      }
      const targetFamilyId = useAppStore.getState().targetFamilyId
      const result = await saveOmniVoice({
        stitchPlan: plan,
        instruct,
        segments,
        accentId:
          matchedAccentBankEntry?.id ?? null,
        familyId: targetFamilyId,
        variantName: deliveryVariant.name,
        variantKind: deliveryVariant.kind,
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
    deliveryVariant,
    candidateSpeeds,
  ])

  const openStitchEditor = useCallback(async () => {
    if (segmentRack.length === 0) return

    const ctx = (() => {
      if (typeof window !== 'undefined' && window.AudioContext) {
        return new (window.AudioContext)()
      }
      return null
    })()

    if (!ctx) {
      setError('AudioContext not available')
      return
    }

    const clips: (StitchPlanClip & { durationMs?: number })[] = []

    for (const row of segmentRack) {
      if (row.selectedTakeIndex < 0) continue
      const candidate = row.candidates[row.selectedTakeIndex]
      if (!candidate || !candidate.candidate_id) continue

      let b64 = candidate.audio_base64
      if (!b64) {
        try {
          b64 = await getSegmentAudioBase64(row.segmentId)
        } catch {
          setError('Missing audio for a segment')
          await ctx.close()
          return
        }
      }

      const byteStr = atob(b64)
      const bytes = new Uint8Array(byteStr.length)
      for (let i = 0; i < byteStr.length; i++) {
        bytes[i] = byteStr.charCodeAt(i)
      }

      let durationMs = 0

      try {
        const arrayBuffer = bytes.buffer
        const audioBuffer = await ctx.decodeAudioData(
          arrayBuffer.slice(0) as ArrayBuffer,
        )
        durationMs = Math.round(audioBuffer.duration * 1000)
      } catch {
        durationMs = 0
      }

      const fromLibrary = candidate.candidate_id.startsWith('lib:')
      clips.push({
        clipId: row.segmentId + '-clip',
        ref: fromLibrary
          ? { segmentId: row.segmentId }
          : { candidateId: candidate.candidate_id },
        text: row.text,
        sourceAudioBase64: b64,
        sampleRate: candidate.sample_rate,
        trimStartMs: 0,
        trimEndMs: 0,
        fadeInMs: 0,
        fadeOutMs: 0,
        prosodyMode: 'auto',
        durationMs,
      })
    }

    await ctx.close()

    if (clips.length === 0) {
      setError('Select at least one take before opening the stitch editor.')
      return
    }

    const paddingLen = Math.max(0, clips.length - 1)
    for (let i = 0; i < paddingLen; i++) {
      setStitchPlanPaddingAt(i, 0)
    }

    setStitchPlanClips(clips as StitchPlanClip[])
    setStitchEditorOpen(true)
  }, [
    segmentRack,
    setError,
    setStitchPlanClips,
    setStitchPlanPaddingAt,
    setStitchEditorOpen,
  ])

  const handleResetSegments = useCallback(() => {
    if (segmentRack.length === 0 && !stitchedUrl) return
    if (
      !window.confirm(
        'Reset all segments? This clears every generated take for this script. Your script text and instruct are kept, and anything already saved to the segment library is unaffected.',
      )
    ) {
      return
    }
    if (stitchedUrl) URL.revokeObjectURL(stitchedUrl)
    setSegmentRack([])
    setStitchPlanClips([])
    setStitchPlanPaddingMs([])
    setStitchEditorOpen(false)
    setStitchedUrl(null)
    setStitchedBlob(null)
    setError(null)
    setCurrentJobId(null)
    setJobTotalSegments(0)
    setJobStatus(null)
  }, [
    segmentRack.length,
    stitchedUrl,
    setSegmentRack,
    setStitchPlanClips,
    setStitchPlanPaddingMs,
    setStitchEditorOpen,
    setStitchedUrl,
    setStitchedBlob,
    setError,
    setCurrentJobId,
    setJobTotalSegments,
    setJobStatus,
  ])

  const insertFromLibraryToTimeline = useCallback(
    async (seg: SegmentMeta) => {
      await insertSegmentIntoStitchTimeline(seg, setError)
    },
    [setError],
  )

  const insertVoiceToTimeline = useCallback(
    async (voice: VoiceMeta) => {
      await insertVoiceIntoStitchTimeline(voice, setError)
    },
    [setError],
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

  const toggleSelectAllFilteredLibrary = useCallback(() => {
    setLibrarySelection((prev) => {
      const allSelected = filteredLibrary.every((m) =>
        prev.has(m.segment_id),
      )
      if (allSelected) {
        const next = new Set(prev)
        filteredLibrary.forEach((m) => next.delete(m.segment_id))
        return next
      }
      const next = new Set(prev)
      filteredLibrary.forEach((m) => next.add(m.segment_id))
      return next
    })
  }, [filteredLibrary, setLibrarySelection])

  const addSelectedLibraryToRack = useCallback(
    () => {
      const chosen = library.filter(
        (m) => librarySelection.has(m.segment_id),
      )
      setSegmentRack((prev) => [
        ...prev,
        ...chosen
          .filter(
            (m) =>
              !prev.some(
                (row) => row.segmentId === m.segment_id,
              ),
          )
          .map((m) => ({
            segmentId: m.segment_id,
            text: m.text,
            candidates: [
              {
                candidate_id: `lib:${m.segment_id}`,
                sample_rate: m.sample_rate,
                audio_base64: m.audio_base64 ?? '',
                duration_sec: m.duration_sec ?? null,
                flagged: false,
                flag_reason: null,
                whisper_transcript: null,
                match_score: null,
              },
            ],
            selectedTakeIndex: 0,
          })),
      ])
      setLibrarySelection(new Set())
      setStitchedUrl(null)
      setSavedVoiceId(null)
    },
    [
      library,
      librarySelection,
      setSegmentRack,
      setLibrarySelection,
      setStitchedUrl,
      setSavedVoiceId,
    ],
  )

  const handleDeleteFromLibrary = useCallback(
    async (segmentId: string) => {
      try {
        await deleteOmniVoiceSegment(segmentId)
        refreshLibrary()
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : String(err),
        )
      }
    },
    [refreshLibrary, setError],
  )

  // -- Render: Left column --
  const leftColumn = (
    <AccentChipPanel
      selections={selections}
      matchedAccentPresetId={matchedAccentBankEntry?.id ?? null}
      onSelectAccentPreset={applyAccentPreset}
      onToggleSingle={toggleSingle}
      onToggleWhisper={toggleWhisper}
    />
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
                {scriptWordCount > 0 && (
                  <Tooltip.Root>
                    <Tooltip.Trigger asChild>
                      <span
                        className={cn(
                          'rounded-full px-1.5 py-0.5 text-[9px] font-semibold tabular-nums',
                          heroMeterState === 'in-range' &&
                            'bg-success/15 text-success dark:text-success',
                          heroMeterState === 'under' &&
                            'bg-muted text-muted-foreground',
                          heroMeterState === 'over' &&
                            'bg-warning/15 text-warning dark:text-warning',
                        )}
                      >
                        ~{estimatedScriptSeconds.toFixed(1)}s
                      </span>
                    </Tooltip.Trigger>
                    <Tooltip.Content side="bottom">
                      Estimated duration (words ÷ {ESTIMATED_WORDS_PER_SECOND} wps). Hero-take
                      target is {HERO_TARGET_MIN_SEC}-{HERO_TARGET_MAX_SEC}s — actual render
                      time may differ, this is just a live guide while you build the script.
                    </Tooltip.Content>
                  </Tooltip.Root>
                )}
              </div>
              <div className="flex items-center gap-1.5">
                {matchedAccentBankEntry &&
                  matchedAccentBankEntry.showcaseSentences.length > 0 && (
                    <Tooltip.Root>
                      <Tooltip.Trigger asChild>
                        <button
                          type="button"
                          onClick={() => applyHeroTake(matchedAccentBankEntry)}
                          className="inline-flex items-center gap-1 rounded-md border border-primary/40 bg-primary/10 px-2.5 py-1 text-[10px] font-semibold text-primary transition-colors hover:bg-primary/20"
                        >
                          ⚡ Build Hero Take
                        </button>
                      </Tooltip.Trigger>
                      <Tooltip.Content side="bottom">
                        One click: auto-picks a {HERO_TARGET_MIN_SEC}-{HERO_TARGET_MAX_SEC}s,
                        feature-diverse set of {matchedAccentBankEntry.label} showcase
                        sentences and replaces the script with them.
                      </Tooltip.Content>
                    </Tooltip.Root>
                  )}
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
                  <div className="flex flex-col gap-1.5 px-2.5 py-2">
                    {activeShowcaseSentences.map((sentence) => (
                      <div
                        key={sentence.text}
                        className="flex flex-wrap items-center gap-1"
                      >
                        <button
                          type="button"
                          title={sentence.note}
                          onClick={() => insertExampleSentence(sentence)}
                          className="rounded-full border border-border/90 bg-muted/70 px-2.5 py-0.5 text-[10px] text-foreground/90 transition-colors hover:bg-accent hover:text-foreground"
                        >
                          {sentence.text}
                        </button>
                        {sentence.features.map((feature) => (
                          <Tooltip.Root key={feature}>
                            <Tooltip.Trigger asChild>
                              <span className="cursor-help rounded border border-border/60 bg-muted/40 px-1 py-0.5 text-[9px] font-medium uppercase tracking-wide text-muted-foreground">
                                {FEATURE_INFO[feature].label}
                              </span>
                            </Tooltip.Trigger>
                            <Tooltip.Content side="bottom" className="max-w-64">
                              {FEATURE_INFO[feature].description}
                            </Tooltip.Content>
                          </Tooltip.Root>
                        ))}
                      </div>
                    ))}
                    <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground/80">
                      Hover a tag above to learn what it's listening for — these are the
                      specific sounds that make an accent recognizable, not just labels.
                    </p>
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
                <p className="mt-0.5 text-[10px] text-warning">
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
              isRackAuditioning
            }
            className="min-w-[160px]"
          >
            {isRackAuditioning
              ? 'Generating…'
              : 'Generate candidates'}
          </Button>

          {isRackAuditioning &&
            useAppStore.getState().ovCurrentJobId && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={async () => {
                  try {
                    const jobId = useAppStore
                      .getState()
                      .ovCurrentJobId
                    if (jobId)
                      await cancelOmniVoiceAudition(jobId)
                  } catch {
                    // Best effort
                  }
                  // Let the poll loop pick up the new status
                }}
                className="h-8 gap-1.5"
              >
                Stop
              </Button>
            )}

          <Disclose level="expert">
            <button
              type="button"
              data-testid="omnivoice-advanced-toggle"
              onClick={() =>
                setShowAdvanced(!showAdvanced)
              }
              className="text-[10px] text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground"
            >
              {showAdvanced
                ? 'Hide advanced'
                : 'Advanced'}
            </button>
          </Disclose>
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
                              ? '2.5'
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
                      Use recommended default (effective 2.5).
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
                        ? Number(guidanceScaleInput) || 2.5
                        : 2.5
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
                    placeholder="2.5"
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

              {/* Match confidence threshold */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-3">
                  <label className="flex min-w-[110px] items-center gap-1 text-[10px] text-muted-foreground">
                    <span>
                      Match confidence
                      <InfoIcon text="Minimum whisper-transcript match score a candidate must hit to avoid being flagged. Lower = more lenient (fewer retries, more borderline takes pass); higher = stricter. Auto uses word-count-based defaults." />
                    </span>
                  </label>
                  <button
                    type="button"
                    onClick={() =>
                      setMinMatchScore(
                        minMatchScore === null
                          ? 0.75
                          : null,
                      )
                    }
                    className={cn(
                      'ml-1 inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-[9px] font-medium transition-colors',
                      minMatchScore === null
                        ? 'border-primary/60 bg-primary/10 text-primary'
                        : 'bg-muted text-muted-foreground hover:bg-muted/80',
                    )}
                  >
                    Auto
                  </button>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min={0.5}
                    max={0.95}
                    step={0.01}
                    value={minMatchScore ?? 0.75}
                    onChange={(e) =>
                      setMinMatchScore(
                        Number(e.target.value),
                      )
                    }
                    className="flex-1 accent-primary"
                  />
                  <span className="w-10 shrink-0 text-right text-[10px] tabular-nums text-muted-foreground">
                    {minMatchScore === null
                      ? '—'
                      : minMatchScore.toFixed(2)}
                  </span>
                </div>
              </div>

              {/* Autoplay takes */}
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 text-[10px] text-muted-foreground">
                  <span>
                    Autoplay takes
                    <InfoIcon text="Automatically plays each take's audio as soon as it's selected or finishes rendering." />
                  </span>
                </label>
                <button
                  type="button"
                  role="switch"
                  aria-checked={
                    autoplayTakes
                  }
                  onClick={() =>
                    setAutoplayTakes(
                      !autoplayTakes,
                    )
                  }
                  className={cn(
                    'relative inline-flex h-5 w-9 cursor-pointer rounded-full border border-border transition-colors',
                    autoplayTakes
                      ? 'bg-primary'
                      : 'bg-muted',
                  )}
                >
                  <span
                    className={cn(
                      'absolute top-[3px] left-[3px] h-3.5 w-3.5 rounded-full bg-background shadow transition-transform',
                      autoplayTakes
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
                <p className="text-[9px] leading-snug text-warning/90">
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
                  data-testid="omnivoice-candidates-per-segment"
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
            <div className="sticky top-0 z-10 flex items-center justify-between gap-2 bg-card/95 py-1 backdrop-blur supports-[backdrop-filter]:bg-card/80">
              <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
                Segment rack
              </p>
              <Tooltip.Root>
                <Tooltip.Trigger asChild>
                  <span
                    className={cn(
                      'rounded-full px-1.5 py-0.5 text-[9px] font-semibold tabular-nums',
                      segmentRackTally.selectedCount === 0 &&
                        'bg-muted text-muted-foreground',
                      segmentRackTally.selectedCount > 0 &&
                        segmentRackTallyState === 'in-range' &&
                        'bg-success/15 text-success dark:text-success',
                      segmentRackTally.selectedCount > 0 &&
                        segmentRackTallyState === 'under' &&
                        'bg-muted text-muted-foreground',
                      segmentRackTally.selectedCount > 0 &&
                        segmentRackTallyState === 'over' &&
                        'bg-warning/15 text-warning dark:text-warning',
                    )}
                  >
                    {segmentRackTally.selectedCount}/{segmentRack.length} selected
                    {segmentRackTally.selectedCount > 0 &&
                      ` · ~${segmentRackTally.totalSec.toFixed(1)}s`}
                  </span>
                </Tooltip.Trigger>
                <Tooltip.Content side="bottom">
                  Rough total of the currently-selected takes' durations — a preview of the
                  final stitched length. Hero-take target is {HERO_TARGET_MIN_SEC}-
                  {HERO_TARGET_MAX_SEC}s; select a take per segment to update this.
                </Tooltip.Content>
              </Tooltip.Root>
              <button
                type="button"
                onClick={handleResetSegments}
                disabled={isRackAuditioning}
                title="Clear every generated segment and take, starting fresh with the same script"
                className="ml-auto shrink-0 whitespace-nowrap rounded-md border border-input px-2 py-1 text-[9px] font-medium text-muted-foreground hover:bg-accent hover:text-destructive disabled:opacity-40"
              >
                Reset segments
              </button>
            </div>

            <div className="flex min-w-0 flex-col gap-1 overflow-y-auto">
              <p className="text-[9px] text-muted-foreground">
                Click a take to select it for stitching; click again to deselect.
              </p>
              {segmentRack.some((r) => r.selectedTakeIndex >= 0) && (
                <p className="text-[9px] text-muted-foreground/70">
                  Your selections are temporary. Use Save to library on individual takes to keep them across sessions.
                </p>
              )}
              {segmentRack.map((row, segIndex) => {
                const isMissing =
                  row.candidates.length > 0 &&
                  row.selectedTakeIndex < 0
                return (
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
                    candidateSpeeds={candidateSpeeds}
                    onCandidateSpeedChange={onCandidateSpeedChange}
                    candidatesPerSegment={candidatesPerSegment}
                    avgCandidateSeconds={lastAvgCandidateSeconds}
                    onSelectBatch={selectCandidateBatch}
                    onSaveToLibrary={(meta) => {
                      setLibrary(
                        library.some((m) => m.segment_id === meta.segment_id)
                          ? library
                          : [meta, ...library]
                      )
                    }}
                    isMissingTake={isMissing}
                    instruct={instruct}
                    accentId={matchedAccentBankEntry?.id ?? null}
                  />
                )
              })}
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
                className="btn-brand shrink-0 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-medium"
              >
                {isStitching
                  ? 'Stitching…'
                  : 'Stitch selected takes'}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={openStitchEditor}
                disabled={segmentRack.length === 0}
                className="shrink-0 inline-flex items-center gap-1 rounded-full px-3 py-1 text-[11px]"
              >
                <Scissors className="h-3 w-3" />
                Open stitch editor
              </Button>
              <span className="self-center text-[9px] text-muted-foreground/70">
                trim, reorder, add gaps
              </span>
            </div>
         </div>
       )}

      {/* Stitched preview */}
       <AnimatePresence>
         {stitchedUrl && (
           console.log('[OmniVoicePanel] Result Block:', { savedVoiceId, isSaving, stitchedUrl, stitchedBlob }),
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
              <div className="flex flex-col gap-2">
                <DeliveryVariantSelector
                  value={deliveryVariantKind}
                  onChange={setDeliveryVariantKind}
                />
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
                      : 'Save to library'}
                </Button>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Stitch editor (timeline) */}
      <AnimatePresence>
        {stitchEditorOpen && (
          <StitchEditorPanel
            onClose={() => setStitchEditorOpen(false)}
            library={library}
            onInsertFromLibrary={insertFromLibraryToTimeline}
            voiceLibrary={voices}
            onInsertVoiceFromLibrary={insertVoiceToTimeline}
            onSave={async (plan: StitchPlanPayload, segments: string[]) => {
              try {
                setIsSaving(true)
                setError(null)
                const result = await saveOmniVoice({
                  instruct,
                  segments,
                  accentId:
                    matchedAccentBankEntry?.id ?? null,
                  stitchPlan: plan,
                  familyId: useAppStore.getState().targetFamilyId,
                  variantName: deliveryVariant.name,
                  variantKind: deliveryVariant.kind,
                })
                setSavedVoiceId(result.voice_id)
                onVoiceCreated?.(result.voice_id)
                setStitchEditorOpen(false)
              } catch (err) {
                setError(
                  err instanceof Error
                    ? err.message
                    : String(err),
                )
              } finally {
                setIsSaving(false)
              }
            }}
          />
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
        <p className="text-[9px] text-muted-foreground/80">
          Saved takes you can reuse in future reference clips.
        </p>
        {isLibraryOpen && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Filter by tag…"
                value={libraryFilter}
                onChange={(e) =>
                  setLibraryFilter(e.target.value)
                }
                className="w-full rounded-md border border-input bg-transparent p-2 text-xs outline-none focus-visible:border-ring"
              />
              <button
                type="button"
                disabled={filteredLibrary.length === 0}
                onClick={toggleSelectAllFilteredLibrary}
                className="shrink-0 whitespace-nowrap rounded-md border border-input px-2 py-2 text-[10px] font-medium text-muted-foreground hover:bg-accent disabled:opacity-40"
              >
                {filteredLibrary.length > 0 &&
                filteredLibrary.every((m) => librarySelection.has(m.segment_id))
                  ? 'Deselect all'
                  : 'Select all'}
              </button>
            </div>
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
                    <div className="flex flex-wrap items-center gap-x-2 text-[10px] text-muted-foreground">
                      <span>{m.tags.join(', ')}</span>
                      {((typeof m.duration_sec === 'number' && m.duration_sec > 0) || m.created_at) && (
                        <span className="text-muted-foreground/60">
                          {typeof m.duration_sec === 'number' && m.duration_sec > 0
                            ? `${m.duration_sec.toFixed(1)}s`
                            : ''}
                          {typeof m.duration_sec === 'number' && m.duration_sec > 0 && m.created_at
                            ? ' · '
                            : ''}
                          {m.created_at
                            ? new Date(m.created_at * 1000).toLocaleDateString('en-GB', { month: 'short', day: '2-digit' })
                            : ''}
                        </span>
                      )}
                    </div>
                  </div>
                  <ClipPlayer
                    audioUrl={`/omnivoice/segments/${encodeURIComponent(m.segment_id)}/audio`}
                    className="w-44"
                  />
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
                addSelectedLibraryToRack
              }
              disabled={
                librarySelection.size === 0
              }
            >
              Add selected to segment rack
            </Button>
          </div>
        )}
      </div>

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
      message: jobMessage || '',
      detail,
      progress: progressFraction,
      etaSeconds: jobEtaSeconds,
      onCancel: () => {
        const jobId = useAppStore.getState().ovCurrentJobId
        if (jobId) cancelOmniVoiceAudition(jobId).catch(() => {})
      },
    })
  }, [
    showLiveStatus,
    jobTotalSegments,
    jobCurrentSegmentIndex,
    jobCandidatesCompleted,
    jobCandidatesTotal,
    jobEtaSeconds,
    jobMessage,
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

function DeliveryVariantSelector({
  value,
  onChange,
}: {
  value: DeliveryVariantKind
  onChange: (value: DeliveryVariantKind) => void
}) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Delivery variant
      </p>
      <div className="flex flex-wrap gap-1.5">
        {DELIVERY_VARIANTS.map((variant) => (
          <button
            key={variant.kind}
            type="button"
            title={variant.hint}
            onClick={() => onChange(variant.kind)}
            className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition ${
              value === variant.kind
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-input bg-background text-muted-foreground hover:bg-accent hover:text-foreground'
            }`}
          >
            {variant.name}
          </button>
        ))}
      </div>
    </div>
  )
}

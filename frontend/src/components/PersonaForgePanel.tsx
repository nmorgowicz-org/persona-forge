import { useEffect, useMemo, useCallback } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  auditionOmniVoice,
  deleteOmniVoiceSegment,
  listOmniVoiceSegments,
  lockInOmniVoiceSegment,
  saveOmniVoice,
  stitchOmniVoice,
} from '@/lib/api'
import { ACCENT_BANK, type AccentBankEntry, type ShowcaseSentence } from '@/lib/accentBank'
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
    <AudioPlayer src={src} blob={blob} autoPlay={autoPlay} className={className} />
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
  const durationInput = useAppStore((s) => s.ovDurationInput)
  const speedInput = useAppStore((s) => s.ovSpeedInput)
  const lockedSegments = useAppStore((s) => s.ovLockedSegments)
  const currentText = useAppStore((s) => s.ovCurrentText)
  const currentCandidates = useAppStore(
    (s) => s.ovCurrentCandidates,
  )
  const currentSelectedIndex = useAppStore(
    (s) => s.ovCurrentSelectedIndex,
  )
  const isAuditioning = useAppStore((s) => s.ovIsAuditioning)
  const isLockingIn = useAppStore((s) => s.ovIsLockingIn)
  const isStitching = useAppStore((s) => s.ovIsStitching)
  const isSaving = useAppStore((s) => s.ovIsSaving)
  const error = useAppStore((s) => s.ovError)
  const stitchedUrl = useAppStore((s) => s.ovStitchedUrl)
  const stitchedBlob = useAppStore((s) => s.ovStitchedBlob)
  const savedVoiceId = useAppStore((s) => s.ovSavedVoiceId)
  const progress = useAppStore((s) => s.ovProgress)
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
  const setDurationInput = useAppStore(
    (s) => s.setOvDurationInput,
  )
  const setSpeedInput = useAppStore((s) => s.setOvSpeedInput)
  const setCurrentText = useAppStore((s) => s.setOvCurrentText)
  const setCurrentCandidates = useAppStore(
    (s) => s.setOvCurrentCandidates,
  )
  const setCurrentSelectedIndex = useAppStore(
    (s) => s.setOvCurrentSelectedIndex,
  )
  const setLockedSegments = useAppStore(
    (s) => s.setOvLockedSegments,
  )
  const setIsAuditioning = useAppStore(
    (s) => s.setOvIsAuditioning,
  )
  const setIsLockingIn = useAppStore((s) => s.setOvIsLockingIn)
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

  const wordCount = currentText.trim()
    ? currentText.trim().split(/\s+/).length
    : 0
  const isShortLine = wordCount > 0 && wordCount < 4
  const effectiveCandidatesPerSegment = isShortLine
    ? Math.max(candidatesPerSegment, 5)
    : candidatesPerSegment

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

  const candidateLabel =
    progress && progress.total > 0
      ? `segment ${progress.current_segment_index + 1}/${
          progress.segment_count || 1
        }, candidate ${
            progress.current_candidate_index + 1
          }/${
              progress.candidates_per_segment || 1
            } (${progress.completed}/${
              progress.total
            })`
      : null

  const activeShowcaseSentences =
    matchedAccentBankEntry?.showcaseSentences ?? []

  // -- Handlers --
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
      setCurrentText('')
      setCurrentCandidates(null)
      setStitchedUrl(null)
      setSavedVoiceId(null)
      setError(null)
    },
    [
      setSelections,
      setLockedSegments,
      setCurrentText,
      setCurrentCandidates,
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

  const applySuggestion = useCallback(
    (sentence: ShowcaseSentence) => {
      setCurrentText(sentence.text)
    },
    [setCurrentText],
  )

  const insertNonVerbalTag = useCallback(
    (tag: string) => {
      setCurrentText((prev) =>
        prev.trim() ? `${prev.trim()} ${tag}` : tag,
      )
    },
    [setCurrentText],
  )

  const handleAuditionCurrent = useCallback(async () => {
    const text = currentText.trim()
    if (!text || !instruct || isAuditioning) return
    setIsAuditioning(true)
    setError(null)
    setCurrentCandidates(null)
    setProgress(null)
    try {
      const result = await auditionOmniVoice({
        segments: [text],
        instruct,
        candidatesPerSegment:
          effectiveCandidatesPerSegment,
        numStep: numStepInput.trim()
          ? Number(numStepInput)
          : undefined,
        durationSeconds: durationInput.trim()
          ? Number(durationInput)
          : undefined,
        speed: speedInput.trim()
          ? Number(speedInput)
          : undefined,
      })
      setCurrentCandidates(
        result.segments[0]?.candidates ?? [],
      )
      setCurrentSelectedIndex(0)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : String(err),
      )
    } finally {
      setIsAuditioning(false)
      setProgress(null)
    }
  }, [
    currentText,
    instruct,
    isAuditioning,
    effectiveCandidatesPerSegment,
    numStepInput,
    durationInput,
    speedInput,
    setIsAuditioning,
    setError,
    setCurrentCandidates,
    setProgress,
    setCurrentSelectedIndex,
  ])

  const mergeWithPreviousLine = useCallback(async () => {
    if (lockedSegments.length === 0) return
    const prev =
      lockedSegments[lockedSegments.length - 1]
    setCurrentText(
      (curr) => `${prev.text} ${curr}`.trim(),
    )
    await handleDeleteFromLibrary(prev.segmentId)
  }, [
    lockedSegments,
    setCurrentText,
  ])

  const discardCandidates = useCallback(
    () => {
      setCurrentCandidates(null)
    },
    [setCurrentCandidates],
  )

  const lockInCurrentTake = useCallback(async () => {
    if (
      !currentCandidates ||
      !currentCandidates[currentSelectedIndex] ||
      isLockingIn
    )
      return
    const chosen =
      currentCandidates[currentSelectedIndex]
    setIsLockingIn(true)
    setError(null)
    try {
      const meta = await lockInOmniVoiceSegment({
        candidateId: chosen.candidate_id,
        text: currentText.trim(),
        instruct,
        accentId:
          matchedAccentBankEntry?.id ?? null,
      })
      setLockedSegments((prev) => [
        ...prev,
        {
          segmentId: meta.segment_id,
          text: meta.text,
          audioBase64:
            meta.audio_base64 ??
            chosen.audio_base64,
        },
      ])
      setCurrentText('')
      setCurrentCandidates(null)
      setStitchedUrl(null)
      setSavedVoiceId(null)
      refreshLibrary()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : String(err),
      )
    } finally {
      setIsLockingIn(false)
    }
  }, [
    currentCandidates,
    currentSelectedIndex,
    isLockingIn,
    currentText,
    instruct,
    matchedAccentBankEntry,
    setIsLockingIn,
    setError,
    setLockedSegments,
    setCurrentText,
    setCurrentCandidates,
    setStitchedUrl,
    setSavedVoiceId,
    refreshLibrary,
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

  const handleStitch = useCallback(async () => {
    if (
      lockedSegments.length === 0 ||
      isStitching
    )
      return
    setIsStitching(true)
    setError(null)
    setSavedVoiceId(null)
    try {
      const blob = await stitchOmniVoice({
        segmentIds: lockedSegments.map(
          (s) => s.segmentId,
        ),
      })
      setStitchedUrl(
        URL.createObjectURL(blob),
      )
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
    lockedSegments,
    isStitching,
    setIsStitching,
    setError,
    setSavedVoiceId,
    setStitchedUrl,
    setStitchedBlob,
  ])

  const handleSave = useCallback(async () => {
    if (
      lockedSegments.length === 0 ||
      isSaving
    )
      return
    setIsSaving(true)
    setError(null)
    try {
      const result = await saveOmniVoice({
        segmentIds: lockedSegments.map(
          (s) => s.segmentId,
        ),
        instruct,
        segments: lockedSegments.map(
          (s) => s.text,
        ),
        accentId:
          matchedAccentBankEntry?.id ??
          null,
      })
      setSavedVoiceId(
        result.voice_id,
      )
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
    lockedSegments,
    isSaving,
    instruct,
    matchedAccentBankEntry,
    onVoiceCreated,
    setIsSaving,
    setError,
    setSavedVoiceId,
  ])

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <div className="flex flex-col gap-5 rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm">
        <div>
          <h2 className="text-base font-semibold">
            Design an accent-cloned voice
          </h2>
          <p className="text-sm text-muted-foreground">
            OmniVoice only accepts a fixed set of tags —
            every option below is guaranteed valid. Pick a
            starting point, then adjust chips freely; the
            composed instruct string on the right always
            matches exactly what the model understands.
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
          <p className="mt-2 rounded-md bg-muted/60 px-2.5 py-2 text-[11px] leading-snug text-muted-foreground">
            Only Australian has a curated
            showcase-sentence bank so far (validated
            hands-on — see
            docs/plans/PLAN_omnivoice_integration.md).
            Other accents use this same closed vocabulary
            tag but haven't been quality-checked yet.
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
          <p className="mt-1.5 text-[11px] text-muted-foreground">
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
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            The only style tag OmniVoice documents —
            there's no "warm"/"sweet"/tone lever here
            (that's a VoiceDesign-only concept).
          </p>
        </ChipSection>
      </div>

      <div className="flex h-fit flex-col gap-4 rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm lg:sticky lg:top-8">
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">
            Composed instruct
          </p>
          <div
            data-testid="omnivoice-instruct"
            className="min-h-9 w-full rounded-md border border-input bg-muted/30 p-2 font-mono text-sm text-muted-foreground"
          >
            {instruct || (
              <span className="italic">
                Pick at least one chip on the left…
              </span>
            )}
          </div>
        </div>

        {lockedSegments.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-xs font-medium text-muted-foreground">
              Locked sentences (
              {lockedSegments.length})
            </p>
            {lockedSegments.map((seg, i) => (
              <div
                key={seg.segmentId}
                className="flex items-center gap-2 rounded-md border border-border bg-muted/30 p-2"
              >
                <span className="flex-1 text-sm">
                  {seg.text}
                </span>
                {seg.audioBase64 && (
                  <ClipPlayer
                    audioBase64={seg.audioBase64}
                    className="w-56"
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

        <div className="flex flex-col gap-3 rounded-lg border border-dashed border-border p-3">
          <p className="text-xs font-medium text-muted-foreground">
            {lockedSegments.length === 0
              ? 'First sentence'
              : 'Next sentence'}
          </p>

          {activeShowcaseSentences.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <p className="text-[11px] text-muted-foreground">
                Suggested lines that showcase this
                accent — click to use, then edit freely:
              </p>
              <div className="flex flex-wrap gap-1.5">
                {activeShowcaseSentences.map(
                  (sentence) => (
                    <button
                      key={sentence.text}
                      type="button"
                      title={sentence.note}
                      onClick={() =>
                        applySuggestion(
                          sentence,
                        )
                      }
                      className={cn(
                        'rounded-full border px-2.5 py-1 text-[11px] transition-colors',
                        currentText ===
                          sentence.text
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'border-border bg-transparent text-muted-foreground hover:bg-accent/40',
                      )}
                    >
                      {sentence.text}
                    </button>
                  ),
                )}
              </div>
            </div>
          )}

          <input
            type="text"
            data-testid="omnivoice-current-sentence"
            placeholder="Type or pick a sentence above…"
            className="w-full rounded-md border border-input bg-transparent p-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            value={currentText}
            onChange={(e) =>
              setCurrentText(e.target.value)
            }
          />

          <div className="flex flex-wrap items-center gap-1.5">
            {NON_VERBAL_TAGS.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() =>
                  insertNonVerbalTag(tag)
                }
                className="rounded-full border border-border bg-transparent px-2 py-0.5 font-mono text-[11px] text-muted-foreground hover:bg-accent/40"
              >
                {tag}
              </button>
            ))}
            {lockedSegments.length > 0 && (
              <button
                type="button"
                onClick={mergeWithPreviousLine}
                className="ml-1 text-[11px] text-muted-foreground underline decoration-dotted hover:text-foreground"
              >
                Merge with previous line
              </button>
            )}
          </div>

          {isShortLine && (
            <p className="text-[11px] text-amber-400">
              Short lines are the least reliable
              single-shot case — using{' '}
              {effectiveCandidatesPerSegment}{' '}
              candidates for this take instead of{' '}
              {candidatesPerSegment}. Consider "Merge
              with previous line" instead if this line
              stands alone.
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              Candidates
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
                className="h-8 w-16 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
            </label>
            <Button
              type="button"
              data-testid="omnivoice-audition-button"
              onClick={
                handleAuditionCurrent
              }
              disabled={
                !currentText.trim() ||
                !instruct ||
                isAuditioning
              }
            >
              {isAuditioning
                ? 'Generating…'
                : 'Generate candidates for this line'}
            </Button>
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-[11px] text-muted-foreground underline decoration-dotted hover:text-foreground"
            >
              {showAdvanced
                ? 'Hide advanced'
                : 'Advanced (quality / pacing)'}
            </button>
          </div>

          <AnimatePresence initial={false}>
            {showAdvanced && (
              <motion.div
                initial={{
                  opacity: 0,
                  height: 0,
                }}
                animate={{
                  opacity: 1,
                  height: 'auto',
                }}
                exit={{
                  opacity: 0,
                  height: 0,
                }}
                className="flex flex-wrap items-center gap-3 overflow-hidden rounded-md bg-muted/40 p-2.5"
              >
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  Steps
                  <input
                    type="number"
                    min={1}
                    max={64}
                    placeholder="32"
                    value={numStepInput}
                    onChange={(e) =>
                      setNumStepInput(
                        e.target.value,
                      )
                    }
                    title="Diffusion step count — higher is slower but can be cleaner. Server clamps to 1–64; leave blank for the model's default (32)."
                    className="h-8 w-16 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                  />
                </label>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  Duration (s)
                  <input
                    type="number"
                    min={0}
                    step={0.1}
                    placeholder="auto"
                    value={
                      durationInput
                    }
                    onChange={(e) =>
                      setDurationInput(
                        e.target.value,
                      )
                    }
                    title="Target clip length in seconds. Overrides Speed when both are set."
                    className="h-8 w-20 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                  />
                </label>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  Speed
                  <input
                    type="number"
                    min={0.25}
                    max={4}
                    step={0.05}
                    placeholder="1.0"
                    value={speedInput}
                    onChange={(e) =>
                      setSpeedInput(
                        e.target.value,
                      )
                    }
                    title="Playback-rate-style multiplier. Server clamps to 0.25–4.0."
                    className="h-8 w-20 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                  />
                </label>
              </motion.div>
            )}
          </AnimatePresence>

          {isAuditioning && (
            <div
              data-testid="omnivoice-progress"
              className="flex flex-col gap-1"
            >
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <motion.div
                  className="h-full bg-primary"
                  animate={{
                    width:
                      progress &&
                      progress.total > 0
                      ? `${Math.min(
                          100,
                          (progress.completed /
                            progress.total) *
                            100,
                        )}%`
                      : '8%',
                  }}
                  transition={{
                    ease: 'easeOut',
                    duration: 0.3,
                  }}
                />
              </div>
              <p className="text-[11px] text-muted-foreground">
                {progress?.phase === 'loading'
                  ? 'Loading OmniVoice checkpoint…'
                  : candidateLabel ??
                    'Starting…'}
                {progress?.phase ===
                  'generating' &&
                  progress.estimated_remaining_seconds !=
                    null && (
                    <>
                      {' '}
                      ·{' '}
                      {formatEta(
                        progress.estimated_remaining_seconds,
                      )}
                    </>
                  )}
              </p>
            </div>
          )}

          <AnimatePresence>
            {currentCandidates &&
              currentCandidates.length >
                0 && (
                <motion.div
                  initial={{
                    opacity: 0,
                    y: 6,
                  }}
                  animate={{
                    opacity: 1,
                    y: 0,
                  }}
                  exit={{
                    opacity: 0,
                    y: 6,
                  }}
                  className="flex flex-col gap-2"
                >
                  {currentCandidates.map(
                    (
                      candidate,
                      i,
                    ) => {
                      const selected =
                        i ===
                        currentSelectedIndex
                      return (
                        <div
                          key={candidate.candidate_id}
                          className="flex items-center gap-2"
                        >
                          <Button
                            type="button"
                            size="sm"
                            variant={
                              selected
                                ? 'default'
                                : 'outline'
                            }
                            onClick={() =>
                              setCurrentSelectedIndex(
                                i,
                              )
                            }
                          >
                            Take {i + 1}
                          </Button>
                          {candidate.flagged && (
                            <span
                              title={
                                candidate.flag_reason ??
                                undefined
                              }
                              className="shrink-0 rounded-full border border-amber-900/50 bg-amber-950/30 px-2 py-0.5 text-[10px] text-amber-300"
                            >
                              possibly bad take
                              {candidate.flag_reason
                                ? ` · ${candidate.flag_reason}`
                                : ''}
                            </span>
                          )}
                          <ClipPlayer
                            audioBase64={
                              candidate.audio_base64
                            }
                            className="flex-1"
                          />
                        </div>
                      )
                    },
                  )}
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      size="sm"
                      onClick={
                        lockInCurrentTake
                      }
                      disabled={
                        isLockingIn
                      }
                    >
                      {isLockingIn
                        ? 'Locking in…'
                        : 'Lock in this take'}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={
                        discardCandidates
                      }
                    >
                      Discard all takes
                    </Button>
                  </div>
                </motion.div>
              )}
          </AnimatePresence>
        </div>

        <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
          <button
            type="button"
            className="flex items-center justify-between text-left text-xs font-medium text-muted-foreground"
            onClick={() =>
              setIsLibraryOpen(
                (v) => !v,
              )
            }
          >
            <span>
              Segment library ({library.length})
            </span>
            <span>
              {isLibraryOpen
                ? 'Hide'
                : 'Browse'}
            </span>
          </button>
          {isLibraryOpen && (
            <div className="flex flex-col gap-2">
              <input
                type="text"
                placeholder="Filter by tag (e.g. australian, female)…"
                value={
                  libraryFilter
                }
                onChange={(e) =>
                  setLibraryFilter(
                    e.target.value,
                  )
                }
                className="w-full rounded-md border border-input bg-transparent p-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
              <div className="flex max-h-64 flex-col gap-1.5 overflow-y-auto">
                {filteredLibrary.length ===
                  0 && (
                  <p className="text-[11px] text-muted-foreground">
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
                      <p className="text-sm">
                        {m.text}
                      </p>
                      <p className="text-[11px] text-muted-foreground">
                        {m.tags.join(
                          ', ',
                        )}
                      </p>
                    </div>
                    {m.audio_base64 && (
                      <ClipPlayer
                        audioBase64={
                          m.audio_base64
                        }
                        className="w-48"
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
                  librarySelection.size ===
                  0
                }
              >
                Add selected to locked
                sentences
              </Button>
            </div>
          )}
        </div>

        {error && (
          <p
            data-testid="omnivoice-error"
            className="text-sm text-destructive"
          >
            {error}
          </p>
        )}

        {lockedSegments.length > 0 && (
          <Button
            type="button"
            data-testid="omnivoice-stitch-button"
            onClick={handleStitch}
            disabled={isStitching}
            className="self-start"
          >
            {isStitching
              ? 'Stitching…'
              : `Stitch ${lockedSegments.length} locked sentence${lockedSegments.length === 1 ? '' : 's'}`}
          </Button>
        )}

        <AnimatePresence>
          {stitchedUrl && (
            <motion.div
              data-testid="omnivoice-result"
              initial={{
                opacity: 0,
                y: 8,
              }}
              animate={{
                opacity: 1,
                y: 0,
              }}
              exit={{
                opacity: 0,
                y: 8,
              }}
              className="flex flex-col gap-3 rounded-md border border-border bg-muted/40 p-3"
            >
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
                  onClick={
                    handleSave
                  }
                  disabled={isSaving}
                  className="self-start"
                >
                  {isSaving
                    ? 'Saving…'
                    : 'Save to voice library'}
                </Button>
              )}
            </motion.div>
          )}
        </AnimatePresence>
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
    <div>
      <p className="mb-1.5 text-xs font-medium text-muted-foreground">
        {title}
      </p>
      {children}
    </div>
  )
}

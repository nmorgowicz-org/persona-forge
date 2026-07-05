import { useMemo, useCallback } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { createVoiceDesign, saveVoiceDesign } from '../lib/api'
import type { EditingVoice } from '../store'
import {
  AGES,
  EMPTY_SELECTIONS,
  GENDERS,
  PERSONA_GROUP_LABELS,
  PERSONAS,
  PRESETS,
  REGISTERS,
  TEXTURES,
  activeWarnings,
  composeDescription,
  hasChipSelections as computeHasChipSelections,
  sampleTextForSelections,
  type PersonaChip,
} from '../lib/voiceDesignChips'
import { VOICE_DESIGN_AUTHORING_TIPS, VOICE_DESIGN_EXAMPLES } from '../lib/voiceDesignExamples'
import { ChipButton } from './Chip'
import { AudioPlayer } from './AudioPlayer'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Dices } from 'lucide-react'
import { useAppStore } from '@/store'

const PERSONA_GROUPS: PersonaChip['group'][] = ['assistant', 'companion', 'power']

function formatEta(seconds: number | null): string {
  if (seconds == null) return 'estimating…'
  if (seconds < 1) return 'almost done'
  if (seconds < 60) return `~${Math.round(seconds)}s remaining`
  return `~${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s remaining`
}

interface VoiceDesignPanelProps {
  onVoiceCreated: (voiceId: string) => void
  initial?: EditingVoice | null
}

export function VoiceDesignPanel({ onVoiceCreated, initial }: VoiceDesignPanelProps) {
  // -- State from store --
  const selections = useAppStore((s) => s.vdSelections)
  const manualDescription = useAppStore((s) => s.vdManualDescription)
  const sampleText = useAppStore((s) => s.vdSampleText)
  const sampleTextTouched = useAppStore((s) => s.vdSampleTextTouched)
  const language = useAppStore((s) => s.vdLanguage)
  const seedInput = useAppStore((s) => s.vdSeedInput)
  const isGenerating = useAppStore((s) => s.vdIsGenerating)
  const modelLoaded = useAppStore((s) => s.modelLoaded)
  const error = useAppStore((s) => s.vdError)
  const progress = useAppStore((s) => s.vdProgress)
  const previewAudioUrl = useAppStore((s) => s.vdPreviewAudioUrl)
  const previewBlob = useAppStore((s) => s.vdPreviewBlob)
  const previewId = useAppStore((s) => s.vdPreviewId)
  const previewSeed = useAppStore((s) => s.vdPreviewSeed)
  const savedVoiceId = useAppStore((s) => s.vdSavedVoiceId)
  const isSaving = useAppStore((s) => s.vdIsSaving)
  const showWritingTips = useAppStore((s) => s.vdShowWritingTips)

  const setSelections = useAppStore((s) => s.setVdSelections)
  const setManualDescription = useAppStore((s) => s.setVdManualDescription)
  const setSampleText = useAppStore((s) => s.setVdSampleText)
  const setSampleTextTouched = useAppStore((s) => s.setVdSampleTextTouched)
  const setLanguage = useAppStore((s) => s.setVdLanguage)
  const setSeedInput = useAppStore((s) => s.setVdSeedInput)
  const setShowWritingTips = useAppStore((s) => s.setVdShowWritingTips)
  const setIsGenerating = useAppStore((s) => s.setVdIsGenerating)
  const setError = useAppStore((s) => s.setVdError)
  const setProgress = useAppStore((s) => s.setVdProgress)
  const setPreviewAudioUrl = useAppStore((s) => s.setVdPreviewAudioUrl)
  const setPreviewBlob = useAppStore((s) => s.setVdPreviewBlob)
  const setPreviewId = useAppStore((s) => s.setVdPreviewId)
  const setPreviewSeed = useAppStore((s) => s.setVdPreviewSeed)
  const setSavedVoiceId = useAppStore((s) => s.setVdSavedVoiceId)
  const setIsSaving = useAppStore((s) => s.setVdIsSaving)

  // -- One-time init from EditingVoice --
  const initRef = useMemo(() => ({ done: false }), [])

  // Voices saved outside the chip-based flow (e.g. Stitch Studio / OmniVoice) persist a
  // differently-shaped `selections` object (or none at all) -- truthy but missing
  // textures/personas arrays, which used to crash this check with a bare `.length` read.
  const hasChipSelections = computeHasChipSelections(initial?.selections)

  if (initial && !initRef.done) {
    initRef.done = true
    setSelections(
      (hasChipSelections && initial.selections) || EMPTY_SELECTIONS,
    )
    setManualDescription(
      initial && !hasChipSelections ? initial.description : null,
    )
    setSampleText(initial?.sampleText ?? '')
    setSampleTextTouched(Boolean(initial?.sampleText))
    setLanguage(initial?.language ?? 'English')
    setSeedInput(initial?.seed != null ? String(initial.seed) : '')
  }

  // -- Derived --
  const composed = useMemo(() => composeDescription(selections), [selections])
  const description = manualDescription ?? composed
  const warnings = useMemo(() => activeWarnings(selections), [selections])
  const effectiveSampleText = sampleTextTouched
    ? sampleText
    : sampleText || sampleTextForSelections(selections)

  // -- Handlers --
  const toggleSingle = useCallback(
    (key: 'gender' | 'age' | 'register', id: string) => {
      setSelections((prev) => ({ ...prev, [key]: prev[key] === id ? null : id }))
      setManualDescription(null)
    },
    [setSelections, setManualDescription],
  )

  const toggleMulti = useCallback(
    (key: 'textures' | 'personas', id: string) => {
      setSelections((prev) => {
        const current = prev[key]
        const next = current.includes(id)
          ? current.filter((v) => v !== id)
          : [...current, id]
        return { ...prev, [key]: next }
      })
      setManualDescription(null)
      if (key === 'personas' && !sampleTextTouched) setSampleText('')
    },
    [setSelections, setManualDescription, sampleTextTouched, setSampleText],
  )

  const applyPreset = useCallback(
    (presetId: string) => {
      const preset = PRESETS.find((p) => p.id === presetId)
      if (!preset) return
      setSelections(preset.selections)
      setManualDescription(null)
      setSampleText(sampleTextForSelections(preset.selections))
      setSampleTextTouched(false)
    },
    [setSelections, setManualDescription, setSampleText, setSampleTextTouched],
  )

  const applyExample = useCallback(
    (exampleId: string) => {
      const example = VOICE_DESIGN_EXAMPLES.find(
        (e) => e.id === exampleId,
      )
      if (!example) return
      setManualDescription(example.text)
    },
    [setManualDescription],
  )

  const handleGenerate = useCallback(async () => {
    if (
      !description.trim() ||
      !effectiveSampleText.trim() ||
      isGenerating
    )
      return
    setIsGenerating(true)
    setError(null)
    setProgress(null)
    try {
      const seed = seedInput.trim()
        ? Number(seedInput)
        : undefined
      const result = await createVoiceDesign({
        description,
        sampleText: effectiveSampleText,
        language,
        seed,
        selections,
      })
      // data URL so it survives unmount without needing revoke.
      const dataUrl = `data:audio/wav;base64,${result.audio_base64}`
      const blob = new Blob(
        [
          Uint8Array.from(
            atob(result.audio_base64),
            (c) => c.charCodeAt(0),
          ),
        ],
        { type: 'audio/wav' },
      )
      setPreviewAudioUrl(dataUrl)
      setPreviewBlob(blob)
      setPreviewId(result.preview_id)
      setPreviewSeed(result.seed)
      setSavedVoiceId(null)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : String(err),
      )
    } finally {
      setIsGenerating(false)
      setProgress(null)
    }
  }, [
    description,
    effectiveSampleText,
    isGenerating,
    seedInput,
    language,
    selections,
    setIsGenerating,
    setError,
    setProgress,
    setPreviewAudioUrl,
    setPreviewBlob,
    setPreviewId,
    setPreviewSeed,
    setSavedVoiceId,
  ])

  // Save preview to voice library (explicit user approval step)
  const handleSave = useCallback(async () => {
    if (!previewId || isSaving) return
    setIsSaving(true)
    setError(null)
    try {
      const result = await saveVoiceDesign(previewId)
      setSavedVoiceId(result.voice_id)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : String(err),
      )
    } finally {
      setIsSaving(false)
    }
  }, [
    previewId,
    isSaving,
    setIsSaving,
    setError,
    setSavedVoiceId,
  ])

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <div className="flex flex-col gap-5 rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm">
        <div>
          <h2 className="text-base font-semibold">
            {initial ? 'Tune this voice' : 'Design a voice'}
          </h2>
          <p className="text-sm text-muted-foreground">
            {initial
              ? 'Adjust the chips below, then generate a preview and save it when you are happy.'
              : 'Pick a starting point, tweak it, then preview and save.'}
          </p>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((preset) => (
            <Button
              key={preset.id}
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => applyPreset(preset.id)}
              className="rounded-full"
            >
              {preset.label}
            </Button>
          ))}
        </div>

        <ChipSection title="Demographics">
          <div className="flex flex-wrap gap-1.5">
            {GENDERS.map((chip) => (
              <ChipButton
                key={chip.id}
                label={chip.label}
                selected={selections.gender === chip.id}
                onClick={() => toggleSingle('gender', chip.id)}
              />
            ))}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {AGES.map((chip) => (
              <ChipButton
                key={chip.id}
                label={chip.label}
                selected={selections.age === chip.id}
                onClick={() => toggleSingle('age', chip.id)}
              />
            ))}
          </div>
        </ChipSection>

        <ChipSection title="Register">
          <div className="flex flex-wrap gap-1.5">
            {REGISTERS.map((chip) => (
              <ChipButton
                key={chip.id}
                label={chip.label}
                selected={selections.register === chip.id}
                onClick={() => toggleSingle('register', chip.id)}
              />
            ))}
          </div>
        </ChipSection>

        <ChipSection title="Texture / timbre">
          <div className="flex flex-wrap gap-1.5">
            {TEXTURES.map((chip) => (
              <ChipButton
                key={chip.id}
                label={chip.label}
                selected={selections.textures.includes(chip.id)}
                onClick={() => toggleMulti('textures', chip.id)}
              />
            ))}
          </div>
        </ChipSection>

        <ChipSection title="Persona / character">
          {PERSONA_GROUPS.map((group) => (
            <div key={group} className="mb-1.5 last:mb-0">
              <p className="mb-1 text-[11px] text-muted-foreground">
                {PERSONA_GROUP_LABELS[group]}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {PERSONAS.filter(
                  (p) => p.group === group,
                ).map((chip) => (
                  <ChipButton
                    key={chip.id}
                    label={chip.label}
                    selected={selections.personas.includes(
                      chip.id,
                    )}
                    onClick={() =>
                      toggleMulti('personas', chip.id)
                    }
                  />
                ))}
              </div>
            </div>
          ))}
        </ChipSection>
      </div>

      <div className="flex h-fit flex-col gap-4 rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm lg:sticky lg:top-8">
        <AnimatePresence initial={false}>
          {warnings.map((message) => (
            <motion.p
              key={message}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden rounded-md border border-amber-900/50 bg-amber-950/30 p-2 text-xs text-amber-300"
            >
              {message}
            </motion.p>
          ))}
        </AnimatePresence>

        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">
            Composed description
            {manualDescription !== null && (
              <button
                type="button"
                onClick={() => setManualDescription(null)}
                className="ml-2 text-[11px] font-normal text-muted-foreground underline decoration-dotted hover:text-foreground"
              >
                reset to chips
              </button>
            )}
          </label>
          <textarea
            data-testid="voice-design-description"
            className="min-h-16 w-full resize-y rounded-md border border-input bg-transparent p-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            value={description}
            onChange={(e) =>
              setManualDescription(e.target.value)
            }
            placeholder="Select chips above, or type a description directly (Advanced mode)."
          />

          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            <Select value="" onValueChange={applyExample}>
              <SelectTrigger
                data-testid="voice-design-example-select"
                className="h-7 w-auto gap-1.5 border-none bg-transparent px-0 text-[11px] text-muted-foreground underline decoration-dotted hover:text-foreground"
              >
                <SelectValue placeholder="Insert a tried-and-true example…" />
              </SelectTrigger>
              <SelectContent>
                {VOICE_DESIGN_EXAMPLES.map(
                  (example) => (
                    <SelectItem
                      key={example.id}
                      value={example.id}
                    >
                      {example.label}
                    </SelectItem>
                  ),
                )}
              </SelectContent>
            </Select>
            <button
              type="button"
              onClick={() =>
                setShowWritingTips((v) => !v)
              }
              className="text-[11px] text-muted-foreground underline decoration-dotted hover:text-foreground"
            >
              {showWritingTips
                ? 'Hide writing tips'
                : 'Show writing tips'}
            </button>
          </div>

          <AnimatePresence initial={false}>
            {showWritingTips && (
              <motion.ul
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="mt-1.5 list-disc space-y-1 overflow-hidden rounded-md bg-muted/60 px-4 py-2 pl-6 text-[11px] leading-snug text-muted-foreground"
              >
                {VOICE_DESIGN_AUTHORING_TIPS.map(
                  (tip) => (
                    <li key={tip}>{tip}</li>
                  ),
                )}
              </motion.ul>
            )}
          </AnimatePresence>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">
            Sample text (max ~15s)
          </label>
          <textarea
            data-testid="voice-design-sample-text"
            className="min-h-14 w-full resize-y rounded-md border border-input bg-transparent p-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            value={effectiveSampleText}
            onChange={(e) => {
              setSampleText(e.target.value)
              setSampleTextTouched(true)
            }}
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Select
            value={language}
            onValueChange={setLanguage}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="English">
                English
              </SelectItem>
              <SelectItem value="Chinese">
                Chinese
              </SelectItem>
            </SelectContent>
          </Select>

          <div className="flex items-center gap-1">
            <input
              type="number"
              inputMode="numeric"
              placeholder="Random seed"
              value={seedInput}
              onChange={(e) =>
                setSeedInput(e.target.value)
              }
              className="h-9 w-32 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            />
            <button
              type="button"
              aria-label="Randomize seed"
              title="Clear to use a fresh random seed"
              onClick={() => setSeedInput('')}
              className="flex size-9 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <Dices className="size-4" />
            </button>
          </div>

          <Button
            type="button"
            data-testid="voice-design-generate-button"
            onClick={handleGenerate}
            disabled={
              !description.trim() ||
              !effectiveSampleText.trim() ||
              isGenerating ||
              !modelLoaded
            }
            title={
              modelLoaded
                ? undefined
                : 'Model is still loading'
            }
          >
            {isGenerating
              ? 'Designing voice…'
              : initial
                ? 'Generate new voice'
                : 'Generate voice'}
          </Button>
        </div>

        {isGenerating && (
          <div
            data-testid="voice-design-progress"
            className="flex flex-col gap-1"
          >
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <motion.div
                className="h-full bg-primary"
                animate={{
                  width:
                    progress?.phase === 'generating'
                      ? '70%'
                      : '18%',
                }}
                transition={{
                  ease: 'easeOut',
                  duration: 0.3,
                }}
              />
            </div>
            <p className="text-[11px] text-muted-foreground">
              {progress?.phase === 'loading'
                ? 'Loading VoiceDesign checkpoint…'
                : 'Generating…'}
              {progress?.phase === 'generating' &&
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

        {error && (
          <p
            data-testid="voice-design-error"
            className="text-sm text-destructive"
          >
            {error}
          </p>
        )}

        <AnimatePresence>
          {previewAudioUrl && previewId && (
            <motion.div
              data-testid="voice-design-result"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              className="flex flex-col gap-3 rounded-md border border-border bg-muted/40 p-3"
            >
              <AudioPlayer
                src={previewAudioUrl}
                blob={previewBlob}
              />
              {previewSeed !== null && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>
                    Seed:{' '}
                    <span className="font-mono text-foreground">
                      {previewSeed}
                    </span>
                  </span>
                  {seedInput !== String(previewSeed) && (
                    <button
                      type="button"
                      onClick={() =>
                        setSeedInput(
                          String(previewSeed),
                        )
                      }
                      className="underline decoration-dotted hover:text-foreground"
                    >
                      Lock this seed
                    </button>
                  )}
                </div>
              )}
              {savedVoiceId ? (
                // Saved: show confirmation + "Use this voice"
                <div className="flex flex-col gap-2">
                  <p className="text-[11px] text-muted-foreground">
                    Saved as{' '}
                    <span className="font-mono text-foreground">
                      {savedVoiceId}
                    </span>
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => onVoiceCreated(savedVoiceId)}
                    className="self-start"
                  >
                    Use this voice
                  </Button>
                </div>
              ) : (
                // Not yet saved: "Save to library"
                <Button
                  type="button"
                  size="sm"
                  onClick={handleSave}
                  disabled={isSaving}
                  className="self-start"
                >
                  {isSaving
                    ? 'Saving…'
                    : 'Save to library'}
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

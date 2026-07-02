import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { createVoiceDesign } from '../lib/api'
import type { EditingVoice } from '../store'
import {
  ACCENTS,
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
  sampleTextForSelections,
  type ChipSelections,
  type PersonaChip,
} from '../lib/voiceDesignChips'
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

const PERSONA_GROUPS: PersonaChip['group'][] = ['assistant', 'companion', 'power']

interface VoiceDesignPanelProps {
  onVoiceCreated: (voiceId: string) => void
  /** Pre-fills the panel from a saved voice (Voice Library "Edit"). Consumed once on mount. */
  initial?: EditingVoice | null
}

export function VoiceDesignPanel({ onVoiceCreated, initial }: VoiceDesignPanelProps) {
  const hasChipSelections = Boolean(
    initial?.selections &&
      (initial.selections.accent ||
        initial.selections.gender ||
        initial.selections.age ||
        initial.selections.register ||
        initial.selections.textures.length > 0 ||
        initial.selections.personas.length > 0),
  )
  const [selections, setSelections] = useState<ChipSelections>(
    (hasChipSelections && initial?.selections) || EMPTY_SELECTIONS,
  )
  const [showExperimentalAccents, setShowExperimentalAccents] = useState(false)
  const [manualDescription, setManualDescription] = useState<string | null>(
    initial && !hasChipSelections ? initial.description : null,
  )
  const [sampleText, setSampleText] = useState(initial?.sampleText ?? '')
  const [sampleTextTouched, setSampleTextTouched] = useState(Boolean(initial?.sampleText))
  const [language, setLanguage] = useState(initial?.language ?? 'English')
  const [seedInput, setSeedInput] = useState(initial?.seed != null ? String(initial.seed) : '')
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [previewAudioUrl, setPreviewAudioUrl] = useState<string | null>(null)
  const [previewBlob, setPreviewBlob] = useState<Blob | null>(null)
  const [previewVoiceId, setPreviewVoiceId] = useState<string | null>(null)
  const [previewSeed, setPreviewSeed] = useState<number | null>(null)

  const composed = useMemo(() => composeDescription(selections), [selections])
  const description = manualDescription ?? composed
  const warnings = useMemo(() => activeWarnings(selections), [selections])
  const effectiveSampleText = sampleTextTouched
    ? sampleText
    : sampleText || sampleTextForSelections(selections)

  function toggleSingle(key: 'accent' | 'gender' | 'age' | 'register', id: string) {
    setSelections((prev) => ({ ...prev, [key]: prev[key] === id ? null : id }))
    setManualDescription(null)
  }

  function toggleMulti(key: 'textures' | 'personas', id: string) {
    setSelections((prev) => {
      const current = prev[key]
      const next = current.includes(id) ? current.filter((v) => v !== id) : [...current, id]
      return { ...prev, [key]: next }
    })
    setManualDescription(null)
    if (key === 'personas' && !sampleTextTouched) setSampleText('')
  }

  function applyPreset(presetId: string) {
    const preset = PRESETS.find((p) => p.id === presetId)
    if (!preset) return
    setSelections(preset.selections)
    setManualDescription(null)
    setSampleText(sampleTextForSelections(preset.selections))
    setSampleTextTouched(false)
  }

  async function handleGenerate() {
    if (!description.trim() || !effectiveSampleText.trim() || isGenerating) return
    setIsGenerating(true)
    setError(null)
    try {
      const seed = seedInput.trim() ? Number(seedInput) : undefined
      const result = await createVoiceDesign({
        description,
        sampleText: effectiveSampleText,
        language,
        seed,
        selections,
      })
      if (previewAudioUrl) URL.revokeObjectURL(previewAudioUrl)
      const bytes = Uint8Array.from(atob(result.audio_base64), (c) => c.charCodeAt(0))
      const blob = new Blob([bytes], { type: 'audio/wav' })
      setPreviewBlob(blob)
      setPreviewAudioUrl(URL.createObjectURL(blob))
      setPreviewVoiceId(result.voice_id)
      setPreviewSeed(result.seed)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsGenerating(false)
    }
  }

  const visibleAccents = ACCENTS.filter((a) => a.tier === 1 || showExperimentalAccents)

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <div className="flex flex-col gap-5 rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm">
        <div>
          <h2 className="text-base font-semibold">
            {initial ? 'Tune this voice' : 'Design a voice'}
          </h2>
          <p className="text-sm text-muted-foreground">
            {initial
              ? 'Adjust the chips below, then generate — this saves as a new voice, so the original is kept untouched.'
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

        <ChipSection title="Accent">
        <div className="flex flex-wrap gap-1.5">
          {visibleAccents.map((chip) => (
            <ChipButton
              key={chip.id}
              label={chip.label}
              selected={selections.accent === chip.id}
              onClick={() => toggleSingle('accent', chip.id)}
              experimental={chip.tier === 2}
            />
          ))}
        </div>
        <button
          type="button"
          onClick={() => setShowExperimentalAccents((v) => !v)}
          className="mt-1.5 text-[11px] text-muted-foreground underline decoration-dotted hover:text-foreground"
        >
          {showExperimentalAccents ? 'Hide experimental accents' : 'Show experimental accents'}
        </button>
      </ChipSection>

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
            <p className="mb-1 text-[11px] text-muted-foreground">{PERSONA_GROUP_LABELS[group]}</p>
            <div className="flex flex-wrap gap-1.5">
              {PERSONAS.filter((p) => p.group === group).map((chip) => (
                <ChipButton
                  key={chip.id}
                  label={chip.label}
                  selected={selections.personas.includes(chip.id)}
                  onClick={() => toggleMulti('personas', chip.id)}
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
            onChange={(e) => setManualDescription(e.target.value)}
            placeholder="Select chips above, or type a description directly (Advanced mode)."
          />
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
          <Select value={language} onValueChange={setLanguage}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="English">English</SelectItem>
              <SelectItem value="Chinese">Chinese</SelectItem>
            </SelectContent>
          </Select>

          <div className="flex items-center gap-1">
            <input
              type="number"
              inputMode="numeric"
              placeholder="Random seed"
              value={seedInput}
              onChange={(e) => setSeedInput(e.target.value)}
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
            disabled={!description.trim() || !effectiveSampleText.trim() || isGenerating}
          >
            {isGenerating
              ? 'Designing voice…'
              : initial
                ? 'Generate & save as new voice'
                : 'Generate & save voice'}
          </Button>
        </div>

        {error && (
          <p data-testid="voice-design-error" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <AnimatePresence>
          {previewAudioUrl && previewVoiceId && (
            <motion.div
              data-testid="voice-design-result"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              className="flex flex-col gap-3 rounded-md border border-border bg-muted/40 p-3"
            >
              <AudioPlayer src={previewAudioUrl} blob={previewBlob} />
              {previewSeed !== null && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>
                    Seed: <span className="font-mono text-foreground">{previewSeed}</span>
                  </span>
                  {seedInput !== String(previewSeed) && (
                    <button
                      type="button"
                      onClick={() => setSeedInput(String(previewSeed))}
                      className="underline decoration-dotted hover:text-foreground"
                    >
                      Lock this seed
                    </button>
                  )}
                </div>
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => onVoiceCreated(previewVoiceId)}
                className="self-start"
              >
                Use this voice
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

function ChipSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-muted-foreground">{title}</p>
      {children}
    </div>
  )
}

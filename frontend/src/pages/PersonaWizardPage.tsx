import { useState } from 'react'
import { motion } from 'motion/react'
import { useAppStore } from '@/store'
import { Button } from '@/components/ui/button'
import {
  PERSONAS,
  PERSONA_GROUP_LABELS,
  SAMPLE_TEXT_BY_PERSONA,
  DEFAULT_SAMPLE_TEXT,
  type PersonaChip,
} from '@/lib/voiceDesignChips'
import { ACCENT_BANK } from '@/lib/accentBank'
import { selectionsFromInstruct } from '@/lib/omnivoiceChips'

// Question set + copy are [decide-once] (docs/plans/20260720-post_merge_initiatives.md, C5).
// This page is an on-ramp only: every path ends by handing off to the real Voice Design
// panel with defaults pre-filled, never a parallel generator (C5 invariant).
type Step = 'use-case' | 'accent-matters' | 'accent-pick'

const PERSONA_GROUPS_ORDER: PersonaChip['group'][] = ['assistant', 'companion', 'power']

export function PersonaWizardPage() {
  const [step, setStep] = useState<Step>('use-case')
  const [persona, setPersona] = useState<PersonaChip | null>(null)

  const setPage = useAppStore((s) => s.setPage)
  const setDesignEngine = useAppStore((s) => s.setDesignEngine)
  const setVdSelections = useAppStore((s) => s.setVdSelections)
  const setVdSampleText = useAppStore((s) => s.setVdSampleText)
  const setVdSampleTextTouched = useAppStore((s) => s.setVdSampleTextTouched)
  const setOvSelections = useAppStore((s) => s.setOvSelections)

  function skipToEditor() {
    setPage('voice-design')
  }

  function landInPersonaEditor(chip: PersonaChip | null) {
    setDesignEngine('qwen')
    setVdSelections({
      gender: null,
      age: null,
      register: null,
      textures: [],
      personas: chip ? [chip.id] : [],
    })
    const sampleText = (chip && SAMPLE_TEXT_BY_PERSONA[chip.id]) || DEFAULT_SAMPLE_TEXT
    setVdSampleText(sampleText)
    setVdSampleTextTouched(true)
    setPage('voice-design')
  }

  function landInAccentEditor(accentId: string) {
    const entry = ACCENT_BANK.find((e) => e.id === accentId)
    if (!entry) return
    setDesignEngine('omnivoice')
    setOvSelections(selectionsFromInstruct(entry.instruct))
    setPage('voice-design')
  }

  return (
    <div className="flex flex-col gap-6">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-semibold tracking-tight">New Voice (Guided)</h1>
        <p className="text-sm text-muted-foreground">
          A few quick questions, then you land in the full editor with sensible defaults already
          applied — you can change anything from there.
        </p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex max-w-2xl flex-col gap-6 rounded-lg border border-border bg-card p-6"
      >
        {step === 'use-case' && (
          <div className="flex flex-col gap-4">
            <h2 className="text-base font-medium">What's this voice for?</h2>
            <div className="flex flex-col gap-4">
              {PERSONA_GROUPS_ORDER.map((group) => (
                <div key={group} className="flex flex-col gap-2">
                  <span className="text-xs font-medium text-muted-foreground">
                    {PERSONA_GROUP_LABELS[group]}
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {PERSONAS.filter((p) => p.group === group).map((chip) => (
                      <button
                        key={chip.id}
                        type="button"
                        onClick={() => {
                          setPersona(chip)
                          setStep('accent-matters')
                        }}
                        className="rounded-full border border-border px-3 py-1.5 text-sm transition-colors hover:border-primary hover:bg-primary/5"
                      >
                        {chip.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={() => {
                setPersona(null)
                setStep('accent-matters')
              }}
              className="self-start text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              Not sure yet — I'll pick traits myself
            </button>
          </div>
        )}

        {step === 'accent-matters' && (
          <div className="flex flex-col gap-4">
            <h2 className="text-base font-medium">Does a specific accent matter?</h2>
            <div className="flex gap-2">
              <Button onClick={() => setStep('accent-pick')}>Yes, pick an accent</Button>
              <Button variant="outline" onClick={() => landInPersonaEditor(persona)}>
                No, accent doesn't matter
              </Button>
            </div>
            <button
              type="button"
              onClick={() => setStep('use-case')}
              className="self-start text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              Back
            </button>
          </div>
        )}

        {step === 'accent-pick' && (
          <div className="flex flex-col gap-4">
            <h2 className="text-base font-medium">Pick an accent</h2>
            <p className="text-xs text-muted-foreground">
              Only a handful of accents are curated with showcase takes so far — more are on the
              way. If yours isn't listed, continue without one for now.
            </p>
            <div className="flex flex-wrap gap-2">
              {ACCENT_BANK.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  onClick={() => landInAccentEditor(entry.id)}
                  className="rounded-full border border-border px-3 py-1.5 text-sm transition-colors hover:border-primary hover:bg-primary/5"
                >
                  {entry.label}
                </button>
              ))}
            </div>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => landInPersonaEditor(persona)}
                className="self-start text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                None of these — continue without an accent
              </button>
              <button
                type="button"
                onClick={() => setStep('accent-matters')}
                className="self-start text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                Back
              </button>
            </div>
          </div>
        )}
      </motion.div>

      <button
        type="button"
        onClick={skipToEditor}
        className="self-start text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
      >
        Skip wizard, go to full editor
      </button>
    </div>
  )
}

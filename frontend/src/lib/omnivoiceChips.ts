// Guided OmniVoice instruct-chip taxonomy.
//
// OmniVoice's `instruct` field is NOT free text — the model repo's `generate()` splits it on
// commas and validates each tag against a fixed attribute grammar (see
// docs/dev/integration/omnivoice_integration.md §1a and [[voicedesign-accent-investigation]]).
// Anything outside this list is silently ignored or destabilizes generation, so the UI must
// only ever compose from these exact tags — no free-text tone/texture chips like VoiceDesign
// has. Order matters: docs/dev/integration/omnivoice_integration.md confirms hands-on that the
// documented order (gender, age, pitch, style, accent last) is the one that reliably works;
// deviating from it was the root cause of an earlier "load-bearing noise/drone" failure mode.

export interface Chip {
  id: string
  label: string
  /** The exact word/phrase inserted into the composed instruct string. Defaults to `label`. */
  text?: string
}

export const GENDERS: Chip[] = [
  { id: 'male', label: 'Male' },
  { id: 'female', label: 'Female' },
]

export const AGES: Chip[] = [
  { id: 'child', label: 'Child' },
  { id: 'teenager', label: 'Teenager' },
  { id: 'young-adult', label: 'Young adult', text: 'young adult' },
  { id: 'middle-aged', label: 'Middle-aged', text: 'middle-aged' },
  { id: 'elderly', label: 'Elderly' },
]

export const PITCHES: Chip[] = [
  { id: 'very-low', label: 'Very low', text: 'very low pitch' },
  { id: 'low', label: 'Low', text: 'low pitch' },
  { id: 'moderate', label: 'Moderate', text: 'moderate pitch' },
  { id: 'high', label: 'High', text: 'high pitch' },
  { id: 'very-high', label: 'Very high', text: 'very high pitch' },
]

// The one and only documented style value — not a general "tone" field.
export const STYLE_WHISPER: Chip = { id: 'whisper', label: 'Whisper' }

// English accents only — applies when the sample text is English. A separate Chinese-dialect
// list exists in the OmniVoice grammar but this UI doesn't offer Chinese generation yet.
export const ACCENTS: Chip[] = [
  { id: 'american', label: 'American' },
  { id: 'british', label: 'British' },
  { id: 'australian', label: 'Australian' },
  { id: 'canadian', label: 'Canadian' },
  { id: 'indian', label: 'Indian' },
  { id: 'chinese', label: 'Chinese' },
  { id: 'korean', label: 'Korean' },
  { id: 'japanese', label: 'Japanese' },
  { id: 'portuguese', label: 'Portuguese' },
  { id: 'russian', label: 'Russian' },
]

export interface OmniVoiceSelections {
  gender: string | null
  age: string | null
  pitch: string | null
  whisper: boolean
  accent: string | null
}

export const EMPTY_OMNIVOICE_SELECTIONS: OmniVoiceSelections = {
  gender: null,
  age: null,
  pitch: null,
  whisper: false,
  accent: null,
}

function findText(chips: Chip[], id: string | null): string | undefined {
  if (!id) return undefined
  const chip = chips.find((c) => c.id === id)
  return chip?.text ?? chip?.label.toLowerCase()
}

/**
 * Assemble the comma-separated instruct string in the fixed order the model requires:
 * gender, age, pitch, style, accent (accent always last, per §1a of the OmniVoice plan).
 */
export function composeInstruct(sel: OmniVoiceSelections): string {
  const parts: string[] = []
  const gender = findText(GENDERS, sel.gender)
  if (gender) parts.push(gender)
  const age = findText(AGES, sel.age)
  if (age) parts.push(age)
  const pitch = findText(PITCHES, sel.pitch)
  if (pitch) parts.push(pitch)
  if (sel.whisper) parts.push('whisper')
  const accent = findText(ACCENTS, sel.accent)
  if (accent) parts.push(`${accent} accent`)
  return parts.join(', ')
}

/** Reverse of composeInstruct — used to seed chip state from an accent-bank preset's instruct string. */
export function selectionsFromInstruct(instruct: string): OmniVoiceSelections {
  const tags = instruct
    .split(',')
    .map((t) => t.trim().toLowerCase())
    .filter(Boolean)
  const sel: OmniVoiceSelections = { ...EMPTY_OMNIVOICE_SELECTIONS }
  for (const tag of tags) {
    if (tag === 'whisper') {
      sel.whisper = true
      continue
    }
    const genderMatch = GENDERS.find((c) => (c.text ?? c.label.toLowerCase()) === tag)
    if (genderMatch) {
      sel.gender = genderMatch.id
      continue
    }
    const ageMatch = AGES.find((c) => (c.text ?? c.label.toLowerCase()) === tag)
    if (ageMatch) {
      sel.age = ageMatch.id
      continue
    }
    const pitchMatch = PITCHES.find((c) => (c.text ?? c.label.toLowerCase()) === tag)
    if (pitchMatch) {
      sel.pitch = pitchMatch.id
      continue
    }
    const accentMatch = ACCENTS.find((c) => tag === `${c.text ?? c.label.toLowerCase()} accent`)
    if (accentMatch) {
      sel.accent = accentMatch.id
      continue
    }
  }
  return sel
}

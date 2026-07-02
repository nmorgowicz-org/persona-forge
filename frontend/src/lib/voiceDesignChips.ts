// Guided VoiceDesign chip taxonomy and composition rules.
// Source of truth: docs/plans/PLAN_voice_design.md §8.3/§8.4. Do not expose the full lexicon
// as raw text in the UI — chips only, "Advanced" mode is the escape hatch for free text.

export interface Chip {
  id: string
  label: string
  /** The exact word/phrase inserted into the composed description. Defaults to `label`. */
  text?: string
}

export interface AccentChip extends Chip {
  tier: 1 | 2
}

export interface PersonaChip extends Chip {
  group: 'assistant' | 'companion' | 'power'
}

export const ACCENTS: AccentChip[] = [
  { id: 'us', label: 'English (US)', text: 'American', tier: 1 },
  { id: 'uk', label: 'English (UK)', text: 'British', tier: 1 },
  { id: 'au', label: 'English (AU)', text: 'Australian', tier: 1 },
  { id: 'ie', label: 'English (IE)', text: 'Irish', tier: 1 },
  { id: 'boston', label: 'Boston', text: 'Boston-accented American', tier: 2 },
  { id: 'nyc', label: 'New York', text: 'New York-accented American', tier: 2 },
  { id: 'southern', label: 'Southern US', text: 'Southern American', tier: 2 },
  { id: 'scottish', label: 'Scottish', text: 'Scottish', tier: 2 },
  { id: 'rp', label: 'Received Pronunciation', text: 'Received Pronunciation British', tier: 2 },
  { id: 'kiwi', label: 'Kiwi (NZ)', text: 'New Zealand', tier: 2 },
]

export const GENDERS: Chip[] = [
  { id: 'female', label: 'Female' },
  { id: 'male', label: 'Male' },
  { id: 'neutral', label: 'Neutral / androgynous' },
]

export const AGES: Chip[] = [
  { id: 'young', label: 'Young adult' },
  { id: 'adult', label: 'Adult' },
  { id: 'mature', label: 'Mature' },
]

export const REGISTERS: Chip[] = [
  { id: 'bass', label: 'Bass' },
  { id: 'baritone', label: 'Baritone' },
  { id: 'tenor', label: 'Tenor' },
  { id: 'alto', label: 'Alto' },
  { id: 'mezzo', label: 'Mezzo-Soprano' },
  { id: 'soprano', label: 'Soprano' },
]

export const TEXTURES: Chip[] = [
  { id: 'silky', label: 'Silky' },
  { id: 'even', label: 'Even' },
  { id: 'warm', label: 'Warm' },
  { id: 'rich', label: 'Rich' },
  { id: 'soft-rounded', label: 'Soft rounded' },
  { id: 'dark', label: 'Dark' },
  { id: 'deep', label: 'Deep' },
  { id: 'full', label: 'Full' },
  { id: 'grounded', label: 'Grounded' },
  { id: 'crisp', label: 'Crisp' },
  { id: 'clear', label: 'Clear' },
  { id: 'precise', label: 'Precise' },
  { id: 'slight-gravel', label: 'Slight gravel' },
  { id: 'bright', label: 'Bright' },
  // Additional validated "Section I control terms" from Alexandria's VOICE_REFERENCE.md
  // not previously covered above.
  { id: 'crystalline', label: 'Crystalline' },
  { id: 'balanced', label: 'Balanced' },
  { id: 'authoritative', label: 'Authoritative' },
  { id: 'firm', label: 'Firm' },
  { id: 'commanding', label: 'Commanding' },
  { id: 'husky', label: 'Husky' },
  { id: 'steady', label: 'Steady' },
  { id: 'clean', label: 'Clean' },
]

export const PERSONAS: PersonaChip[] = [
  { id: 'warm-assistant', label: 'Warm Assistant', group: 'assistant' },
  { id: 'confident-professional', label: 'Confident Professional', group: 'assistant' },
  { id: 'calm-grounded', label: 'Calm & Grounded', group: 'assistant' },
  { id: 'bubbly-energetic', label: 'Bubbly & Energetic', group: 'assistant' },
  { id: 'playful', label: 'Playful', group: 'companion' },
  { id: 'flirty', label: 'Flirty', group: 'companion' },
  { id: 'mysterious', label: 'Mysterious', group: 'companion' },
  { id: 'sultry-intimate', label: 'Sultry / Intimate', group: 'companion' },
  { id: 'authoritative-dominant', label: 'Authoritative / Dominant', group: 'power' },
  { id: 'soft-submissive', label: 'Soft / Submissive', group: 'power' },
]

export const PERSONA_GROUP_LABELS: Record<PersonaChip['group'], string> = {
  assistant: 'Assistant-forward',
  companion: 'Companion / social',
  power: 'Power dynamic',
}

export const TONE_OPTIONS: Chip[] = [
  { id: 'neutral', label: 'Neutral' },
  { id: 'calm-thoughtful', label: 'Calm, thoughtful' },
  { id: 'warm-amused', label: 'Warm and amused' },
  { id: 'tense-whispered', label: 'Tense, whispered' },
  { id: 'softly-excited', label: 'Softly excited' },
  { id: 'frustrated-clipped', label: 'Frustrated, clipped' },
]

// Persona-linked default sample text (§8.4) — the reference clip should already carry the
// persona's prosody, not a flat generic greeting.
export const SAMPLE_TEXT_BY_PERSONA: Record<string, string> = {
  'warm-assistant': "Hi, I'm here to help. What can I do for you today?",
  'confident-professional': "Let's get straight to it — here's exactly what we're going to do.",
  playful: "Well hello there. I was hoping you'd show up.",
  flirty: "Well hello there. I was hoping you'd show up.",
  'authoritative-dominant': "Listen closely, because I'm only going to say this once.",
  'sultry-intimate': "Come a little closer. I don't bite... much.",
  'calm-grounded': "Take a breath. We've got plenty of time to figure this out.",
}

export const DEFAULT_SAMPLE_TEXT = "Hi, I'm here to help. What can I do for you today?"

export interface ChipSelections {
  accent: string | null
  gender: string | null
  age: string | null
  register: string | null
  textures: string[]
  personas: string[]
}

export const EMPTY_SELECTIONS: ChipSelections = {
  accent: null,
  gender: null,
  age: null,
  register: null,
  textures: [],
  personas: [],
}

function findLabel(chips: Chip[], id: string | null): string | undefined {
  if (!id) return undefined
  return chips.find((c) => c.id === id)?.text ?? chips.find((c) => c.id === id)?.label
}

/**
 * Assemble a single description string, in the fixed anatomy order the model responds to
 * best: accent -> demographics -> register -> texture/timbre -> persona/character. This is a
 * UX assembly rule (alexandria empirical findings), not a model-enforced field — the
 * `/voice_design` API takes one free-text `description`.
 */
export function composeDescription(sel: ChipSelections): string {
  const accent = findLabel(ACCENTS, sel.accent)
  const age = findLabel(AGES, sel.age)
  const gender = findLabel(GENDERS, sel.gender)
  const register = REGISTERS.find((c) => c.id === sel.register)?.label
  const textures = sel.textures
    .map((id) => TEXTURES.find((c) => c.id === id)?.label)
    .filter((v): v is string => Boolean(v))
  const personas = sel.personas
    .map((id) => PERSONAS.find((c) => c.id === id)?.label)
    .filter((v): v is string => Boolean(v))

  const leadParts = [accent, age, gender].filter(Boolean)
  const lead = leadParts.length > 0 ? leadParts.join(' ') : ''

  const clauses: string[] = []
  if (lead) clauses.push(lead)
  if (register) clauses.push(register.toLowerCase())
  if (textures.length > 0) clauses.push(`${textures.join(', ').toLowerCase()} timbre`)
  if (personas.length > 0) clauses.push(`${personas.join(' and ').toLowerCase()} personality`)

  if (clauses.length === 0) return ''
  return clauses.join(', ') + '.'
}

export interface UnstableCombo {
  ids: string[]
  message: string
}

// Known unstable combinations (§8.3) — warn inline, don't block.
export const UNSTABLE_COMBOS: UnstableCombo[] = [
  {
    ids: ['bright', 'bubbly-energetic'],
    message:
      "This combination tends to create emotional instability. Consider using 'Bright' alone " +
      "and moving energy-related traits to the 'Tone' field for delivery control.",
  },
]

export function activeWarnings(sel: ChipSelections): string[] {
  const selected = new Set([...sel.textures, ...sel.personas])
  return UNSTABLE_COMBOS.filter((combo) => combo.ids.every((id) => selected.has(id))).map(
    (combo) => combo.message,
  )
}

export function sampleTextForSelections(sel: ChipSelections): string {
  for (const personaId of sel.personas) {
    if (SAMPLE_TEXT_BY_PERSONA[personaId]) return SAMPLE_TEXT_BY_PERSONA[personaId]
  }
  return DEFAULT_SAMPLE_TEXT
}

export interface VoiceDesignPreset {
  id: string
  label: string
  selections: ChipSelections
}

// Starter presets (§8.3) — one-click, no composing required.
export const PRESETS: VoiceDesignPreset[] = [
  {
    id: 'warm-assistant-us-female',
    label: 'Warm Assistant (US, female)',
    selections: {
      accent: 'us',
      gender: 'female',
      age: 'adult',
      register: 'mezzo',
      textures: ['warm', 'clear'],
      personas: ['warm-assistant'],
    },
  },
  {
    id: 'confident-professional-uk-male',
    label: 'Confident Professional (UK, male)',
    selections: {
      accent: 'uk',
      gender: 'male',
      age: 'adult',
      register: 'baritone',
      textures: ['rich', 'precise'],
      personas: ['confident-professional'],
    },
  },
  {
    id: 'playful-companion-au-female',
    label: 'Playful Companion (AU, female)',
    selections: {
      accent: 'au',
      gender: 'female',
      age: 'young',
      register: 'mezzo',
      textures: ['silky', 'even'],
      personas: ['playful'],
    },
  },
]

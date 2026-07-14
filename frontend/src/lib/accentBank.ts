// Curated per-accent sentence bank for the OmniVoice engine.
//
// NOT YET CURATED beyond AU/GB: entries below are structural placeholders pointing at
// OmniVoice instruct vocabulary validated in docs/dev/integration/omnivoice_integration.md, not a
// finished, human-listened-through sentence bank. `previewAudioUrl` intentionally stays null
// until a curation pass (docs/dev/features/persona_forge_studio.md §5 decision 3: repo-committed,
// human-picked audio, not build-time generated) promotes real files from
// audio/omnivoice_*_*.wav.
//
// instruct vocabulary itself is closed and strictly validated server-side (comma-separated
// gender/age/pitch/style/accent tags only) — see voicedesign-accent-investigation memory.
//
// showcaseSentences are *suggestions*, not a fixed script: each targets a specific accent
// feature (a vowel shift, rhythm/intonation pattern, lexical tell) so a user auditioning an
// accent has a real starting point for "what would actually expose this accent" instead of a
// blank textarea. The panel lets a user pick any subset, reorder, or type their own — or use
// `buildHeroTake` to auto-assemble a single-click, feature-diverse "hero" take.
//
// Feature taxonomy is Wells' lexical sets (https://en.wikipedia.org/wiki/Lexical_set) plus two
// non-phonetic buckets (LEXICAL_TELL, INTONATION) for accent cues that aren't a single vowel.
// See ecampusontario.pressbooks.pub/lexicalsets/chapter/18-goat-lexical-set for the GOAT
// research nick did (2026-07-04) that seeded this — GOAT differentiates AU/GB from US well but
// AU-vs-GB needs MOUTH/PRICE and lexical tells more than GOAT alone.

export type AccentFeature =
  | 'GOAT'
  | 'FACE'
  | 'MOUTH_PRICE'
  | 'BATH_TRAP'
  | 'RHOTICITY'
  | 'NURSE'
  | 'INTONATION'
  | 'LEXICAL_TELL'

export const FEATURE_INFO: Record<AccentFeature, { label: string; description: string }> = {
  GOAT: {
    label: 'GOAT vowel',
    description:
      'The vowel in "go," "home," "show." AU/GB diphthongize it (roughly "guh-oh"); General American keeps it closer to a pure tone.',
  },
  FACE: {
    label: 'FACE vowel',
    description:
      'The vowel in "day," "way," "today." Australian shifts this noticeably toward "oi"/"ay" territory ("toh-dye") — one of the more recognizable AU tells.',
  },
  MOUTH_PRICE: {
    label: 'MOUTH / PRICE vowels',
    description:
      'The vowels in "loud," "found" (MOUTH) and "wide," "tide" (PRICE). Australian raises/backs these the most; British is milder; General American is flattest. Often a stronger AU-vs-GB cue than GOAT.',
  },
  BATH_TRAP: {
    label: 'BATH/TRAP split',
    description:
      'Words like "dance," "class," "after," "can\'t." AU and GB use a broad "ah" here; General American keeps the short "a" from TRAP. Good for separating any Commonwealth accent from US.',
  },
  RHOTICITY: {
    label: 'Rhoticity (the "r" after vowels)',
    description:
      'Whether a written "r" after a vowel is actually pronounced — "car," "further," "water." AU/GB drop it (non-rhotic); General American pronounces it (rhotic). Categorical, not gradient — often the single strongest accent cue.',
  },
  NURSE: {
    label: 'NURSE vowel',
    description:
      'The vowel in "nurse," "first," "her." Useful for telling closely related non-rhotic accents apart (e.g. AU vs NZ) once the bigger tells are already covered.',
  },
  INTONATION: {
    label: 'Rhythm & intonation',
    description:
      'Sentence-level pitch pattern and stress timing — rising tag-questions ("...hey?"), idiomatic phrasing rhythm. Not a single vowel, but often what makes a line "sound like" an accent even before the vowels register.',
  },
  LEXICAL_TELL: {
    label: 'Lexical tell',
    description:
      'A word or phrase a speaker of that accent would naturally use ("arvo," "mate," "brilliant," "queue") that a generic accent wouldn\'t say — a vocabulary giveaway rather than a pronunciation one.',
  },
}

export interface ShowcaseSentence {
  text: string
  // What accent feature this sentence is designed to expose — shown as a hint so a user can
  // choose sentences that stress-test the specific traits they care about.
  note: string
  // Structured tags (subset of AccentFeature) so `buildHeroTake` can pick a feature-diverse,
  // non-redundant combination instead of just the first few sentences in list order.
  features: AccentFeature[]
}

export interface AccentBankEntry {
  id: string
  label: string
  instruct: string
  showcaseSentences: ShowcaseSentence[]
  previewAudioUrl: string | null
}

// Real data point (nick, 2026-07-04): a 25-word sentence rendered to ~6.4s at guidance=2.5,
// steps=32 — about 3.9 words/sec. Normal conversational speech is closer to ~2.5 words/sec;
// splitting the difference keeps the hero-take estimate from running short in practice.
export const ESTIMATED_WORDS_PER_SECOND = 3.2

// A "hero" take should be long enough to give the clone real range to work with, short enough
// to stay auditionable in one pass (docs/dev/features/persona_forge_studio.md hero-reference goal, nick
// 2026-07-04: "we need 10-15 seconds for a proper hero set of sentences").
export const HERO_TARGET_MIN_SEC = 10
export const HERO_TARGET_MAX_SEC = 15

export function estimateSeconds(text: string): number {
  const words = text.trim().split(/\s+/).filter(Boolean).length
  return words / ESTIMATED_WORDS_PER_SECOND
}

/**
 * Greedily assemble a feature-diverse subset of an accent's showcase sentences that lands in
 * [minSec, maxSec] of estimated duration. Walks sentences in curated order, keeping one once it
 * either covers a not-yet-seen feature or the running total is still short of minSec; stops once
 * the target window is filled or every feature is covered. Always returns at least one sentence
 * if the entry has any.
 */
export function buildHeroTake(
  entry: AccentBankEntry,
  opts: { minSec?: number; maxSec?: number } = {},
): ShowcaseSentence[] {
  const minSec = opts.minSec ?? HERO_TARGET_MIN_SEC
  const maxSec = opts.maxSec ?? HERO_TARGET_MAX_SEC
  const allFeatures = new Set(entry.showcaseSentences.flatMap((s) => s.features))

  const picked: ShowcaseSentence[] = []
  const covered = new Set<AccentFeature>()
  let totalSec = 0

  for (const sentence of entry.showcaseSentences) {
    if (totalSec >= maxSec) break
    const sec = estimateSeconds(sentence.text)
    const addsNewFeature = sentence.features.some((f) => !covered.has(f))
    const underMin = totalSec < minSec
    if (!addsNewFeature && !underMin) continue
    if (totalSec + sec > maxSec && picked.length > 0) continue

    picked.push(sentence)
    sentence.features.forEach((f) => covered.add(f))
    totalSec += sec

    if (totalSec >= minSec && covered.size >= allFeatures.size) break
  }

  if (picked.length === 0 && entry.showcaseSentences.length > 0) {
    picked.push(entry.showcaseSentences[0])
  }
  return picked
}

export const ACCENT_BANK: AccentBankEntry[] = [
  {
    id: 'au',
    label: 'Australian',
    // nick wants a younger, higher, sweeter-sounding take (2026-07-03) — pitch and age are
    // the only literal levers in OmniVoice's closed instruct vocabulary (no warmth/sweet tag
    // exists, see voicedesign-accent-investigation memory), so this is "high pitch" +
    // "young adult" as the closest available combination. Bump to "very high pitch" via the
    // UI's instruct override if this still isn't bright enough once auditioned live.
    instruct: 'female, young adult, high pitch, australian accent',
    showcaseSentences: [
      {
        text: "It's closed, you know.",
        note: 'baseline — short, neutral, easy first listen',
        features: [],
      },
      {
        text: "I'm not going home till the show's over, mate.",
        note: 'GOAT vowel in "going/home/show\'s/over" + the "mate" lexical tell',
        features: ['GOAT', 'LEXICAL_TELL'],
      },
      {
        text: "No way I'm paying that much for a plate of prawns today.",
        note: 'FACE vowel shift in "today"/"way" toward "oi/ay" ("toh-dye")',
        features: ['FACE'],
      },
      {
        text: 'Grab your togs, we\'re heading down the beach this arvo.',
        note: 'AU-only vocabulary ("togs," "arvo") a generic English accent would never say',
        features: ['LEXICAL_TELL'],
      },
      {
        text: "Can't be bothered dancing after a day like that, hey?",
        note: 'BATH/TRAP broad-A in "can\'t/dancing/after" + rising tag-question on "hey?"',
        features: ['BATH_TRAP', 'INTONATION'],
      },
      {
        text: "She's right, no worries, we'll sort it out later.",
        note: 'idiomatic AU reassurance phrasing + its rhythm/stress pattern',
        features: ['LEXICAL_TELL', 'INTONATION'],
      },
      {
        text: 'Is that really the best price you can do?',
        note: 'PRICE vowel in "price" + fronted "ee" in "really" + natural question intonation',
        features: ['MOUTH_PRICE', 'INTONATION'],
      },
      {
        text: "Her car's parked further down, near the water.",
        note: 'non-rhotic — "car\'s/further/water" all drop the written "r"',
        features: ['RHOTICITY'],
      },
    ],
    previewAudioUrl: null,
  },
  {
    id: 'gb',
    label: 'British',
    // Unlike the AU entry above, nick hasn't given a demographic preference for this one, so
    // it's accent-only — clicking the preset resets gender/age/pitch chips (same as any
    // preset does) rather than asserting a specific target voice. Revisit once one's validated.
    instruct: 'british accent',
    showcaseSentences: [
      {
        text: 'Right, shall we pop round for a spot of tea, then?',
        note: '"pop round"/"spot of tea" lexical tells + clipped, rhythmic RP-ish phrasing',
        features: ['LEXICAL_TELL', 'INTONATION'],
      },
      {
        text: "No, don't go home alone, Joe — it's rather cold out.",
        note: 'GOAT vowel in "go/home/alone/Joe" — closer/less-diphthongized than the AU version',
        features: ['GOAT', 'LEXICAL_TELL'],
      },
      {
        text: 'The loud crowd found the wide tide line by the shore.',
        note: 'MOUTH/PRICE — noticeably milder raising than AU on the same words',
        features: ['MOUTH_PRICE'],
      },
      {
        text: "I can't fathom why the class went dancing after the bath.",
        note: 'BATH/TRAP broad-A in "can\'t/class/after/bath" — shared with AU, absent in GA',
        features: ['BATH_TRAP'],
      },
      {
        text: "Her car's parked further down, near the water tower.",
        note: 'non-rhotic, same as AU — the pair that most separates it from General American',
        features: ['RHOTICITY'],
      },
      {
        text: "It's a bit of a faff, isn't it, love?",
        note: '"faff"/"love" lexical tells + falling-then-checking tag-question rhythm',
        features: ['LEXICAL_TELL', 'INTONATION'],
      },
      {
        text: "The first nurse worked the early shift, didn't she?",
        note: 'NURSE vowel in "first/nurse/early" — helps separate GB from AU/NZ once bigger tells are covered',
        features: ['NURSE', 'INTONATION'],
      },
    ],
    previewAudioUrl: null,
  },
]

// Looks up which AccentFeatures a saved segment's text was designed to exercise, by matching
// it against the curated showcase bank for its accent. Free-typed text that doesn't match any
// showcase sentence verbatim returns []  — classifying arbitrary text is the Option B follow-up.
export function lookupFeatureTags(
  accentId: string | null | undefined,
  text: string,
): AccentFeature[] {
  if (!accentId) return []
  const entry = ACCENT_BANK.find((e) => e.id === accentId)
  if (!entry) return []
  const trimmed = text.trim()
  const sentence = entry.showcaseSentences.find((s) => s.text.trim() === trimmed)
  return sentence?.features ?? []
}

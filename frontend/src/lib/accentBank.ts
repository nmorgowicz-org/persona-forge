// Curated per-accent sentence bank for the Persona Forge OmniVoice engine.
//
// NOT YET CURATED: entries below are structural placeholders pointing at the OmniVoice
// instruct vocabulary validated in docs/plans/PLAN_omnivoice_integration.md, not a finished,
// human-listened-through sentence bank. `previewAudioUrl` intentionally stays null until a
// curation pass (PLAN_persona_forge_studio.md §5 decision 3: repo-committed, human-picked
// audio, not build-time generated) promotes real files from audio/omnivoice_au_*.wav.
//
// The instruct vocabulary itself is closed and strictly validated server-side (comma-separated
// gender/age/pitch/style/accent tags only) — see voicedesign-accent-investigation memory.
//
// showcaseSentences are *suggestions*, not a fixed script: each targets a specific accent
// feature (a vowel shift, a rhythm/intonation pattern, a lexical tell) so a user auditioning
// an accent has a starting point for "what would actually expose this accent" instead of a
// blank textarea. The panel lets the user pick any subset, reorder, or type their own.

export interface ShowcaseSentence {
  text: string
  // What accent feature this sentence is designed to expose — shown as a hint so the user
  // can choose sentences that stress-test the specific traits they care about.
  note: string
}

export interface AccentBankEntry {
  id: string
  label: string
  instruct: string
  showcaseSentences: ShowcaseSentence[]
  previewAudioUrl: string | null
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
      },
      {
        text: "I'm not going home till the show's over, mate.",
        note: 'the AU "mate" tell + broad, non-rhotic "over" and "show\'s"',
      },
      {
        text: "No way I'm paying that much for a plate of prawns today.",
        note: '"today"/"way" — the AU-distinctive /eɪ/ diphthong shift toward /ɐɪ/ ("toh-dye")',
      },
      {
        text: "Grab your togs, we're heading down the beach this arvo.",
        note: 'AU-only vocabulary ("togs", "arvo") that a generic English accent won\'t say naturally',
      },
      {
        text: "Can't be bothered dancing after a day like that, hey?",
        note: 'flattened "a" in "can\'t"/"dancing" + rising tag-question intonation on "hey?"',
      },
      {
        text: "She's right, no worries, we'll sort it out later.",
        note: 'idiomatic AU reassurance phrasing + rhythm/stress pattern',
      },
      {
        text: "Is that really the best price you can do?",
        note: 'fronted "ee" in "really" + natural question intonation',
      },
    ],
    previewAudioUrl: null,
  },
]

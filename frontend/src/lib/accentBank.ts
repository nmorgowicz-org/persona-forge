// Curated per-accent sentence bank for the Persona Forge (OmniVoice) engine.
//
// NOT YET CURATED: entries below are structural placeholders pointing at the OmniVoice
// instruct vocabulary validated in docs/plans/PLAN_omnivoice_integration.md, not a finished,
// human-listened-through sentence bank. `previewAudioUrl` intentionally stays null until a
// curation pass (PLAN_persona_forge_studio.md §5 decision 3: repo-committed, human-picked
// audio, not build-time generated) promotes real files from audio/omnivoice_au_*.wav.
//
// The instruct vocabulary itself is closed and strictly validated server-side (comma-separated
// gender/age/pitch/style/accent tags only) — see voicedesign-accent-investigation memory.

export interface AccentBankEntry {
  id: string
  label: string
  instruct: string
  segments: string[]
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
    segments: [
      "It's closed, you know.",
      "I'm not going home till the show's over.",
    ],
    previewAudioUrl: null,
  },
]

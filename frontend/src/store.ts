import { create } from 'zustand'
import type {
  OmniVoiceAuditionResult,
  OmniVoiceCandidate,
  OmniVoiceProgress,
  SegmentMeta,
  VoiceDesignProgress,
  VoiceMeta,
} from './lib/api'
import { applyTheme, loadStoredTheme, type Theme } from './lib/theme'
import type { ChipSelections } from './lib/voiceDesignChips'
import type { OmniVoiceSelections } from './lib/omnivoiceChips'

export type Page = 'speak' | 'voice-design' | 'voice-library' | 'integrations' | 'runtime'
export type DesignEngine = 'qwen' | 'omnivoice'

// A voice queued up from the Voice Library's "Edit" action, to be consumed once by
// VoiceDesignPage and cleared — see VoiceDesignPage.tsx. Editing forks a new voice on save
// (there's no in-place update), so this only ever pre-fills the design panel.
export interface EditingVoice {
  voiceId: string
  description: string
  sampleText: string
  language: string
  seed: number | null
  selections: ChipSelections | null
}

export interface LockedSegment {
  segmentId: string
  text: string
  audioBase64: string
}

export interface SegmentRackRow {
  segmentId: string
  text: string
  candidates: OmniVoiceCandidate[]
  selectedTakeIndex: number
}

interface StoreState {
  // ---- Core ----
  page: Page
  theme: Theme
  text: string
  voiceId: string | null
  voices: VoiceMeta[]
  audioUrl: string | null
  isGenerating: boolean
  error: string | null
  editingVoice: EditingVoice | null
  designEngine: DesignEngine

  setPage: (page: Page) => void
  setTheme: (theme: Theme) => void
  setText: (text: string) => void
  setVoiceId: (voiceId: string | null) => void
  setVoices: (voices: VoiceMeta[]) => void
  setAudioUrl: (url: string | null) => void
  setGenerating: (isGenerating: boolean) => void
  setError: (error: string | null) => void
  setEditingVoice: (voice: EditingVoice | null) => void
  setDesignEngine: (engine: DesignEngine) => void

  // ---- VoiceDesign (Qwen) ----
  vdSelections: ChipSelections
  vdManualDescription: string | null
  vdSampleText: string
  vdSampleTextTouched: boolean
  vdLanguage: string
  vdSeedInput: string
  vdShowWritingTips: boolean
  vdIsGenerating: boolean
  vdError: string | null
  vdProgress: VoiceDesignProgress | null
  vdPreviewAudioUrl: string | null
  vdPreviewBlob: Blob | null
  vdPreviewId: string | null
  vdPreviewSeed: number | null
  vdSavedVoiceId: string | null
  vdIsSaving: boolean

  setVdSelections: (
    updater: ChipSelections | ((prev: ChipSelections) => ChipSelections),
  ) => void
  setVdManualDescription: (v: string | null) => void
  setVdSampleText: (v: string) => void
  setVdSampleTextTouched: (v: boolean) => void
  setVdLanguage: (v: string) => void
  setVdSeedInput: (v: string) => void
  setVdShowWritingTips: (v: boolean | ((p: boolean) => boolean)) => void
  setVdIsGenerating: (v: boolean) => void
  setVdError: (v: string | null) => void
  setVdProgress: (v: VoiceDesignProgress | null) => void
  setVdPreviewAudioUrl: (v: string | null) => void
  setVdPreviewBlob: (v: Blob | null) => void
  setVdPreviewId: (v: string | null) => void
  setVdPreviewSeed: (v: number | null) => void
  setVdSavedVoiceId: (v: string | null) => void
  setVdIsSaving: (v: boolean) => void

  // ---- OmniVoice (PersonaForge) ----
  ovSelections: OmniVoiceSelections
  ovCandidatesPerSegment: number
  ovShowAdvanced: boolean
  ovNumStepInput: string
  ovDurationInput: string
  ovSpeedInput: string
  ovGuidanceScaleInput: string
  ovDiverseCandidates: boolean
  ovScriptText: string
  ovSegmentRack: SegmentRackRow[]
  ovIsRackAuditioning: boolean
  ovCurrentText: string
  ovCurrentCandidates: OmniVoiceCandidate[] | null
  ovCurrentSelectedIndex: number
  ovLockedSegments: LockedSegment[]
  ovIsAuditioning: boolean
  ovIsLockingIn: boolean
  ovIsStitching: boolean
  ovIsSaving: boolean
  ovError: string | null
  ovStitchedUrl: string | null
  ovStitchedBlob: Blob | null
  ovSavedVoiceId: string | null
  ovProgress: OmniVoiceProgress | null
  ovLibrary: SegmentMeta[]
  ovLibraryFilter: string
  ovIsLibraryOpen: boolean
  ovLibrarySelection: Set<string>

  setOvSelections: (
    updater:
      | OmniVoiceSelections
      | ((prev: OmniVoiceSelections) => OmniVoiceSelections),
  ) => void
  setOvCandidatesPerSegment: (v: number) => void
  setOvShowAdvanced: (v: boolean) => void
  setOvNumStepInput: (v: string) => void
  setOvDurationInput: (v: string) => void
  setOvSpeedInput: (v: string) => void
  setOvGuidanceScaleInput: (v: string) => void
  setOvDiverseCandidates: (v: boolean) => void
  setOvScriptText: (
    updater: string | ((prev: string) => string),
  ) => void
  setOvSegmentRack: (v: SegmentRackRow[]) => void
  setOvIsRackAuditioning: (v: boolean) => void
  setOvCurrentText: (
    updater: string | ((prev: string) => string),
  ) => void
  setOvCurrentCandidates: (v: OmniVoiceCandidate[] | null) => void
  setOvCurrentSelectedIndex: (v: number) => void
  setOvLockedSegments: (
    updater:
      | LockedSegment[]
      | ((prev: LockedSegment[]) => LockedSegment[]),
  ) => void
  setOvIsAuditioning: (v: boolean) => void
  setOvIsLockingIn: (v: boolean) => void
  setOvIsStitching: (v: boolean) => void
  setOvIsSaving: (v: boolean) => void
  setOvError: (v: string | null) => void
  setOvStitchedUrl: (v: string | null) => void
  setOvStitchedBlob: (v: Blob | null) => void
  setOvSavedVoiceId: (v: string | null) => void
  setOvProgress: (v: OmniVoiceProgress | null) => void
  setOvLibrary: (v: SegmentMeta[]) => void
  setOvLibraryFilter: (v: string) => void
  setOvIsLibraryOpen: (
    v: boolean | ((p: boolean) => boolean),
  ) => void
  setOvLibrarySelection: (
    updater: Set<string> | ((prev: Set<string>) => Set<string>),
  ) => void
}

const initialTheme = loadStoredTheme()
applyTheme(initialTheme)

export const useAppStore = create<StoreState>((set) => ({
  // -- Core --
  page: 'speak',
  theme: initialTheme,
  text: '',
  voiceId: null,
  voices: [],
  audioUrl: null,
  isGenerating: false,
  error: null,
  editingVoice: null,
  designEngine: 'qwen',

  setPage: (page) => set({ page }),
  setTheme: (theme) => {
    applyTheme(theme)
    set({ theme })
  },
  setText: (text) => set({ text }),
  setVoiceId: (voiceId) => set({ voiceId }),
  setVoices: (voices) => set({ voices }),
  setAudioUrl: (audioUrl) => set({ audioUrl }),
  setGenerating: (isGenerating) => set({ isGenerating }),
  setError: (error) => set({ error }),
  setEditingVoice: (editingVoice) => set({ editingVoice }),
  setDesignEngine: (engine) => set({ designEngine: engine }),

  // -- VoiceDesign --
  vdSelections: {
    gender: null,
    age: null,
    register: null,
    textures: [],
    personas: [],
  },
  vdManualDescription: null,
  vdSampleText: '',
  vdSampleTextTouched: false,
  vdLanguage: 'English',
  vdSeedInput: '',
  vdShowWritingTips: false,
  vdIsGenerating: false,
  vdError: null,
  vdProgress: null,
  vdPreviewAudioUrl: null,
  vdPreviewBlob: null,
  vdPreviewId: null,
  vdPreviewSeed: null,
  vdSavedVoiceId: null,
  vdIsSaving: false,

  setVdSelections: (updater) =>
    set((s) => ({
      vdSelections:
        typeof updater === 'function'
          ? updater(s.vdSelections)
          : updater,
    })),
  setVdManualDescription: (v) => set({ vdManualDescription: v }),
  setVdSampleText: (v) => set({ vdSampleText: v }),
  setVdSampleTextTouched: (v) => set({ vdSampleTextTouched: v }),
  setVdLanguage: (v) => set({ vdLanguage: v }),
  setVdSeedInput: (v) => set({ vdSeedInput: v }),
  setVdShowWritingTips: (v) =>
    set((s) => ({
      vdShowWritingTips:
        typeof v === 'function' ? v(s.vdShowWritingTips) : v,
    })),
  setVdIsGenerating: (v) => set({ vdIsGenerating: v }),
  setVdError: (v) => set({ vdError: v }),
  setVdProgress: (v) => set({ vdProgress: v }),
  setVdPreviewAudioUrl: (v) => set({ vdPreviewAudioUrl: v }),
  setVdPreviewBlob: (v) => set({ vdPreviewBlob: v }),
  setVdPreviewId: (v: string | null) => set({ vdPreviewId: v }),
  setVdPreviewSeed: (v: number | null) => set({ vdPreviewSeed: v }),
  setVdSavedVoiceId: (v: string | null) => set({ vdSavedVoiceId: v }),
  setVdIsSaving: (v: boolean) => set({ vdIsSaving: v }),

  // -- OmniVoice --
  ovSelections: {
    gender: null,
    age: null,
    pitch: null,
    whisper: false,
    accent: null,
  },
  ovCandidatesPerSegment: 3,
  ovShowAdvanced: false,
  ovNumStepInput: '',
  ovDurationInput: '',
  ovSpeedInput: '',
  ovGuidanceScaleInput: '',
  ovDiverseCandidates: false,
  ovScriptText: '',
  ovSegmentRack: [],
  ovIsRackAuditioning: false,
  ovCurrentText: '',
  ovCurrentCandidates: null,
  ovCurrentSelectedIndex: 0,
  ovLockedSegments: [],
  ovIsAuditioning: false,
  ovIsLockingIn: false,
  ovIsStitching: false,
  ovIsSaving: false,
  ovError: null,
  ovStitchedUrl: null,
  ovStitchedBlob: null,
  ovSavedVoiceId: null,
  ovProgress: null,
  ovLibrary: [],
  ovLibraryFilter: '',
  ovIsLibraryOpen: false,
  ovLibrarySelection: new Set(),

  setOvSelections: (updater) =>
    set((s) => ({
      ovSelections:
        typeof updater === 'function'
          ? updater(s.ovSelections)
          : updater,
    })),
  setOvCandidatesPerSegment: (v) => set({ ovCandidatesPerSegment: v }),
  setOvShowAdvanced: (v) => set({ ovShowAdvanced: v }),
  setOvNumStepInput: (v) => set({ ovNumStepInput: v }),
  setOvDurationInput: (v) => set({ ovDurationInput: v }),
  setOvSpeedInput: (v) => set({ ovSpeedInput: v }),
  setOvGuidanceScaleInput: (v) =>
    set({ ovGuidanceScaleInput: v }),
  setOvDiverseCandidates: (v) =>
    set({ ovDiverseCandidates: v }),
  setOvScriptText: (updater) =>
    set((s) => ({
      ovScriptText:
        typeof updater === 'function'
          ? updater(s.ovScriptText)
          : updater,
    })),
  setOvSegmentRack: (v) =>
    set({ ovSegmentRack: v }),
  setOvIsRackAuditioning: (v) =>
    set({ ovIsRackAuditioning: v }),
  setOvCurrentText: (updater) =>
    set((s) => ({
      ovCurrentText:
        typeof updater === 'function'
          ? updater(s.ovCurrentText)
          : updater,
    })),
  setOvCurrentCandidates: (v) => set({ ovCurrentCandidates: v }),
  setOvCurrentSelectedIndex: (v) =>
    set({ ovCurrentSelectedIndex: v }),
  setOvLockedSegments: (updater) =>
    set((s) => ({
      ovLockedSegments:
        typeof updater === 'function'
          ? updater(s.ovLockedSegments)
          : updater,
    })),
  setOvIsAuditioning: (v) => set({ ovIsAuditioning: v }),
  setOvIsLockingIn: (v) => set({ ovIsLockingIn: v }),
  setOvIsStitching: (v) => set({ ovIsStitching: v }),
  setOvIsSaving: (v) => set({ ovIsSaving: v }),
  setOvError: (v) => set({ ovError: v }),
  setOvStitchedUrl: (v) => set({ ovStitchedUrl: v }),
  setOvStitchedBlob: (v) => set({ ovStitchedBlob: v }),
  setOvSavedVoiceId: (v) => set({ ovSavedVoiceId: v }),
  setOvProgress: (v) => set({ ovProgress: v }),
  setOvLibrary: (v) => set({ ovLibrary: v }),
  setOvLibraryFilter: (v) => set({ ovLibraryFilter: v }),
  setOvIsLibraryOpen: (v) =>
    set((s) => ({
      ovIsLibraryOpen:
        typeof v === 'function' ? v(s.ovIsLibraryOpen) : v,
    })),
  setOvLibrarySelection: (updater) =>
    set((s) => {
      const prev = s.ovLibrarySelection
      const next =
        typeof updater === 'function' ? updater(prev) : updater
      return { ovLibrarySelection: next }
    }),
}))

// ---- Store-level polling: survives unmounts ----
// Centralized so in-flight jobs keep updating when user navigates away and back.

const PROGRESS_POLL_MS = 700

// VoiceDesign poller
let vdPollHandle: ReturnType<typeof setInterval> | null = null

function updateVdPollHandle(isGenerating: boolean) {
  if (vdPollHandle && !isGenerating) {
    clearInterval(vdPollHandle)
    vdPollHandle = null
  }
  if (!vdPollHandle && isGenerating) {
    vdPollHandle = setInterval(async () => {
      try {
        const res = await fetch('/voice_design/progress')
        if (!res.ok) return
        const data = await res.json()
        useAppStore.getState().setVdProgress(data)
      } catch {
        // Transient; will retry
      }
    }, PROGRESS_POLL_MS)
  }
}

// OmniVoice poller
let ovPollHandle: ReturnType<typeof setInterval> | null = null

function updateOvPollHandle(isAuditioning: boolean) {
  if (ovPollHandle && !isAuditioning) {
    clearInterval(ovPollHandle)
    ovPollHandle = null
  }
  if (!ovPollHandle && isAuditioning) {
    ovPollHandle = setInterval(async () => {
      try {
        const res = await fetch('/omnivoice/progress')
        if (!res.ok) return
        const data = await res.json()
        useAppStore.getState().setOvProgress(data)
      } catch {
        // Transient; will retry
      }
    }, PROGRESS_POLL_MS)
  }
}

useAppStore.subscribe((state, prevState) => {
  if (state.vdIsGenerating !== prevState.vdIsGenerating)
    updateVdPollHandle(state.vdIsGenerating)
  if (state.ovIsAuditioning !== prevState.ovIsAuditioning)
    updateOvPollHandle(state.ovIsAuditioning)
})

import { create } from 'zustand'
import type {
  OmniVoiceAuditionProgressResult,
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

export interface ActivityStatus {
  active: boolean
  title: string
  message: string
  detail: string | null
  progress: number
  etaSeconds: number | null
}

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

// Stitch editor (PLAN_stitch_editor.md §5)
export type ClipRef =
  | { segmentId: string }
  | { candidateId: string }

export interface StitchPlanClip {
  clipId: string
  ref: ClipRef
  text: string
  sourceAudioBase64: string
  sampleRate: number
  durationMs?: number
  trimStartMs: number
  trimEndMs: number
  fadeInMs: number
  fadeOutMs: number
}

export interface StitchPlanDsp {
  segmentTargetDbfs: number
  finalTargetDbfs: number
  finalCeilingDb: number
  crossfadeMs: number
  compressEnabled: boolean
  compressThresholdDb: number
  compressRatio: number
}

interface StoreState {
  // ---- Core ----
  page: Page
  theme: Theme
  modelLoaded: boolean
  loadingMessage: string | null
  text: string
  voiceId: string | null
  voices: VoiceMeta[]
  audioUrl: string | null
  isGenerating: boolean
  error: string | null
  editingVoice: EditingVoice | null
  designEngine: DesignEngine
  activityStatus: ActivityStatus | null

  setPage: (page: Page) => void
  setTheme: (theme: Theme) => void
  setModelLoaded: (v: boolean) => void
  setLoadingMessage: (v: string | null) => void
  setText: (text: string) => void
  setVoiceId: (voiceId: string | null) => void
  setVoices: (voices: VoiceMeta[]) => void
  setAudioUrl: (url: string | null) => void
  setGenerating: (isGenerating: boolean) => void
  setError: (error: string | null) => void
  setEditingVoice: (voice: EditingVoice | null) => void
  setDesignEngine: (engine: DesignEngine) => void
  setActivityStatus: (v: ActivityStatus | null) => void

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
  ovMinMatchScore: number | null
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
   ovCurrentJobId: string | null
   ovJobTotalSegments: number
   ovJobStatus: 'queued' | 'running' | 'completed' | 'failed' | null
    ovJobSegmentsCompleted: OmniVoiceAuditionProgressResult['segments_completed']
    ovJobCurrentSegmentIndex: number | null
    ovJobMessage: string | null
    ovJobEtaSeconds: number | null
    ovJobCandidatesTotal: number
    ovJobCandidatesCompleted: number
    ovJobCurrentCandidateIndex: number | null
   ovAutoplayTakes: boolean
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
  setOvMinMatchScore: (v: number | null) => void
  setOvScriptText: (
    updater: string | ((prev: string) => string),
  ) => void
  setOvSegmentRack: (
    updater:
      | SegmentRackRow[]
      | ((prev: SegmentRackRow[]) => SegmentRackRow[]),
  ) => void
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
   setOvCurrentJobId: (v: string | null) => void
   setOvJobTotalSegments: (v: number) => void
   setOvJobStatus: (v: 'running' | 'completed' | 'failed' | null) => void
   setOvJobSegmentsCompleted: (v: OmniVoiceAuditionProgressResult['segments_completed']) => void
    setOvJobCurrentSegmentIndex: (v: number | null) => void
    setOvJobMessage: (v: string | null) => void
    setOvJobEtaSeconds: (v: number | null) => void
    setOvJobCandidatesTotal: (v: number) => void
    setOvJobCandidatesCompleted: (v: number) => void
    setOvJobCurrentCandidateIndex: (v: number | null) => void
   setOvAutoplayTakes: (v: boolean) => void
   setOvLibrary: (v: SegmentMeta[]) => void
   setOvLibraryFilter: (v: string) => void
   setOvIsLibraryOpen: (
     v: boolean | ((p: boolean) => boolean),
   ) => void
  setOvLibrarySelection: (
      updater: Set<string> | ((prev: Set<string>) => Set<string>),
    ) => void

  // ---- Stitch editor (PLAN_stitch_editor.md) ----
  ovStitchPlanClips: StitchPlanClip[]
  ovStitchPlanPaddingMs: number[]
  ovStitchPlanDsp: StitchPlanDsp
  ovStitchEditorOpen: boolean
  ovStitchPreviewUrl: string | null
  ovStitchPreviewBlob: Blob | null
  ovIsRenderingPreview: boolean

  setOvStitchPlanClips: (
    updater:
      | StitchPlanClip[]
      | ((prev: StitchPlanClip[]) => StitchPlanClip[]),
  ) => void
  reorderOvStitchPlanClip: (fromIndex: number, toIndex: number) => void
  updateOvStitchPlanClip: (clipId: string, patch: Partial<StitchPlanClip>) => void
  removeOvStitchPlanClip: (clipId: string) => void
  setOvStitchPlanPaddingAt: (gapIndex: number, ms: number) => void
  setOvStitchPlanDsp: (patch: Partial<StitchPlanDsp>) => void
  setOvStitchEditorOpen: (v: boolean) => void
  setOvStitchPreviewUrl: (v: string | null) => void
  setOvStitchPreviewBlob: (v: Blob | null) => void
  setOvIsRenderingPreview: (v: boolean) => void
}

const initialTheme = loadStoredTheme()
applyTheme(initialTheme)

export const useAppStore = create<StoreState>((set) => ({
  // -- Core --
  page: 'speak',
  theme: initialTheme,
  modelLoaded: false,
  loadingMessage: null,
  text: '',
  voiceId: null,
  voices: [],
  audioUrl: null,
  isGenerating: false,
  error: null,
  editingVoice: null,
  designEngine: 'qwen',
  activityStatus: null,

  setPage: (page) => set({ page }),
  setTheme: (theme) => {
    applyTheme(theme)
    set({ theme })
  },
  setModelLoaded: (modelLoaded) => set({ modelLoaded }),
  setLoadingMessage: (loadingMessage) => set({ loadingMessage }),
  setText: (text) => set({ text }),
  setVoiceId: (voiceId) => set({ voiceId }),
  setVoices: (voices) => set({ voices }),
  setAudioUrl: (audioUrl) => set({ audioUrl }),
  setGenerating: (isGenerating) => set({ isGenerating }),
  setError: (error) => set({ error }),
  setEditingVoice: (editingVoice) => set({ editingVoice }),
  setDesignEngine: (engine) => set({ designEngine: engine }),
  setActivityStatus: (activityStatus) => set({ activityStatus }),

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
  ovNumStepInput: '32',
  ovDurationInput: '',
  ovSpeedInput: '',
  ovGuidanceScaleInput: '',
  ovDiverseCandidates: true,
  ovMinMatchScore: null,
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
  ovCurrentJobId: null,
  ovJobTotalSegments: 0,
  ovJobStatus: null,
  ovJobSegmentsCompleted: [],
  ovJobCurrentSegmentIndex: null,
   ovJobMessage: null,
   ovJobEtaSeconds: null,
   ovJobCandidatesTotal: 0,
   ovJobCandidatesCompleted: 0,
   ovJobCurrentCandidateIndex: null,
   ovAutoplayTakes: true,
   ovLibrary: [],
  ovLibraryFilter: '',
    ovIsLibraryOpen: false,
    ovLibrarySelection: new Set(),

    // Stitch editor
    ovStitchPlanClips: [],
    ovStitchPlanPaddingMs: [],
    ovStitchPlanDsp: {
      segmentTargetDbfs: -20,
      finalTargetDbfs: -18,
      finalCeilingDb: -1,
      crossfadeMs: 100,
      compressEnabled: true,
      compressThresholdDb: -24,
      compressRatio: 2.5,
    },
    ovStitchEditorOpen: false,
    ovStitchPreviewUrl: null,
    ovStitchPreviewBlob: null,
    ovIsRenderingPreview: false,

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
  setOvMinMatchScore: (v) =>
    set({ ovMinMatchScore: v }),
  setOvScriptText: (updater) =>
    set((s) => ({
      ovScriptText:
        typeof updater === 'function'
          ? updater(s.ovScriptText)
          : updater,
    })),
  setOvSegmentRack: (updater) =>
    set((s) => ({
      ovSegmentRack:
        typeof updater === 'function'
          ? updater(s.ovSegmentRack)
          : updater,
    })),
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
  setOvCurrentJobId: (v) => set({ ovCurrentJobId: v }),
  setOvJobTotalSegments: (v) => set({ ovJobTotalSegments: v }),
  setOvJobStatus: (v) => set({ ovJobStatus: v }),
  setOvJobSegmentsCompleted: (v) => set({ ovJobSegmentsCompleted: v }),
  setOvJobCurrentSegmentIndex: (v) => set({ ovJobCurrentSegmentIndex: v }),
   setOvJobMessage: (v) => set({ ovJobMessage: v }),
   setOvJobEtaSeconds: (v) => set({ ovJobEtaSeconds: v }),
   setOvJobCandidatesTotal: (v) => set({ ovJobCandidatesTotal: v }),
   setOvJobCandidatesCompleted: (v) => set({ ovJobCandidatesCompleted: v }),
   setOvJobCurrentCandidateIndex: (v) => set({ ovJobCurrentCandidateIndex: v }),
   setOvAutoplayTakes: (v: boolean) => set({ ovAutoplayTakes: v }),
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

  // Stitch editor actions
  setOvStitchPlanClips: (updater) =>
    set((s) => ({
      ovStitchPlanClips:
        typeof updater === 'function'
          ? updater(s.ovStitchPlanClips)
          : updater,
    })),
  reorderOvStitchPlanClip: (fromIndex, toIndex) =>
    set((s) => {
      const clips = [...s.ovStitchPlanClips]
      const [moved] = clips.splice(fromIndex, 1)
      clips.splice(toIndex, 0, moved)
      return { ovStitchPlanClips: clips }
    }),
  updateOvStitchPlanClip: (clipId, patch) =>
    set((s) => ({
      ovStitchPlanClips: s.ovStitchPlanClips.map((c) =>
        c.clipId === clipId ? { ...c, ...patch } : c,
      ),
    })),
  removeOvStitchPlanClip: (clipId) =>
    set((s) => ({
      ovStitchPlanClips: s.ovStitchPlanClips.filter(
        (c) => c.clipId !== clipId,
      ),
    })),
  setOvStitchPlanPaddingAt: (gapIndex, ms) =>
    set((s) => {
      const pad = [...s.ovStitchPlanPaddingMs]
      pad[gapIndex] = ms
      return { ovStitchPlanPaddingMs: pad }
    }),
  setOvStitchPlanDsp: (patch) =>
    set((s) => ({
      ovStitchPlanDsp: { ...s.ovStitchPlanDsp, ...patch },
    })),
  setOvStitchEditorOpen: (v) => set({ ovStitchEditorOpen: v }),
  setOvStitchPreviewUrl: (v) => set({ ovStitchPreviewUrl: v }),
  setOvStitchPreviewBlob: (v) => set({ ovStitchPreviewBlob: v }),
  setOvIsRenderingPreview: (v) => set({ ovIsRenderingPreview: v }),
}))

// ---- Store-level polling: survives unmounts ----
// Centralized so in-flight jobs keep updating when user navigates away and back.

const PROGRESS_POLL_MS = 700

// Model-loading poller: runs until model_loaded is true.
;(async () => {
  async function poll() {
    try {
      const res = await fetch('/health')
      if (!res.ok) return
      const data = await res.json()
      const store = useAppStore.getState()
      if (data.model_loaded !== store.modelLoaded) {
        store.setModelLoaded(Boolean(data.model_loaded))
      }
      if (data.loading_message !== store.loadingMessage) {
        store.setLoadingMessage(data.loading_message || null)
      }
    } catch {
      // Transient; will retry
    }
  }

  // First fetch immediately
  await poll()

  // Then poll every second until model is loaded
  const interval = setInterval(() => {
    const store = useAppStore.getState()
    if (store.modelLoaded) {
      clearInterval(interval)
      return
    }
    void poll()
  }, 1000)
})()

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

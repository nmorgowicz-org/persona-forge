import { create } from 'zustand'
import type {
  GenerateJobProgress,
  OmniVoiceAuditionProgressResult,
  OmniVoiceCandidate,
  SegmentMeta,
  VoiceDesignProgress,
  VoiceMeta,
} from './lib/api'
import { applyTheme, loadStoredTheme, type Theme } from './lib/theme'
import {
  loadStoredExperienceLevel,
  storeExperienceLevel,
  type ExperienceLevel,
} from './lib/experienceLevel'
import type { ChipSelections } from './lib/voiceDesignChips'
import type { OmniVoiceSelections } from './lib/omnivoiceChips'

export type Page = 'wizard' | 'speak' | 'voice-design' | 'voice-library' | 'stitch-studio' | 'integrations' | 'runtime'
export type DesignEngine = 'qwen' | 'omnivoice'

export interface ActivityStatus {
  active: boolean
  title: string
  message: string
  detail: string | null
  progress: number
  etaSeconds: number | null
  // When set, the status bar renders a Stop button that invokes this — lets a long-running
  // job be cancelled from anywhere on the page, not just from controls above the fold.
  onCancel?: (() => void) | null
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

export interface CandidateBatch {
  durationSec: number
  candidates: OmniVoiceCandidate[]
}

export interface SegmentRackRow {
  segmentId: string
  text: string
  candidates: OmniVoiceCandidate[]
  selectedTakeIndex: number
  // Batches replaced by a Regen at a different target duration, most-recent first — lets
  // the user flip back to a prior batch for A/B comparison instead of losing it outright.
  previousBatches?: CandidateBatch[]
}

// Stitch editor (docs/archive/stitch-editor/stitch_editor.md §5)
export type ClipRef =
  | { segmentId: string }
  | { candidateId: string }
  | { voiceId: string }

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
  prosodyMode?: 'off' | 'auto' | 'precise'
}

export interface StitchPlanDsp {
  segmentTargetDbfs: number
  finalTargetDbfs: number
  finalCeilingDb: number
  crossfadeMs: number
  compressEnabled: boolean
  compressThresholdDb: number
  compressRatio: number
  prosodyStylePreset: 'Neutral' | 'Storyteller' | 'Calm' | 'Energetic' | 'Broadcast' | 'Clean'
  paceMultiplier: number
  pauseOffsetMs: number
}

interface StoreState {
  // ---- Core ----
  page: Page
  theme: Theme
  // Global progressive-disclosure preference: 'guided' hides power-user controls behind
  // Disclose (see components/Disclose.tsx) without unmounting them; 'expert' shows everything.
  uiExperienceLevel: ExperienceLevel
  modelLoaded: boolean
  serviceStarted: boolean
  loadingMessage: string | null
  healthStatus: string | null
  healthError: string | null
  text: string
  voiceId: string | null
  voices: VoiceMeta[]
   speakAudioUrl: string | null
   speakIsGenerating: boolean
   speakError: string | null
   speakJobId: string | null
   speakJobProgress: GenerateJobProgress | null
   speakLastSeed: number | null
   speakAudioBlob: Blob | null
   editingVoice: EditingVoice | null
   designEngine: DesignEngine
   designEngineTouched: boolean
   activityStatus: ActivityStatus | null
  runtimeTtsBackend: string | null
  pocketTtsVoiceCloningAvailable: boolean | null
  swapInProgress: boolean
  healthBackend: string | null
  reconfigInProgress: boolean
  pocketTtsVoiceCloningMessage: string | null
  setRuntimeConfig: (patch: {
    runtimeTtsBackend?: string | null
    pocketTtsVoiceCloningAvailable?: boolean | null
    reconfigInProgress?: boolean
    pocketTtsVoiceCloningMessage?: string | null
  }) => void
  refTextValidation:
    | {
        severity: string | null
        matchScore: number | null
        whisperTranscript: string | null
      }
    | null
  setRefTextValidation: (v: StoreState['refTextValidation']) => void

  setPage: (page: Page) => void
  setTheme: (theme: Theme) => void
  setUiExperienceLevel: (level: ExperienceLevel) => void
  setModelLoaded: (v: boolean) => void
  setServiceStarted: (v: boolean) => void
  setLoadingMessage: (v: string | null) => void
  setText: (text: string) => void
  setVoiceId: (voiceId: string | null) => void
  setVoices: (voices: VoiceMeta[]) => void
  setSpeakAudioUrl: (url: string | null) => void
  setSpeakIsGenerating: (v: boolean) => void
  setSpeakError: (v: string | null) => void
  setSpeakJobId: (v: string | null) => void
  setSpeakJobProgress: (v: GenerateJobProgress | null) => void
  setSpeakLastSeed: (v: number | null) => void
  setSpeakAudioBlob: (v: Blob | null) => void
  setEditingVoice: (voice: EditingVoice | null) => void
  setDesignEngine: (engine: DesignEngine) => void
  targetFamilyId: string | null
  setTargetFamilyId: (familyId: string | null) => void
  setActivityStatus: (v: ActivityStatus | null) => void
  glossaryOpen: boolean
  setGlossaryOpen: (v: boolean) => void
  // Term-ID (glossary key or troubleshooting KB id) to scroll/highlight to when the
  // glossary opens — set by InfoIcon "Learn more" links and diagnosis chips (C4).
  glossaryFocusId: string | null
  openGlossaryAt: (id: string | null) => void

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

  // ---- OmniVoice ----
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
  ovIsLockingIn: boolean
  ovIsStitching: boolean
  ovIsSaving: boolean
  ovError: string | null
  ovStitchedUrl: string | null
  ovStitchedBlob: Blob | null
  ovSavedVoiceId: string | null
  // Set right after a Stitch Studio save; the Voice Library reads this on mount to
  // auto-open that voice's Adjust Prosody popover, then clears it so it doesn't
  // reopen on a later, unrelated visit to the library.
  deepLinkProsodyVoiceId: string | null
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
  setOvIsLockingIn: (v: boolean) => void
  setOvIsStitching: (v: boolean) => void
  setOvIsSaving: (v: boolean) => void
  setOvError: (v: string | null) => void
  setOvStitchedUrl: (v: string | null) => void
  setOvStitchedBlob: (v: Blob | null) => void
  setOvSavedVoiceId: (v: string | null) => void
  setDeepLinkProsodyVoiceId: (v: string | null) => void
   setOvCurrentJobId: (v: string | null) => void
   setOvJobTotalSegments: (v: number) => void
   setOvJobStatus: (v: 'queued' | 'running' | 'completed' | 'failed' | null) => void
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

  // ---- Stitch editor (docs/archive/stitch-editor/stitch_editor.md) ----
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
  setOvStitchPlanPaddingMs: (v: number[]) => void
  setOvStitchPlanDsp: (patch: Partial<StitchPlanDsp>) => void
  setOvStitchEditorOpen: (v: boolean) => void
  setOvStitchPreviewUrl: (v: string | null) => void
  setOvStitchPreviewBlob: (v: Blob | null) => void
  setOvIsRenderingPreview: (v: boolean) => void
}

const initialTheme = loadStoredTheme()
applyTheme(initialTheme)
const initialExperienceLevel = loadStoredExperienceLevel()

export const useAppStore = create<StoreState>((set) => ({
  // -- Core --
  page: 'speak',
  theme: initialTheme,
  uiExperienceLevel: initialExperienceLevel,
  modelLoaded: false,
  serviceStarted: false,
  loadingMessage: null,
  healthStatus: null,
  healthError: null,
  text: '',
  voiceId: null,
   voices: [],
   speakAudioUrl: null,
   speakIsGenerating: false,
   speakError: null,
   speakJobId: null,
   speakJobProgress: null,
   speakLastSeed: null,
  speakAudioBlob: null,
  editingVoice: null,
   designEngine: 'omnivoice',
   designEngineTouched: false,
   targetFamilyId: null,
    activityStatus: null,
    runtimeTtsBackend: 'pocket_tts',
    pocketTtsVoiceCloningAvailable: null,
    swapInProgress: false,
    healthBackend: null,
    reconfigInProgress: false,
    pocketTtsVoiceCloningMessage: null,
    refTextValidation: null,

    setPage: (page) => set({ page }),
  setTheme: (theme) => {
    applyTheme(theme)
    set({ theme })
  },
  setUiExperienceLevel: (uiExperienceLevel) => {
    storeExperienceLevel(uiExperienceLevel)
    set({ uiExperienceLevel })
  },
  setModelLoaded: (modelLoaded) => set({ modelLoaded }),
  setServiceStarted: (serviceStarted) => set({ serviceStarted }),
  setLoadingMessage: (loadingMessage) => set({ loadingMessage }),
  setText: (text) => set({ text }),
  setVoiceId: (voiceId) => set({ voiceId }),
  setVoices: (voices) => set({ voices }),
  setSpeakAudioUrl: (url) => set({ speakAudioUrl: url }),
  setSpeakIsGenerating: (v) => set({ speakIsGenerating: v }),
  setSpeakError: (v) => set({ speakError: v }),
  setSpeakJobId: (v) => set({ speakJobId: v }),
  setSpeakJobProgress: (v) => set({ speakJobProgress: v }),
  setSpeakLastSeed: (v) => set({ speakLastSeed: v }),
  setSpeakAudioBlob: (v) => set({ speakAudioBlob: v }),
  setEditingVoice: (editingVoice) => set({ editingVoice }),
  setDesignEngine: (engine) => set({ designEngine: engine, designEngineTouched: true }),
  setTargetFamilyId: (targetFamilyId) => set({ targetFamilyId }),
  setActivityStatus: (activityStatus) => set({ activityStatus }),
  setGlossaryOpen: (v: boolean) => set({ glossaryOpen: v }),
  glossaryOpen: false,
  glossaryFocusId: null,
  openGlossaryAt: (id) => set({ glossaryOpen: true, glossaryFocusId: id }),
  setRuntimeConfig: (patch) => {
    set(patch)
    // The default design engine follows the backend (OmniVoice on pocket_tts, Qwen
    // VoiceDesign on the Qwen backends) until the user picks one explicitly.
    if (patch.runtimeTtsBackend !== undefined) {
      const s = useAppStore.getState()
      if (!s.designEngineTouched) {
        const preferred: DesignEngine = s.runtimeTtsBackend === 'pocket_tts' ? 'omnivoice' : 'qwen'
        if (s.designEngine !== preferred) set({ designEngine: preferred })
      }
    }
  },

   setRefTextValidation: (refTextValidation) => set({ refTextValidation }),

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
  ovIsLockingIn: false,
  ovIsStitching: false,
  ovIsSaving: false,
  ovError: null,
  ovStitchedUrl: null,
  ovStitchedBlob: null,
  ovSavedVoiceId: null,
  deepLinkProsodyVoiceId: null,
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
      prosodyStylePreset: 'Neutral',
      paceMultiplier: 1,
      pauseOffsetMs: 0,
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
  setOvIsLockingIn: (v) => set({ ovIsLockingIn: v }),
  setOvIsStitching: (v) => set({ ovIsStitching: v }),
  setOvIsSaving: (v) => set({ ovIsSaving: v }),
  setOvError: (v) => set({ ovError: v }),
  setOvStitchedUrl: (v) => set({ ovStitchedUrl: v }),
  setOvStitchedBlob: (v) => set({ ovStitchedBlob: v }),
  setOvSavedVoiceId: (v) => set({ ovSavedVoiceId: v }),
  setDeepLinkProsodyVoiceId: (v) => set({ deepLinkProsodyVoiceId: v }),
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
    set((s) => {
      const idx = s.ovStitchPlanClips.findIndex((c) => c.clipId === clipId)
      if (idx === -1) return {}
      const clips = s.ovStitchPlanClips.filter((c) => c.clipId !== clipId)
      // Removing a clip merges its two adjacent gaps into one — drop the gap that
      // followed it (or, if it was last, the one that preceded it) so the padding
      // array stays aligned to clips.length - 1; otherwise every later gap index
      // silently points at the wrong boundary.
      const pad = [...s.ovStitchPlanPaddingMs]
      if (idx < pad.length) pad.splice(idx, 1)
      else if (idx - 1 >= 0) pad.splice(idx - 1, 1)
      return { ovStitchPlanClips: clips, ovStitchPlanPaddingMs: pad }
    }),
  setOvStitchPlanPaddingAt: (gapIndex, ms) =>
    set((s) => {
      const pad = [...s.ovStitchPlanPaddingMs]
      pad[gapIndex] = ms
      return { ovStitchPlanPaddingMs: pad }
    }),
  setOvStitchPlanPaddingMs: (v) => set({ ovStitchPlanPaddingMs: v }),
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

// Model-loading poller: stays alive for the whole app lifetime. Polls at 1s while a model
// load is in flight (cold boot, post-boot swap-back, or OmniVoice load) and backs off to
// ~5s in steady state. Post-boot loads must keep updating loadingMessage/swapInProgress/
// modelLoaded — the top notification bar depends on this staying alive.
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
      if (Boolean(data.service_started) !== store.serviceStarted) {
        store.setServiceStarted(Boolean(data.service_started))
      }
      if (data.loading_message !== store.loadingMessage) {
        store.setLoadingMessage(data.loading_message || null)
      }
      if ((data.status || null) !== store.healthStatus) {
        useAppStore.setState({ healthStatus: data.status || null })
      }
      if ((data.error || null) !== store.healthError) {
        useAppStore.setState({ healthError: data.error || null })
      }
      if (data.swap_in_progress !== store.swapInProgress) {
        useAppStore.setState({ swapInProgress: Boolean(data.swap_in_progress) })
      }
      const resolvedBackend = data.resolved_backend || data.backend
      if (resolvedBackend !== store.healthBackend) {
        useAppStore.setState({
          healthBackend: resolvedBackend || null,
          runtimeTtsBackend: resolvedBackend || null,
        })
        // The default design engine follows the backend (OmniVoice on pocket_tts, Qwen
        // VoiceDesign on the Qwen backends) until the user picks one explicitly.
        if (!useAppStore.getState().designEngineTouched) {
          const preferred = resolvedBackend === 'pocket_tts' ? 'omnivoice' : 'qwen'
          if (useAppStore.getState().designEngine !== preferred) {
            useAppStore.setState({ designEngine: preferred })
          }
        }
      }
      // Sync Pocket TTS voice-cloning status into the store whenever /health
      // indicates the backend is pocket_tts — this is the single source of truth
      // for PocketTTSWarningBanner and survives page navigations / refreshes.
      if (resolvedBackend === 'pocket_tts') {
        const pt = (data as any).pocket_tts as
          | { voice_cloning_available?: boolean; message?: string }
          | null
        if (pt) {
          const available = Boolean(pt.voice_cloning_available)
          const message = (pt.message || '').trim() || null
          if (available !== store.pocketTtsVoiceCloningAvailable || message !== store.pocketTtsVoiceCloningMessage) {
            useAppStore.setState({
              pocketTtsVoiceCloningAvailable: available,
              pocketTtsVoiceCloningMessage: message,
            })
          }
        }
      }
      const rvt = data.ref_text_validation as
        | {
            severity?: string
            match_score?: number
            whisper_transcript?: string
          }
        | null
      if (rvt) {
        store.setRefTextValidation({
          severity: rvt.severity || null,
          matchScore: rvt.match_score ?? null,
          whisperTranscript: rvt.whisper_transcript || null,
        })
      }
    } catch {
      // Transient; will retry
    }
  }

  async function tick() {
    await poll()
    const s = useAppStore.getState()
    const loading =
      !s.serviceStarted ||
      s.loadingMessage !== null ||
      s.swapInProgress ||
      !s.modelLoaded
    setTimeout(() => void tick(), loading ? 1000 : 5000)
  }
  void tick()
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

useAppStore.subscribe((state, prevState) => {
  if (state.vdIsGenerating !== prevState.vdIsGenerating)
    updateVdPollHandle(state.vdIsGenerating)
})

// One rich picker replacing all four LibraryPickerButton instantiations (segments/voices x
// empty-state/populated-state). A real Radix dialog (large enough to actually browse, not a
// cramped popover) with Segments/Reference voices tabs, search, project filter, sort,
// multi-select with select-all, and explicit Add / Enter / double-click insert. List metadata
// never includes audio, so every row starts with a neutral duration rail; audio (and its peaks,
// via the shared bounded cache) is fetched only when a row is actually auditioned, and only one
// row plays at a time. Rows use content-visibility (see index.css .segment-browser-row) so a
// 250-row library scrolls smoothly without a virtualization dependency.
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { Loader2, Pause, Play, Plus } from 'lucide-react'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { base64ToBlob, cn } from '@/lib/utils'
import { getClipAudioAnalysis } from '@/lib/waveform'
import { getSegmentAudioBase64, getVoice, type SegmentMeta, type VoiceMeta } from '@/lib/api'
import { SegmentPreviewRail } from './SegmentPreviewRail'

type BrowserTab = 'segments' | 'voices'
type SortMode = 'newest' | 'duration' | 'name'

interface BrowserRow {
  id: string
  label: string
  meta: string | null
  durationSec: number | null
  projectId: string | null
  projectName: string | null
  createdAt: number
  fetchAudioBase64: () => Promise<string | null>
}

function segmentToRow(seg: SegmentMeta): BrowserRow {
  return {
    id: seg.segment_id,
    label: seg.text,
    meta: [seg.language, ...(seg.tags ?? [])].filter(Boolean).join(' · ') || null,
    durationSec: seg.duration_sec ?? null,
    projectId: seg.project_id ?? null,
    projectName: seg.project_name ?? null,
    createdAt: seg.created_at,
    fetchAudioBase64: async () => seg.audio_base64 ?? (await getSegmentAudioBase64(seg.segment_id)),
  }
}

function voiceToRow(voice: VoiceMeta): BrowserRow {
  return {
    id: voice.voice_id,
    label: voice.description || voice.voice_id,
    meta:
      [voice.language, voice.sample_text ? `Sample: ${voice.sample_text.slice(0, 60)}${voice.sample_text.length > 60 ? '…' : ''}` : null]
        .filter(Boolean)
        .join(' · ') || null,
    durationSec: null,
    projectId: voice.project_id ?? null,
    projectName: voice.project_name ?? null,
    createdAt: voice.created_at,
    fetchAudioBase64: async () => voice.audio_base64 ?? (await getVoice(voice.voice_id)).audio_base64 ?? null,
  }
}

export interface SegmentBrowserModalController {
  /** Opens the picker dialog programmatically (e.g. from the studio's "Add clips" guidance). */
  open: () => void
}

export interface SegmentBrowserModalProps {
  segments: SegmentMeta[]
  onInsertSegments: (segs: SegmentMeta[], afterClipId: string | null) => void
  voices?: VoiceMeta[]
  onInsertVoices?: (voices: VoiceMeta[], afterClipId: string | null) => void
  /** Clip to splice newly-inserted assets after; null appends at the end of the timeline. */
  insertAfterClipId: string | null
  /** Optional controller the parent uses to open the dialog without a DOM click. */
  controllerRef?: { current: SegmentBrowserModalController | null }
}

export function SegmentBrowserModal({
  segments,
  onInsertSegments,
  voices,
  onInsertVoices,
  insertAfterClipId,
  controllerRef,
}: SegmentBrowserModalProps) {
  const [open, setOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<BrowserTab>('segments')
  const [search, setSearch] = useState('')
  const [projectFilter, setProjectFilter] = useState('all')
  const [sortMode, setSortMode] = useState<SortMode>('newest')
  const [selectedSegmentIds, setSelectedSegmentIds] = useState<Set<string>>(new Set())
  const [selectedVoiceIds, setSelectedVoiceIds] = useState<Set<string>>(new Set())
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const [peaksById, setPeaksById] = useState<Record<string, number[]>>({})
  const [loadingAudioId, setLoadingAudioId] = useState<string | null>(null)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audioUrlRef = useRef<string | null>(null)
  const searchInputRef = useRef<HTMLInputElement | null>(null)
  // Bumped on every new audition click and on close, so a slower in-flight fetch/decode/play
  // can detect it has been superseded and bail out instead of clobbering newer playback state
  // or resuming audio after the dialog has closed.
  const playbackTokenRef = useRef(0)

  const hasVoices = (voices?.length ?? 0) > 0 && !!onInsertVoices

  useEffect(() => {
    if (!open) {
      playbackTokenRef.current += 1
      audioRef.current?.pause()
      setPlayingId(null)
    }
  }, [open])

  useEffect(() => {
    return () => {
      audioRef.current?.pause()
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
    }
  }, [])

  // Optional controller: expose open() to the parent without changing how the dialog is
  // otherwise driven (the trigger button keeps working as before).
  useEffect(() => {
    if (!controllerRef) return
    controllerRef.current = { open: () => setOpen(true) }
    return () => {
      controllerRef.current = null
    }
  }, [controllerRef])

  const resetPickerState = useCallback(() => {
    setSelectedSegmentIds(new Set())
    setSelectedVoiceIds(new Set())
    setSearch('')
    setProjectFilter('all')
  }, [])

  const rows = useMemo<BrowserRow[]>(
    () => (activeTab === 'segments' ? segments.map(segmentToRow) : (voices ?? []).map(voiceToRow)),
    [activeTab, segments, voices],
  )

  const projectOptions = useMemo(() => {
    const map = new Map<string, string>()
    for (const r of rows) if (r.projectId) map.set(r.projectId, r.projectName ?? r.projectId)
    return Array.from(map.entries())
  }, [rows])

  const filteredSorted = useMemo(() => {
    let list = rows
    if (projectFilter === 'ungrouped') list = list.filter((r) => !r.projectId)
    else if (projectFilter !== 'all') list = list.filter((r) => r.projectId === projectFilter)
    const q = search.trim().toLowerCase()
    if (q) list = list.filter((r) => r.label.toLowerCase().includes(q) || (r.meta ?? '').toLowerCase().includes(q))
    const sorted = [...list]
    if (sortMode === 'newest') sorted.sort((a, b) => b.createdAt - a.createdAt)
    else if (sortMode === 'duration') sorted.sort((a, b) => (b.durationSec ?? 0) - (a.durationSec ?? 0))
    else sorted.sort((a, b) => a.label.localeCompare(b.label))
    return sorted
  }, [rows, projectFilter, search, sortMode])

  const selectedIds = activeTab === 'segments' ? selectedSegmentIds : selectedVoiceIds
  const setSelectedIds = activeTab === 'segments' ? setSelectedSegmentIds : setSelectedVoiceIds

  const toggleSelected = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [setSelectedIds])

  const allFilteredSelected = filteredSorted.length > 0 && filteredSorted.every((r) => selectedIds.has(r.id))
  const toggleSelectAll = useCallback(() => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (allFilteredSelected) {
        for (const r of filteredSorted) next.delete(r.id)
      } else {
        for (const r of filteredSorted) next.add(r.id)
      }
      return next
    })
  }, [allFilteredSelected, filteredSorted, setSelectedIds])

  const commitInsert = useCallback((ids: string[]) => {
    if (ids.length === 0) return
    if (activeTab === 'segments') {
      const chosen = segments.filter((s) => ids.includes(s.segment_id))
      if (chosen.length > 0) onInsertSegments(chosen, insertAfterClipId)
    } else {
      const chosen = (voices ?? []).filter((v) => ids.includes(v.voice_id))
      if (chosen.length > 0) onInsertVoices?.(chosen, insertAfterClipId)
    }
    resetPickerState()
    setOpen(false)
  }, [activeTab, segments, voices, onInsertSegments, onInsertVoices, insertAfterClipId, resetPickerState])

  const handleInsertSelected = useCallback(() => {
    commitInsert(Array.from(selectedIds))
  }, [commitInsert, selectedIds])

  const handleDoubleClickInsert = useCallback((row: BrowserRow) => {
    commitInsert([row.id])
  }, [commitInsert])

  const togglePlay = useCallback(async (row: BrowserRow) => {
    if (playingId === row.id) {
      audioRef.current?.pause()
      setPlayingId(null)
      return
    }
    const token = ++playbackTokenRef.current
    audioRef.current?.pause()
    setLoadingAudioId(row.id)
    try {
      const b64 = await row.fetchAudioBase64()
      if (token !== playbackTokenRef.current) return // superseded by another click or a close
      if (!b64) return
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
      const url = URL.createObjectURL(base64ToBlob(b64))
      audioUrlRef.current = url
      if (!peaksById[row.id]) {
        const analysis = await getClipAudioAnalysis(`browser:${row.id}:${b64.length}`, b64, 32)
        if (token !== playbackTokenRef.current) return
        setPeaksById((prev) => ({ ...prev, [row.id]: analysis.peaks }))
      }
      if (!audioRef.current) {
        const audio = new Audio()
        audio.addEventListener('timeupdate', () => {
          if (audio.duration) setProgress(audio.currentTime / audio.duration)
        })
        audio.addEventListener('ended', () => setPlayingId(null))
        audioRef.current = audio
      }
      audioRef.current.src = url
      setProgress(0)
      await audioRef.current.play()
      if (token !== playbackTokenRef.current) {
        audioRef.current.pause()
        return
      }
      setPlayingId(row.id)
    } finally {
      if (token === playbackTokenRef.current) setLoadingAudioId(null)
    }
  }, [playingId, peaksById])

  const handleKeyDown = useCallback((e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' && e.target !== searchInputRef.current) {
      e.preventDefault()
      handleInsertSelected()
    }
  }, [handleInsertSelected])

  return (
    <>
      <button
        type="button"
        data-testid="stitch-picker-toggle-segments"
        onClick={() => setOpen(true)}
        className="inline-flex h-8 items-center gap-1.5 rounded border border-border bg-background px-2.5 text-xs hover:bg-muted"
      >
        <Plus className="size-3.5" /> Add segments
      </button>

      <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) resetPickerState() }}>
        <DialogContent
          data-testid="segment-browser-dialog"
          className="flex max-h-[85vh] w-full max-w-2xl flex-col gap-3 sm:max-w-2xl"
          onKeyDown={handleKeyDown}
        >
          <DialogTitle className="text-sm font-semibold">Add to timeline</DialogTitle>
          <DialogDescription className="sr-only">
            Browse saved segments and reference voices to insert into the stitch timeline.
          </DialogDescription>

          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v === 'voices' ? 'voices' : 'segments')}>
            <TabsList>
              <TabsTrigger value="segments">Segments</TabsTrigger>
              {hasVoices && <TabsTrigger value="voices">Reference voices</TabsTrigger>}
            </TabsList>
          </Tabs>

          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={searchInputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search…"
              className="h-8 min-w-0 flex-1 rounded-md border border-border bg-muted/40 px-2.5 text-xs text-foreground outline-none focus:border-cyan-500/50"
            />
            <select
              data-testid="segment-browser-project-filter"
              value={projectFilter}
              onChange={(e) => setProjectFilter(e.target.value)}
              className="h-8 rounded-md border border-border bg-muted/40 px-2 text-xs text-foreground outline-none"
            >
              <option value="all">All projects</option>
              <option value="ungrouped">Ungrouped</option>
              {projectOptions.map(([id, name]) => (
                <option key={id} value={id}>{name}</option>
              ))}
            </select>
            <select
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value as SortMode)}
              className="h-8 rounded-md border border-border bg-muted/40 px-2 text-xs text-foreground outline-none"
            >
              <option value="newest">Newest</option>
              <option value="duration">Duration</option>
              <option value="name">Name</option>
            </select>
            <button
              type="button"
              onClick={toggleSelectAll}
              disabled={filteredSorted.length === 0}
              className="shrink-0 text-[10px] text-muted-foreground underline decoration-dotted hover:text-foreground disabled:opacity-40"
            >
              {allFilteredSelected ? 'Deselect all' : 'Select all'}
            </button>
          </div>

          <div className="flex flex-col divide-y divide-border overflow-y-auto">
            {filteredSorted.length === 0 && (
              <p className="px-1 py-4 text-center text-xs text-muted-foreground">No matches</p>
            )}
            {filteredSorted.map((row) => {
              const checked = selectedIds.has(row.id)
              const isPlaying = playingId === row.id
              return (
                <div
                  key={row.id}
                  className="segment-browser-row flex items-center gap-2 py-2"
                  onDoubleClick={() => handleDoubleClickInsert(row)}
                >
                  <input
                    type="checkbox"
                    data-testid={`stitch-picker-item-${activeTab}`}
                    checked={checked}
                    onChange={() => toggleSelected(row.id)}
                    className="size-3.5 shrink-0 accent-cyan-500"
                  />
                  <button
                    type="button"
                    data-testid="segment-browser-audio"
                    data-playing={isPlaying}
                    onClick={() => void togglePlay(row)}
                    title="Audition"
                    className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground"
                  >
                    {loadingAudioId === row.id ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : isPlaying ? (
                      <Pause className="size-3.5" />
                    ) : (
                      <Play className="size-3.5" />
                    )}
                  </button>
                  <div className="min-w-0 flex-1" title={row.meta ? `${row.label}\n${row.meta}` : row.label}>
                    <p className="truncate text-xs text-foreground">{row.label}</p>
                    {row.meta && <p className="truncate text-[10px] text-muted-foreground">{row.meta}</p>}
                  </div>
                  <SegmentPreviewRail
                    peaks={peaksById[row.id] ?? null}
                    progress={isPlaying ? progress : 0}
                    isPlaying={isPlaying}
                  />
                  {row.durationSec != null && (
                    <span className="shrink-0 text-[10px] text-muted-foreground">{row.durationSec.toFixed(1)}s</span>
                  )}
                  {row.projectName && (
                    <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[9px] text-muted-foreground">
                      {row.projectName}
                    </span>
                  )}
                </div>
              )
            })}
          </div>

          <div className={cn('flex items-center justify-between border-t border-border pt-2')}>
            <span className="text-xs text-muted-foreground">{selectedIds.size} selected</span>
            <button
              type="button"
              data-testid={`stitch-picker-insert-${activeTab}`}
              onClick={handleInsertSelected}
              disabled={selectedIds.size === 0}
              className="btn-brand rounded-full px-3 py-1.5 text-xs font-medium"
            >
              Add ({selectedIds.size})
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

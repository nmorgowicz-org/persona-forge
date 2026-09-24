// One rich picker replacing all four LibraryPickerButton instantiations (segments/voices x
// empty-state/populated-state). A real Radix dialog (large enough to actually browse, not a
// cramped popover) with Segments/Reference voices tabs, search, project filter, sort,
// multi-select with select-all, and explicit Add / Enter / double-click insert. List metadata
// never includes audio, so every row starts with a neutral duration rail; audio (and its peaks,
// via the shared bounded cache) is fetched only when a row is actually auditioned, and only one
// row plays at a time. Rows use content-visibility (see index.css .segment-browser-row) so a
// 250-row library scrolls smoothly without a virtualization dependency.
import { memo, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { Copy, Loader2, Pause, Play, Plus } from 'lucide-react'
import { useAppStore } from '@/store'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { base64ToBlob, cn } from '@/lib/utils'
import { getClipAudioAnalysis } from '@/lib/waveform'
import { getSegmentAudioBase64, getVoice, type SegmentMeta, type VoiceMeta } from '@/lib/api'
import { useAudioSource } from '@/hooks/useAudioTransport'
import { SegmentPreviewRail } from './SegmentPreviewRail'
import * as ContextMenu from '../ui/context-menu'

type BrowserTab = 'segments' | 'voices'
type SortMode = 'newest' | 'duration' | 'name'

interface BrowserRow {
  id: string
  /** Identity domain: segment ids and voice ids are separate namespaces and can collide. */
  kind: 'segment' | 'voice'
  label: string
  meta: string | null
  durationSec: number | null
  projectId: string | null
  projectName: string | null
  createdAt: number
  /** Shared waveform cache key and peaks-state key: `<kind>:<persistent-id>:<revision>`. */
  assetKey: string
  fetchAudioBase64: () => Promise<string | null>
}

function segmentToRow(seg: SegmentMeta): BrowserRow {
  const id = seg.segment_id
  // Segment audio is immutable per segment_id: save_segment writes clip.wav exactly once and
  // no endpoint rewrites it (a segment is only deleted or re-assigned to a project), so the id
  // already identifies the audio and created_at is a defensive revision. If segments ever become
  // editable, this needs a real content digest instead (as VoiceMeta.sha256 is for voices).
  return {
    id,
    kind: 'segment',
    label: seg.text,
    meta: [seg.language, ...(seg.tags ?? [])].filter(Boolean).join(' · ') || null,
    durationSec: seg.duration_sec ?? null,
    projectId: seg.project_id ?? null,
    projectName: seg.project_name ?? null,
    createdAt: seg.created_at,
    assetKey: `segment:${id}:${seg.created_at}`,
    fetchAudioBase64: async () => seg.audio_base64 ?? (await getSegmentAudioBase64(id)),
  }
}

function voiceToRow(voice: VoiceMeta): BrowserRow {
  const id = voice.voice_id
  // Voices expose a real content digest; fall back to created_at for metadata without one.
  const revision = voice.sha256 ?? String(voice.created_at)
  return {
    id,
    kind: 'voice',
    label: voice.description || voice.voice_id,
    meta:
      [voice.language, voice.sample_text ? `Sample: ${voice.sample_text.slice(0, 60)}${voice.sample_text.length > 60 ? '…' : ''}` : null]
        .filter(Boolean)
        .join(' · ') || null,
    durationSec: null,
    projectId: voice.project_id ?? null,
    projectName: voice.project_name ?? null,
    createdAt: voice.created_at,
    assetKey: `voice:${id}:${revision}`,
    fetchAudioBase64: async () => voice.audio_base64 ?? (await getVoice(id)).audio_base64 ?? null,
  }
}

interface BrowserRowItemProps {
  row: BrowserRow
  checked: boolean
  isPlaying: boolean
  isLoading: boolean
  progress: number
  peaks: number[] | null
  onToggleSelect: (id: string) => void
  onTogglePlay: (row: BrowserRow) => void
  onDoubleClickInsert: (row: BrowserRow) => void
  /** Context-menu insert: the same path as a double click, exposed for the row menu. */
  onInsertRow: (row: BrowserRow) => void
}

/** One browser row, memoized so playback progress re-renders only the active row, never the
 * whole (up to 250-row) list. */
const BrowserRowItem = memo(function BrowserRowItem({
  row,
  checked,
  isPlaying,
  isLoading,
  progress,
  peaks,
  onToggleSelect,
  onTogglePlay,
  onDoubleClickInsert,
  onInsertRow,
}: BrowserRowItemProps) {
  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger asChild>
    <div
      data-testid="segment-browser-row"
      className="segment-browser-row flex items-center gap-2 py-2"
      onDoubleClick={() => onDoubleClickInsert(row)}
    >
      <input
        type="checkbox"
        data-testid={`stitch-picker-item-${row.kind === 'segment' ? 'segments' : 'voices'}`}
        checked={checked}
        onChange={() => onToggleSelect(row.id)}
        aria-label={row.label}
        className="size-3.5 shrink-0 accent-cyan-500"
      />
      <button
        type="button"
        data-testid="segment-browser-audio"
        data-playing={isPlaying}
        onClick={() => void onTogglePlay(row)}
        title="Audition"
        aria-label={`Audition ${row.label}`}
        className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground"
      >
        {isLoading ? (
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
      <SegmentPreviewRail peaks={peaks} progress={isPlaying ? progress : 0} isPlaying={isPlaying} />
      {row.durationSec != null && (
        <span className="shrink-0 text-[10px] text-muted-foreground">{row.durationSec.toFixed(1)}s</span>
      )}
      {row.projectName && (
        <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[9px] text-muted-foreground">
          {row.projectName}
        </span>
      )}

    </div>
      </ContextMenu.Trigger>
      <ContextMenu.Content data-testid="stitch-context-menu" data-menu-scope="segment">
        <ContextMenu.Label>{row.kind === 'segment' ? 'Segment' : 'Voice'}</ContextMenu.Label>
        <ContextMenu.Item data-testid="stitch-menu-insert" onSelect={() => onInsertRow(row)}>
          <Plus className="size-3" />
          Insert
        </ContextMenu.Item>
        <ContextMenu.Item data-testid="stitch-menu-audition" onSelect={() => onTogglePlay(row)}>
          {isPlaying ? <Pause className="size-3" /> : <Play className="size-3" />}
          {isPlaying ? 'Stop audition' : 'Audition'}
        </ContextMenu.Item>
        <ContextMenu.Item
          data-testid="stitch-menu-copy-id"
          onSelect={() => {
            void navigator.clipboard
              ?.writeText(row.id)
              .then(() => useAppStore.getState().announce(`Copied ${row.id}`))
              .catch(() => {})
          }}
        >
          <Copy className="size-3" />
          Copy id
        </ContextMenu.Item>
      </ContextMenu.Content>
    </ContextMenu.Root>
  )
})

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
  /** Hide the inline trigger when the caller supplies its own action (an empty state's single
   * next step, for instance) and drives the dialog through `controllerRef`. */
  hideTrigger?: boolean
}

export function SegmentBrowserModal({
  segments,
  onInsertSegments,
  voices,
  onInsertVoices,
  insertAfterClipId,
  controllerRef,
  hideTrigger = false,
}: SegmentBrowserModalProps) {
  const [open, setOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<BrowserTab>('segments')
  const [search, setSearch] = useState('')
  const [projectFilter, setProjectFilter] = useState('all')
  const [sortMode, setSortMode] = useState<SortMode>('newest')
  const [selectedSegmentIds, setSelectedSegmentIds] = useState<Set<string>>(new Set())
  const [selectedVoiceIds, setSelectedVoiceIds] = useState<Set<string>>(new Set())
  const [playingId, setPlayingIdState] = useState<string | null>(null)
  // Ref mirror so togglePlay stays referentially stable across play/stop (memoized rows must
  // not re-render just because playback started or stopped).
  const playingIdRef = useRef<string | null>(null)
  const setPlayingId = useCallback((id: string | null) => {
    playingIdRef.current = id
    setPlayingIdState(id)
  }, [])
  const [progress, setProgress] = useState(0)
  // Peaks keyed by asset identity (`<kind>:<persistent-id>:<revision>`), never a bare row id:
  // segment and voice ids are separate identity domains that can collide, and a revision bump
  // must drop a row back to the neutral rail. A superseded entry is unreachable (no row carries
  // its key anymore) -- that is the invalidation.
  const [peaksByKey, setPeaksByKey] = useState<Record<string, number[]>>({})
  const [loadingAudioId, setLoadingAudioId] = useState<string | null>(null)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audioUrlRef = useRef<string | null>(null)
  const searchInputRef = useRef<HTMLInputElement | null>(null)
  // Bumped on every new audition click and on close, so a slower in-flight fetch/decode/play
  // can detect it has been superseded and bail out instead of clobbering newer playback state
  // or resuming audio after the dialog has closed.
  const playbackTokenRef = useRef(0)
  // This modal is one audio source in the transport coordinator (T1): an audition here
  // silences whatever else is sounding, including the arrangement playing underneath it.
  const source = useAudioSource('segment-audition', 'Segment audition')

  /** The one way an audition ends: pausing, clearing the row's playing state, and giving up
   * playback focus. Every stop path routes through it so none can leave a stale claim. */
  const stopAudition = useCallback(() => {
    audioRef.current?.pause()
    setPlayingId(null)
    source.release()
  }, [setPlayingId, source])
  // The Audio object is created once and outlives individual renders; its 'ended' listener
  // reads the latest stop path through this ref.
  const stopAuditionRef = useRef(stopAudition)
  stopAuditionRef.current = stopAudition

  const hasVoices = (voices?.length ?? 0) > 0 && !!onInsertVoices

  useEffect(() => {
    if (!open) {
      playbackTokenRef.current += 1
      stopAudition()
      // Close leaves no audition state behind: a late in-flight resolve must not re-show a
      // spinner on reopen, and the object URL must not survive close/reopen cycles.
      setLoadingAudioId(null)
      if (audioUrlRef.current) {
        URL.revokeObjectURL(audioUrlRef.current)
        audioUrlRef.current = null
      }
    }
  }, [open, setPlayingId])

  useEffect(() => {
    return () => {
      audioRef.current?.pause()
      source.release()
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
    }
  }, [source])

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

  const handleInsertRow = handleDoubleClickInsert

  const togglePlay = useCallback(async (row: BrowserRow) => {
    if (playingIdRef.current === row.id) {
      stopAudition()
      return
    }
    const token = ++playbackTokenRef.current
    audioRef.current?.pause()
    setLoadingAudioId(row.id)
    // A superseded in-flight audition (a newer click or a close) must not clobber newer state;
    // at most it clears its own row's spinner if one is still showing.
    const dropStaleLoading = () => {
      setLoadingAudioId((cur) => (cur === row.id ? null : cur))
    }
    try {
      const b64 = await row.fetchAudioBase64()
      if (token !== playbackTokenRef.current) {
        dropStaleLoading()
        return // superseded by another click or a close
      }
      if (!b64) return
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
      const url = URL.createObjectURL(base64ToBlob(b64))
      audioUrlRef.current = url
      if (!peaksByKey[row.assetKey]) {
        const analysis = await getClipAudioAnalysis(row.assetKey, b64, 32)
        if (token !== playbackTokenRef.current) {
          // Superseded mid-decode: release the object URL this stale audition just allocated.
          URL.revokeObjectURL(url)
          if (audioUrlRef.current === url) audioUrlRef.current = null
          dropStaleLoading()
          return
        }
        setPeaksByKey((prev) => ({ ...prev, [row.assetKey]: analysis.peaks }))
      }
      if (!audioRef.current) {
        const audio = new Audio()
        audio.addEventListener('timeupdate', () => {
          if (audio.duration) setProgress(audio.currentTime / audio.duration)
        })
        audio.addEventListener('ended', stopAuditionRef.current)
        audioRef.current = audio
      }
      audioRef.current.src = url
      setProgress(0)
      // Auditioning a row takes playback focus (N6): whatever else is sounding -- the
      // arrangement under the modal, a deck elsewhere -- stops.
      source.claim(stopAudition)
      await audioRef.current.play()
      if (token !== playbackTokenRef.current) {
        stopAudition()
        return
      }
      setPlayingId(row.id)
    } finally {
      if (token === playbackTokenRef.current) setLoadingAudioId(null)
    }
  }, [peaksByKey, setPlayingId])

  const handleKeyDown = useCallback((e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Enter') return
    // Only the dialog/row surface commits the selection. Enter from an interactive control
    // (checkbox, audition button, selects, tabs, footer buttons, search input) keeps that
    // control's native behavior instead of triggering an insert.
    const target = e.target as HTMLElement | null
    if (target?.closest('input, button, select, textarea, a')) return
    e.preventDefault()
    handleInsertSelected()
  }, [handleInsertSelected])

  return (
    <>
      {!hideTrigger && (
        <button
          type="button"
          data-testid="stitch-picker-toggle-segments"
          onClick={() => setOpen(true)}
          className="inline-flex h-8 items-center gap-1.5 rounded border border-border bg-background px-2.5 text-xs hover:bg-muted"
        >
          <Plus className="size-3.5" /> Add segments
        </button>
      )}

      <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) resetPickerState() }}>
        {/* DialogContent is programmatically focusable (not in the Tab order) so the dialog
            surface itself can be the Enter target: clicking the padding focuses it, and Enter
            commits the current selection. Radix initial-focus still lands on the first real
            control. */}
        <DialogContent
          data-testid="segment-browser-dialog"
          className="flex max-h-[85vh] w-full max-w-2xl flex-col gap-3 sm:max-w-2xl"
          tabIndex={-1}
          onKeyDown={handleKeyDown}
        >
          <DialogTitle className="text-sm font-semibold">Add to timeline</DialogTitle>
          <DialogDescription className="sr-only">
            Browse saved segments and reference voices to insert into the stitch timeline.
          </DialogDescription>

          <Tabs
            value={activeTab}
            onValueChange={(v) => {
              // Project ids are per-tab identity domains; a filter valid on one tab can filter
              // the other tab's rows to nothing ("No matches"). Reset it on every tab switch.
              setActiveTab(v === 'voices' ? 'voices' : 'segments')
              setProjectFilter('all')
            }}
          >
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
            {filteredSorted.map((row) => (
              <BrowserRowItem
                key={row.id}
                row={row}
                checked={selectedIds.has(row.id)}
                isPlaying={playingId === row.id}
                isLoading={loadingAudioId === row.id}
                progress={progress}
                peaks={peaksByKey[row.assetKey] ?? null}
                onToggleSelect={toggleSelected}
                onTogglePlay={togglePlay}
                onDoubleClickInsert={handleDoubleClickInsert}
                onInsertRow={handleInsertRow}
              />
            ))}
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

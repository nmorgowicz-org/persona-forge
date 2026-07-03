import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  auditionOmniVoice,
  deleteOmniVoiceSegment,
  getOmniVoiceProgress,
  listOmniVoiceSegments,
  lockInOmniVoiceSegment,
  saveOmniVoice,
  stitchOmniVoice,
  type OmniVoiceCandidate,
  type OmniVoiceProgress,
  type SegmentMeta,
} from '@/lib/api'
import { ACCENT_BANK, type AccentBankEntry, type ShowcaseSentence } from '@/lib/accentBank'
import { AccentBank } from './AccentBank'
import { AudioPlayer } from './AudioPlayer'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

// Job-kickoff scaffolding for the OmniVoice engine (docs/plans/PLAN_persona_forge_studio.md
// §4 step 4). Validates the audition -> cherry-pick -> lock-in -> stitch -> save contract
// end-to-end with plain <audio> playback; the VST-level SegmentRack/StitchPreview waveform
// surfaces (§3.3, step 5) replace this UI later without touching the API contract.
//
// One-sentence-at-a-time workflow (feedback from nick, 2026-07-03): rather than a single
// multi-line textarea auditioned all at once, the user builds the reference clip
// incrementally — work one sentence, generate candidates, pick a take, lock it in, then
// move to the next sentence. This matches how OmniVoice is actually reliable (single-shot
// short-sentence generation, per [[voicedesign-accent-investigation]]) and lets the user
// react to each take before committing to the next line.
//
// Second feedback round (nick, 2026-07-03): lock-in now persists immediately to the durable
// segment library (POST /omnivoice/segments) instead of only living in local React state —
// so good takes survive a page reload / accumulate across sessions and can be tagged/browsed
// by trait ("australian accent", "female", ...). Stitching pulls from the library via
// segment_ids rather than only the current session's candidate_ids. A real progress bar
// (polling GET /omnivoice/progress) replaces the old indeterminate top-of-page banner, and
// candidates can be explicitly discarded instead of only "not picked."

interface LockedSegment {
  segmentId: string
  text: string
  audioBase64: string
}

const DEFAULT_ACCENT = ACCENT_BANK[0] ?? null
const PROGRESS_POLL_MS = 700

function formatEta(seconds: number | null): string {
  if (seconds == null) return 'estimating…'
  if (seconds < 1) return 'almost done'
  if (seconds < 60) return `~${Math.round(seconds)}s remaining`
  return `~${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s remaining`
}

interface PersonaForgePanelProps {
  onVoiceCreated?: (voiceId: string) => void
}

export function PersonaForgePanel({ onVoiceCreated }: PersonaForgePanelProps) {
  const [selectedAccent, setSelectedAccent] = useState<AccentBankEntry | null>(DEFAULT_ACCENT)
  const [instruct, setInstruct] = useState(DEFAULT_ACCENT?.instruct ?? '')
  const [candidatesPerSegment, setCandidatesPerSegment] = useState(3)

  const [lockedSegments, setLockedSegments] = useState<LockedSegment[]>([])
  const [currentText, setCurrentText] = useState('')
  const [currentCandidates, setCurrentCandidates] = useState<OmniVoiceCandidate[] | null>(null)
  const [currentSelectedIndex, setCurrentSelectedIndex] = useState(0)

  const [isAuditioning, setIsAuditioning] = useState(false)
  const [isLockingIn, setIsLockingIn] = useState(false)
  const [isStitching, setIsStitching] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stitchedUrl, setStitchedUrl] = useState<string | null>(null)
  const [stitchedBlob, setStitchedBlob] = useState<Blob | null>(null)
  const [savedVoiceId, setSavedVoiceId] = useState<string | null>(null)

  const [progress, setProgress] = useState<OmniVoiceProgress | null>(null)

  const [library, setLibrary] = useState<SegmentMeta[]>([])
  const [libraryFilter, setLibraryFilter] = useState('')
  const [isLibraryOpen, setIsLibraryOpen] = useState(false)
  const [librarySelection, setLibrarySelection] = useState<Set<string>>(new Set())

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!isAuditioning) {
      if (pollRef.current) clearInterval(pollRef.current)
      pollRef.current = null
      return
    }
    pollRef.current = setInterval(async () => {
      try {
        setProgress(await getOmniVoiceProgress())
      } catch {
        // Transient — the poll just retries next tick.
      }
    }, PROGRESS_POLL_MS)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [isAuditioning])

  async function refreshLibrary() {
    try {
      setLibrary(await listOmniVoiceSegments())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  useEffect(() => {
    refreshLibrary()
  }, [])

  function resetForAccent(entry: AccentBankEntry) {
    setSelectedAccent(entry)
    setInstruct(entry.instruct)
    setLockedSegments([])
    setCurrentText('')
    setCurrentCandidates(null)
    setStitchedUrl(null)
    setSavedVoiceId(null)
    setError(null)
  }

  function applySuggestion(sentence: ShowcaseSentence) {
    setCurrentText(sentence.text)
    setCurrentCandidates(null)
  }

  async function handleAuditionCurrent() {
    const text = currentText.trim()
    if (!text || isAuditioning) return
    setIsAuditioning(true)
    setError(null)
    setCurrentCandidates(null)
    setProgress(null)
    try {
      const result = await auditionOmniVoice({
        segments: [text],
        instruct,
        candidatesPerSegment,
      })
      setCurrentCandidates(result.segments[0]?.candidates ?? [])
      setCurrentSelectedIndex(0)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsAuditioning(false)
      setProgress(null)
    }
  }

  function discardCandidates() {
    setCurrentCandidates(null)
  }

  async function lockInCurrentTake() {
    if (!currentCandidates || !currentCandidates[currentSelectedIndex] || isLockingIn) return
    const chosen = currentCandidates[currentSelectedIndex]
    setIsLockingIn(true)
    setError(null)
    try {
      const meta = await lockInOmniVoiceSegment({
        candidateId: chosen.candidate_id,
        text: currentText.trim(),
        instruct,
        accentId: selectedAccent?.id ?? null,
      })
      setLockedSegments((prev) => [
        ...prev,
        { segmentId: meta.segment_id, text: meta.text, audioBase64: meta.audio_base64 ?? chosen.audio_base64 },
      ])
      setCurrentText('')
      setCurrentCandidates(null)
      setStitchedUrl(null)
      setSavedVoiceId(null)
      refreshLibrary()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsLockingIn(false)
    }
  }

  function removeLockedSegment(index: number) {
    setLockedSegments((prev) => prev.filter((_, i) => i !== index))
    setStitchedUrl(null)
    setSavedVoiceId(null)
  }

  function toggleLibrarySelection(segmentId: string) {
    setLibrarySelection((prev) => {
      const next = new Set(prev)
      if (next.has(segmentId)) next.delete(segmentId)
      else next.add(segmentId)
      return next
    })
  }

  function addSelectedFromLibrary() {
    const chosen = library.filter((m) => librarySelection.has(m.segment_id))
    setLockedSegments((prev) => [
      ...prev,
      ...chosen
        .filter((m) => !prev.some((s) => s.segmentId === m.segment_id))
        .map((m) => ({ segmentId: m.segment_id, text: m.text, audioBase64: m.audio_base64 ?? '' })),
    ])
    setLibrarySelection(new Set())
    setStitchedUrl(null)
    setSavedVoiceId(null)
  }

  async function handleDeleteFromLibrary(segmentId: string) {
    try {
      await deleteOmniVoiceSegment(segmentId)
      setLockedSegments((prev) => prev.filter((s) => s.segmentId !== segmentId))
      refreshLibrary()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleStitch() {
    if (lockedSegments.length === 0 || isStitching) return
    setIsStitching(true)
    setError(null)
    setSavedVoiceId(null)
    try {
      const blob = await stitchOmniVoice({ segmentIds: lockedSegments.map((s) => s.segmentId) })
      if (stitchedUrl) URL.revokeObjectURL(stitchedUrl)
      setStitchedBlob(blob)
      setStitchedUrl(URL.createObjectURL(blob))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsStitching(false)
    }
  }

  async function handleSave() {
    if (lockedSegments.length === 0 || isSaving) return
    setIsSaving(true)
    setError(null)
    try {
      const result = await saveOmniVoice({
        segmentIds: lockedSegments.map((s) => s.segmentId),
        instruct,
        segments: lockedSegments.map((s) => s.text),
        accentId: selectedAccent?.id ?? null,
      })
      setSavedVoiceId(result.voice_id)
      onVoiceCreated?.(result.voice_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsSaving(false)
    }
  }

  const filteredLibrary = libraryFilter.trim()
    ? library.filter((m) =>
        m.tags.some((t) => t.toLowerCase().includes(libraryFilter.trim().toLowerCase())),
      )
    : library

  const candidateLabel =
    progress && progress.total > 0
      ? `segment ${progress.current_segment_index + 1}/${progress.segment_count || 1}, candidate ${
          progress.current_candidate_index + 1
        }/${progress.candidates_per_segment || 1} (${progress.completed}/${progress.total})`
      : null

  return (
    <div className="flex flex-col gap-5 rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm">
      <div>
        <h2 className="text-base font-semibold">Design an accent-cloned voice</h2>
        <p className="text-sm text-muted-foreground">
          Pick an accent, work one sentence at a time — generate a few candidates, pick the
          best take, lock it in — then stitch your locked sentences into one reference clip.
          Locked takes are saved to your segment library and can be reused in later sessions.
        </p>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-medium text-muted-foreground">Accent</p>
        <AccentBank selectedId={selectedAccent?.id ?? null} onSelect={resetForAccent} />
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">
          Instruct (comma-separated: gender, age, pitch, optional "whisper", accent — closed
          vocabulary, no free-text tone words like "warm"/"sweet")
        </label>
        <input
          type="text"
          data-testid="omnivoice-instruct"
          className="w-full rounded-md border border-input bg-transparent p-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          value={instruct}
          onChange={(e) => setInstruct(e.target.value)}
        />
      </div>

      {lockedSegments.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium text-muted-foreground">
            Locked sentences ({lockedSegments.length})
          </p>
          {lockedSegments.map((seg, i) => (
            <div
              key={seg.segmentId}
              className="flex items-center gap-2 rounded-md border border-border bg-muted/30 p-2"
            >
              <span className="flex-1 text-sm">{seg.text}</span>
              {seg.audioBase64 && (
                <audio
                  src={`data:audio/wav;base64,${seg.audioBase64}`}
                  controls
                  className="h-8 w-40"
                />
              )}
              <Button type="button" size="sm" variant="ghost" onClick={() => removeLockedSegment(i)}>
                Remove
              </Button>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-3 rounded-lg border border-dashed border-border p-3">
        <p className="text-xs font-medium text-muted-foreground">
          {lockedSegments.length === 0 ? 'First sentence' : 'Next sentence'}
        </p>

        {selectedAccent && selectedAccent.showcaseSentences.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <p className="text-[11px] text-muted-foreground">
              Suggested lines that showcase this accent — click to use, then edit freely:
            </p>
            <div className="flex flex-wrap gap-1.5">
              {selectedAccent.showcaseSentences.map((sentence) => (
                <button
                  key={sentence.text}
                  type="button"
                  title={sentence.note}
                  onClick={() => applySuggestion(sentence)}
                  className={cn(
                    'rounded-full border px-2.5 py-1 text-[11px] transition-colors',
                    currentText === sentence.text
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border bg-transparent text-muted-foreground hover:bg-accent/40',
                  )}
                >
                  {sentence.text}
                </button>
              ))}
            </div>
          </div>
        )}

        <input
          type="text"
          data-testid="omnivoice-current-sentence"
          placeholder="Type or pick a sentence above…"
          className="w-full rounded-md border border-input bg-transparent p-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          value={currentText}
          onChange={(e) => {
            setCurrentText(e.target.value)
            setCurrentCandidates(null)
          }}
        />

        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            Candidates
            <input
              type="number"
              min={1}
              max={6}
              value={candidatesPerSegment}
              onChange={(e) => setCandidatesPerSegment(Number(e.target.value) || 1)}
              className="h-8 w-16 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            />
          </label>
          <Button
            type="button"
            data-testid="omnivoice-audition-button"
            onClick={handleAuditionCurrent}
            disabled={!currentText.trim() || isAuditioning}
          >
            {isAuditioning ? 'Generating…' : 'Generate candidates for this line'}
          </Button>
        </div>

        {isAuditioning && (
          <div data-testid="omnivoice-progress" className="flex flex-col gap-1">
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <motion.div
                className="h-full bg-primary"
                animate={{
                  width:
                    progress && progress.total > 0
                      ? `${Math.min(100, (progress.completed / progress.total) * 100)}%`
                      : '8%',
                }}
                transition={{ ease: 'easeOut', duration: 0.3 }}
              />
            </div>
            <p className="text-[11px] text-muted-foreground">
              {progress?.phase === 'loading'
                ? 'Loading OmniVoice checkpoint…'
                : candidateLabel ?? 'Starting…'}
              {progress?.phase === 'generating' && progress.estimated_remaining_seconds != null && (
                <> · {formatEta(progress.estimated_remaining_seconds)}</>
              )}
            </p>
          </div>
        )}

        <AnimatePresence>
          {currentCandidates && currentCandidates.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 6 }}
              className="flex flex-col gap-2"
            >
              {currentCandidates.map((candidate, i) => {
                const url = `data:audio/wav;base64,${candidate.audio_base64}`
                const selected = i === currentSelectedIndex
                return (
                  <div key={candidate.candidate_id} className="flex items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant={selected ? 'default' : 'outline'}
                      onClick={() => setCurrentSelectedIndex(i)}
                    >
                      Take {i + 1}
                    </Button>
                    <audio src={url} controls className="h-8 flex-1" />
                  </div>
                )
              })}
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  onClick={lockInCurrentTake}
                  disabled={isLockingIn}
                >
                  {isLockingIn ? 'Locking in…' : 'Lock in this take'}
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={discardCandidates}>
                  Discard all takes
                </Button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
        <button
          type="button"
          className="flex items-center justify-between text-left text-xs font-medium text-muted-foreground"
          onClick={() => setIsLibraryOpen((v) => !v)}
        >
          <span>Segment library ({library.length})</span>
          <span>{isLibraryOpen ? 'Hide' : 'Browse'}</span>
        </button>
        {isLibraryOpen && (
          <div className="flex flex-col gap-2">
            <input
              type="text"
              placeholder="Filter by tag (e.g. australian, female)…"
              value={libraryFilter}
              onChange={(e) => setLibraryFilter(e.target.value)}
              className="w-full rounded-md border border-input bg-transparent p-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            />
            <div className="flex max-h-64 flex-col gap-1.5 overflow-y-auto">
              {filteredLibrary.length === 0 && (
                <p className="text-[11px] text-muted-foreground">No segments match.</p>
              )}
              {filteredLibrary.map((m) => (
                <div
                  key={m.segment_id}
                  className={cn(
                    'flex items-center gap-2 rounded-md border p-2',
                    librarySelection.has(m.segment_id)
                      ? 'border-primary bg-primary/5'
                      : 'border-border',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={librarySelection.has(m.segment_id)}
                    onChange={() => toggleLibrarySelection(m.segment_id)}
                  />
                  <div className="flex-1">
                    <p className="text-sm">{m.text}</p>
                    <p className="text-[11px] text-muted-foreground">{m.tags.join(', ')}</p>
                  </div>
                  {m.audio_base64 && (
                    <audio
                      src={`data:audio/wav;base64,${m.audio_base64}`}
                      controls
                      className="h-8 w-32"
                    />
                  )}
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => handleDeleteFromLibrary(m.segment_id)}
                  >
                    Delete
                  </Button>
                </div>
              ))}
            </div>
            <Button
              type="button"
              size="sm"
              className="self-start"
              onClick={addSelectedFromLibrary}
              disabled={librarySelection.size === 0}
            >
              Add selected to locked sentences
            </Button>
          </div>
        )}
      </div>

      {error && (
        <p data-testid="omnivoice-error" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {lockedSegments.length > 0 && (
        <Button
          type="button"
          data-testid="omnivoice-stitch-button"
          onClick={handleStitch}
          disabled={isStitching}
          className="self-start"
        >
          {isStitching ? 'Stitching…' : `Stitch ${lockedSegments.length} locked sentence${lockedSegments.length === 1 ? '' : 's'}`}
        </Button>
      )}

      <AnimatePresence>
        {stitchedUrl && (
          <motion.div
            data-testid="omnivoice-result"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            className="flex flex-col gap-3 rounded-md border border-border bg-muted/40 p-3"
          >
            <AudioPlayer src={stitchedUrl} blob={stitchedBlob} />
            {savedVoiceId ? (
              <p className="text-xs text-muted-foreground">
                Saved to voice library as{' '}
                <span className="font-mono text-foreground">{savedVoiceId}</span>.
              </p>
            ) : (
              <Button
                type="button"
                data-testid="omnivoice-save-button"
                variant="outline"
                size="sm"
                onClick={handleSave}
                disabled={isSaving}
                className="self-start"
              >
                {isSaving ? 'Saving…' : 'Save to voice library'}
              </Button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  auditionOmniVoice,
  saveOmniVoice,
  stitchOmniVoice,
  type OmniVoiceCandidate,
} from '@/lib/api'
import { ACCENT_BANK, type AccentBankEntry } from '@/lib/accentBank'
import { AccentBank } from './AccentBank'
import { AudioPlayer } from './AudioPlayer'
import { Button } from '@/components/ui/button'

// Job-kickoff scaffolding for the Persona Forge (OmniVoice) engine
// (docs/plans/PLAN_persona_forge_studio.md §4 step 4). Validates the
// audition -> cherry-pick -> stitch -> save contract end-to-end with plain
// <audio> playback; the VST-level SegmentRack/StitchPreview waveform
// surfaces (§3.3, step 5) replace this UI later without touching the API
// contract.

interface SegmentCandidates {
  text: string
  candidates: OmniVoiceCandidate[]
  selectedIndex: number
}

const DEFAULT_ACCENT = ACCENT_BANK[0] ?? null

interface PersonaForgePanelProps {
  onVoiceCreated?: (voiceId: string) => void
}

export function PersonaForgePanel({ onVoiceCreated }: PersonaForgePanelProps) {
  const [selectedAccent, setSelectedAccent] = useState<AccentBankEntry | null>(DEFAULT_ACCENT)
  const [segmentsText, setSegmentsText] = useState(
    DEFAULT_ACCENT ? DEFAULT_ACCENT.segments.join('\n') : '',
  )
  const [instruct, setInstruct] = useState(DEFAULT_ACCENT?.instruct ?? '')
  const [candidatesPerSegment, setCandidatesPerSegment] = useState(3)
  const [isAuditioning, setIsAuditioning] = useState(false)
  const [isStitching, setIsStitching] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [segments, setSegments] = useState<SegmentCandidates[] | null>(null)
  const [stitchedUrl, setStitchedUrl] = useState<string | null>(null)
  const [stitchedBlob, setStitchedBlob] = useState<Blob | null>(null)
  const [savedVoiceId, setSavedVoiceId] = useState<string | null>(null)

  function selectAccent(entry: AccentBankEntry) {
    setSelectedAccent(entry)
    setSegmentsText(entry.segments.join('\n'))
    setInstruct(entry.instruct)
    setSegments(null)
    setStitchedUrl(null)
    setSavedVoiceId(null)
  }

  async function handleAudition() {
    const lines = segmentsText
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
    if (!selectedAccent || lines.length === 0 || isAuditioning) return

    setIsAuditioning(true)
    setError(null)
    setSegments(null)
    setStitchedUrl(null)
    setSavedVoiceId(null)
    try {
      const result = await auditionOmniVoice({
        segments: lines,
        instruct,
        candidatesPerSegment,
      })
      setSegments(
        result.segments.map((seg, i) => ({
          text: lines[i],
          candidates: seg.candidates,
          selectedIndex: 0,
        })),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsAuditioning(false)
    }
  }

  function pickCandidate(segmentIndex: number, candidateIndex: number) {
    setSegments((prev) =>
      prev
        ? prev.map((seg, i) =>
            i === segmentIndex ? { ...seg, selectedIndex: candidateIndex } : seg,
          )
        : prev,
    )
  }

  async function handleStitch() {
    if (!segments || isStitching) return
    setIsStitching(true)
    setError(null)
    setSavedVoiceId(null)
    try {
      const selections = segments.map((seg) => seg.candidates[seg.selectedIndex].candidate_id)
      const blob = await stitchOmniVoice(selections)
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
    if (!segments || isSaving) return
    setIsSaving(true)
    setError(null)
    try {
      const selections = segments.map((seg) => seg.candidates[seg.selectedIndex].candidate_id)
      const result = await saveOmniVoice({
        selections,
        instruct,
        segments: segments.map((seg) => seg.text),
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

  return (
    <div className="flex flex-col gap-5 rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm">
      <div>
        <h2 className="text-base font-semibold">Design an accent-cloned voice</h2>
        <p className="text-sm text-muted-foreground">
          Pick an accent, generate a few candidates per sentence, cherry-pick the best takes,
          then stitch into one reference clip.
        </p>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-medium text-muted-foreground">Accent</p>
        <AccentBank selectedId={selectedAccent?.id ?? null} onSelect={selectAccent} />
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

      <div>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">
          Reference sentences (one per line — each becomes its own segment)
        </label>
        <textarea
          data-testid="omnivoice-segments"
          className="min-h-24 w-full resize-y rounded-md border border-input bg-transparent p-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          value={segmentsText}
          onChange={(e) => setSegmentsText(e.target.value)}
        />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          Candidates/segment
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
          onClick={handleAudition}
          disabled={!selectedAccent || !segmentsText.trim() || isAuditioning}
        >
          {isAuditioning ? 'Generating candidates…' : 'Generate candidates'}
        </Button>
      </div>

      {error && (
        <p data-testid="omnivoice-error" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <AnimatePresence>
        {segments && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            className="flex flex-col gap-4"
          >
            {segments.map((seg, segIndex) => (
              <div key={segIndex} className="rounded-lg border border-border p-3">
                <p className="mb-2 text-sm">{seg.text}</p>
                <div className="flex flex-col gap-2">
                  {seg.candidates.map((candidate, candIndex) => {
                    const url = `data:audio/wav;base64,${candidate.audio_base64}`
                    const selected = candIndex === seg.selectedIndex
                    return (
                      <div key={candidate.candidate_id} className="flex items-center gap-2">
                        <Button
                          type="button"
                          size="sm"
                          variant={selected ? 'default' : 'outline'}
                          onClick={() => pickCandidate(segIndex, candIndex)}
                        >
                          Take {candIndex + 1}
                        </Button>
                        <audio src={url} controls className="h-8 flex-1" />
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}

            <Button
              type="button"
              data-testid="omnivoice-stitch-button"
              onClick={handleStitch}
              disabled={isStitching}
              className="self-start"
            >
              {isStitching ? 'Stitching…' : 'Stitch selected takes'}
            </Button>
          </motion.div>
        )}
      </AnimatePresence>

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

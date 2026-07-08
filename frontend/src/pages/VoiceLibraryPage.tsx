import { useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { AudioWaveform, Layers, Loader2, Mic2, Pencil, Plus, Sparkles, Trash2 } from 'lucide-react'
import {
  deleteOmniVoiceSegment,
  deleteVoice,
  getVoice,
  listOmniVoiceSegments,
  listVoices,
  updateVoiceSampleText,
  type SegmentMeta,
  type VoiceMeta,
} from '@/lib/api'
import { hasChipSelections, type ChipSelections } from '@/lib/voiceDesignChips'
import { AudioPlayer } from '@/components/AudioPlayer'
import { Button } from '@/components/ui/button'
import { createStitchClipFromSegment } from '@/lib/stitchClips'
import { useAppStore, type StitchPlanClip } from '@/store'

// Shape persisted by /omnivoice/save into voice.selections -- see app.py's omnivoice_save
// handler. stitch_plan is the raw (snake_case) editor payload, kept verbatim so a voice
// assembled in Stitch Studio can later be reopened there instead of only existing as a
// flattened audio blob (candidate_id-only clips are the exception: those reference the
// ephemeral in-memory audition cache and can't be recovered once it's evicted/restarted).
interface OmniVoiceSelections {
  engine?: string
  stitch_plan?: {
    clips?: {
      segment_id?: string
      candidate_id?: string
      voice_id?: string
      trim_start_ms?: number
      trim_end_ms?: number
      fade_in_ms?: number
      fade_out_ms?: number
    }[]
    padding_ms?: number[]
    crossfade_ms?: number
    segment_target_dbfs?: number
    final_target_dbfs?: number
    final_ceiling_db?: number
    compress?: { threshold_db: number; ratio: number } | null
  } | null
}

function toBase64FromUrl(url: string): Promise<string> {
  return fetch(url)
    .then((r) => {
      if (!r.ok) throw new Error(`Failed to fetch audio (${r.status}): ${url}`)
      return r.arrayBuffer()
    })
    .then((buf) => {
      const bytes = new Uint8Array(buf)
      let binary = ''
      for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
      return btoa(binary)
    })
}

function ClipPlayerUrl({ segmentId, className }: { segmentId: string; className?: string }) {
  const url = `/omnivoice/segments/${encodeURIComponent(segmentId)}/audio`
  const [blob, setBlob] = useState<Blob | null>(null)
  const [src, setSrc] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`Failed to fetch audio (${r.status}): ${url}`)
        return r.blob()
      })
      .then((b) => {
        if (!cancelled) {
          setBlob(b)
          setSrc(URL.createObjectURL(b))
        }
      })
      .catch(() => {
        if (!cancelled) setSrc(url)
      })
    return () => {
      cancelled = true
    }
  }, [url])

  useEffect(() => {
    const u = src
    return () => {
      if (u && u.startsWith('blob:')) URL.revokeObjectURL(u)
    }
  }, [src])

  if (!src) return null

  return <AudioPlayer src={src} blob={blob} className={className} autoPlay={false} />
}

// Auto-loads (but does not auto-play) a saved voice's reference audio without a
// "Load preview" click, mirroring the saved-segment cards below (ClipPlayerUrl).
function VoiceAudioAutoPlayer({ voiceId }: { voiceId: string }) {
  const [state, setState] = useState<{ url: string; blob: Blob } | 'loading' | 'error'>('loading')

  useEffect(() => {
    let cancelled = false
    setState('loading')
    getVoice(voiceId)
      .then((full) => {
        if (cancelled) return
        if (!full.audio_base64) {
          setState('error')
          return
        }
        const bytes = Uint8Array.from(atob(full.audio_base64), (c) => c.charCodeAt(0))
        const blob = new Blob([bytes], { type: 'audio/wav' })
        setState({ url: URL.createObjectURL(blob), blob })
      })
      .catch(() => {
        if (!cancelled) setState('error')
      })
    return () => {
      cancelled = true
    }
  }, [voiceId])

  useEffect(() => {
    return () => {
      if (state !== 'loading' && state !== 'error') URL.revokeObjectURL(state.url)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voiceId])

  if (state === 'loading') {
    return (
      <div className="flex h-9 items-center gap-1.5 text-xs text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" />
        Loading waveform…
      </div>
    )
  }
  if (state === 'error') {
    return <p className="text-xs text-muted-foreground">Couldn't load audio.</p>
  }
  return <AudioPlayer src={state.url} blob={state.blob} autoPlay={false} />
}

function VoiceCard({
  voice,
  busy,
  onUse,
  onDesignFrom,
  onReopenInStitchStudio,
  onDelete,
  onSaveSampleText,
}: {
  voice: VoiceMeta
  busy: boolean
  onUse: () => void
  onDesignFrom: (() => void) | null
  onReopenInStitchStudio: (() => void) | null
  onDelete: () => void
  onSaveSampleText: (text: string) => Promise<void>
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(voice.sample_text)
  const [saving, setSaving] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  const commit = async () => {
    const trimmed = draft.trim()
    setEditing(false)
    if (!trimmed || trimmed === voice.sample_text) {
      setDraft(voice.sample_text)
      return
    }
    setSaving(true)
    try {
      await onSaveSampleText(trimmed)
    } finally {
      setSaving(false)
    }
  }

  return (
    <motion.div
      data-testid="voice-card"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -2 }}
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 text-card-foreground shadow-sm transition-shadow duration-200 hover:border-border/80 hover:shadow-lg"
    >
      <div>
        <p className="text-sm font-medium">{voice.voice_id}</p>
        <p className="line-clamp-2 text-xs text-muted-foreground">{voice.description}</p>
      </div>

      <div className="rounded-lg border border-border/60 bg-muted/20 p-2">
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Reference text
        </p>
        {editing ? (
          <textarea
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                commit()
              } else if (e.key === 'Escape') {
                e.preventDefault()
                setDraft(voice.sample_text)
                setEditing(false)
              }
            }}
            rows={2}
            className="w-full resize-none rounded border border-cyan-500/40 bg-background px-2 py-1 text-xs text-foreground outline-none"
          />
        ) : (
          <p
            className="cursor-text text-xs text-foreground hover:text-cyan-400"
            title="Click to edit — this is the cloning transcript, so it must match the audio"
            onClick={() => {
              setDraft(voice.sample_text)
              setEditing(true)
            }}
          >
            {voice.sample_text || '(no reference text — click to add)'}
            {saving && ' (saving…)'}
          </p>
        )}
      </div>

      <VoiceAudioAutoPlayer voiceId={voice.voice_id} />

      <div className="flex gap-2">
        <Button size="sm" className="flex-1" onClick={onUse}>
          Use in Speak
        </Button>
        {onDesignFrom && (
          <Button
            size="sm"
            variant="outline"
            aria-label="Design a new voice from this one"
            title="Design a new voice from this one's chip settings"
            disabled={busy}
            onClick={onDesignFrom}
          >
            <Sparkles className="size-4" />
          </Button>
        )}
        {onReopenInStitchStudio && (
          <Button
            size="sm"
            variant="outline"
            aria-label="Reopen in Stitch Studio"
            title="Reopen the clips this voice was assembled from in Stitch Studio"
            disabled={busy}
            onClick={onReopenInStitchStudio}
          >
            <Layers className="size-4" />
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          aria-label="Edit reference text"
          title="Edit reference text"
          disabled={busy}
          onClick={() => {
            setDraft(voice.sample_text)
            setEditing(true)
          }}
        >
          <Pencil className="size-4" />
        </Button>
        <Button
          size="sm"
          variant="outline"
          aria-label="Delete this voice"
          title="Delete this voice"
          disabled={busy}
          onClick={onDelete}
        >
          <Trash2 className="size-4" />
        </Button>
      </div>
    </motion.div>
  )
}

export function VoiceLibraryPage() {
  const voices = useAppStore((s) => s.voices)
  const segments = useAppStore((s) => s.ovLibrary)
  const storeSetVoices = useAppStore((s) => s.setVoices)
  const storeSetSegments = useAppStore((s) => s.setOvLibrary)

  const [error, setError] = useState<string | null>(null)
  const [busyVoiceId, setBusyVoiceId] = useState<string | null>(null)
  const [busySegmentId, setBusySegmentId] = useState<string | null>(null)

  const [segSearch, setSegSearch] = useState('')

  const setVoiceId = useAppStore((s) => s.setVoiceId)
  const setPage = useAppStore((s) => s.setPage)
  const setEditingVoice = useAppStore((s) => s.setEditingVoice)
  const setDesignEngine = useAppStore((s) => s.setDesignEngine)
  const setOvStitchEditorOpen = useAppStore((s) => s.setOvStitchEditorOpen)
  const setOvStitchPlanClips = useAppStore((s) => s.setOvStitchPlanClips)
  const setOvStitchPlanPaddingMs = useAppStore((s) => s.setOvStitchPlanPaddingMs)
  const setOvStitchPlanDsp = useAppStore((s) => s.setOvStitchPlanDsp)

  async function refresh() {
    const [v, segs] = await Promise.all([
      listVoices().catch((err) => {
        setError(err instanceof Error ? err.message : String(err))
        return [] as VoiceMeta[]
      }),
      listOmniVoiceSegments().catch(() => [] as SegmentMeta[]),
    ])
    storeSetVoices(v)
    storeSetSegments(segs)
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const filteredSegments = useMemo(() => {
    if (!segSearch.trim()) return segments
    const q = segSearch.trim().toLowerCase()
    return segments.filter((s) => {
      if (s.text.toLowerCase().includes(q)) return true
      return (s.tags ?? []).some((t) => (t ?? '').toLowerCase().includes(q))
    })
  }, [segments, segSearch])

  async function insertSegmentIntoStitchEditor(seg: SegmentMeta) {
    setError(null)
    try {
      const clip = await createStitchClipFromSegment(seg)

      setPage('voice-design')
      setDesignEngine('omnivoice')

      setOvStitchPlanClips((prev: any) => [...(prev ?? []), clip])
      setOvStitchEditorOpen(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  // Only meaningful for chip-based voices: re-opens VoiceDesignPanel pre-filled with this
  // voice's chip selections so the user can tweak and save as a NEW voice (always forks --
  // re-generates the reference audio, unlike editing reference text below). Voices built via
  // Stitch Studio/OmniVoice don't have chip selections, so this action isn't offered for them
  // (setDesignEngine('qwen') here is what was missing before, which used to route stitch-plan
  // voices into the wrong panel and crash).
  async function designFromVoice(voiceId: string) {
    setBusyVoiceId(voiceId)
    setError(null)
    try {
      const full = await getVoice(voiceId)
      setEditingVoice({
        voiceId: full.voice_id,
        description: full.description,
        sampleText: full.sample_text,
        language: full.language,
        seed: full.seed ?? null,
        selections: (full.selections as ChipSelections | null | undefined) ?? null,
      })
      setDesignEngine('qwen')
      setPage('voice-design')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyVoiceId(null)
    }
  }

  // Rebuilds a Stitch Studio timeline from a voice's saved stitch_plan (its actual assembly
  // origin -- segment/voice refs, trims, fades, padding, DSP) so it can be re-arranged and
  // re-saved, instead of only ever existing as a flattened audio blob. Re-saving always forks
  // a new voice (no in-place audio replace yet); clips that only carried an ephemeral
  // candidate_id (never locked into the segment library) can't be recovered and are skipped.
  async function reopenInStitchStudio(voice: VoiceMeta) {
    setBusyVoiceId(voice.voice_id)
    setError(null)
    try {
      const sel = (voice.selections as OmniVoiceSelections | null | undefined) ?? null
      const plan = sel?.stitch_plan
      const planClips = plan?.clips ?? []

      const rebuilt: StitchPlanClip[] = []
      let skipped = 0
      for (const [i, c] of planClips.entries()) {
        if (c.segment_id) {
          const seg = segments.find((s) => s.segment_id === c.segment_id)
          if (!seg) {
            skipped++
            continue
          }
          const b64 = await toBase64FromUrl(
            `/omnivoice/segments/${encodeURIComponent(c.segment_id)}/audio`,
          )
          rebuilt.push({
            clipId: `clip_reopen_${Date.now()}_${i}`,
            ref: { segmentId: c.segment_id },
            text: seg.text,
            sourceAudioBase64: b64,
            sampleRate: seg.sample_rate ?? 24000,
            durationMs:
              typeof seg.duration_sec === 'number' && seg.duration_sec > 0
                ? Math.round(seg.duration_sec * 1000)
                : 0,
            trimStartMs: c.trim_start_ms ?? 0,
            trimEndMs: c.trim_end_ms ?? 0,
            fadeInMs: c.fade_in_ms ?? 0,
            fadeOutMs: c.fade_out_ms ?? 0,
          })
        } else if (c.voice_id) {
          const full = await getVoice(c.voice_id)
          if (!full.audio_base64) {
            skipped++
            continue
          }
          rebuilt.push({
            clipId: `clip_reopen_${Date.now()}_${i}`,
            ref: { voiceId: c.voice_id },
            text: full.sample_text,
            sourceAudioBase64: full.audio_base64,
            sampleRate: 24000,
            durationMs: 0,
            trimStartMs: c.trim_start_ms ?? 0,
            trimEndMs: c.trim_end_ms ?? 0,
            fadeInMs: c.fade_in_ms ?? 0,
            fadeOutMs: c.fade_out_ms ?? 0,
          })
        } else {
          skipped++
        }
      }

      if (rebuilt.length === 0) {
        setError(
          "This voice's original clips are no longer available (only ephemeral audition candidates were used, not saved segments) — it can't be reopened for editing.",
        )
        return
      }

      setOvStitchPlanClips(rebuilt)
      setOvStitchPlanPaddingMs(plan?.padding_ms ?? new Array(Math.max(0, rebuilt.length - 1)).fill(0))
      setOvStitchPlanDsp({
        crossfadeMs: plan?.crossfade_ms,
        segmentTargetDbfs: plan?.segment_target_dbfs,
        finalTargetDbfs: plan?.final_target_dbfs,
        finalCeilingDb: plan?.final_ceiling_db,
        compressEnabled: plan?.compress != null,
        compressThresholdDb: plan?.compress?.threshold_db,
        compressRatio: plan?.compress?.ratio,
      })
      setDesignEngine('omnivoice')
      setPage('voice-design')
      setOvStitchEditorOpen(true)

      if (skipped > 0) {
        setError(
          `${skipped} clip(s) from the original assembly couldn't be recovered (ephemeral audition candidates) and were skipped.`,
        )
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyVoiceId(null)
    }
  }

  async function saveSampleText(voiceId: string, text: string) {
    setError(null)
    try {
      await updateVoiceSampleText(voiceId, text)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function remove(voiceId: string) {
    if (!window.confirm(`Delete voice ${voiceId}? This can't be undone.`)) return
    setBusyVoiceId(voiceId)
    setError(null)
    try {
      await deleteVoice(voiceId)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyVoiceId(null)
    }
  }

  async function removeSegment(segmentId: string) {
    if (!window.confirm('Delete this segment? This can’t be undone.')) return
    setBusySegmentId(segmentId)
    setError(null)
    try {
      await deleteOmniVoiceSegment(segmentId)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusySegmentId(null)
    }
  }

  const formatSegmentMeta = (m: SegmentMeta) => {
    const parts: string[] = []
    const tags = m.tags?.join(', ')
    if (tags) parts.push(tags)
    if (typeof m.duration_sec === 'number' && m.duration_sec > 0)
      parts.push(`${m.duration_sec.toFixed(1)}s`)
    if (m.created_at) {
      const d = new Date(m.created_at * 1000)
      parts.push(d.toLocaleDateString('en-GB', { month: 'short', day: '2-digit' }))
    }
    return parts.join(' · ')
  }

  return (
    <div className="flex flex-col gap-6">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-semibold tracking-tight">Voice Library</h1>
        <p className="text-sm text-muted-foreground">
          Voices you've designed and saved, ready to use in Speak or over the API.
        </p>
      </motion.div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* Voices */}
      {voices.length === 0 && segments.length === 0 && !error ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border py-16 text-center">
          <Mic2 className="size-6 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">No voices saved yet.</p>
          <Button size="sm" variant="secondary" onClick={() => setPage('voice-design')}>
            Design your first voice
          </Button>
        </div>
      ) : (
        <>
          {voices.length > 0 && (
            <section className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold tracking-tight">
                  Saved voices ({voices.length})
                </h2>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {voices.map((voice) => (
                  <VoiceCard
                    key={voice.voice_id}
                    voice={voice}
                    busy={busyVoiceId === voice.voice_id}
                    onUse={() => {
                      setVoiceId(voice.voice_id)
                      setPage('speak')
                    }}
                    onDesignFrom={
                      hasChipSelections(voice.selections) ? () => designFromVoice(voice.voice_id) : null
                    }
                    onReopenInStitchStudio={
                      (voice.selections as OmniVoiceSelections | null | undefined)?.stitch_plan?.clips
                        ?.length
                        ? () => reopenInStitchStudio(voice)
                        : null
                    }
                    onDelete={() => remove(voice.voice_id)}
                    onSaveSampleText={(text) => saveSampleText(voice.voice_id, text)}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Saved segments */}
          <section className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold tracking-tight">
                  Saved segments ({segments.length})
                </h2>
                <p className="text-[10px] text-muted-foreground">
                  Individual takes you can hear, reuse, and insert into the stitch editor.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <div className="relative">
                  <input
                    type="text"
                    placeholder="Search segments…"
                    value={segSearch}
                    onChange={(e) => setSegSearch(e.target.value)}
                    className="h-8 w-48 rounded-md border border-border bg-muted/20 px-3 text-xs outline-none ring-0 focus:border-ring"
                  />
                </div>
              </div>
            </div>

            {segments.length === 0 && (
              <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border py-10 text-center">
                  <AudioWaveform className="size-5 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  No saved segments yet.
                </p>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setPage('voice-design')
                    setDesignEngine('omnivoice')
                  }}
                >
                  Generate segments with OmniVoice
                </Button>
              </div>
            )}

            {filteredSegments.length > 0 ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {filteredSegments.map((seg, i) => (
                  <motion.div
                    key={seg.segment_id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.02 }}
                    whileHover={{ y: -1 }}
                    className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3 text-card-foreground shadow-sm transition-shadow hover:shadow-lg"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1">
                        <p className="text-xs">{seg.text}</p>
                        <p className="mt-1 text-[10px] text-muted-foreground">
                          {formatSegmentMeta(seg)}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="self-start"
                        aria-label="Delete segment"
                        title="Delete segment"
                        disabled={busySegmentId === seg.segment_id}
                        onClick={() => removeSegment(seg.segment_id)}
                      >
                        <Trash2 className="size-3.5 text-muted-foreground" />
                      </Button>
                    </div>

                    <div className="flex items-center gap-2">
                      <div className="flex-1">
                        <ClipPlayerUrl
                          segmentId={seg.segment_id}
                          className="w-full"
                        />
                      </div>
                      <Button
                        size="sm"
                        className="gap-1"
                        onClick={() => insertSegmentIntoStitchEditor(seg)}
                      >
                        <Plus className="size-3.5" />
                        Insert into stitch editor
                      </Button>
                    </div>
                  </motion.div>
                ))}
              </div>
            ) : segSearch.trim() ? (
              <p className="text-xs text-muted-foreground">
                No segments match your search.
              </p>
            ) : null}
          </section>
        </>
      )}
    </div>
  )
}

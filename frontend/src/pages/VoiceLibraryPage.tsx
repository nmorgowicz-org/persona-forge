import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { AudioWaveform, Mic2, Pencil, Plus, Trash2 } from 'lucide-react'
import {
  deleteOmniVoiceSegment,
  deleteVoice,
  getVoice,
  listOmniVoiceSegments,
  listVoices,
  type SegmentMeta,
  type VoiceMeta,
} from '@/lib/api'
import type { ChipSelections } from '@/lib/voiceDesignChips'
import { AudioPlayer } from '@/components/AudioPlayer'
import { Button } from '@/components/ui/button'
import { useAppStore } from '@/store'

function toBase64FromUrl(url: string): Promise<string> {
  return fetch(url)
    .then((r) => r.arrayBuffer())
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
      .then((r) => r.blob())
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

export function VoiceLibraryPage() {
  const [voices, setVoices] = useState<VoiceMeta[]>([])
  const [segments, setSegments] = useState<SegmentMeta[]>([])
  const [error, setError] = useState<string | null>(null)
  const [playing, setPlaying] = useState<Record<string, { url: string; blob: Blob }>>({})
  const [busyVoiceId, setBusyVoiceId] = useState<string | null>(null)
  const [busySegmentId, setBusySegmentId] = useState<string | null>(null)

  const [segSearch, setSegSearch] = useState('')

  const setVoiceId = useAppStore((s) => s.setVoiceId)
  const setPage = useAppStore((s) => s.setPage)
  const setEditingVoice = useAppStore((s) => s.setEditingVoice)
  const setDesignEngine = useAppStore((s) => s.setDesignEngine)
  const setOvStitchEditorOpen = useAppStore((s) => s.setOvStitchEditorOpen)
  const setOvStitchPlanClips = useAppStore((s) => s.setOvStitchPlanClips)

  function refresh() {
    return Promise.all([
      listVoices().catch((err) => {
        setError(err instanceof Error ? err.message : String(err))
        return [] as VoiceMeta[]
      }),
      listOmniVoiceSegments().catch(() => [] as SegmentMeta[]),
    ]).then(([v, segs]) => {
      setVoices(v)
      setSegments(segs)
    })
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
      const url = `/omnivoice/segments/${encodeURIComponent(seg.segment_id)}/audio`
      const b64 = await toBase64FromUrl(url)

      setPage('voice-design')
      setDesignEngine('omnivoice')

      const clipId = `clip_seg_${Date.now()}`
      const durationMs =
        typeof seg.duration_sec === 'number' && seg.duration_sec > 0
          ? Math.round(seg.duration_sec * 1000)
          : 0

      setOvStitchPlanClips((prev: any) => [
        ...(prev ?? []),
        {
          clipId,
          ref: { segmentId: seg.segment_id },
          text: seg.text,
          sourceAudioBase64: b64,
          sampleRate: seg.sample_rate ?? 24000,
          durationMs,
          trimStartMs: 0,
          trimEndMs: 0,
          fadeInMs: 0,
          fadeOutMs: 0,
        },
      ])

      setOvStitchEditorOpen(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function preview(voiceId: string) {
    if (playing[voiceId]) return
    try {
      const full = await getVoice(voiceId)
      if (!full.audio_base64) return
      const bytes = Uint8Array.from(atob(full.audio_base64), (c) => c.charCodeAt(0))
      const blob = new Blob([bytes], { type: 'audio/wav' })
      setPlaying((prev) => ({ ...prev, [voiceId]: { url: URL.createObjectURL(blob), blob } }))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function edit(voiceId: string) {
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
      setPage('voice-design')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyVoiceId(null)
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
                {voices.map((voice, i) => (
                  <motion.div
                    key={voice.voice_id}
                    data-testid="voice-card"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.03 }}
                    whileHover={{ y: -2 }}
                    className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 text-card-foreground shadow-sm transition-shadow duration-200 hover:border-border/80 hover:shadow-lg"
                  >
                    <div>
                      <p className="text-sm font-medium">{voice.voice_id}</p>
                      <p className="line-clamp-2 text-xs text-muted-foreground">
                        {voice.description}
                      </p>
                    </div>

                    {playing[voice.voice_id] ? (
                      <AudioPlayer
                        src={playing[voice.voice_id].url}
                        blob={playing[voice.voice_id].blob}
                      />
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => preview(voice.voice_id)}>
                        Load preview
                      </Button>
                    )}

                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        className="flex-1"
                        onClick={() => {
                          setVoiceId(voice.voice_id)
                          setPage('speak')
                        }}
                      >
                        Use in Speak
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        aria-label="Tune this voice"
                        title="Tune this voice"
                        disabled={busyVoiceId === voice.voice_id}
                        onClick={() => edit(voice.voice_id)}
                      >
                        <Pencil className="size-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        aria-label="Delete this voice"
                        title="Delete this voice"
                        disabled={busyVoiceId === voice.voice_id}
                        onClick={() => remove(voice.voice_id)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  </motion.div>
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

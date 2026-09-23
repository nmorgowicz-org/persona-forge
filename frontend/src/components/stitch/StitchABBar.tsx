// A/B plan snapshots for Stitch Studio (M5). Capture the plan as A, keep editing to B, and
// switch between the two without losing either; each snapshot can be auditioned on its own.
//
// The snapshots live in module state, deliberately: they are session-local (a reload clears
// them, navigating away and back does not) and are never written to the store, the plan
// payload, or the backend. The plan itself stays exactly where it was -- switching is one
// `replaceOvStitchPlan`, so it is one undoable entry like any other plan change (A-6).
//
// Auditioning is a third audio owner, so it goes through the playback-focus registry (N6):
// claiming playback pauses whatever owned it before, including the arrangement transport.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Pause, Play } from 'lucide-react'
import { create } from 'zustand'
import { useAppStore } from '@/store'
import { cloneStitchPlanState, hashStitchPlan, type StitchPlanState } from '@/lib/stitchPlan'
import { useAudioSource } from '@/hooks/useAudioTransport'
import { useStitchPreview } from '@/hooks/useStitchPreview'
import { cn } from '@/lib/utils'

type Slot = 'a' | 'b'

interface Snapshot {
  plan: StitchPlanState
  /** Fingerprint of the plan as captured, to tell "still this snapshot" from "edited since". */
  hash: string
}

interface StitchABStore {
  a: Snapshot | null
  b: Snapshot | null
  active: Slot | null
  capture(slot: Slot, plan: StitchPlanState): void
  activate(slot: Slot): void
}

export const useStitchABStore = create<StitchABStore>((set, get) => ({
  a: null,
  b: null,
  active: null,

  capture: (slot, plan) =>
    set({
      [slot]: { plan: cloneStitchPlanState(plan), hash: hashStitchPlan(plan) },
      active: slot,
    } as Pick<StitchABStore, Slot> & { active: Slot }),

  activate: (slot) => {
    const snapshot = get()[slot]
    if (!snapshot) return
    // A clone, so the live plan can never alias the snapshot's own objects.
    useAppStore.getState().replaceOvStitchPlan(cloneStitchPlanState(snapshot.plan))
    set({ active: slot })
  },
}))

export function StitchABBar() {
  const clips = useAppStore((s) => s.ovStitchPlanClips)
  const paddingMs = useAppStore((s) => s.ovStitchPlanPaddingMs)
  const dsp = useAppStore((s) => s.ovStitchPlanDsp)
  const regionEditsByClip = useAppStore((s) => s.ovStitchRegionEditsByClip)
  const plan = useMemo<StitchPlanState>(
    () => ({ clips, paddingMs, dsp, regionEditsByClip }),
    [clips, paddingMs, dsp, regionEditsByClip],
  )
  const planHash = useMemo(() => hashStitchPlan(plan), [plan])

  const a = useStitchABStore((s) => s.a)
  const b = useStitchABStore((s) => s.b)
  const active = useStitchABStore((s) => s.active)
  const capture = useStitchABStore((s) => s.capture)
  const activate = useStitchABStore((s) => s.activate)

  // An empty slot previews nothing; useStitchPreview clears rather than rendering for it.
  const emptyPlan = useMemo<StitchPlanState>(
    () => ({ clips: [], paddingMs: [], dsp, regionEditsByClip: {} }),
    [dsp],
  )
  const previewA = useStitchPreview(a?.plan ?? emptyPlan)
  const previewB = useStitchPreview(b?.plan ?? emptyPlan)
  const previewFor = { a: previewA, b: previewB }

  // Each snapshot audition is one audio source in the transport coordinator (T1).
  const source = useAudioSource('ab-snapshot', 'A/B snapshot')
  const audioARef = useRef<HTMLAudioElement | null>(null)
  const audioBRef = useRef<HTMLAudioElement | null>(null)
  const [playingSlot, setPlayingSlot] = useState<Slot | null>(null)

  const stopAudition = useCallback(() => {
    audioARef.current?.pause()
    audioBRef.current?.pause()
    setPlayingSlot(null)
    source.release()
  }, [source])
  // The registry keeps this callback: it must reach the current render's state.
  const stopRef = useRef(stopAudition)
  stopRef.current = stopAudition

  const audition = (slot: Slot) => {
    const element = slot === 'a' ? audioARef.current : audioBRef.current
    if (!element || !previewFor[slot].url) return
    if (playingSlot === slot) {
      stopAudition()
      return
    }
    stopAudition()
    source.claim(() => stopRef.current())
    element.currentTime = 0
    void element.play().catch(() => {})
  }

  useEffect(() => () => stopRef.current(), [])

  return (
    <div
      data-testid="stitch-ab-bar"
      className="flex flex-wrap items-center gap-2 rounded-lg border border-border/60 bg-muted/20 px-3 py-2"
    >
      <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground/70">A/B snapshots</span>
      {(['a', 'b'] as Slot[]).map((slot) => {
        const snapshot = slot === 'a' ? a : b
        const preview = previewFor[slot]
        const isActive = active === slot
        const editedSince = isActive && !!snapshot && snapshot.hash !== planHash
        const upper = slot.toUpperCase()
        return (
          <div
            key={slot}
            className={cn(
              'flex items-center gap-1 rounded border px-1.5 py-1',
              isActive ? 'border-cyan-500/50 bg-cyan-500/10' : 'border-border/60',
            )}
          >
            <button
              type="button"
              data-testid={`stitch-ab-slot-${slot}`}
              data-active={isActive}
              disabled={!snapshot}
              onClick={() => activate(slot)}
              title={snapshot ? `Switch the plan to snapshot ${upper}` : `Nothing captured in ${upper} yet`}
              className="inline-flex items-center gap-1.5 rounded px-1 py-0.5 text-[11px] font-medium text-foreground hover:bg-muted disabled:opacity-40 disabled:hover:bg-transparent"
            >
              <span className="font-mono uppercase">{slot}</span>
              {isActive && (
                <span className="rounded bg-cyan-500/20 px-1 text-[9px] uppercase tracking-wide text-cyan-200">
                  {editedSince ? 'active · edited' : 'active'}
                </span>
              )}
            </button>
            <button
              type="button"
              data-testid={`stitch-ab-capture-${slot}`}
              disabled={!clips.length}
              onClick={() => capture(slot, plan)}
              title={`Capture the current plan as ${upper}`}
              className="rounded px-1 py-0.5 text-[10px] text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40 disabled:hover:bg-transparent"
            >
              {snapshot ? `Re-capture ${upper}` : `Capture ${upper}`}
            </button>
            <button
              type="button"
              data-testid={`stitch-ab-audition-${slot}`}
              disabled={!preview.url}
              onClick={() => audition(slot)}
              aria-label={playingSlot === slot ? `Pause snapshot ${upper}` : `Audition snapshot ${upper}`}
              title={preview.url ? `Audition snapshot ${upper}` : `Waiting for the ${upper} preview to render`}
              className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40 disabled:hover:bg-transparent"
            >
              {playingSlot === slot ? <Pause className="size-3" /> : <Play className="size-3" />}
            </button>
            <audio
              ref={slot === 'a' ? audioARef : audioBRef}
              src={preview.url ?? undefined}
              preload="auto"
              data-testid={`stitch-ab-audio-${slot}`}
              onPlay={() => setPlayingSlot(slot)}
              onTimeUpdate={(event) =>
                source.report(event.currentTarget.currentTime, event.currentTarget.duration)
              }
              onPause={() => setPlayingSlot((current) => (current === slot ? null : current))}
              onEnded={() => {
                setPlayingSlot(null)
                source.release()
              }}
            />
          </div>
        )
      })}
    </div>
  )
}

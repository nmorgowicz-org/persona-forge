// The app's one audio transport coordinator (plan A / T1, growing N6's playback-focus
// registry).
//
// Every surface that can make sound registers itself here: a stable `kind`
// (`stitch-arrangement`), a human label, and the callback that silences it. The coordinator
// arbitrates -- one audible source at a time -- and publishes *who* is audible and *where*
// it is, so "one sound at a time" and the transport readout are two views of one fact
// instead of two mechanisms that can disagree.
//
// It deliberately owns no audio element and no clock. Each surface keeps its own element,
// its own transport logic, and its own playback contract: the arrangement wraps a loop
// brace, the compare lanes carry a drag-selection, the deck loops a region. A surface
// *reports* its position from the tick it already runs and the coordinator never drives it.
// That is the difference between coordinating and taking over, and it is why this landed
// without changing a single playback behavior.
//
// Position is reported per animation frame, so nothing here may allocate or re-render per
// frame: the snapshot object is reused, and consumers write straight to the DOM.

export interface AudioSource {
  /** Unique per registration: `audio-deck`, then `audio-deck#2`. Never reused, so a stale
   * claim can't alias a live one. */
  readonly id: string
  /** The surface kind, stable across instances: `audio-deck`. */
  readonly kind: string
  /** Human-readable name for the readout. */
  readonly label: string
  /** Take playback focus, pausing whoever held it. `pause` must stay safe to call at any
   * time, including after the owning element has been detached from the document: that is
   * exactly how a player that unmounted mid-playback gets silenced (a detached media element
   * keeps sounding). */
  claim(pause: () => void): void
  /** Give up playback focus. Only the current holder can release it, so a player that
   * someone else already stopped cannot release the claim that replaced it. The last
   * reported position stays readable -- a stopped transport still shows where it stopped. */
  release(): void
  /** Publish this source's position and duration. Ignored unless this source is the active
   * one, so a paused surface cannot move the readout after it lost focus. */
  report(positionSec: number, durationSec?: number | null): void
  /** Unregister on unmount: drop the source, and its claim with it. */
  dispose(): void
}

export interface TransportState {
  /** Registered source ids, in registration order. */
  readonly sources: string[]
  readonly activeId: string | null
  readonly activeKind: string | null
  readonly activeLabel: string | null
  readonly positionSec: number | null
  readonly durationSec: number | null
}

type Listener = (state: TransportState) => void

interface Entry {
  kind: string
  label: string
}

interface Claimant extends Entry {
  id: string
  pause: () => void
}

const entries = new Map<string, Entry>()
/** Instances seen per kind, only ever incremented: ids are never reused. */
const instances = new Map<string, number>()
const listeners = new Set<Listener>()

let active: Claimant | null = null
let positionSec: number | null = null
let durationSec: number | null = null
let registeredIds: string[] = []

/** Reused by every notification: read it, don't keep it. */
const snapshot: TransportState & {
  sources: string[]
  activeId: string | null
  activeKind: string | null
  activeLabel: string | null
  positionSec: number | null
  durationSec: number | null
} = {
  sources: registeredIds,
  activeId: null,
  activeKind: null,
  activeLabel: null,
  positionSec: null,
  durationSec: null,
}

function notify(): void {
  snapshot.sources = registeredIds
  snapshot.activeId = active?.id ?? null
  snapshot.activeKind = active?.kind ?? null
  snapshot.activeLabel = active?.label ?? null
  snapshot.positionSec = positionSec
  snapshot.durationSec = durationSec
  for (const listener of listeners) listener(snapshot)
}

function claim(id: string, pause: () => void): void {
  if (active?.id === id) return
  const entry = entries.get(id)
  const previous = active
  // Install the new claimant BEFORE pausing the previous one: the previous owner's pause
  // handler releases its own id, which must not clear the claim that just replaced it.
  active = { id, kind: entry?.kind ?? id, label: entry?.label ?? id, pause }
  notify()
  previous?.pause()
}

function release(id: string): void {
  if (active?.id !== id) return
  active = null
  notify()
}

function report(id: string, nextPositionSec: number, nextDurationSec?: number | null): void {
  if (active?.id !== id) return
  positionSec = nextPositionSec
  if (nextDurationSec != null) durationSec = nextDurationSec
  notify()
}

/** Register a surface as an audio source. Call once per mounted surface (see
 * `useAudioSource`); `dispose()` it on unmount. */
export function registerSource(kind: string, label: string): AudioSource {
  const count = (instances.get(kind) ?? 0) + 1
  instances.set(kind, count)
  const id = count === 1 ? kind : `${kind}#${count}`
  entries.set(id, { kind, label })
  registeredIds = [...registeredIds, id]
  notify()
  return {
    id,
    kind,
    label,
    claim: (pause) => claim(id, pause),
    release: () => release(id),
    report: (nextPositionSec, nextDurationSec) => report(id, nextPositionSec, nextDurationSec),
    dispose: () => {
      entries.delete(id)
      registeredIds = registeredIds.filter((registered) => registered !== id)
      // A source that unmounts mid-playback must not stay the active one: its element is
      // detached, so nothing would ever report a new position for it.
      if (active?.id === id) {
        const pause = active.pause
        active = null
        pause()
      }
      notify()
    },
  }
}

/** The current transport state. The returned object is reused across notifications. */
export function getTransportState(): TransportState {
  return snapshot
}

/** Subscribe to coordinator updates. Returns an unsubscribe function. */
export function subscribeTransport(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

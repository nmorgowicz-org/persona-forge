// One sound at a time (plan A / N6).
//
// Every component that can start audio claims playback focus when it starts and releases it
// when it stops. Claiming pauses whoever held focus, so starting any player silences the
// previous one -- what a DAW or a plugin host does when you audition something new.
//
// Deliberately the smallest possible registry: no shared element, no shared position, no
// transport state. Its only job is "who is allowed to be audible right now". The accepted T1
// phase (shared audio transport coordinator) grows this registry into the full coordinator
// rather than replacing it.
//
// A component whose several elements are *meant* to sound together -- the prosody A/B
// compare, the stitch transport's arrangement/clip-range modes -- claims once for the group.

interface Claimant {
  id: string
  pause: () => void
}

let current: Claimant | null = null

/** Take playback focus, pausing whoever held it. `pause` must stay safe to call at any time,
 * including after the owning element has been detached from the document: that is exactly how
 * a player that unmounted mid-playback gets silenced (a detached media element keeps
 * sounding). */
export function claimPlayback(id: string, pause: () => void): void {
  if (current?.id === id) return
  const previous = current
  // Install the new claimant BEFORE pausing the previous one: the previous owner's pause
  // handler releases its own id, which must not clear the claim that just replaced it.
  current = { id, pause }
  previous?.pause()
}

/** Give up playback focus. Only the current holder can release it, so a player that someone
 * else already stopped cannot release the claim that replaced it. */
export function releasePlayback(id: string): void {
  if (current?.id === id) current = null
}

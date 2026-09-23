// One shortcut/command registry for the whole app (M4). A surface registers a *scope* -- a
// title plus the commands it offers -- and the Cmd/Ctrl+K palette and the `?` keymap both read
// that same registry, so a binding can never be documented in one place and dispatched from
// another. Moving a page's keymap here is what makes it visible in the keymap for free.
//
// Registration is by mount: a scope exists exactly while its surface is mounted, so the keymap
// describes the page you are actually looking at. Dispatch is innermost-first (the most
// recently registered scope wins), which is how a page shadows a global binding.
//
// The one rule every binding shares: an event whose target is an editable control is never
// dispatched. Typing a space in a name field is a space, not a play/pause. A command can opt
// out of that (the palette's own Cmd/Ctrl+K should work while typing) but nothing else does --
// in particular Cmd/Ctrl+Z in a text field stays the browser's undo.
import { useEffect, useMemo, useSyncExternalStore } from 'react'

export interface ShortcutCommand {
  /** Stable id; also the palette's `data-command-id`. */
  id: string
  /** Palette label and the keymap row's description. */
  label: string
  /** Display form of the binding, e.g. 'Space' or 'Cmd/Ctrl+K'. A row that documents a mouse
   * gesture ('Click ruler') carries one and omits `match`. */
  keys?: string
  /** Secondary line in the palette. */
  hint?: string
  /** Runs the command. Key-driven commands receive the event that matched (a directional
   * binding needs to know which arrow fired); the palette calls them with none. */
  run?: (event?: KeyboardEvent) => void
  /** False for a binding that only makes sense as a key (a direction, a gesture): it is still
   * documented in the keymap, but does not appear in the palette. */
  palette?: boolean
  /** Whether this key event triggers the command. */
  match?: (event: KeyboardEvent) => boolean
  /** Fire even when the event target is an editable control. Only for modifier chords that
   * have no meaning inside a field. */
  allowInEditable?: boolean
}

export interface ShortcutScope {
  id: string
  title: string
  commands: ShortcutCommand[]
  /** Dispatch gate for a scope whose bindings only apply in part of the page (a focused
   * region). Registered scopes are always *listed*; this only decides whether they fire. */
  when?: () => boolean
}

/** True for anything that owns its own keystrokes. */
export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable
}

/** True when the platform's primary modifier is held (Cmd on macOS, Ctrl elsewhere). */
export function isPrimaryModifier(event: KeyboardEvent): boolean {
  return event.metaKey || event.ctrlKey
}

const registrations = new Map<string, { scope: ShortcutScope; token: symbol }>()
const listeners = new Set<() => void>()
let version = 0
let cached: ShortcutScope[] = []
let cachedVersion = -1

function emit(): void {
  version += 1
  for (const listener of listeners) listener()
}

export function registerShortcutScope(scope: ShortcutScope): () => void {
  const token = Symbol(scope.id)
  registrations.set(scope.id, { scope, token })
  emit()
  return () => {
    // Only the registration that is still current may remove it: two surfaces can share a
    // scope id (the studio timeline and the quick-insert timeline), and the unmount of the
    // older one must not delete the newer one's registration.
    if (registrations.get(scope.id)?.token === token) {
      registrations.delete(scope.id)
      emit()
    }
  }
}

export function getShortcutScopes(): ShortcutScope[] {
  if (cachedVersion !== version) {
    cached = [...registrations.values()].map((entry) => entry.scope)
    cachedVersion = version
  }
  return cached
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Every registered scope, in registration order (app first, then the mounted page). */
export function useShortcutScopes(): ShortcutScope[] {
  return useSyncExternalStore(subscribe, getShortcutScopes, getShortcutScopes)
}

/** Registers a scope for as long as the calling component is mounted. `commands` and `when`
 * must be memoized by the caller: a new identity re-registers. */
export function useShortcutScope(id: string, title: string, commands: ShortcutCommand[], when?: () => boolean): void {
  const scope = useMemo(() => ({ id, title, commands, when }), [id, title, commands, when])
  useEffect(() => registerShortcutScope(scope), [scope])
}

/* ---------- overlay state ---------- */

// Module state, not component state: the dispatcher opens these surfaces from a keydown, and
// any surface (the timeline's own Shortcuts button) can open them without prop drilling.
interface OverlayState {
  palette: boolean
  keymap: boolean
}

let overlays: OverlayState = { palette: false, keymap: false }
const overlayListeners = new Set<() => void>()

function setOverlays(patch: Partial<OverlayState>): void {
  overlays = { ...overlays, ...patch }
  for (const listener of overlayListeners) listener()
}

export function openCommandPalette(): void {
  setOverlays({ palette: true, keymap: false })
}

export function openShortcutKeymap(): void {
  setOverlays({ keymap: true, palette: false })
}

export function setCommandPaletteOpen(open: boolean): void {
  setOverlays({ palette: open })
}

export function setShortcutKeymapOpen(open: boolean): void {
  setOverlays({ keymap: open })
}

export function isShortcutKeymapOpen(): boolean {
  return overlays.keymap
}

function subscribeOverlays(listener: () => void): () => void {
  overlayListeners.add(listener)
  return () => {
    overlayListeners.delete(listener)
  }
}

function getOverlays(): OverlayState {
  return overlays
}

export function useShortcutOverlays(): OverlayState {
  return useSyncExternalStore(subscribeOverlays, getOverlays, getOverlays)
}

/* ---------- dispatch ---------- */

function dispatch(event: KeyboardEvent): void {
  const editable = isEditableTarget(event.target)
  // Innermost first: the page that registered last gets the first chance at the key.
  const scopes = [...registrations.values()].map((entry) => entry.scope).reverse()
  for (const scope of scopes) {
    if (scope.when && !scope.when()) continue
    for (const command of scope.commands) {
      if (!command.match || !command.run) continue
      if (editable && !command.allowInEditable) continue
      if (!command.match(event)) continue
      event.preventDefault()
      command.run(event)
      return
    }
  }
}

let installed = false

function install(): void {
  if (installed) return
  installed = true
  window.addEventListener('keydown', dispatch)
}

install()

// The two surfaces that read the shared shortcut registry (M4): the Cmd/Ctrl+K command palette
// and the `?` keymap. Both are driven entirely by hooks/useGlobalShortcuts, so a page's keys
// appear here the moment the page mounts -- there is no second list to keep in sync.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import {
  setCommandPaletteOpen,
  setShortcutKeymapOpen,
  useShortcutOverlays,
  useShortcutScopes,
  type ShortcutCommand,
} from '@/hooks/useGlobalShortcuts'
import { cn } from '@/lib/utils'

interface PaletteEntry {
  command: ShortcutCommand
  scopeTitle: string
}

function flatten(scopes: ReturnType<typeof useShortcutScopes>): PaletteEntry[] {
  const entries: PaletteEntry[] = []
  for (const scope of scopes) {
    for (const command of scope.commands) {
      if (!command.run || command.palette === false) continue
      entries.push({ command, scopeTitle: scope.title })
    }
  }
  return entries
}

export function CommandPalette() {
  const { palette } = useShortcutOverlays()
  const scopes = useShortcutScopes()
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const entries = useMemo(() => flatten(scopes), [scopes])
  const results = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return entries
    return entries.filter(({ command }) => `${command.label} ${command.hint ?? ''}`.toLowerCase().includes(needle))
  }, [entries, query])

  // A fresh query starts at the top of the new result list.
  useEffect(() => setActiveIndex(0), [query])
  useEffect(() => {
    if (palette) {
      setQuery('')
      setActiveIndex(0)
    }
  }, [palette])

  const runEntry = useCallback((entry: PaletteEntry | undefined) => {
    if (!entry) return
    setCommandPaletteOpen(false)
    entry.command.run?.()
  }, [])

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((index) => (results.length ? (index + 1) % results.length : 0))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((index) => (results.length ? (index - 1 + results.length) % results.length : 0))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      runEntry(results[activeIndex])
    }
  }

  return (
    <Dialog open={palette} onOpenChange={setCommandPaletteOpen}>
      <DialogContent data-testid="command-palette" className="max-w-lg gap-0 overflow-hidden p-0">
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <DialogDescription className="sr-only">Search for a command and run it</DialogDescription>
        <div className="flex items-center gap-2 border-b border-border/70 px-3">
          <Search className="size-3.5 shrink-0 text-muted-foreground" />
          <input
            ref={inputRef}
            data-testid="command-palette-input"
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
            onKeyDown={onKeyDown}
            placeholder="Search commands…"
            aria-label="Search commands"
            autoFocus
            className="h-11 w-full min-w-0 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground/60"
          />
        </div>
        <div role="listbox" aria-label="Commands" className="max-h-72 overflow-y-auto p-1">
          {results.length === 0 && <p className="px-3 py-6 text-center text-xs text-muted-foreground">No matching command</p>}
          {results.map((entry, index) => (
            <button
              key={`${entry.scopeTitle}:${entry.command.id}`}
              type="button"
              role="option"
              aria-selected={index === activeIndex}
              data-testid="command-item"
              data-command-id={entry.command.id}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => runEntry(entry)}
              className={cn(
                'flex w-full items-center gap-3 rounded px-2.5 py-1.5 text-left text-xs',
                index === activeIndex ? 'bg-muted text-foreground' : 'text-muted-foreground',
              )}
            >
              <span className="min-w-0 flex-1 truncate">{entry.command.label}</span>
              {entry.command.hint && <span className="shrink-0 text-[10px] text-muted-foreground/70">{entry.command.hint}</span>}
              {entry.command.keys && (
                <kbd className="shrink-0 rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-foreground">
                  {entry.command.keys}
                </kbd>
              )}
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** The `?` surface: every registered scope's documented bindings, grouped by surface. */
export function ShortcutKeymap() {
  const { keymap } = useShortcutOverlays()
  const scopes = useShortcutScopes()

  return (
    <Dialog open={keymap} onOpenChange={setShortcutKeymapOpen}>
      <DialogContent data-testid="shortcut-keymap" className="max-w-lg">
        <DialogTitle>Keyboard shortcuts</DialogTitle>
        <DialogDescription className="sr-only">Keyboard shortcuts for the current page</DialogDescription>
        <div className="flex max-h-[60vh] flex-col gap-4 overflow-y-auto">
          {scopes.map((scope) => {
            const rows = scope.commands.filter((command) => command.keys)
            if (rows.length === 0) return null
            return (
              <section key={scope.id} className="flex flex-col gap-2">
                <h3 className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground/70">{scope.title}</h3>
                <dl className="flex flex-col gap-1.5">
                  {rows.map((command) => (
                    <div
                      key={command.id}
                      data-testid="shortcut-row"
                      data-keys={command.keys}
                      className="flex items-start justify-between gap-4"
                    >
                      <dt className="shrink-0 rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground">
                        {command.keys}
                      </dt>
                      <dd className="text-right text-xs text-muted-foreground">{command.label}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            )
          })}
        </div>
      </DialogContent>
    </Dialog>
  )
}

import { useEffect, useState } from 'react'
import {
  CheckCircle2,
  CircleSlash,
  Download,
  HardDrive,
  Loader2,
  RefreshCw,
  Trash2,
} from 'lucide-react'
import {
  installEngine,
  listEngines,
  removeEngine,
  verifyEngine,
  type EngineCard,
  type EngineState,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

const STATUS_LABEL: Record<EngineState['status'], string> = {
  'built-in': 'Built in',
  'not-installed': 'Not installed',
  installed: 'Installed',
  verified: 'Verified',
  invalid: 'Invalid',
}

function formatBytes(value: number): string {
  if (value <= 0) return '0 MB'
  const mib = value / (1024 * 1024)
  return mib >= 1024 ? `${(mib / 1024).toFixed(1)} GB` : `${mib.toFixed(0)} MB`
}

function statusVariant(status: EngineState['status']) {
  if (status === 'invalid') return 'destructive' as const
  if (status === 'not-installed') return 'outline' as const
  if (status === 'installed') return 'secondary' as const
  return 'default' as const
}

export function SpeechEnginesCard() {
  const [engines, setEngines] = useState<EngineCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pendingAction, setPendingAction] = useState<{
    id: string
    action: 'verify' | 'install' | 'remove'
  } | null>(null)

  useEffect(() => {
    let cancelled = false
    listEngines()
      .then((cards) => {
        if (!cancelled) setEngines(cards)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(String((err as Error)?.message || err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function verify(engineId: string) {
    setPendingAction({ id: engineId, action: 'verify' })
    setError(null)
    try {
      const refreshed = await verifyEngine(engineId)
      setEngines((current) =>
        current.map((engine) => (engine.id === refreshed.id ? refreshed : engine)),
      )
    } catch (err) {
      setError(String((err as Error)?.message || err))
    } finally {
      setPendingAction(null)
    }
  }

  async function install(engineId: string) {
    setPendingAction({ id: engineId, action: 'install' })
    setError(null)
    try {
      const refreshed = await installEngine(engineId)
      setEngines((current) =>
        current.map((engine) => (engine.id === refreshed.id ? refreshed : engine)),
      )
    } catch (err) {
      setError(String((err as Error)?.message || err))
    } finally {
      setPendingAction(null)
    }
  }

  async function remove(engineId: string) {
    setPendingAction({ id: engineId, action: 'remove' })
    setError(null)
    try {
      await removeEngine(engineId)
      setEngines((current) => current.filter((engine) => engine.id !== engineId))
    } catch (err) {
      setError(String((err as Error)?.message || err))
    } finally {
      setPendingAction(null)
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-panel border border-border bg-card p-5 text-card-foreground shadow-sm">
      <div className="flex items-center gap-2">
        <HardDrive className="size-4 text-primary" />
        <p className="text-sm font-semibold">Speech engines</p>
      </div>
      <p className="text-xs text-muted-foreground">
        One active engine serves the API. Packs are verified locally against their pinned
        hashes before use; installing additional engines arrives with the pack installer.
      </p>

      {error && (
        <p className="rounded-control border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </p>
      )}

      {loading ? (
        <p className="text-xs text-muted-foreground">Loading engines…</p>
      ) : (
        <div className="flex flex-col divide-y divide-border">
          {engines.map((engine) => (
            <div key={engine.id} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{engine.label}</span>
                <code className="font-mono text-[10px] text-muted-foreground">{engine.id}</code>
                {engine.active && <Badge className="text-[10px]">active</Badge>}
                <Badge variant="outline" className="text-[10px]">
                  {engine.kind === 'builtin' ? 'built in' : engine.kind === 'pack' ? 'pack' : 'built in + pack'}
                </Badge>
                <Badge variant={statusVariant(engine.state.status)} className="text-[10px]">
                  {STATUS_LABEL[engine.state.status]}
                </Badge>
                {engine.version && (
                  <Badge variant="outline" className="text-[10px]">
                    v{engine.version}
                  </Badge>
                )}
              </div>

              {engine.description && (
                <p className="text-xs text-muted-foreground">{engine.description}</p>
              )}

              <div className="flex flex-wrap items-center gap-1.5">
                {engine.capabilities.clone && (
                  <Badge variant="outline" className="text-[10px]">
                    cloning
                  </Badge>
                )}
                {engine.capabilities.presets && (
                  <Badge variant="outline" className="text-[10px]">
                    built-in voices
                  </Badge>
                )}
                {engine.capabilities.streaming && (
                  <Badge variant="outline" className="text-[10px]">
                    streaming: {engine.capabilities.streaming}
                  </Badge>
                )}
                {engine.capabilities.languages && engine.capabilities.languages.length > 0 && (
                  <Badge variant="outline" className="text-[10px]">
                    {engine.capabilities.languages.length} languages
                  </Badge>
                )}
                <Badge variant="outline" className="text-[10px]">
                  {engine.runtime}
                </Badge>
              </div>

              <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
                {engine.state.artifacts_total > 0 && (
                  <span className="inline-flex items-center gap-1">
                    <CheckCircle2 className="size-3" />
                    {engine.state.artifacts_present}/{engine.state.artifacts_total} artifacts
                  </span>
                )}
                {engine.state.disk_bytes > 0 && <span>{formatBytes(engine.state.disk_bytes)}</span>}
                {engine.kind !== 'builtin' && (
                  <>
                    {engine.state.status !== 'verified' && (
                      <Button
                        type="button"
                        size="xs"
                        variant="outline"
                        disabled={pendingAction !== null}
                        onClick={() => void install(engine.id)}
                      >
                        {pendingAction?.id === engine.id &&
                        pendingAction.action === 'install' ? (
                          <Loader2 className="animate-spin" />
                        ) : (
                          <Download />
                        )}
                        {engine.state.status === 'not-installed' ? 'Install' : 'Repair'}
                      </Button>
                    )}
                    <Button
                      type="button"
                      size="xs"
                      variant="outline"
                      disabled={pendingAction !== null}
                      onClick={() => void verify(engine.id)}
                    >
                      {pendingAction?.id === engine.id &&
                      pendingAction.action === 'verify' ? (
                        <Loader2 className="animate-spin" />
                      ) : (
                        <RefreshCw />
                      )}
                      Verify hashes
                    </Button>
                    <Button
                      type="button"
                      size="xs"
                      variant="ghost"
                      disabled={engine.active || pendingAction !== null}
                      title={
                        engine.active
                          ? 'Switch to another engine before removing this one'
                          : undefined
                      }
                      onClick={() => void remove(engine.id)}
                    >
                      {pendingAction?.id === engine.id &&
                      pendingAction.action === 'remove' ? (
                        <Loader2 className="animate-spin" />
                      ) : (
                        <Trash2 />
                      )}
                      Remove
                    </Button>
                  </>
                )}
              </div>

              {engine.state.errors.length > 0 && (
                <ul className="flex flex-col gap-1 rounded-control border border-destructive/30 bg-destructive/5 px-3 py-2 text-[11px] text-destructive">
                  {engine.state.errors.map((message) => (
                    <li key={message} className="inline-flex items-center gap-1">
                      <CircleSlash className="size-3 shrink-0" />
                      {message}
                    </li>
                  ))}
                </ul>
              )}

              {engine.pack && engine.pack.artifacts.length > 0 && (
                <details className="text-[11px] text-muted-foreground">
                  <summary className={cn('cursor-pointer select-none hover:text-foreground')}>
                    Pinned artifacts ({engine.pack.artifacts.length})
                  </summary>
                  <ul className="mt-1 flex flex-col gap-1 pl-4">
                    {engine.pack.artifacts.map((artifact) => (
                      <li key={artifact.path} className="font-mono text-[10px]">
                        {artifact.path} · {formatBytes(artifact.size)} · {artifact.sha256.slice(0, 12)}…
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

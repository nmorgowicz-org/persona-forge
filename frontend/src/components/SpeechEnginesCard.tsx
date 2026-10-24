import { useEffect, useState } from 'react'
import {
  CheckCircle2,
  CircleSlash,
  Download,
  ExternalLink,
  HardDrive,
  Zap,
  Loader2,
  RefreshCw,
  Trash2,
} from 'lucide-react'
import {
  installEngine,
  listEngines,
  recheckEngine,
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
    action: 'verify' | 'install' | 'remove' | 'recheck'
  } | null>(null)

  const busy = engines.some(
    (engine) => engine.install_job?.state === 'running' || engine.load_status?.state === 'loading',
  )

  // Installs and re-checks run in the background; refresh the cards until they settle.
  useEffect(() => {
    if (!busy) return
    const timer = window.setInterval(() => {
      listEngines()
        .then(setEngines)
        .catch(() => undefined)
    }, 2000)
    return () => window.clearInterval(timer)
  }, [busy])

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
      if (refreshed) {
        setEngines((current) =>
          current.map((engine) => (engine.id === refreshed.id ? refreshed : engine)),
        )
      } else {
        setEngines(await listEngines())
      }
    } catch (err) {
      setError(String((err as Error)?.message || err))
    } finally {
      setPendingAction(null)
    }
  }

  async function recheck(engineId: string) {
    setPendingAction({ id: engineId, action: 'recheck' })
    setError(null)
    try {
      await recheckEngine(engineId)
      setEngines(await listEngines())
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
        hashes before use. Installing an engine downloads it once; it then runs offline.
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
                        disabled={pendingAction !== null || engine.install_job?.state === 'running'}
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
                      disabled={
                        engine.active ||
                        pendingAction !== null ||
                        engine.install_job?.state === 'running'
                      }
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

              {engine.install_job?.state === 'running' && (
                <div className="flex flex-col gap-1" role="status">
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full bg-primary transition-all"
                      style={{
                        width: `${Math.round(
                          (engine.install_job.step_index / Math.max(engine.install_job.step_count, 1)) * 100,
                        )}%`,
                      }}
                    />
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    Step {engine.install_job.step_index} of {engine.install_job.step_count}:{' '}
                    {engine.install_job.step}. This can take several minutes the first time.
                  </p>
                </div>
              )}

              {engine.install_job?.state === 'error' && engine.install_job.error && (
                <p className="rounded-control border border-destructive/30 bg-destructive/5 px-3 py-2 text-[11px] text-destructive">
                  Install failed: {engine.install_job.error} Choose Repair to try again.
                </p>
              )}

              {engine.load_status?.mode && engine.state.status === 'verified' && (
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                  <Zap className="size-3" />
                  {engine.load_status.mode === 'eager'
                    ? 'Running in standard mode (slower than real time).'
                    : engine.load_status.mode === 'compiled'
                      ? 'Running in fast mode.'
                      : 'Running on Apple silicon.'}
                </div>
              )}

              {engine.load_status?.state === 'error' && engine.load_status.error && (
                <p className="rounded-control border border-destructive/30 bg-destructive/5 px-3 py-2 text-[11px] text-destructive">
                  {engine.load_status.error}
                </p>
              )}

              {engine.load_status?.fast_mode_issue && (
                <div className="flex flex-col gap-1.5 rounded-control border border-border bg-muted/40 px-3 py-2 text-[11px]">
                  <p>{engine.load_status.fast_mode_issue.message}</p>
                  <p className="text-muted-foreground">{engine.load_status.fast_mode_issue.action}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    {engine.load_status.fast_mode_issue.help_url && (
                      <a
                        href={engine.load_status.fast_mode_issue.help_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline"
                      >
                        <ExternalLink className="size-3" />
                        Get the tools
                      </a>
                    )}
                    <Button
                      type="button"
                      size="xs"
                      variant="outline"
                      disabled={pendingAction !== null || engine.load_status.state === 'loading'}
                      onClick={() => void recheck(engine.id)}
                    >
                      {engine.load_status.state === 'loading' ||
                      (pendingAction?.id === engine.id && pendingAction.action === 'recheck') ? (
                        <Loader2 className="animate-spin" />
                      ) : (
                        <RefreshCw />
                      )}
                      Re-check
                    </Button>
                  </div>
                  {engine.load_status.fast_mode_issue.detail && (
                    <details className="text-muted-foreground">
                      <summary className="cursor-pointer select-none">Technical details</summary>
                      <code className="font-mono text-[10px]">
                        {engine.load_status.fast_mode_issue.detail}
                      </code>
                    </details>
                  )}
                </div>
              )}

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

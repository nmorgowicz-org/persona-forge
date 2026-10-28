import { loadCompareSummary, type EngineSummary } from '@/lib/compareResults'
import { engineLoadNote, isEngineBusy } from '@/lib/engineStatus'
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
  benchmarkEngine,
  installEngine,
  listEngines,
  recheckEngine,
  removeEngine,
  verifyEngine,
  type EngineCard,
  type EngineInstallCheck,
  type EngineState,
} from '@/lib/api'
import { getPref, setPref } from '@/lib/uiPreferences'
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

/** "Install check: RTF 0.18 on mps", or the slower-than-real-time warning, or why it was not measured. */
function installCheckText(check: EngineInstallCheck): string {
  if (check.outcome === 'unavailable') {
    return `Install check: speed could not be measured${check.error ? ` (${check.error})` : ''}`
  }
  const rtf = check.rtf !== null ? `RTF ${check.rtf.toFixed(2)}` : 'RTF unknown'
  const where = check.device
    ? ` on ${check.device}${check.mode && check.mode !== check.device ? ` (${check.mode})` : ''}`
    : ''
  const load = check.load_average !== null ? `, load ${check.load_average}` : ''
  return check.outcome === 'slow'
    ? `Install check: runs slower than real time on this machine (${rtf}${where}${load})`
    : `Install check: ${rtf}${where}${load}`
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
    action: 'verify' | 'install' | 'remove' | 'recheck' | 'benchmark'
  } | null>(null)

  const [language, setLanguage] = useState<'en' | 'all'>(() =>
    getPref<'en' | 'all'>('voiceCatalog.language', 'en'),
  )

  function changeLanguage(next: 'en' | 'all') {
    setLanguage(next)
    setPref('voiceCatalog.language', next)
  }

  const busy = engines.some(
    (engine) => engine.install_job?.state === 'running' || isEngineBusy(engine.load_status),
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

  const [ratings, setRatings] = useState<Record<string, EngineSummary>>({})
  useEffect(() => {
    loadCompareSummary()
      .then((saved) => setRatings(Object.fromEntries(saved.summary.map((row) => [row.engine, row]))))
      .catch(() => undefined)
  }, [])

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

  async function benchmark(engineId: string) {
    setPendingAction({ id: engineId, action: 'benchmark' })
    setError(null)
    try {
      const result = await benchmarkEngine(engineId)
      setEngines((current) =>
        current.map((engine) => (engine.id === engineId ? { ...engine, benchmark: result } : engine)),
      )
    } catch (err) {
      setError(`Benchmark failed: ${String((err as Error)?.message || err)}`)
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

      <label className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-medium">Voice languages</span>
        <select
          className="rounded-control border border-border bg-background px-2 py-1 text-xs"
          value={language}
          onChange={(event) => changeLanguage(event.target.value === 'all' ? 'all' : 'en')}
        >
          <option value="en">English only</option>
          <option value="all">All languages</option>
        </select>
        <span className="text-muted-foreground">
          Hides other languages from voice lists. Requests can still name any voice.
        </span>
      </label>

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
                {engine.api_default && (
                  <Badge variant="secondary" className="text-[10px]" data-testid="engine-api-default-badge">
                    API default
                  </Badge>
                )}
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
                    {engine.capabilities.languages.length}{' '}
                    {engine.capabilities.languages.length === 1 ? 'language' : 'languages'}
                  </Badge>
                )}
                <Badge variant="outline" className="text-[10px]">
                  {engine.runtime}
                </Badge>
                {engine.hardware_fit && (
                  <Badge
                    variant={engine.hardware_fit.level === 'recommended' ? 'secondary' : 'outline'}
                    className={cn('text-[10px]', engine.hardware_fit.level === 'unsupported' && 'text-destructive')}
                    data-testid={`engine-fit-${engine.id}`}
                  >
                    {engine.hardware_fit.text}
                  </Badge>
                )}
                {ratings[engine.id] && (
                  <Badge variant="outline" className="text-[10px]" data-testid={`engine-ratings-${engine.id}`}>
                    Your ratings: {ratings[engine.id].natural.toFixed(1)} natural,{' '}
                    {ratings[engine.id].clean.toFixed(1)} clean ({ratings[engine.id].clips})
                  </Badge>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
                {engine.state.artifacts_total > 0 && (
                  <span className="inline-flex items-center gap-1">
                    <CheckCircle2 className="size-3" />
                    {engine.state.artifacts_present}/{engine.state.artifacts_total} artifacts
                  </span>
                )}
                {engine.state.disk_bytes > 0 && <span>{formatBytes(engine.state.disk_bytes)}</span>}
                {(engine.benchmark || !engine.install_check) && (
                  <span data-testid={`engine-benchmark-${engine.id}`}>
                    {engine.benchmark
                      ? `Measured here: ${engine.benchmark.rtf_median?.toFixed(2)} s per s of audio (worst ${engine.benchmark.rtf_worst?.toFixed(2)}), first request ${engine.benchmark.cold_seconds.toFixed(1)} s${engine.benchmark.load_average !== null ? `, load ${engine.benchmark.load_average}` : ''}`
                      : 'Speed not measured'}
                  </span>
                )}
                {engine.install_check && (
                  <span
                    data-testid={`engine-install-check-${engine.id}`}
                    data-outcome={engine.install_check.outcome}
                    title={engine.install_check.note ?? undefined}
                    className={cn(engine.install_check.outcome !== 'ok' && 'text-warning')}
                  >
                    {installCheckText(engine.install_check)}
                  </span>
                )}
                {engine.state.status !== 'not-installed' && (
                  <Button
                    type="button"
                    size="xs"
                    variant="outline"
                    disabled={pendingAction !== null}
                    onClick={() => void benchmark(engine.id)}
                  >
                    {pendingAction?.id === engine.id && pendingAction.action === 'benchmark' ? (
                      <Loader2 className="animate-spin" />
                    ) : (
                      <Zap />
                    )}
                    Run quick benchmark
                  </Button>
                )}
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
                        engine.api_default ||
                        pendingAction !== null ||
                        engine.install_job?.state === 'running'
                      }
                      title={
                        engine.active
                          ? 'Switch to another engine before removing this one'
                          : engine.api_default
                            ? 'This engine serves the API default. Change the API default first (Voices → Built-in, or Integrations).'
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

              {engine.api_default && (
                <p className="text-[11px] text-muted-foreground" data-testid="engine-api-default-note">
                  This engine serves the API default, so it can't be removed. Change the API default
                  first (Voices → Built-in, or Integrations).
                </p>
              )}

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
                  Install failed: {engine.install_job.error} Choose {engine.state.status === 'not-installed' ? 'Install' : 'Repair'} to try again.
                </p>
              )}

              {isEngineBusy(engine.load_status) && (
                <div
                  role="status"
                  data-testid={`engine-${engine.id}-${engine.load_status?.state}`}
                  className="flex items-center gap-2 rounded-control border border-border bg-muted/40 px-3 py-2 text-[11px]"
                >
                  <Loader2 className="size-3 shrink-0 animate-spin" />
                  {engineLoadNote(engine.label, engine.load_status)}
                </div>
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
                      disabled={pendingAction !== null || isEngineBusy(engine.load_status)}
                      onClick={() => void recheck(engine.id)}
                    >
                      {isEngineBusy(engine.load_status) ||
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

import { useCallback, useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import {
  getEngineDetails,
  type EngineDetails,
  type EngineLogTail,
  type HfTokenStatus,
} from '@/lib/api'
import { formatBytes, installCheckText } from '@/lib/engineFormat'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { HfTokenField } from '@/components/HfTokenField'

function idleText(details: EngineDetails): string {
  const { seconds, source } = details.idle_unload
  if (seconds === null) return 'not reported'
  const where = source ? ` (from ${source})` : ''
  if (seconds === 0) return `never unloads${where}`
  return seconds >= 120 ? `${Math.round(seconds / 60)} min idle${where}` : `${Math.round(seconds)} s idle${where}`
}

function Row({ label, children, testId }: { label: string; children: React.ReactNode; testId?: string }) {
  return (
    <div className="flex flex-wrap gap-x-2" data-testid={testId}>
      <dt className="w-32 shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 flex-1 break-words">{children}</dd>
    </div>
  )
}

function LogView({ title, tail, testId }: { title: string; tail: EngineLogTail; testId: string }) {
  const text = tail.lines.join('\n')
  return (
    <div className="flex flex-col gap-1" data-testid={testId}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{title}</span>
        <span className="text-muted-foreground">
          {tail.lines.length === 0
            ? 'nothing logged yet'
            : `last ${tail.lines.length} lines${tail.dropped ? ` (${tail.dropped} earlier dropped)` : ''}`}
          {tail.source === 'file' ? ', read from the saved install log' : ''}
        </span>
        {tail.lines.length > 0 && (
          <Button
            type="button"
            size="xs"
            variant="ghost"
            onClick={() => void navigator.clipboard?.writeText(text).catch(() => undefined)}
          >
            Copy
          </Button>
        )}
      </div>
      <pre
        role="log"
        aria-label={title}
        tabIndex={0}
        className={cn(
          'max-h-56 overflow-auto whitespace-pre-wrap break-all rounded-control border border-border bg-muted/40 p-2 font-mono text-[10px]',
          tail.lines.length === 0 && 'text-muted-foreground',
        )}
      >
        {text || '(empty)'}
      </pre>
    </div>
  )
}

/**
 * The "Details" expander for an engine card: manifest pins, what is really installed, runtime,
 * install check, idle unload, disk used, and the bounded, redacted install and worker logs.
 * Refreshes every 2 s while the engine is installing so the install log follows progress.
 */
export function EngineDetailsPanel({
  engineId,
  installing,
  showTokenField,
  onTokenChanged,
}: {
  engineId: string
  installing: boolean
  /** False while the card itself already shows the token field, so it is not drawn twice. */
  showTokenField: boolean
  onTokenChanged: (status: HfTokenStatus) => void
}) {
  const [details, setDetails] = useState<EngineDetails | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    getEngineDetails(engineId)
      .then((next) => {
        setDetails(next)
        setError(null)
      })
      .catch((err: unknown) => setError(String((err as Error)?.message || err)))
  }, [engineId])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!installing) return
    const timer = window.setInterval(load, 2000)
    return () => window.clearInterval(timer)
  }, [installing, load])

  if (error) {
    return <p className="text-[11px] text-destructive">Could not load details: {error}</p>
  }
  if (!details) {
    return (
      <p className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <Loader2 className="size-3 animate-spin" /> Loading details…
      </p>
    )
  }

  const { engine, runtime } = details
  return (
    <div
      className="flex flex-col gap-3 rounded-control border border-border bg-muted/20 p-3 text-[11px]"
      data-testid={`engine-details-${engineId}`}
    >
      <dl className="flex flex-col gap-1">
        <Row label="Pack" testId={`engine-details-pack-${engineId}`}>
          {engine.pack_id ? `${engine.pack_id} v${engine.pack_version}` : 'not installed'}
          {engine.revision ? `, revision ${engine.revision}` : ''}
          {engine.manifest_sha256 && (
            <span className="text-muted-foreground"> · manifest {engine.manifest_sha256.slice(0, 12)}…</span>
          )}
        </Row>
        <Row label="Runtime variant">{runtime.variant ?? 'unknown'}</Row>
        <Row label="Device / mode">
          {runtime.device ?? 'not measured'}
          {runtime.mode && runtime.mode !== runtime.device ? ` / ${runtime.mode}` : ''}
          {runtime.load_state ? ` · worker ${runtime.load_state}` : ''}
        </Row>
        <Row label="Install check">
          {details.install_check ? installCheckText(details.install_check) : 'not run yet'}
        </Row>
        <Row label="Idle unload">{idleText(details)}</Row>
        <Row label="Disk used">{details.disk_bytes === null ? 'not installed' : formatBytes(details.disk_bytes)}</Row>
        {(engine.source || engine.license) && (
          <Row label="Source / licence">
            {[engine.source, engine.license].filter(Boolean).join(' · ')}
          </Row>
        )}
      </dl>

      {(details.packages.length > 0 || details.other_pins.length > 0) && (
        <div className="flex flex-col gap-1" data-testid={`engine-details-packages-${engineId}`}>
          <span className="font-medium">Packages</span>
          <ul className="flex flex-col gap-0.5 font-mono text-[10px]">
            {details.packages.map((pkg) => (
              <li key={pkg.name}>
                {pkg.name} pinned {pkg.pinned}
                {pkg.installed === null ? (
                  <span className="text-muted-foreground"> · not found in the {pkg.where}</span>
                ) : pkg.installed === pkg.pinned ? (
                  <span className="text-muted-foreground"> · installed {pkg.installed}</span>
                ) : (
                  <span className="text-warning"> · installed {pkg.installed} (differs from the pin)</span>
                )}
              </li>
            ))}
            {details.other_pins.map((pin) => (
              <li key={pin}>{pin}</li>
            ))}
          </ul>
        </div>
      )}

      {details.weights.length > 0 && (
        <div className="flex flex-col gap-1" data-testid={`engine-details-weights-${engineId}`}>
          <span className="font-medium">Model weights</span>
          <ul className="flex flex-col gap-0.5 font-mono text-[10px]">
            {details.weights.map((weight) => (
              <li key={`${weight.kind}:${weight.name}`}>
                {weight.name} · {formatBytes(weight.size_bytes)}
                {weight.revision ? ` · revision ${/^[0-9a-f]{40}$/.test(weight.revision) ? weight.revision.slice(0, 12) : weight.revision}` : ''}
                {weight.sha256 ? ` · sha256 ${weight.sha256.slice(0, 12)}…` : ''}
                {!weight.present && <span className="text-warning"> · missing</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {details.hf_gate && showTokenField && (
        <HfTokenField
          engineId={engineId}
          gate={details.hf_gate}
          onChanged={(status) => {
            onTokenChanged(status)
            load()
          }}
        />
      )}

      <div className="flex flex-col gap-2" id={`engine-logs-${engineId}`}>
        <LogView title="Install log" tail={details.logs.install} testId={`engine-log-install-${engineId}`} />
        <LogView title="Worker log (stderr)" tail={details.logs.worker} testId={`engine-log-worker-${engineId}`} />
        <p className="text-muted-foreground">
          Logs keep the last {details.logs.max_lines} lines and have tokens removed. The worker log is
          kept in memory until the app restarts.
        </p>
      </div>
    </div>
  )
}

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Check, ChevronLeft, ChevronRight, Copy, Loader2, Play, Plug } from 'lucide-react'
import { useAppStore } from '@/store'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { PageHeader } from '@/components/ui/page-header'
import { MOTION } from '@/lib/motion'
import { curlSnippet, jsSnippet, pythonSnippet } from '@/lib/apiSnippets'
import { getPref, setPref } from '@/lib/uiPreferences'
import {
  buildServableVoiceRows,
  engineChipText,
  engineSortTier,
  speakSelectionFallback,
} from '@/lib/voiceServability'
import { READINESS_BADGE_CLASSES } from '@/lib/voiceReadiness'
import { cn } from '@/lib/utils'
import {
  getApiDefault,
  listCatalogVoices,
  listEngines,
  listAllVoiceBindings,
  listVoices,
  setApiDefault,
  type ApiDefaultRecord,
  type BuiltInVoiceMeta,
  type EngineCard,
  type VoiceEngineBinding,
  type VoiceMeta,
} from '@/lib/api'

type TestState =
  | { phase: 'idle' }
  | { phase: 'running' }
  | { phase: 'ok'; firstByteMs: number; totalMs: number; url: string }
  | { phase: 'error'; message: string }

function CodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="group relative rounded-control border border-border bg-muted/30 transition-colors hover:border-border/80">
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        className={cn(
          'absolute top-2 right-2 transition-all',
          copied ? 'text-primary' : 'opacity-60 group-hover:opacity-100',
        )}
        onClick={() => {
          navigator.clipboard.writeText(code)
          setCopied(true)
          setTimeout(() => setCopied(false), 1200)
        }}
      >
        <AnimatePresence mode="wait" initial={false}>
          {copied ? (
            <motion.span
              key="check"
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.5, opacity: 0 }}
              transition={MOTION.snappy}
              className="flex"
            >
              <Check className="size-3.5" />
            </motion.span>
          ) : (
            <motion.span
              key="copy"
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.5, opacity: 0 }}
              transition={MOTION.snappy}
              className="flex"
            >
              <Copy className="size-3.5" />
            </motion.span>
          )}
        </AnimatePresence>
      </Button>
      <pre className="overflow-x-auto p-4 text-xs leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  )
}

export function IntegrationsPage() {
  const setPage = useAppStore((s) => s.setPage)
  const storeVoiceId = useAppStore((s) => s.voiceId)
  const storeVoices = useAppStore((s) => s.voices)
  const speakEngineChoice = useAppStore((s) => s.speakEngineChoice)
  const speakEnginePreset = useAppStore((s) => s.speakEnginePreset)
  const pocketCloningAvailable = useAppStore((s) => s.pocketTtsVoiceCloningAvailable)
  const modelLoaded = useAppStore((s) => s.modelLoaded)
  const serviceStarted = useAppStore((s) => s.serviceStarted)
  const healthStatus = useAppStore((s) => s.healthStatus)

  const [apiDefault, setApiDefaultState] = useState<ApiDefaultRecord | null>(null)
  const [voices, setVoices] = useState<VoiceMeta[]>(storeVoices)
  const [catalogVoices, setCatalogVoices] = useState<BuiltInVoiceMeta[]>([])
  const [bindings, setBindings] = useState<Record<string, VoiceEngineBinding[]>>({})
  const [engines, setEngines] = useState<EngineCard[]>([])
  const [refreshVersion, setRefreshVersion] = useState(0)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const runtimeTtsBackend = useAppStore((s) => s.runtimeTtsBackend)
  const [enforceLanguage, setEnforceLanguage] = useState(() => getPref<boolean>('api.enforceLanguage', false))
  // The "Servable now" filter defaults on: the section promises what the endpoint can serve
  // right now, so rows that would 409/400/503 stay behind the toggle (plan §5.7).
  const [servableOnly, setServableOnly] = useState(() => getPref<boolean>('integrations.servableOnly', true))
  const [idsPage, setIdsPage] = useState(0)
  const [idsQuery, setIdsQuery] = useState('')
  const [useSpeakVoice, setUseSpeakVoice] = useState(false)
  const [pendingVoice, setPendingVoice] = useState<string | null>(null)
  // Engine a saved voice runs on when made the default; '' = the active engine.
  const [cloneEngines, setCloneEngines] = useState<EngineCard[]>([])
  const [savedVoiceEngine, setSavedVoiceEngine] = useState('')
  const [pageError, setPageError] = useState<string | null>(null)
  const [test, setTest] = useState<TestState>({ phase: 'idle' })
  const defaultMutationVersion = useRef(0)
  const refreshIds = useCallback(() => {
    setCatalogLoading(true)
    setRefreshVersion((version) => version + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    const defaultVersionAtStart = defaultMutationVersion.current
    Promise.all([
      listVoices(),
      listCatalogVoices(),
      getApiDefault(),
      listEngines(),
      listAllVoiceBindings(),
    ])
      .then(([saved, catalog, effective, engines, voiceBindings]) => {
        if (cancelled) return
        setVoices(saved)
        setCatalogVoices(catalog.voices)
        if (defaultMutationVersion.current === defaultVersionAtStart) setApiDefaultState(effective)
        setBindings(voiceBindings)
        setEngines(engines)
        setPageError(null)
        setCloneEngines(
          engines.filter(
            (engine) =>
              (engine.kind === 'pack' || engine.kind === 'builtin+pack') &&
              engine.capabilities.clone &&
              (engine.state.status === 'installed' || engine.state.status === 'verified'),
          ),
        )
      })
      .catch((err: unknown) => {
        if (!cancelled) setPageError(String((err as Error)?.message || err))
        if (!cancelled) {
          // A failed status read must not leave stale "ready" bindings usable in snippets.
          setBindings({})
          setEngines([])
          setCatalogVoices([])
        }
      })
      .finally(() => {
        if (!cancelled) setCatalogLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [refreshVersion])

  // Status-only reads never prepare or warm an engine. Follow explicit preparations and
  // refresh after returning to the tab; a manual refresh also reconciles external pack edits.
  useEffect(() => {
    window.addEventListener('focus', refreshIds)
    const preparing = Object.values(bindings).some((items) =>
      items.some((binding) => binding.status === 'preparing'),
    )
    const timer = preparing ? window.setTimeout(refreshIds, 2000) : undefined
    return () => {
      window.removeEventListener('focus', refreshIds)
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [bindings, refreshIds])

  // Match Speak's actual request, including its legacy Engine voice dropdown override.
  const speakVoiceId = speakEnginePreset || storeVoiceId
  const defaultVoiceId = apiDefault?.voice ?? null
  const rows = useMemo(
    () =>
      buildServableVoiceRows({
        catalog: catalogVoices,
        saved: voices,
        bindings,
        runtimeTtsBackend,
        engines,
        serviceReady: (serviceStarted || modelLoaded) && healthStatus !== 'error',
        pocketCloningAvailable,
        enforceLanguage,
      }).sort((a, b) => {
        const firstA = a.engines[0]?.label ?? ''
        const firstB = b.engines[0]?.label ?? ''
        const tierA = engineSortTier(firstA)
        const tierB = engineSortTier(firstB)
        return tierA !== tierB ? tierA - tierB : firstA.localeCompare(firstB) || a.label.localeCompare(b.label)
      }),
    [catalogVoices, voices, bindings, runtimeTtsBackend, engines, serviceStarted, modelLoaded, healthStatus, pocketCloningAvailable, enforceLanguage],
  )
  const speakRow = speakVoiceId ? (rows.find((row) => row.id === speakVoiceId) ?? null) : null
  // 25 rows per page keeps 100+ pack voices (Kitten ships 115) scrollable and honest — no
  // virtualization dependency, and the count line states exactly what is on show (plan §5.7).
  const query = idsQuery.trim().toLocaleLowerCase()
  const visibleRows = rows.filter((row) =>
    (!servableOnly || row.servable) &&
    (!query || [row.id, row.label, row.kind, row.language, ...row.engines.map((engine) => engine.label)]
      .join(' ').toLocaleLowerCase().includes(query)),
  )
  const IDS_PAGE_SIZE = 25
  const pageCount = Math.max(1, Math.ceil(visibleRows.length / IDS_PAGE_SIZE))
  const idsPage0 = Math.min(idsPage, pageCount - 1)
  const pageRows = visibleRows.slice(idsPage0 * IDS_PAGE_SIZE, (idsPage0 + 1) * IDS_PAGE_SIZE)
  const mainSpeakPreset = catalogVoices.find((voice) => voice.voice_id === storeVoiceId)
  const impliedSpeakEngine = mainSpeakPreset?.engine &&
    mainSpeakPreset.engine !== 'pocket-tts' && mainSpeakPreset.installed !== false
    ? mainSpeakPreset.engine
    : null
  const selectionEngineId = impliedSpeakEngine ?? (speakEngineChoice || null)
  const speakFallback = useSpeakVoice
    ? speakSelectionFallback(rows, speakVoiceId, selectionEngineId)
    : null
  const usingSpeak = useSpeakVoice && !speakFallback && Boolean(speakRow)
  // No explicit default means omit the voice and let the route use its runtime reference.
  // Never substitute the first saved voice for an absent or broken Speak selection.
  const exampleVoiceId = usingSpeak ? speakVoiceId! : defaultVoiceId
  // A default served by a pack engine is addressed by that engine's id; a saved voice has no
  // namespace to imply it, so its snippet names the engine too.
  const packDefaultEngine =
    apiDefault && apiDefault.engine &&
    !['pocket-tts', 'pytorch', 'openvino', 'pocket_tts'].includes(apiDefault.engine)
      ? apiDefault.engine
      : null
  const exampleModel =
    usingSpeak
      ? (selectionEngineId ?? (speakRow?.kind !== 'saved' ? speakRow?.engines[0]?.id : null) ?? undefined)
      : packDefaultEngine ?? undefined

  // Idle-unloaded is a healthy state: the service stays up and reloads transparently on
  // the next request, so it must read as Ready — not offline.
  const status = !serviceStarted && !modelLoaded
    ? {
        label: 'Starting up',
        detail: 'The service is starting; the endpoint will answer once it is up.',
        badge: 'outline' as const,
      }
    : modelLoaded
      ? {
          label: 'Loaded and serving',
          detail: 'Requests are served without a cold start.',
          badge: 'default' as const,
        }
      : healthStatus === 'error'
        ? {
            label: 'Error',
            detail: 'The model failed to load. Check the logs.',
            badge: 'destructive' as const,
          }
        : {
            label: 'Ready',
            detail: 'Idle-unloaded — loads on the next request.',
            badge: 'secondary' as const,
          }

  async function makeDefault(voice: string) {
    setPendingVoice(voice)
    setPageError(null)
    defaultMutationVersion.current += 1
    try {
      const isSaved = voice.startsWith('vd_')
      const record = await setApiDefault({
        voice,
        ...(isSaved && savedVoiceEngine ? { engine: savedVoiceEngine } : {}),
      })
      setApiDefaultState(record)
      setUseSpeakVoice(false)
    } catch (err) {
      setPageError(String((err as Error)?.message || err))
    } finally {
      // Also invalidate a GET started while this PUT was in flight.
      defaultMutationVersion.current += 1
      setPendingVoice(null)
    }
  }

  async function runTest() {
    setTest((prev) => {
      if (prev.phase === 'ok') URL.revokeObjectURL(prev.url)
      return { phase: 'running' }
    })
    const started = performance.now()
    try {
      const res = await fetch('/v1/audio/speech', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...(exampleModel ? { model: exampleModel } : {}),
          input: 'Hello from Hermes.',
          ...(exampleVoiceId ? { voice_id: exampleVoiceId } : {}),
          response_format: 'mp3',
        }),
      })
      const firstByteMs = performance.now() - started
      if (!res.ok) {
        const text = await res.text()
        setTest({ phase: 'error', message: `${res.status}: ${text.slice(0, 240)}` })
        return
      }
      const blob = await res.blob()
      const totalMs = performance.now() - started
      setTest({ phase: 'ok', firstByteMs, totalMs, url: URL.createObjectURL(blob) })
    } catch (err) {
      setTest({ phase: 'error', message: String((err as Error)?.message || err) })
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <PageHeader
          title="Integrations"
          description="Speech engines and their voices are served over an OpenAI-compatible endpoint. Snippets and tests below use the effective API default."
        />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center gap-3 rounded-panel border border-border bg-card p-4 text-card-foreground shadow-sm"
      >
        <div className="relative flex size-9 shrink-0 items-center justify-center rounded-control bg-primary/10 text-primary">
          <Plug className="size-4" />
          {status.label === 'Loaded and serving' && (
            <span className="absolute -top-0.5 -right-0.5 flex size-2.5">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/60" />
              <span className="relative inline-flex size-full rounded-full bg-primary ring-2 ring-card" />
            </span>
          )}
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium">Speech service status</p>
          <p className="text-xs text-muted-foreground">{status.detail}</p>
        </div>
        <Badge variant={status.badge}>{status.label.toLowerCase()}</Badge>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.03 }}
        className="flex flex-col gap-3 rounded-panel border border-border bg-card p-5 text-card-foreground shadow-sm"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold">Effective API default</p>
            <p className="text-xs text-muted-foreground">
              Used by requests that omit a voice. A Speak selection is transient and never
              changes this.
            </p>
          </div>
          <label className="flex items-start gap-2 text-xs" data-testid="snippet-speak-toggle">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={useSpeakVoice}
              onChange={(event) => setUseSpeakVoice(event.target.checked)}
            />
            <span>
              <span className="font-medium">Use the selected Speak voice instead.</span> Snippets
              derive from the API default; this derives them from the voice selected on the Speak
              page.
            </span>
          </label>
        </div>
        {!catalogLoading && speakFallback && (
          <p
            className="rounded-control border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning"
            data-testid="snippet-fallback-reason"
          >
            {speakFallback.reason}
          </p>
        )}
        {apiDefault ? (
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-sm font-medium">{apiDefault.display_name || apiDefault.voice}</span>
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">
              {apiDefault.voice}
            </code>
            <Badge variant="outline" className="text-[10px]" data-testid="api-default-engine">
              {apiDefault.engine_label || apiDefault.engine || 'engine: current'}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              {apiDefault.kind === 'preset' ? 'built-in voice' : 'saved voice'}
            </Badge>
            {apiDefault.problem ? (
              <Badge variant="destructive" className="text-[10px]">
                needs repair
              </Badge>
            ) : (
              <Badge variant="secondary" className="text-[10px]">
                ready
              </Badge>
            )}
            {apiDefault.variant && (
              <Badge variant="outline" className="text-[10px]">
                variant: {apiDefault.variant}
              </Badge>
            )}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            No API default is set. Requests without a voice fall back to the runtime default
            reference. Pick a voice below to make it explicit.
          </p>
        )}
        {apiDefault?.problem && (
          <div
            role="alert"
            className="flex flex-col gap-2 rounded-control border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive"
            data-testid="api-default-problem"
          >
            <p>
              <span className="font-medium">Requests without a voice are failing.</span>{' '}
              {apiDefault.problem.message} {apiDefault.problem.repair}
            </p>
            <div className="flex flex-wrap gap-2">
              {apiDefault.problem.code === 'engine_not_installed' && (
                <Button type="button" size="xs" variant="outline" onClick={() => setPage('runtime')}>
                  Open Speech engines
                </Button>
              )}
              <Button
                type="button"
                size="xs"
                variant="outline"
                onClick={() => {
                  setPref('voiceLibrary.tab', 'builtin')
                  setPage('voice-library')
                }}
              >
                Choose another default
              </Button>
            </div>
          </div>
        )}
        {pageError && <p className="text-xs text-destructive">{pageError}</p>}
        <label className="flex items-start gap-2 text-xs" data-testid="enforce-language">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={enforceLanguage}
            onChange={(event) => {
              setEnforceLanguage(event.target.checked)
              setPref('api.enforceLanguage', event.target.checked)
            }}
          />
          <span>
            <span className="font-medium">Enforce English on the API.</span> When on, requests for non-English
            voices or languages get an error that says why, instead of audio. When off (the default), the
            request is served as asked, even if the voice is hidden from lists.
          </span>
        </label>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="flex flex-col gap-3 rounded-panel border border-border bg-card p-5 text-card-foreground shadow-sm"
      >
        <div>
          <p className="text-sm font-semibold">OpenAI-compatible speech endpoint</p>
          <p className="text-xs text-muted-foreground">
            <code>POST /v1/audio/speech</code> — pass any saved voice_id or a built-in voice
            (<code>pocket:*</code>, or a pack engine's <code>kokoro:*</code>, <code>phonon:*</code>,
            <code> kitten2:*</code>, <code>pocket-lite:*</code>) as the voice. A namespaced voice is
            served by its own engine.
          </p>
        </div>
        <CodeBlock code={curlSnippet(exampleVoiceId, exampleModel)} />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="flex flex-col gap-3 rounded-panel border border-border bg-card p-5 text-card-foreground shadow-sm"
      >
        <div>
          <p className="text-sm font-semibold">Python (OpenAI SDK)</p>
          <p className="text-xs text-muted-foreground">
            Drop-in for any app already using the OpenAI SDK for TTS, like Hermes. The SDK
            appends the request path to <code>base_url</code>, so it carries the{' '}
            <code>/v1</code> that curl spells out.
          </p>
        </div>
        <CodeBlock code={pythonSnippet(exampleVoiceId, exampleModel)} />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.13 }}
        className="flex flex-col gap-3 rounded-panel border border-border bg-card p-5 text-card-foreground shadow-sm"
      >
        <div>
          <p className="text-sm font-semibold">JavaScript (OpenAI SDK)</p>
          <p className="text-xs text-muted-foreground">
            Same base-URL convention as Python: <code>baseURL</code> ends in <code>/v1</code>.
          </p>
        </div>
        <CodeBlock code={jsSnippet(exampleVoiceId, exampleModel)} />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.13 }}
        className="flex flex-col gap-3 rounded-panel border border-border bg-card p-5 text-card-foreground shadow-sm"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold">Test endpoint</p>
            <p className="text-xs text-muted-foreground">
              Sends a short request as <code>{exampleVoiceId ?? 'the runtime reference'}</code>. It never changes the API
              default.
            </p>
          </div>
          <Button
            type="button"
            size="sm"
            onClick={() => void runTest()}
            disabled={test.phase === 'running' || catalogLoading}
          >
            {test.phase === 'running' ? (
              <Loader2 className="animate-spin" data-icon="inline-start" />
            ) : (
              <Play data-icon="inline-start" />
            )}
            {test.phase === 'running' ? 'Testing…' : 'Test endpoint'}
          </Button>
        </div>
        {test.phase === 'ok' && (
          <div className="flex flex-col gap-2">
            <p className="text-xs text-muted-foreground">
              First byte {Math.round(test.firstByteMs)} ms · total{' '}
              {(test.totalMs / 1000).toFixed(2)} s
            </p>
            <audio controls src={test.url} className="w-full" />
          </div>
        )}
        {test.phase === 'error' && (
          <p className="text-xs text-destructive break-words">{test.message}</p>
        )}
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.16 }}
        className="flex flex-col gap-3 rounded-panel border border-border bg-card p-5 text-card-foreground shadow-sm"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold">Available voice IDs</p>
            <p className="text-xs text-muted-foreground">
              Read-only readiness snapshot, not a promise that weights are resident. "Servable
              now" (on by default) keeps voices with at least one usable engine; blocked pairs
              explain the repair. Idle engines load on request, and eligible saved voices may
              prepare lazily. Turn the filter off to inspect unavailable IDs.
            </p>
          </div>
          <label className="flex items-start gap-2 text-xs" data-testid="servable-filter">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={servableOnly}
              onChange={(event) => {
                setServableOnly(event.target.checked)
                setPref('integrations.servableOnly', event.target.checked)
                setIdsPage(0)
              }}
            />
            <span className="font-medium">Servable now</span>
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            aria-label="Search available voice IDs"
            placeholder="Search IDs, names or engines…"
            data-testid="ids-search"
            className="min-w-48 flex-1 rounded-control border border-border bg-background px-3 py-2 text-xs"
            value={idsQuery}
            onChange={(event) => {
              setIdsQuery(event.target.value)
              setIdsPage(0)
            }}
          />
          <Button
            type="button"
            size="sm"
            variant="outline"
            data-testid="ids-refresh"
            disabled={catalogLoading}
            onClick={refreshIds}
          >
            {catalogLoading ? 'Refreshing…' : 'Refresh IDs'}
          </Button>
        </div>
        {cloneEngines.length > 0 && (
          <label className="flex flex-wrap items-center gap-2 text-xs" data-testid="saved-voice-engine">
            <span className="font-medium">Saved voices run on</span>
            <select
              className="rounded-control border border-border bg-background px-2 py-1 text-xs"
              value={savedVoiceEngine}
              onChange={(event) => setSavedVoiceEngine(event.target.value)}
            >
              <option value="">The active engine</option>
              {cloneEngines.map((engine) => (
                <option key={engine.id} value={engine.id}>
                  {engine.label}
                </option>
              ))}
            </select>
            <span className="text-muted-foreground">
              Applies when you press Set default on a saved voice. Built-in voices of Kokoro, Phonon and
              the other packs are set from Voices → Built-in.
            </span>
          </label>
        )}
        {visibleRows.length > 0 && (
          <>
            <div className="overflow-x-auto" data-testid="available-ids">
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="py-1.5 pr-3 font-medium">Voice ID</th>
                    <th className="py-1.5 pr-3 font-medium">Label</th>
                    <th className="py-1.5 pr-3 font-medium">Engine</th>
                    <th className="py-1.5 font-medium">Default</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((row) => {
                    const isDefault = apiDefault?.voice === row.id
                    return (
                      <tr
                        key={row.id}
                        data-testid="voice-row"
                        className={cn(
                          'border-b border-border/60',
                          isDefault && 'bg-primary/5',
                        )}
                      >
                        <td className="py-1.5 pr-3">
                          <span className="flex items-center gap-1.5">
                            <code className="font-mono text-[11px]" data-testid="voice-id">
                              {row.id}
                            </code>
                            <Button
                              type="button"
                              size="icon-xs"
                              variant="ghost"
                              aria-label={`Copy ${row.id}`}
                              data-testid="copy-voice-id"
                              onClick={() => void navigator.clipboard.writeText(row.id)}
                            >
                              <Copy />
                            </Button>
                          </span>
                        </td>
                        <td className="max-w-56 truncate py-1.5 pr-3 text-muted-foreground">
                          {row.label}
                        </td>
                        <td className="py-1.5 pr-3">
                          <span className="flex flex-wrap gap-1">
                            {row.engines.map((engine) => (
                              <Badge
                                key={`${row.id}-${engine.label}`}
                                variant="outline"
                                className={cn(
                                  'text-[10px]',
                                  engine.servable
                                    ? undefined
                                    : READINESS_BADGE_CLASSES[
                                        engine.reason?.startsWith('Install') ? 'muted' : 'warn'
                                      ],
                                )}
                                data-testid="engine-chip"
                                title={engine.reason ?? undefined}
                              >
                                {engineChipText(engine)}
                              </Badge>
                            ))}
                          </span>
                        </td>
                        <td className="py-1.5">
                          {isDefault ? (
                            <Badge className="text-[10px]">API default</Badge>
                          ) : row.servable ? (
                            <Button
                              type="button"
                              size="xs"
                              variant="ghost"
                              disabled={pendingVoice !== null || catalogLoading}
                              data-testid="set-default"
                              onClick={() => void makeDefault(row.id)}
                            >
                              {pendingVoice === row.id ? (
                                <Loader2 className="animate-spin" />
                              ) : (
                                'Set default'
                              )}
                            </Button>
                          ) : (
                            <span
                              className="text-[10px] text-muted-foreground"
                              title={row.engines
                                .map((engine) => engine.reason)
                                .filter(Boolean)
                                .join(' ')}
                            >
                              Not servable yet
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span data-testid="ids-count">
                Showing {pageRows.length} of {visibleRows.length} IDs
                {pageCount > 1 ? ` · page ${idsPage0 + 1} of ${pageCount}` : ''}
                {` · ${rows.length} total`}
                {servableOnly ? ' · servable now' : ' · including not-yet-servable'}
              </span>
              {pageCount > 1 && (
                <span className="flex items-center gap-1">
                  <Button
                    type="button"
                    size="icon-xs"
                    variant="ghost"
                    aria-label="Previous page"
                    data-testid="ids-prev"
                    disabled={idsPage0 === 0}
                    onClick={() => setIdsPage(Math.max(0, idsPage0 - 1))}
                  >
                    <ChevronLeft />
                  </Button>
                  <Button
                    type="button"
                    size="icon-xs"
                    variant="ghost"
                    aria-label="Next page"
                    data-testid="ids-next"
                    disabled={idsPage0 >= pageCount - 1}
                    onClick={() => setIdsPage(Math.min(pageCount - 1, idsPage0 + 1))}
                  >
                    <ChevronRight />
                  </Button>
                </span>
              )}
            </div>
          </>
        )}
        {visibleRows.length === 0 && (
          <p className="text-xs text-muted-foreground">
            {catalogLoading ? 'Loading voice IDs…' : 'No matching voice IDs. Try another search or turn off Servable now.'}
          </p>
        )}
      </motion.div>
    </div>
  )
}

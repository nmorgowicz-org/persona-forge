import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Check,
  Copy,
  Download,
  Loader2,
  Play,
  Search,
  Square,
  Star,
  Volume2,
} from 'lucide-react'
import {
  generateSpeech,
  getApiDefault,
  installEngine,
  listCatalogVoices,
  listEngines,
  setApiDefault,
  type ApiDefaultRecord,
  type BuiltInEngineSummary,
  type BuiltInVoiceMeta,
  type EngineInstallJob,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store'
import {
  readFavoriteVoiceIds,
  subscribeFavoriteVoices,
  toggleFavoriteVoice,
} from '@/lib/voiceFavorites'
import { getPref, setPref } from '@/lib/uiPreferences'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'

const CATEGORY_LABELS: Record<string, string> = {
  conversation: 'Conversation',
  reading: 'Reading',
  multilingual: 'Multilingual',
  other: 'Other',
}

function isPackVoice(voice: BuiltInVoiceMeta): boolean {
  return Boolean(voice.engine) && voice.engine !== 'pocket-tts'
}

/** Voices of an engine that is not installed come from the bundled catalog and cannot be previewed yet. */
function needsInstall(voice: BuiltInVoiceMeta): boolean {
  return voice.installed === false
}

function isEnglishVoice(voice: BuiltInVoiceMeta): boolean {
  const code = (voice.language_code || '').toLowerCase()
  return code.startsWith('en') || /english/i.test(voice.language || '')
}

export function BuiltInVoicesTab() {
  const setPage = useAppStore((s) => s.setPage)
  const setVoiceId = useAppStore((s) => s.setVoiceId)

  const [voices, setVoices] = useState<BuiltInVoiceMeta[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [language, setLanguage] = useState<'en' | 'all'>(() =>
    getPref<'en' | 'all'>('voiceCatalog.language', 'en'),
  )
  const [category, setCategory] = useState('all')
  const [engineFilter, setEngineFilter] = useState('all')
  const [engines, setEngines] = useState<BuiltInEngineSummary[]>([])
  const [favorites, setFavorites] = useState<string[]>(() => readFavoriteVoiceIds())
  const [previewing, setPreviewing] = useState<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [previewName, setPreviewName] = useState<string | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [detail, setDetail] = useState<BuiltInVoiceMeta | null>(null)
  const [apiDefault, setApiDefaultState] = useState<ApiDefaultRecord | null>(null)
  const [settingDefault, setSettingDefault] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [installedOnly, setInstalledOnly] = useState(false)
  const [installingId, setInstallingId] = useState<string | null>(null)
  const [installJob, setInstallJob] = useState<EngineInstallJob | null>(null)
  const [installError, setInstallError] = useState<string | null>(null)
  const previewToken = useRef(0)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    Promise.all([listCatalogVoices(), getApiDefault()])
      .then(([catalog, effective]) => {
        if (cancelled) return
        setVoices(catalog.voices)
        setEngines(catalog.engines)
        setApiDefaultState(effective)
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

  useEffect(() => subscribeFavoriteVoices(() => setFavorites(readFavoriteVoiceIds())), [])

  useEffect(() => {
    if (!previewUrl) return
    return () => URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  const categories = useMemo(
    () => Array.from(new Set(voices.map((voice) => voice.category).filter(Boolean))).sort(),
    [voices],
  )
  const hiddenByLanguage = useMemo(
    () => (language === 'en' ? voices.filter((voice) => !isEnglishVoice(voice)).length : 0),
    [voices, language],
  )
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return voices.filter((voice) => {
      if (language === 'en' && !isEnglishVoice(voice)) return false
      if (category !== 'all' && voice.category !== category) return false
      if (engineFilter !== 'all' && (voice.engine ?? 'pocket-tts') !== engineFilter) return false
      if (installedOnly && needsInstall(voice)) return false
      if (!q) return true
      return (
        voice.display_name.toLowerCase().includes(q) ||
        voice.voice_id.toLowerCase().includes(q) ||
        (voice.language || '').toLowerCase().includes(q) ||
        (voice.note || '').toLowerCase().includes(q)
      )
    })
  }, [voices, language, category, engineFilter, installedOnly, query])

  function changeLanguage(next: 'en' | 'all') {
    setLanguage(next)
    setPref('voiceCatalog.language', next)
  }

  function stopPreview() {
    previewToken.current += 1
    setPreviewing(null)
    setPreviewName(null)
    setPreviewUrl(null)
  }

  /** Install an engine from the catalog, follow its progress, then refresh the list with its real voices. */
  async function installFromCatalog(engineId: string) {
    if (installingId) return
    setInstallingId(engineId)
    setInstallJob(null)
    setInstallError(null)
    try {
      await installEngine(engineId)
      for (;;) {
        const card = (await listEngines()).find((engine) => engine.id === engineId)
        if (!mounted.current) return
        const job = card?.install_job ?? null
        setInstallJob(job)
        if (job?.state === 'error') {
          setInstallError(job.error || 'The install failed.')
          return
        }
        if (job?.state !== 'running' && card && card.state.status !== 'not-installed') break
        await new Promise((resolve) => setTimeout(resolve, 2000))
        if (!mounted.current) return
      }
      const catalog = await listCatalogVoices()
      if (!mounted.current) return
      setVoices(catalog.voices)
      setEngines(catalog.engines)
    } catch (err) {
      if (mounted.current) setInstallError(String((err as Error)?.message || err))
    } finally {
      if (mounted.current) setInstallingId(null)
    }
  }

  function installButton(voice: BuiltInVoiceMeta, size: 'xs' | 'sm') {
    const busy = installingId === voice.engine
    return (
      <Button
        type="button"
        size={size}
        variant="outline"
        disabled={installingId !== null}
        onClick={() => voice.engine && void installFromCatalog(voice.engine)}
      >
        {busy ? (
          <>
            <Loader2 className="animate-spin" /> Installing…
          </>
        ) : (
          <>
            <Download /> Install {voice.engine_label}
          </>
        )}
      </Button>
    )
  }

  async function previewVoice(voice: BuiltInVoiceMeta) {
    if (previewing === voice.voice_id) {
      stopPreview()
      return
    }
    stopPreview()
    const token = ++previewToken.current
    setPreviewError(null)
    setPreviewName(voice.display_name)
    setPreviewing(voice.voice_id)
    try {
      const text = `Hi, I'm ${voice.display_name}. This is how I sound.`
      let blob: Blob
      if (isPackVoice(voice)) {
        // Pack engines are served beside the active backend through the OpenAI-compatible route.
        const res = await fetch('/v1/audio/speech', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: voice.engine, input: text, voice: voice.voice_id, response_format: 'wav' }),
        })
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(body?.error?.message || `HTTP ${res.status}`)
        }
        blob = await res.blob()
      } else {
        blob = (await generateSpeech({ text, voiceId: voice.voice_id, responseFormat: 'mp3' })).blob
      }
      if (token !== previewToken.current) return
      setPreviewUrl(URL.createObjectURL(blob))
    } catch (err) {
      if (token === previewToken.current) {
        setPreviewError(String((err as Error)?.message || err))
      }
    } finally {
      if (token === previewToken.current) setPreviewing(null)
    }
  }

  async function makeDefault(voice: BuiltInVoiceMeta) {
    setSettingDefault(voice.voice_id)
    setError(null)
    try {
      setApiDefaultState(
        await setApiDefault({ voice: voice.voice_id, engine: voice.backend }),
      )
    } catch (err) {
      setError(String((err as Error)?.message || err))
    } finally {
      setSettingDefault(null)
    }
  }

  async function copyVoiceId(voiceId: string) {
    await navigator.clipboard.writeText(voiceId)
    setCopiedId(voiceId)
    setTimeout(() => setCopiedId(null), 1200)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search built-in voices"
            aria-label="Search built-in voices"
            className="pl-8"
          />
        </div>
        <Select
          value={language}
          onValueChange={(value) => changeLanguage(value === 'all' ? 'all' : 'en')}
        >
          <SelectTrigger className="w-40" aria-label="Language filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="en">English only</SelectItem>
            <SelectItem value="all">All languages</SelectItem>
          </SelectContent>
        </Select>
        {engines.length > 1 && (
          <Select value={engineFilter} onValueChange={setEngineFilter}>
            <SelectTrigger className="w-56" aria-label="Engine filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All engines</SelectItem>
              {engines.map((engine) => (
                <SelectItem key={engine.id} value={engine.id}>
                  {engine.label}
                  {engine.installed ? '' : ' (not installed)'}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger className="w-40" aria-label="Category filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All categories</SelectItem>
            {categories.map((value) => (
              <SelectItem key={value} value={value}>
                {CATEGORY_LABELS[value] || value}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {engines.some((engine) => !engine.installed) && (
          <Button
            type="button"
            size="sm"
            variant={installedOnly ? 'secondary' : 'outline'}
            aria-pressed={installedOnly}
            onClick={() => setInstalledOnly((value) => !value)}
          >
            Installed only
          </Button>
        )}
        <span className="text-xs text-muted-foreground tabular-nums">
          {filtered.length} voice{filtered.length === 1 ? '' : 's'}
        </span>
      </div>

      {hiddenByLanguage > 0 && (
        <p className="text-xs text-muted-foreground">
          {hiddenByLanguage} non-English voice{hiddenByLanguage === 1 ? '' : 's'} hidden by the
          language filter.{' '}
          <button
            type="button"
            className="underline underline-offset-2 hover:text-foreground"
            onClick={() => changeLanguage('all')}
          >
            Show all languages
          </button>
        </p>
      )}

      {engines.some((engine) => !engine.installed) && (
        <p className="text-xs text-muted-foreground" data-testid="catalog-not-installed">
          Voices marked "Needs install" belong to engines that are not installed yet (
          {engines
            .filter((engine) => !engine.installed)
            .map((engine) => engine.label)
            .join(', ')}
          ). You can browse them now; install an engine here or under Runtime → Speech engines to hear it.
        </p>
      )}
      {installingId && (
        <p className="text-xs text-muted-foreground" data-testid="catalog-install-progress">
          Installing {engines.find((engine) => engine.id === installingId)?.label ?? installingId}
          {installJob && installJob.step_count > 0
            ? `: step ${installJob.step_index} of ${installJob.step_count}, ${installJob.step}.`
            : '…'}{' '}
          This can take several minutes the first time.
        </p>
      )}
      {installError && (
        <p className="rounded-control border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          Install failed: {installError}
        </p>
      )}

      {previewUrl && (
        <div className="flex flex-wrap items-center gap-3 rounded-panel border border-border bg-muted/30 p-3">
          <Volume2 className="size-4 shrink-0 text-primary" />
          <span className="text-xs font-medium">{previewName ?? 'Preview'}</span>
          <audio key={previewUrl} src={previewUrl} controls autoPlay className="h-8 min-w-56 flex-1" />
          <Button type="button" size="xs" variant="ghost" onClick={stopPreview}>
            Close
          </Button>
        </div>
      )}
      {previewError && (
        <p className="rounded-control border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {previewError}
        </p>
      )}
      {error && (
        <p className="rounded-control border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </p>
      )}

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-32 rounded-panel" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <p className="rounded-panel border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          No voices match these filters.
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((voice) => {
            const isFavorite = favorites.includes(voice.voice_id)
            const isPreviewing = previewing === voice.voice_id
            const isApiDefault = apiDefault?.voice === voice.voice_id
            return (
              <div
                key={voice.voice_id}
                className={cn(
                  'flex flex-col gap-2 rounded-panel border border-border bg-card p-4 text-card-foreground shadow-sm transition-colors',
                  isApiDefault && 'border-primary/40',
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate text-sm font-medium">{voice.display_name}</span>
                    <span className="truncate font-mono text-[10px] text-muted-foreground">
                      {voice.voice_id}
                    </span>
                  </div>
                  <button
                    type="button"
                    aria-label={
                      isFavorite
                        ? `Remove ${voice.display_name} from favorites`
                        : `Add ${voice.display_name} to favorites`
                    }
                    aria-pressed={isFavorite}
                    onClick={() => setFavorites(toggleFavoriteVoice(voice.voice_id))}
                    className={cn(
                      'rounded-control p-1 transition-colors hover:bg-muted',
                      isFavorite ? 'text-warning' : 'text-muted-foreground',
                    )}
                  >
                    <Star className={cn('size-4', isFavorite && 'fill-current')} />
                  </button>
                </div>

                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant="outline" className="text-[10px]">
                    {voice.engine_label ?? 'Pocket'}
                  </Badge>
                  <Badge variant="outline" className="text-[10px]">
                    {voice.language}
                  </Badge>
                  <Badge variant="outline" className="text-[10px]">
                    {CATEGORY_LABELS[voice.category] || voice.category}
                  </Badge>
                  {needsInstall(voice) && (
                    <Badge variant="secondary" className="text-[10px]">
                      Needs install
                    </Badge>
                  )}
                  {isApiDefault && <Badge className="text-[10px]">API default</Badge>}
                </div>

                {voice.note && (
                  <p className="line-clamp-2 text-xs text-muted-foreground">{voice.note}</p>
                )}

                <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-1">
                  {needsInstall(voice) ? (
                    installButton(voice, 'xs')
                  ) : (
                  <Button
                    type="button"
                    size="xs"
                    variant={isPreviewing ? 'secondary' : 'outline'}
                    disabled={previewing !== null && !isPreviewing}
                    onClick={() => void previewVoice(voice)}
                  >
                    {isPreviewing ? (
                      <>
                        <Loader2 className="animate-spin" /> Generating…
                      </>
                    ) : previewUrl && previewName === voice.display_name ? (
                      <>
                        <Square /> Stop
                      </>
                    ) : (
                      <>
                        <Play /> Preview
                      </>
                    )}
                  </Button>
                  )}
                  <Button type="button" size="xs" variant="ghost" onClick={() => setDetail(voice)}>
                    Details
                  </Button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <Sheet open={detail !== null} onOpenChange={(open) => !open && setDetail(null)}>
        <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
          {detail && (
            <>
              <SheetHeader>
                <SheetTitle>{detail.display_name}</SheetTitle>
                <SheetDescription>
                  {needsInstall(detail)
                    ? `${detail.engine_label} is not installed yet. This voice is listed from the engine's catalog; install the engine to hear it.`
                    : isPackVoice(detail)
                    ? `Built-in ${detail.engine_label} voice, generated locally. Served beside the active engine.`
                    : 'Built-in Pocket voice — ready to serve without a saved reference.'}
                </SheetDescription>
              </SheetHeader>
              <div className="flex flex-col gap-4 px-4 pb-6">
                <div className="flex flex-wrap gap-1.5">
                  <Badge variant="outline">{detail.engine_label ?? 'Pocket'}</Badge>
                  <Badge variant="outline">{detail.language}</Badge>
                  <Badge variant="outline">
                    {CATEGORY_LABELS[detail.category] || detail.category}
                  </Badge>
                  {needsInstall(detail) && <Badge variant="secondary">Needs install</Badge>}
                  {apiDefault?.voice === detail.voice_id && <Badge>API default</Badge>}
                </div>
                {detail.note && <p className="text-sm text-muted-foreground">{detail.note}</p>}
                {isPackVoice(detail) && (
                  <p className="text-xs text-muted-foreground">
                    To use this voice, pick {detail.engine_label} in the Engine selector on Speak, or pass{' '}
                    <code>model: {detail.engine}</code> and this voice ID to the API. It can't be set as the API
                    default yet, because the default applies to the active engine.
                  </p>
                )}

                <div className="flex flex-col gap-1">
                  <span className="micro-label">API voice ID</span>
                  <div className="flex items-center gap-1.5">
                    <code className="flex-1 rounded-control border border-border bg-muted/30 px-2 py-1 font-mono text-[11px]">
                      {detail.voice_id}
                    </code>
                    <Button
                      type="button"
                      size="icon-sm"
                      variant="ghost"
                      aria-label="Copy voice ID"
                      onClick={() => void copyVoiceId(detail.voice_id)}
                    >
                      {copiedId === detail.voice_id ? <Check /> : <Copy />}
                    </Button>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  {needsInstall(detail) ? (
                    installButton(detail, 'sm')
                  ) : (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={previewing !== null && previewing !== detail.voice_id}
                    onClick={() => void previewVoice(detail)}
                  >
                    {previewing === detail.voice_id ? (
                      <>
                        <Loader2 className="animate-spin" /> Generating…
                      </>
                    ) : (
                      <>
                        <Play /> Preview
                      </>
                    )}
                  </Button>
                  )}
                  {!isPackVoice(detail) && (
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => {
                        setVoiceId(detail.voice_id)
                        setPage('speak')
                      }}
                    >
                      Use in Speak
                    </Button>
                  )}
                  {!isPackVoice(detail) && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={settingDefault === detail.voice_id || apiDefault?.voice === detail.voice_id}
                    onClick={() => void makeDefault(detail)}
                  >
                    {settingDefault === detail.voice_id ? (
                      <Loader2 className="animate-spin" />
                    ) : apiDefault?.voice === detail.voice_id ? (
                      'API default'
                    ) : (
                      'Set as API default'
                    )}
                  </Button>
                  )}
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setFavorites(toggleFavoriteVoice(detail.voice_id))}
                  >
                    <Star
                      className={cn(
                        favorites.includes(detail.voice_id) && 'fill-current text-warning',
                      )}
                    />
                    {favorites.includes(detail.voice_id) ? 'Favorited' : 'Favorite'}
                  </Button>
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}

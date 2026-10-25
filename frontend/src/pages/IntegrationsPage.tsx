import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Check, Copy, Loader2, Play, Plug } from 'lucide-react'
import { useAppStore } from '@/store'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { PageHeader } from '@/components/ui/page-header'
import { MOTION } from '@/lib/motion'
import { getPref, setPref } from '@/lib/uiPreferences'
import { cn } from '@/lib/utils'
import {
  getApiDefault,
  listBuiltInVoices,
  listVoices,
  setApiDefault,
  type ApiDefaultRecord,
  type BuiltInVoiceMeta,
  type VoiceMeta,
} from '@/lib/api'

const CURL_SNIPPET = (voiceId: string) => `curl -X POST "$PERSONA_FORGE_BASE_URL/v1/audio/speech" \\
  -H "Content-Type: application/json" \\
  -d '{
    "input": "Hello from Hermes.",
    "voice_id": "${voiceId}",
    "response_format": "mp3"
  }' \\
  --output speech.mp3`

const PYTHON_SNIPPET = (voiceId: string) => `from openai import OpenAI

client = OpenAI(base_url="$PERSONA_FORGE_BASE_URL", api_key="not-needed")

response = client.audio.speech.create(
    model="persona-forge",
    voice="${voiceId}",
    input="Hello from Hermes.",
)
response.stream_to_file("speech.mp3")`

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
  const storeVoiceId = useAppStore((s) => s.voiceId)
  const storeVoices = useAppStore((s) => s.voices)
  const modelLoaded = useAppStore((s) => s.modelLoaded)
  const serviceStarted = useAppStore((s) => s.serviceStarted)
  const healthStatus = useAppStore((s) => s.healthStatus)

  const [apiDefault, setApiDefaultState] = useState<ApiDefaultRecord | null>(null)
  const [voices, setVoices] = useState<VoiceMeta[]>(storeVoices)
  const [builtIns, setBuiltIns] = useState<BuiltInVoiceMeta[]>([])
  const [enforceLanguage, setEnforceLanguage] = useState(() => getPref<boolean>('api.enforceLanguage', false))
  const [useSpeakVoice, setUseSpeakVoice] = useState(false)
  const [pendingVoice, setPendingVoice] = useState<string | null>(null)
  const [pageError, setPageError] = useState<string | null>(null)
  const [test, setTest] = useState<TestState>({ phase: 'idle' })

  useEffect(() => {
    let cancelled = false
    Promise.all([listVoices(), listBuiltInVoices(), getApiDefault()])
      .then(([saved, presets, effective]) => {
        if (cancelled) return
        setVoices(saved)
        setBuiltIns(presets)
        setApiDefaultState(effective)
      })
      .catch((err: unknown) => {
        if (!cancelled) setPageError(String((err as Error)?.message || err))
      })
    return () => {
      cancelled = true
    }
  }, [])

  const speakVoiceId = storeVoiceId ?? voices[0]?.voice_id ?? null
  const defaultVoiceId = apiDefault?.voice ?? null
  const exampleVoiceId =
    (useSpeakVoice ? speakVoiceId : defaultVoiceId) ?? speakVoiceId ?? 'my-voice'

  const voiceEntries = [
    ...voices.map((voice) => ({
      id: voice.voice_id,
      label: voice.display_name || voice.description || voice.voice_id,
      engine: apiDefault?.engine ?? null,
    })),
    ...builtIns.map((voice) => ({
      id: voice.voice_id,
      label: `${voice.display_name} · ${voice.language}`,
      engine: voice.backend,
    })),
  ]

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
    try {
      const record = await setApiDefault({ voice })
      setApiDefaultState(record)
      setUseSpeakVoice(false)
    } catch (err) {
      setPageError(String((err as Error)?.message || err))
    } finally {
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
          input: 'Hello from Hermes.',
          voice_id: exampleVoiceId,
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
          <Button
            type="button"
            size="sm"
            variant={useSpeakVoice ? 'default' : 'outline'}
            onClick={() => setUseSpeakVoice((value) => !value)}
          >
            {useSpeakVoice ? 'Snippets: Speak voice' : 'Snippets: API default'}
          </Button>
        </div>
        {apiDefault ? (
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-sm font-medium">{apiDefault.display_name || apiDefault.voice}</span>
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">
              {apiDefault.voice}
            </code>
            <Badge variant="outline" className="text-[10px]">
              {apiDefault.engine || 'engine: current'}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              {apiDefault.kind === 'preset' ? 'built-in voice' : 'saved voice'}
            </Badge>
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
            <code>POST /v1/audio/speech</code> — pass any saved voice_id or built-in
            <code> pocket:*</code> voice as the voice.
          </p>
        </div>
        <CodeBlock code={CURL_SNIPPET(exampleVoiceId)} />
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
            Drop-in for any app already using the OpenAI SDK for TTS, like Hermes.
          </p>
        </div>
        <CodeBlock code={PYTHON_SNIPPET(exampleVoiceId)} />
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
              Sends a short request as <code>{exampleVoiceId}</code>. It never changes the API
              default.
            </p>
          </div>
          <Button
            type="button"
            size="sm"
            onClick={() => void runTest()}
            disabled={test.phase === 'running'}
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
        <div>
          <p className="text-sm font-semibold">Available voice IDs</p>
          <p className="text-xs text-muted-foreground">
            Everything the endpoint can serve right now, including built-in voices that need no
            saved reference.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {voiceEntries.map((entry) => (
            <span
              key={entry.id}
              className={cn(
                'inline-flex items-center gap-2 rounded-control border px-2 py-1',
                apiDefault?.voice === entry.id
                  ? 'border-primary/40 bg-primary/5'
                  : 'border-border',
              )}
            >
              <code className="font-mono text-[11px]">{entry.id}</code>
              <span className="max-w-40 truncate text-[11px] text-muted-foreground">
                {entry.label}
              </span>
              {entry.engine && (
                <Badge variant="outline" className="text-[10px]">
                  {entry.engine}
                </Badge>
              )}
              {apiDefault?.voice === entry.id ? (
                <Badge className="text-[10px]">API default</Badge>
              ) : (
                <Button
                  type="button"
                  size="xs"
                  variant="ghost"
                  disabled={pendingVoice === entry.id}
                  onClick={() => void makeDefault(entry.id)}
                >
                  {pendingVoice === entry.id ? <Loader2 className="animate-spin" /> : 'Set default'}
                </Button>
              )}
            </span>
          ))}
          {voiceEntries.length === 0 && (
            <p className="text-xs text-muted-foreground">No voices available yet.</p>
          )}
        </div>
      </motion.div>
    </div>
  )
}

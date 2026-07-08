import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Check, Copy, Plug } from 'lucide-react'
import { useAppStore } from '@/store'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const CURL_SNIPPET = (voiceId: string) => `curl -X POST "$QWEN3_TTS_BASE_URL/v1/audio/speech" \\
  -H "Content-Type: application/json" \\
  -d '{
    "input": "Hello from Hermes.",
    "voice_id": "${voiceId}",
    "response_format": "mp3"
  }' \\
  --output speech.mp3`

const PYTHON_SNIPPET = (voiceId: string) => `from openai import OpenAI

client = OpenAI(base_url="$QWEN3_TTS_BASE_URL", api_key="not-needed")

response = client.audio.speech.create(
    model="qwen3-tts",
    voice="${voiceId}",
    input="Hello from Hermes.",
)
response.stream_to_file("speech.mp3")`

function CodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="group relative rounded-lg border border-border bg-muted/30 transition-colors hover:border-border/80">
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
              transition={{ duration: 0.15 }}
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
              transition={{ duration: 0.15 }}
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
  const voiceId = useAppStore((s) => s.voiceId)
  const voices = useAppStore((s) => s.voices)
  const storeModelLoaded = useAppStore((s) => s.modelLoaded)
  const storeServiceStarted = useAppStore((s) => s.serviceStarted)
  const exampleVoiceId = voiceId ?? voices[0]?.voice_id ?? 'my-voice'

  return (
    <div className="flex flex-col gap-6">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-semibold tracking-tight">Integrations</h1>
        <p className="text-sm text-muted-foreground">
          Voices designed here are served by the always-resident base model over an
          OpenAI-compatible endpoint — Hermes and other apps consume them directly.
        </p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center gap-3 rounded-xl border border-border bg-card p-4 text-card-foreground shadow-sm"
      >
        <div className="relative flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Plug className="size-4" />
          {storeModelLoaded && (
            <span className="absolute -top-0.5 -right-0.5 flex size-2.5">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/60" />
              <span className="relative inline-flex size-full rounded-full bg-primary ring-2 ring-card" />
            </span>
          )}
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium">Base model status</p>
          <p className="text-xs text-muted-foreground">
            {storeModelLoaded
              ? 'Loaded and serving'
              : storeServiceStarted
                ? 'Service running, model not loaded'
                : 'Starting up'}
          </p>
        </div>
        <Badge variant={storeModelLoaded ? 'default' : 'outline'}>
          {storeModelLoaded ? 'online' : 'offline'}
        </Badge>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm"
      >
        <div>
          <p className="text-sm font-semibold">OpenAI-compatible speech endpoint</p>
          <p className="text-xs text-muted-foreground">
            <code>POST /v1/audio/speech</code> — pass any saved voice_id as the voice.
          </p>
        </div>
        <CodeBlock code={CURL_SNIPPET(exampleVoiceId)} />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm"
      >
        <div>
          <p className="text-sm font-semibold">Python (OpenAI SDK)</p>
          <p className="text-xs text-muted-foreground">
            Drop-in for any app already using the OpenAI SDK for TTS, like Hermes.
          </p>
        </div>
        <CodeBlock code={PYTHON_SNIPPET(exampleVoiceId)} />
      </motion.div>

      {voices.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="flex flex-col gap-2 rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm"
        >
          <p className="text-sm font-semibold">Available voice IDs</p>
          <div className="flex flex-wrap gap-1.5">
            {voices.map((v) => (
              <Badge key={v.voice_id} variant="outline" className="font-mono text-[11px]">
                {v.voice_id}
              </Badge>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  )
}

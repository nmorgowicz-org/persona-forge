import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { generateSpeech, listVoices } from '@/lib/api'
import { TONE_OPTIONS } from '@/lib/voiceDesignChips'
import { useAppStore } from '@/store'
import { VoiceSelector } from '@/components/VoiceSelector'
import { AudioPlayer } from '@/components/AudioPlayer'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Info, Dices } from 'lucide-react'

export function SpeakPage() {
  const {
    text,
    setText,
    voiceId,
    setVoiceId,
    voices,
    setVoices,
    audioUrl,
    setAudioUrl,
    isGenerating,
    setGenerating,
    error,
    setError,
  } = useAppStore()
  const [language, setLanguage] = useState('English')
  const [tone, setTone] = useState('neutral')
  const [seedInput, setSeedInput] = useState('')
  const [lastSeed, setLastSeed] = useState<number | null>(null)
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null)

  async function refreshVoices() {
    try {
      setVoices(await listVoices())
    } catch {
      // Non-fatal — voice library may be empty or briefly unavailable during a swap.
    }
  }

  useEffect(() => {
    refreshVoices()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleGenerate() {
    if (!text.trim() || isGenerating) return
    setGenerating(true)
    setError(null)
    try {
      const toneLabel = TONE_OPTIONS.find((t) => t.id === tone)?.label
      const instruct = tone !== 'neutral' && toneLabel ? toneLabel : undefined
      const seed = seedInput.trim() ? Number(seedInput) : undefined
      const result = await generateSpeech({ text, language, voiceId, instruct, seed, responseFormat: 'mp3' })
      if (audioUrl) URL.revokeObjectURL(audioUrl)
      setAudioBlob(result.blob)
      setAudioUrl(URL.createObjectURL(result.blob))
      setLastSeed(result.seed)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-semibold tracking-tight">Speak</h1>
        <p className="text-sm text-muted-foreground">
          Type text, pick a voice, and hear it spoken.
        </p>
      </motion.div>

      <motion.div
        className="flex flex-col gap-5 rounded-xl border border-border bg-card p-6 text-card-foreground shadow-sm"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
      >
        <textarea
          data-testid="speak-text-input"
          className="min-h-48 resize-y rounded-lg border border-input bg-transparent p-4 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          placeholder="Say something..."
          value={text}
          onChange={(e) => setText(e.target.value)}
        />

        <div className="flex flex-wrap items-center gap-3">
          <VoiceSelector voices={voices} voiceId={voiceId} onChange={setVoiceId} />

          <Select value={language} onValueChange={setLanguage}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="English">English</SelectItem>
              <SelectItem value="Chinese">Chinese</SelectItem>
            </SelectContent>
          </Select>

          <Select value={tone} onValueChange={setTone}>
            <SelectTrigger className="w-44">
              <SelectValue placeholder="Tone" />
            </SelectTrigger>
            <SelectContent>
              {TONE_OPTIONS.map((t) => (
                <SelectItem key={t.id} value={t.id}>
                  {t.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Tooltip>
            <TooltipTrigger asChild>
              <Info className="size-3.5 shrink-0 text-muted-foreground" />
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-56">
              Voice is what it sounds like. Tone is how it delivers this line. Tone currently
              has no effect on the base voice-clone model — it's forwarded for
              forward-compatibility with CustomVoice.
            </TooltipContent>
          </Tooltip>

          <div className="flex items-center gap-1">
            <input
              type="number"
              inputMode="numeric"
              placeholder="Random seed"
              value={seedInput}
              onChange={(e) => setSeedInput(e.target.value)}
              className="h-9 w-32 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            />
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label="Randomize seed"
                  onClick={() => setSeedInput('')}
                  className="flex size-9 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
                >
                  <Dices className="size-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="top">
                Clear to use a fresh random seed next generation
              </TooltipContent>
            </Tooltip>
          </div>

          <Button
            type="button"
            data-testid="speak-generate-button"
            onClick={handleGenerate}
            disabled={!text.trim() || isGenerating}
          >
            {isGenerating ? 'Generating…' : 'Generate'}
          </Button>
        </div>

        {error && (
          <p data-testid="speak-error" className="text-sm text-destructive">
            {error}
          </p>
        )}

        {audioUrl && (
          <div data-testid="speak-result" className="flex flex-col gap-2">
            <AudioPlayer src={audioUrl} blob={audioBlob} />
            {lastSeed !== null && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>
                  Seed: <span className="font-mono text-foreground">{lastSeed}</span>
                </span>
                {seedInput !== String(lastSeed) && (
                  <button
                    type="button"
                    onClick={() => setSeedInput(String(lastSeed))}
                    className="underline decoration-dotted hover:text-foreground"
                  >
                    Lock this seed
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </motion.div>
    </div>
  )
}

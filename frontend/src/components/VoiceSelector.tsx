import type { VoiceMeta } from '../lib/api'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const MOUNTED_REF_SOURCE = 'mounted_ref_audio' as const

function isMountedRef(voice: VoiceMeta): boolean {
  return (voice as VoiceMeta & { source?: string }).source === MOUNTED_REF_SOURCE
}

function voiceNeedsReview(voice: VoiceMeta): boolean {
  if (voice.sample_text_source === 'user' && !voice.needs_review) return false
  const severity = voice.asr?.severity
  return Boolean(
    voice.needs_review ||
      severity === 'warn' ||
      severity === 'fail' ||
      severity === 'no_speech' ||
      severity === 'error',
  )
}

interface VoiceSelectorProps {
  voices: VoiceMeta[]
  voiceId: string | null
  onChange: (voiceId: string | null) => void
}

export function VoiceSelector({ voices, voiceId, onChange }: VoiceSelectorProps) {
  return (
    <Select value={voiceId ?? 'default'} onValueChange={(v) => onChange(v === 'default' ? null : v)}>
      <SelectTrigger className="min-w-48">
        <SelectValue placeholder="Default voice" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="default">Default voice</SelectItem>
        {voices.map((voice) => {
          const mounted = isMountedRef(voice)
          const review = voiceNeedsReview(voice)
          return (
            <SelectItem key={voice.voice_id} value={voice.voice_id}>
              <span className="flex items-center gap-1.5">
                <span>
                  {voice.description.length > 42
                    ? `${voice.description.slice(0, 42)}…`
                    : voice.description}
                </span>
                {mounted && (
                  <span className="inline-flex items-center rounded-full border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-cyan-400">
                    Mounted
                  </span>
                )}
                {review && (
                  <span className="inline-flex items-center rounded-full border border-amber-500/30 bg-amber-500/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-amber-300">
                    Review
                  </span>
                )}
              </span>
            </SelectItem>
          )
        })}
      </SelectContent>
    </Select>
  )
}

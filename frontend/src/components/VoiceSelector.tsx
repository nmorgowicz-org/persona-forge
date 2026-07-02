import type { VoiceMeta } from '../lib/api'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

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
        {voices.map((voice) => (
          <SelectItem key={voice.voice_id} value={voice.voice_id}>
            {voice.description.length > 48 ? `${voice.description.slice(0, 48)}…` : voice.description}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

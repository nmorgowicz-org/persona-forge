import type { VoiceMeta } from '@/lib/api'

interface SavedVoicePickerProps {
  voices: VoiceMeta[]
  selectedId: string | null
  onChange: (voiceId: string) => void
  search: string
  onSearchChange: (value: string) => void
}

export function SavedVoicePicker({ voices, selectedId, onChange, search, onSearchChange }: SavedVoicePickerProps) {
  const query = search.trim().toLowerCase()
  const matches = query
    ? voices.filter((voice) => [voice.voice_id, voice.display_name, voice.description].some((value) => value?.toLowerCase().includes(query)))
    : voices

  return (
    <div className="flex flex-col gap-2">
      <label className="text-xs font-medium text-muted-foreground" htmlFor="voice-edit-search">Saved voice</label>
      <input
        id="voice-edit-search"
        value={search}
        onChange={(event) => onSearchChange(event.currentTarget.value)}
        placeholder="Search saved voices…"
        className="h-9 rounded-md border border-border bg-background px-3 text-sm"
      />
      <select
        data-testid="voice-edit-picker"
        value={selectedId ?? ''}
        onChange={(event) => onChange(event.currentTarget.value)}
        className="h-10 rounded-md border border-border bg-background px-3 text-sm"
        aria-label="Choose a saved voice"
      >
        <option value="" disabled>Choose a saved voice</option>
        {matches.map((voice) => (
          <option key={voice.voice_id} value={voice.voice_id}>
            {voice.display_name || voice.description || voice.voice_id} — {voice.voice_id}
          </option>
        ))}
      </select>
    </div>
  )
}

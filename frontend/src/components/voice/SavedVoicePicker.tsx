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
  // Always keep the currently selected voice in the matches, even when the search
  // query filters it out, so the select doesn't blank to the placeholder while the
  // editor below is still editing it.
  const matches = query
    ? voices.filter((voice) =>
        voice.voice_id === selectedId ||
        [voice.voice_id, voice.display_name, voice.description].some((value) => value?.toLowerCase().includes(query)),
      )
    : voices

  return (
    <div className="flex flex-col gap-2">
      <label className="micro-label" htmlFor="voice-edit-search">Search</label>
      <input
        id="voice-edit-search"
        value={search}
        onChange={(event) => onSearchChange(event.currentTarget.value)}
        placeholder="Search saved voices…"
        className="h-9 rounded-md border border-border bg-background px-3 text-sm"
      />
      <label className="micro-label" htmlFor="voice-edit-picker">Saved voice</label>
      <select
        id="voice-edit-picker"
        data-testid="voice-edit-picker"
        value={selectedId ?? ''}
        onChange={(event) => onChange(event.currentTarget.value)}
        className="h-10 rounded-md border border-border bg-background px-3 text-sm"
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

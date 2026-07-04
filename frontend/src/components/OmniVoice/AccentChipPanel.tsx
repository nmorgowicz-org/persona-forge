import { AccentBank } from '@/components/AccentBank'
import { ChipButton } from '@/components/Chip'
import { ACCENT_BANK, type AccentBankEntry } from '@/lib/accentBank'
import {
  ACCENTS,
  AGES,
  GENDERS,
  PITCHES,
  STYLE_WHISPER,
  type OmniVoiceSelections,
} from '@/lib/omnivoiceChips'
import { ChipSection } from './ChipSection'

interface AccentChipPanelProps {
  selections: OmniVoiceSelections
  matchedAccentPresetId: string | null
  onSelectAccentPreset: (entry: AccentBankEntry) => void
  onToggleSingle: (key: 'gender' | 'age' | 'pitch' | 'accent', id: string) => void
  onToggleWhisper: () => void
}

// The chip-based OmniVoice instruct composer — left column of Persona Forge. Fully
// self-contained given the current selections + a handful of toggle callbacks, so it's
// split out of OmniVoicePanel.tsx to keep that file from growing further.
export function AccentChipPanel({
  selections,
  matchedAccentPresetId,
  onSelectAccentPreset,
  onToggleSingle,
  onToggleWhisper,
}: AccentChipPanelProps) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3 text-card-foreground shadow-sm">
      <div>
        <h2 className="text-[13px] font-semibold tracking-tight">
          Design an accent-cloned voice
        </h2>
        <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground">
          OmniVoice uses a fixed tag vocabulary — every
          option below is validated. Pick a starting
          preset, then adjust chips; the right panel
          always reflects the exact instruct string
          being sent.
        </p>
      </div>

      {ACCENT_BANK.length > 0 && (
        <AccentBank
          selectedId={matchedAccentPresetId}
          onSelect={onSelectAccentPreset}
        />
      )}

      <ChipSection title="Accent">
        <div className="flex flex-wrap gap-1.5">
          {ACCENTS.map((chip) => (
            <ChipButton
              key={chip.id}
              label={chip.label}
              selected={selections.accent === chip.id}
              onClick={() => onToggleSingle('accent', chip.id)}
            />
          ))}
        </div>
        <p className="mt-2 rounded-md bg-muted/60 px-2.5 py-2 text-[10px] leading-tight text-muted-foreground">
          Only Australian has a curated showcase-sentence
          bank (validated hands-on). Other accents use the
          same closed tag set but are not yet
          quality-checked.
        </p>
      </ChipSection>

      <ChipSection title="Demographics">
        <div className="flex flex-wrap gap-1.5">
          {GENDERS.map((chip) => (
            <ChipButton
              key={chip.id}
              label={chip.label}
              selected={selections.gender === chip.id}
              onClick={() => onToggleSingle('gender', chip.id)}
            />
          ))}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {AGES.map((chip) => (
            <ChipButton
              key={chip.id}
              label={chip.label}
              selected={selections.age === chip.id}
              onClick={() => onToggleSingle('age', chip.id)}
            />
          ))}
        </div>
      </ChipSection>

      <ChipSection title="Pitch">
        <div className="flex flex-wrap gap-1.5">
          {PITCHES.map((chip) => (
            <ChipButton
              key={chip.id}
              label={chip.label}
              selected={selections.pitch === chip.id}
              onClick={() => onToggleSingle('pitch', chip.id)}
            />
          ))}
        </div>
        <p className="mt-1.5 text-[10px] text-muted-foreground">
          "High pitch" trends tinnier in testing —
          "moderate" is usually the safer default.
        </p>
      </ChipSection>

      <ChipSection title="Style">
        <div className="flex flex-wrap gap-1.5">
          <ChipButton
            label={STYLE_WHISPER.label}
            selected={selections.whisper}
            onClick={onToggleWhisper}
          />
        </div>
        <p className="mt-1.5 text-[10px] text-muted-foreground">
          The only style tag OmniVoice documents — there's
          no "warm" or "sweet" here (that's
          VoiceDesign-only).
        </p>
      </ChipSection>
    </div>
  )
}

import { useId, useMemo, useState } from 'react'
import { Check, ChevronDown, Plus, Search, Star } from 'lucide-react'
import type { BuiltInVoiceMeta, VoiceMeta } from '../lib/api'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store'
import { readFavoriteVoiceIds, toggleFavoriteVoice } from '@/lib/voiceFavorites'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

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

function getSourceBadge(source?: string) {
  const sources: Record<string, { label: string; color: string }> = {
    VoiceDesign: {
      label: 'VoiceDesign',
      color: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
    },
    OmniVoice: {
      label: 'OmniVoice',
      color: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30',
    },
    Upload: {
      label: 'Upload',
      color: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
    },
    Pocket: {
      label: 'Pocket',
      color: 'bg-warning/10 text-warning border-warning/30',
    },
  }
  const config = sources[source || '']
  if (!config) return null
  return (
    <Badge
      variant="outline"
      className={`border px-1 py-0 text-[9px] font-medium uppercase tracking-wide ${config.color}`}
    >
      {config.label}
    </Badge>
  )
}

interface VoiceSelectorProps {
  voices: VoiceMeta[]
  builtInVoices?: BuiltInVoiceMeta[]
  voiceId: string | null
  onChange: (voiceId: string | null) => void
}

interface VoiceOption {
  id: string | null
  label: string
  hint?: string
  group: 'default' | 'favorites' | 'voices' | 'builtin'
  voice?: VoiceMeta
  builtin?: BuiltInVoiceMeta
  index: number
}

interface VoiceOptionSection {
  key: string
  label: string
  familyId?: string
  familyName?: string
  options: VoiceOption[]
}

function voiceLabel(voice: VoiceMeta): string {
  const label = voice.description || voice.display_name || voice.voice_id
  return label.length > 42 ? `${label.slice(0, 42)}…` : label
}

export function VoiceSelector({
  voices,
  builtInVoices = [],
  voiceId,
  onChange,
}: VoiceSelectorProps) {
  const labelId = useId()
  const listboxId = useId()
  const setPage = useAppStore((s) => s.setPage)
  const setTargetFamilyId = useAppStore((s) => s.setTargetFamilyId)
  const setDesignEngine = useAppStore((s) => s.setDesignEngine)

  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [highlight, setHighlight] = useState(0)
  const [favoriteIds, setFavoriteIds] = useState<string[]>(() => readFavoriteVoiceIds())

  const sections = useMemo(() => {
    const q = query.trim().toLowerCase()
    const matches = (id: string, label: string, hint?: string) =>
      !q ||
      id.toLowerCase().includes(q) ||
      label.toLowerCase().includes(q) ||
      Boolean(hint && hint.toLowerCase().includes(q))

    const result: VoiceOptionSection[] = []
    let index = 0
    const next = (
      group: VoiceOption['group'],
      id: string | null,
      label: string,
      hint?: string,
      voice?: VoiceMeta,
      builtin?: BuiltInVoiceMeta,
    ): VoiceOption => ({ group, id, label, hint, voice, builtin, index: index++ })

    const families = new Map<string, VoiceMeta[]>()
    const uncategorized: VoiceMeta[] = []
    voices.forEach((voice) => {
      if (voice.family_id) {
        if (!families.has(voice.family_id)) families.set(voice.family_id, [])
        families.get(voice.family_id)!.push(voice)
      } else {
        uncategorized.push(voice)
      }
    })

    const buildVoiceOption = (voice: VoiceMeta) =>
      next(
        'voices',
        voice.voice_id,
        voice.variant_name
          ? `${voice.variant_name}: ${voiceLabel(voice)}`
          : voiceLabel(voice),
        voice.language,
        voice,
      )

    const favoriteOptions: VoiceOption[] = []
    voices.forEach((voice) => {
      if (!favoriteIds.includes(voice.voice_id)) return
      if (!matches(voice.voice_id, voiceLabel(voice), voice.language)) return
      favoriteOptions.push({ ...buildVoiceOption(voice), group: 'favorites' })
    })
    builtInVoices.forEach((voice) => {
      if (!favoriteIds.includes(voice.voice_id)) return
      if (!matches(voice.voice_id, voice.display_name, voice.language)) return
      favoriteOptions.push({
        group: 'favorites',
        id: voice.voice_id,
        label: voice.display_name,
        hint: `${voice.language} · built-in`,
        builtin: voice,
        index: 0,
      })
    })

    if (!q) {
      result.push({
        key: 'default',
        label: 'Runtime default',
        options: [next('default', null, 'Runtime default', 'Mounted reference audio')],
      })
    }
    if (favoriteOptions.length > 0) {
      result.push({ key: 'favorites', label: 'Favorites', options: favoriteOptions })
    }

    families.forEach((familyVoices, familyId) => {
      const options = familyVoices
        .filter((voice) =>
          matches(voice.voice_id, voiceLabel(voice), voice.language),
        )
        .map(buildVoiceOption)
      if (options.length === 0) return
      result.push({
        key: `family-${familyId}`,
        label: familyVoices[0].display_name || familyId,
        familyId,
        familyName: familyVoices[0].display_name || familyId,
        options,
      })
    })

    const generalOptions = uncategorized
      .filter((voice) => matches(voice.voice_id, voiceLabel(voice), voice.language))
      .map(buildVoiceOption)
    if (generalOptions.length > 0) {
      result.push({ key: 'general', label: 'My voices', options: generalOptions })
    }

    const builtInsByCategory = new Map<string, BuiltInVoiceMeta[]>()
    builtInVoices.forEach((voice) => {
      if (!matches(voice.voice_id, voice.display_name, voice.language)) return
      const category = voice.category || 'other'
      if (!builtInsByCategory.has(category)) builtInsByCategory.set(category, [])
      builtInsByCategory.get(category)!.push(voice)
    })
    const categoryOrder = ['conversation', 'reading', 'multilingual', 'other']
    Array.from(builtInsByCategory.entries())
      .sort(
        ([a], [b]) =>
          (categoryOrder.indexOf(a) === -1 ? 99 : categoryOrder.indexOf(a)) -
          (categoryOrder.indexOf(b) === -1 ? 99 : categoryOrder.indexOf(b)),
      )
      .forEach(([category, categoryVoices]) => {
        result.push({
          key: `builtin-${category}`,
          label: `Built-in · ${category}`,
          options: categoryVoices.map((voice) =>
            next(
              'builtin',
              voice.voice_id,
              voice.display_name,
              `${voice.language} · built-in`,
              undefined,
              voice,
            ),
          ),
        })
      })

    // Reassign indices after merging favorites so keyboard order matches render order.
    index = 0
    result.forEach((section) => {
      section.options.forEach((option) => {
        option.index = index++
      })
    })
    return result
  }, [voices, builtInVoices, favoriteIds, query])

  const flatOptions = useMemo(
    () => sections.flatMap((section) => section.options),
    [sections],
  )
  const activeIndex =
    flatOptions.length === 0 ? 0 : Math.min(highlight, flatOptions.length - 1)

  const selected = flatOptions.find((option) => option.id === voiceId)
  const triggerLabel = selected?.label ?? 'Runtime default'

  function choose(option: VoiceOption) {
    onChange(option.id)
    setOpen(false)
    setQuery('')
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlight((current) => Math.min(current + 1, flatOptions.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlight((current) => Math.max(current - 1, 0))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      const option = flatOptions[activeIndex]
      if (option) choose(option)
    } else if (event.key === 'Home') {
      event.preventDefault()
      setHighlight(0)
    } else if (event.key === 'End') {
      event.preventDefault()
      setHighlight(Math.max(flatOptions.length - 1, 0))
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <span id={labelId} className="micro-label">
        Selected in Speak
      </span>
      <Popover
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (next) {
            setFavoriteIds(readFavoriteVoiceIds())
            setQuery('')
            setHighlight(0)
          }
        }}
      >
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            aria-controls={listboxId}
            aria-labelledby={labelId}
            className="min-w-56 justify-between font-normal"
            data-testid="voice-selector-trigger"
          >
            <span className="flex min-w-0 items-center gap-1.5">
              <span className="truncate">{triggerLabel}</span>
              {selected?.hint && (
                <span className="truncate text-[10px] text-muted-foreground">
                  {selected.hint}
                </span>
              )}
            </span>
            <ChevronDown className="opacity-60" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-96 p-0">
          <div className="flex items-center gap-2 border-b border-border px-2 py-2">
            <Search className="size-3.5 shrink-0 text-muted-foreground" />
            <Input
              autoFocus
              value={query}
              onChange={(event) => {
                setQuery(event.target.value)
                setHighlight(0)
              }}
              onKeyDown={handleKeyDown}
              placeholder="Search voices"
              aria-label="Search voices"
              aria-controls={listboxId}
              aria-activedescendant={
                flatOptions[activeIndex] ? `voice-option-${flatOptions[activeIndex].index}` : undefined
              }
              className="h-7 border-0 bg-transparent px-0 shadow-none focus-visible:ring-0"
            />
          </div>
          <div
            id={listboxId}
            role="listbox"
            aria-label="Voices"
            className="max-h-80 overflow-y-auto p-1"
          >
            {sections.length === 0 ? (
              <p className="px-2 py-6 text-center text-xs text-muted-foreground">
                No voices match “{query}”.
              </p>
            ) : (
              sections.map((section) => (
                <div key={section.key} role="group" aria-label={section.label}>
                  <div className="flex items-center justify-between px-2 py-1">
                    <span className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                      {section.label}
                    </span>
                    {section.familyId && (
                      <button
                        type="button"
                        title={`Create variant for ${section.familyName}`}
                        onClick={() => {
                          setTargetFamilyId(section.familyId!)
                          setDesignEngine('omnivoice')
                          setPage('voice-design')
                          setOpen(false)
                        }}
                        className="flex items-center gap-1 text-[10px] text-muted-foreground transition-colors hover:text-cyan-400"
                      >
                        <Plus className="size-3" /> Variant
                      </button>
                    )}
                  </div>
                  {section.options.map((option) => {
                    const active = option.id === voiceId
                    const isFavorite = option.id ? favoriteIds.includes(option.id) : false
                    return (
                      <div
                        key={`${option.group}-${option.id ?? 'default'}`}
                        id={`voice-option-${option.index}`}
                        role="option"
                        aria-selected={active}
                        tabIndex={-1}
                        onMouseEnter={() => setHighlight(option.index)}
                        onClick={() => choose(option)}
                        className={cn(
                          'flex cursor-pointer items-center gap-2 rounded-control px-2 py-1.5 text-xs',
                          option.index === activeIndex && 'bg-muted',
                          active && 'ring-1 ring-cyan-500/50 bg-cyan-500/5',
                        )}
                      >
                        <span className="flex min-w-0 flex-1 flex-col">
                          <span className="flex items-center gap-1.5">
                            <span className="truncate">{option.label}</span>
                            {option.voice && getSourceBadge(option.voice.source)}
                            {option.builtin && (
                              <Badge variant="outline" className="text-[9px]">
                                Pocket
                              </Badge>
                            )}
                          </span>
                          {option.hint && (
                            <span className="truncate text-[10px] text-muted-foreground">
                              {option.hint}
                            </span>
                          )}
                        </span>

                        {option.voice && isMountedRef(option.voice) && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-px text-[9px] font-medium tracking-wide text-cyan-400 uppercase">
                                Mounted
                              </span>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="max-w-48">
                              This voice is backed by the mounted reference audio on the host.
                            </TooltipContent>
                          </Tooltip>
                        )}
                        {option.voice && voiceNeedsReview(option.voice) && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span className="rounded-full border border-warning/30 bg-warning/10 px-1.5 py-px text-[9px] font-medium tracking-wide text-warning uppercase">
                                Review
                              </span>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="max-w-48">
                              The reference has been flagged for potential quality issues.
                            </TooltipContent>
                          </Tooltip>
                        )}
                        {active && <Check className="size-3.5 shrink-0 text-primary" />}
                        {option.id && (
                          <button
                            type="button"
                            aria-label={
                              isFavorite ? 'Remove from favorites' : 'Add to favorites'
                            }
                            aria-pressed={isFavorite}
                            onClick={(event) => {
                              event.stopPropagation()
                              setFavoriteIds(toggleFavoriteVoice(option.id!))
                            }}
                            className={cn(
                              'shrink-0 rounded p-0.5 hover:bg-background/60',
                              isFavorite ? 'text-warning' : 'text-muted-foreground',
                            )}
                          >
                            <Star
                              className={cn('size-3.5', isFavorite && 'fill-current')}
                            />
                          </button>
                        )}
                      </div>
                    )
                  })}
                </div>
              ))
            )}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}

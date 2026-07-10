import { Plus } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { BuiltInVoiceMeta, VoiceMeta } from '../lib/api'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { useAppStore } from '@/store'

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
    'VoiceDesign': { label: 'VoiceDesign', color: 'bg-purple-500/10 text-purple-400 border-purple-500/30' },
    'OmniVoice': { label: 'OmniVoice', color: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30' },
    'Upload': { label: 'Upload', color: 'bg-slate-500/10 text-slate-400 border-slate-500/30' },
    'Pocket': { label: 'Pocket', color: 'bg-amber-500/10 text-amber-400 border-amber-500/30' },
  }
  const config = sources[source || '']
  if (!config) return null
  return (
    <Badge variant="outline" className={`border px-1 py-0 text-[9px] font-medium uppercase tracking-wide ${config.color}`}>
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

function voiceLabel(voice: VoiceMeta): string {
  const description = voice.description || voice.display_name || voice.voice_id
  return description.length > 30 ? `${description.slice(0, 30)}...` : description
}

function categoryLabel(category: string): string {
  const labels: Record<string, string> = {
    conversation: 'Pocket built-ins: conversation',
    reading: 'Pocket built-ins: reading',
    multilingual: 'Pocket built-ins: multilingual',
    other: 'Pocket built-ins: other',
  }
  return labels[category] ?? `Pocket built-ins: ${category}`
}

export function VoiceSelector({ voices, builtInVoices = [], voiceId, onChange }: VoiceSelectorProps) {
  const setPage = useAppStore((s) => s.setPage)
  const setTargetFamilyId = useAppStore((s) => s.setTargetFamilyId)
  const setDesignEngine = useAppStore((s) => s.setDesignEngine)

  // Group voices by family_id
  const families = new Map<string, VoiceMeta[]>()
  const uncategorized: VoiceMeta[] = []

  voices.forEach((v) => {
    if (v.family_id) {
      if (!families.has(v.family_id)) families.set(v.family_id, [])
      families.get(v.family_id)!.push(v)
    } else {
      uncategorized.push(v)
    }
  })

  const builtInsByCategory = new Map<string, BuiltInVoiceMeta[]>()
  builtInVoices.forEach((voice) => {
    const category = voice.category || 'other'
    if (!builtInsByCategory.has(category)) builtInsByCategory.set(category, [])
    builtInsByCategory.get(category)!.push(voice)
  })
  const categoryOrder = ['conversation', 'reading', 'multilingual', 'other']
  const builtInCategories = Array.from(builtInsByCategory.entries()).sort(
    ([a], [b]) => {
      const ai = categoryOrder.indexOf(a)
      const bi = categoryOrder.indexOf(b)
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi) || a.localeCompare(b)
    },
  )

  return (
    <Select value={voiceId ?? 'default'} onValueChange={(v) => onChange(v === 'default' ? null : v)}>
      <SelectTrigger className="min-w-48">
        <SelectValue placeholder="Default voice" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="default">Default voice</SelectItem>

        {builtInCategories.map(([category, categoryVoices]) => (
          <div key={category}>
            <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground opacity-70">
              {categoryLabel(category)}
            </div>
            {categoryVoices.map((voice) => {
              const isActive = voiceId === voice.voice_id
              return (
                <SelectItem
                  key={voice.voice_id}
                  value={voice.voice_id}
                  className={isActive ? 'ring-1 ring-cyan-500/50 bg-cyan-500/5' : ''}
                >
                  <span className="flex items-center gap-1.5">
                    <span className="truncate max-w-[140px]">{voice.display_name}</span>
                    {getSourceBadge('Pocket')}
                    <span className="inline-flex items-center rounded-full border border-slate-500/30 bg-slate-500/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-slate-300">
                      {voice.language_code}
                    </span>
                    <span className="hidden max-w-[110px] truncate text-[10px] text-muted-foreground sm:inline">
                      {voice.note}
                    </span>
                  </span>
                </SelectItem>
              )
            })}
            <Separator className="my-1" />
          </div>
        ))}

        {/* Categorized Families */}
            {Array.from(families.entries()).map(([familyId, familyVoices]) => {
              const familyName = familyVoices[0].display_name || familyId
              return (
                <div key={familyId}>
                  <div className="flex items-center justify-between px-2 py-1.5">
                    <div className="text-xs font-semibold text-muted-foreground opacity-70">
                      {familyName}
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setTargetFamilyId(familyId)
                        setDesignEngine('omnivoice')
                        setPage('voice-design')
                      }}
                       className="group flex items-center gap-1 text-muted-foreground transition-colors hover:text-cyan-400"
                      title={`Create variant for ${familyName}`}
                    >
                       <Plus className="h-3 w-3" />
                                             <span className="text-pretty text-[10px] hidden group-hover:inline">Add Variant</span>
                    </button>

                  </div>
                  {familyVoices.map((voice) => {
                    const mounted = isMountedRef(voice)
                    const review = voiceNeedsReview(voice)
                    const isActive = voiceId === voice.voice_id
                    return (
                      <SelectItem
                        key={voice.voice_id}
                        value={voice.voice_id}
                        className={isActive ? 'ring-1 ring-cyan-500/50 bg-cyan-500/5' : ''}
                      >
                        <span className="flex items-center gap-1.5">
                          <span className="truncate max-w-[140px]">
	                            {voice.variant_name ? `${voice.variant_name}: ` : ''}
	                            {voiceLabel(voice)}
                          </span>
                          {getSourceBadge(voice.source)}
                          {voice.variant_name && (
                            <span className="inline-flex items-center rounded-full border border-amber-500/30 bg-amber-500/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-amber-300">
                              {voice.variant_name}
                            </span>
                          )}
                          {mounted && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="inline-flex items-center rounded-full border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-cyan-400">
                                  Mounted
                                </span>
                              </TooltipTrigger>
                               <TooltipContent side="top" className="max-w-48">
                                This voice is directly backed by the mounted reference audio on the host system.
                              </TooltipContent>
                            </Tooltip>
                          )}
                          {review && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="inline-flex items-center rounded-full border border-amber-500/30 bg-amber-500/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-amber-300">
                                  Review
                                </span>
                              </TooltipTrigger>
                               <TooltipContent side="top" className="max-w-48">
                                This reference has been flagged for potential quality issues (clipping, silence, or low SNR).
                              </TooltipContent>
                            </Tooltip>
                          )}
                        </span>
                      </SelectItem>
                    )
                  })}
              <Separator className="my-1" />
            </div>
          )
        })}

        {/* Uncategorized */}
        {uncategorized.length > 0 && (
          <>
            {uncategorized.length > 0 && (
              <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground opacity-70">
                General
              </div>
            )}
            {uncategorized.map((voice) => {
              const mounted = isMountedRef(voice)
              const review = voiceNeedsReview(voice)
              const isActive = voiceId === voice.voice_id
              return (
                <SelectItem
                  key={voice.voice_id}
                  value={voice.voice_id}
                  className={isActive ? 'ring-1 ring-cyan-500/50 bg-cyan-500/5' : ''}
                >
                  <span className="flex items-center gap-1.5">
                    <span className="truncate max-w-[140px]">
	                      {voiceLabel(voice)}
                    </span>
                    {getSourceBadge(voice.source)}
{mounted && (
  <Tooltip>
    <TooltipTrigger asChild>
       <span className="inline-flex items-center rounded-full border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-cyan-400">
        Mounted
      </span>
    </TooltipTrigger>
     <TooltipContent side="top" className="max-w-48">
      Reference directly mounted from host system.
    </TooltipContent>
  </Tooltip>
)}
{review && (
  <Tooltip>
    <TooltipTrigger asChild>
       <span className="inline-flex items-center rounded-full border border-amber-500/30 bg-amber-500/10 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-amber-300">
        Review
      </span>
    </TooltipTrigger>
     <TooltipContent side="top" className="max-w-48">
      Reference flagged for quality issues.
    </TooltipContent>
  </Tooltip>
)}
                  </span>
                </SelectItem>
              )
            })}
            <Separator className="my-1" />
          </>
        )}
      </SelectContent>
    </Select>
  )
}

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Settings2 } from 'lucide-react'
import { getRuntimeConfig, updateRuntimeConfig, type RuntimeConfigState } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Toggle } from '@/components/ui/toggle'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

type LiveDraft = RuntimeConfigState['live']

export function RuntimeConfigPage() {
  const [state, setState] = useState<RuntimeConfigState | null>(null)
  const [draft, setDraft] = useState<LiveDraft | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)

  function refresh() {
    getRuntimeConfig()
      .then((s) => {
        setState(s)
        setDraft(s.live)
        setError(null)
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }

  useEffect(() => {
    refresh()
  }, [])

  async function apply() {
    if (!draft || !state) return
    // Only send keys that actually changed — TTS_BACKEND/OV_DYNAMIC_QUANT_GROUP_SIZE trigger
    // a full model reload, so a no-op change shouldn't pay that cost.
    const changed: Partial<LiveDraft> = {}
    for (const key of Object.keys(draft) as (keyof LiveDraft)[]) {
      if (draft[key] !== state.live[key]) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ;(changed as any)[key] = draft[key]
      }
    }
    if (Object.keys(changed).length === 0) return
    setApplying(true)
    setError(null)
    try {
      const next = await updateRuntimeConfig(changed)
      setState(next)
      setDraft(next.live)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setApplying(false)
    }
  }

  const dirty = Boolean(
    draft && state && (Object.keys(draft) as (keyof LiveDraft)[]).some((k) => draft[k] !== state.live[k]),
  )

  return (
    <div className="flex flex-col gap-6">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-semibold tracking-tight">Runtime</h1>
        <p className="text-sm text-muted-foreground">
          Live knobs for how this container is running right now. Changes to backend or
          quantization briefly reload the model — in-flight requests wait, they don't fail.
        </p>
      </motion.div>

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {state?.reconfig_in_progress && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
          Reconfiguration in progress — the model is reloading.
        </div>
      )}

      {draft && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col gap-5 rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm"
        >
          <div className="flex items-center gap-2">
            <Settings2 className="size-4 text-primary" />
            <p className="text-sm font-semibold">Live-adjustable</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Backend (reloads model)
              </label>
              <Select
                value={draft.TTS_BACKEND}
                onValueChange={(v) => setDraft({ ...draft, TTS_BACKEND: v })}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="openvino">openvino</SelectItem>
                  <SelectItem value="pytorch">pytorch</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Idle unload (seconds, 0 = disabled)
              </label>
              <Input
                type="number"
                min={0}
                value={draft.IDLE_UNLOAD_SECONDS}
                onChange={(e) =>
                  setDraft({ ...draft, IDLE_UNLOAD_SECONDS: Number(e.target.value) })
                }
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                OV dynamic quant group size (reloads model)
              </label>
              <Input
                type="number"
                min={0}
                value={draft.OV_DYNAMIC_QUANT_GROUP_SIZE}
                onChange={(e) =>
                  setDraft({ ...draft, OV_DYNAMIC_QUANT_GROUP_SIZE: Number(e.target.value) })
                }
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-muted-foreground">Silence trim</label>
              <Toggle
                variant="outline"
                pressed={draft.SILENCE_TRIM}
                onPressedChange={(v) => setDraft({ ...draft, SILENCE_TRIM: v })}
                className="w-fit"
              >
                {draft.SILENCE_TRIM ? 'On' : 'Off'}
              </Toggle>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Silence trim threshold (fraction of peak)
              </label>
              <Input
                type="number"
                step="0.001"
                min={0}
                max={1}
                value={draft.SILENCE_TRIM_THRESH}
                onChange={(e) =>
                  setDraft({ ...draft, SILENCE_TRIM_THRESH: Number(e.target.value) })
                }
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Silence trim pad (ms)
              </label>
              <Input
                type="number"
                min={0}
                value={draft.SILENCE_TRIM_PAD_MS}
                onChange={(e) =>
                  setDraft({ ...draft, SILENCE_TRIM_PAD_MS: Number(e.target.value) })
                }
              />
            </div>
          </div>

          <div className="flex justify-end">
            <Button onClick={apply} disabled={!dirty || applying}>
              {applying ? 'Applying…' : 'Apply'}
            </Button>
          </div>
        </motion.div>
      )}

      {state && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm"
        >
          <p className="text-sm font-semibold">Read-only — set by the container, not this app</p>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(state.read_only.mounts).map(([name, mode]) => (
              <Badge key={name} variant="outline" className="font-mono text-[11px]">
                {name}: {mode ?? 'unavailable'}
              </Badge>
            ))}
            <Badge variant="outline" className="font-mono text-[11px]">
              ref_audio: {state.read_only.ref_audio_path_set ? 'set' : 'unset'}
            </Badge>
            <Badge variant="outline" className="font-mono text-[11px]">
              hf_token: {state.read_only.hf_token_set ? 'set' : 'unset'}
            </Badge>
            <Badge variant="outline" className="font-mono text-[11px]">
              device: {state.read_only.device}
            </Badge>
            <Badge variant="outline" className="font-mono text-[11px]">
              torch_dtype: {state.read_only.torch_dtype}
            </Badge>
          </div>
        </motion.div>
      )}

      {state && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm"
        >
          <p className="text-sm font-semibold">Requires re-export</p>
          <p className="text-xs text-muted-foreground">{state.not_live.reason}</p>
          <div className="flex flex-wrap gap-1.5">
            <Badge variant="outline" className="font-mono text-[11px] opacity-60">
              TTS_MAX_SPEECH_SECONDS: {state.not_live.TTS_MAX_SPEECH_SECONDS ?? 'default'}
            </Badge>
            <Badge variant="outline" className="font-mono text-[11px] opacity-60">
              MODEL_SIZE: {state.not_live.MODEL_SIZE ?? 'default'}
            </Badge>
            <Badge variant="outline" className="font-mono text-[11px] opacity-60">
              compression: {state.not_live.compression ?? 'n/a'}
            </Badge>
          </div>
        </motion.div>
      )}
    </div>
  )
}

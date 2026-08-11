import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Settings2, Cpu } from 'lucide-react'
import { getRuntimeConfig, updateRuntimeConfig, type RuntimeConfigState } from '@/lib/api'
import { AcceleratorCoachCard } from '@/components/AcceleratorCoachCard'
import { useAppStore } from '@/store'
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

// D7: "Show advanced" only hides via CSS — it must never conditionally unmount power-user
// controls, so a collapsed Expert section still exists in the DOM.
function expertClass(expertMode: boolean) {
  return expertMode ? '' : 'hidden'
}

// Phase A7b's `live_metadata` is additive/optional — every consumer must degrade gracefully
// when it's absent (e.g. talking to a backend that predates A7b).
type LiveKeyMeta = { source: 'file' | 'env' | 'default'; locked: boolean; restart_required: boolean }

function KeyBadges({ meta }: { meta: LiveKeyMeta | undefined }) {
  if (!meta) return null
  return (
    <div className="flex flex-wrap items-center gap-1">
      <Badge variant="outline" className="text-[9px] px-1 py-0 font-mono">
        {meta.source}
      </Badge>
      {meta.locked && (
        <Badge variant="secondary" className="text-[9px] px-1 py-0">
          env-locked
        </Badge>
      )}
      <Badge variant="outline" className="text-[9px] px-1 py-0">
        {meta.restart_required ? 'needs restart' : 'applies live'}
      </Badge>
    </div>
  )
}

export function RuntimeConfigPage() {
  const [state, setState] = useState<RuntimeConfigState | null>(null)
  const [draft, setDraft] = useState<LiveDraft | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const [redetecting, setRedetecting] = useState(false)
  const [expertMode, setExpertMode] = useState(false)
  const setRuntimeConfig = useAppStore((s) => s.setRuntimeConfig)

  const refresh = useCallback(() => {
    return getRuntimeConfig()
      .then((s) => {
        setState(s)
        setDraft(s.live)
        setError(null)
        setRuntimeConfig({
          runtimeTtsBackend: s.live.TTS_BACKEND,
          pocketTtsVoiceCloningAvailable: s.live.pocket_tts_voice_cloning_available,
        })
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [setRuntimeConfig])

  async function redetect() {
    setRedetecting(true)
    try {
      await refresh()
    } finally {
      setRedetecting(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [refresh])

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
      setRuntimeConfig({
        runtimeTtsBackend: next.live.TTS_BACKEND,
        pocketTtsVoiceCloningAvailable: next.live.pocket_tts_voice_cloning_available,
      })
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
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start justify-between gap-4"
      >
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Runtime</h1>
          <p className="text-sm text-muted-foreground">
            Live knobs for how this container is running right now. Changes to backend or
            quantization briefly reload the model — in-flight requests wait, they don't fail.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setExpertMode((v) => !v)}>
          {expertMode ? 'Hide advanced' : 'Show advanced'}
        </Button>
      </motion.div>

      {state?.accelerator && (
        <AcceleratorCoachCard
          accelerator={state.accelerator}
          onRedetect={redetect}
          redetecting={redetecting}
        />
      )}

      {state?.accelerator && (
        <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm">
          <div className="flex items-center gap-2">
            <Cpu className="size-4 text-primary" />
            <p className="text-sm font-semibold">Detected accelerator</p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Badge variant="outline" className="font-mono text-[11px]">
              family: {state.accelerator.detected_family}
            </Badge>
            <Badge variant="outline" className="font-mono text-[11px]">
              device: {state.accelerator.device}
            </Badge>
            <Badge variant="outline" className="font-mono text-[11px]">
              capable: {state.accelerator.capable ? 'yes' : 'no'}
            </Badge>
            <span className={expertClass(expertMode)}>
              <Badge variant="outline" className="font-mono text-[11px]">
                has_fp64: {state.accelerator.has_fp64 == null ? 'n/a' : String(state.accelerator.has_fp64)}
              </Badge>
              <Badge variant="outline" className="ml-1.5 font-mono text-[11px]">
                fp64_emulation: {state.accelerator.emu_active ? 'active' : 'off'}
              </Badge>
            </span>
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {state?.reconfig_in_progress && (
        <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
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
              <div className="flex items-center justify-between gap-2">
                <label className="text-xs font-medium text-muted-foreground">
                  Backend (reloads model)
                </label>
                <span className={expertClass(expertMode)}>
                  <KeyBadges meta={state?.live_metadata?.TTS_BACKEND} />
                </span>
              </div>
              <Select
                value={draft.TTS_BACKEND}
                disabled={state?.live_metadata?.TTS_BACKEND?.locked}
                onValueChange={(v) => {
                  const nextBackend = v as string
                  const prevBackend = draft.TTS_BACKEND
                  let dtype = draft.MODEL_DTYPE

                  // If switching away from openvino and currently bf16, default to float32.
                  if (prevBackend === 'openvino' && nextBackend !== 'openvino' && dtype === 'bfloat16') {
                    dtype = 'float32'
                  }

                  setDraft({ ...draft, TTS_BACKEND: nextBackend, MODEL_DTYPE: dtype })
                }}
              >
                <SelectTrigger
                  className="w-full"
                  title={state?.live_metadata?.TTS_BACKEND?.locked ? 'Locked by container env var' : undefined}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="openvino">openvino</SelectItem>
                  <SelectItem value="pytorch">pytorch</SelectItem>
                  <SelectItem value="pocket_tts">
                    pocket_tts (small, fast, experimental)
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between gap-2">
                <label className="text-xs font-medium text-muted-foreground">
                  Idle unload (seconds, 0 = disabled)
                </label>
                <span className={expertClass(expertMode)}>
                  <KeyBadges meta={state?.live_metadata?.IDLE_UNLOAD_SECONDS} />
                </span>
              </div>
              <Input
                type="number"
                min={0}
                value={draft.IDLE_UNLOAD_SECONDS}
                disabled={state?.live_metadata?.IDLE_UNLOAD_SECONDS?.locked}
                title={
                  state?.live_metadata?.IDLE_UNLOAD_SECONDS?.locked
                    ? 'Locked by container env var'
                    : undefined
                }
                onChange={(e) =>
                  setDraft({ ...draft, IDLE_UNLOAD_SECONDS: Number(e.target.value) })
                }
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between gap-2">
                <label className="text-xs font-medium text-muted-foreground">
                  OV dynamic quant group size (reloads model)
                </label>
                <span className={expertClass(expertMode)}>
                  <KeyBadges meta={state?.live_metadata?.OV_DYNAMIC_QUANT_GROUP_SIZE} />
                </span>
              </div>
              <Input
                type="number"
                min={0}
                value={draft.OV_DYNAMIC_QUANT_GROUP_SIZE}
                disabled={state?.live_metadata?.OV_DYNAMIC_QUANT_GROUP_SIZE?.locked}
                title={
                  state?.live_metadata?.OV_DYNAMIC_QUANT_GROUP_SIZE?.locked
                    ? 'Locked by container env var'
                    : undefined
                }
                onChange={(e) =>
                  setDraft({ ...draft, OV_DYNAMIC_QUANT_GROUP_SIZE: Number(e.target.value) })
                }
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between gap-2">
                <label className="text-xs font-medium text-muted-foreground">
                  Model dtype (reloads model)
                </label>
                <span className={expertClass(expertMode)}>
                  <KeyBadges meta={state?.live_metadata?.MODEL_DTYPE} />
                </span>
              </div>
              {draft.TTS_BACKEND === 'openvino' ? (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>bf16</span>
                  <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                    required
                  </Badge>
                </div>
              ) : (
                <Select
                  value={draft.MODEL_DTYPE}
                  disabled={state?.live_metadata?.MODEL_DTYPE?.locked}
                  onValueChange={(v) => setDraft({ ...draft, MODEL_DTYPE: v })}
                >
                  <SelectTrigger
                    className="w-full"
                    title={state?.live_metadata?.MODEL_DTYPE?.locked ? 'Locked by container env var' : undefined}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="float32">
                      fp32 (safer, usually required on many CPUs)
                    </SelectItem>
                    <SelectItem value="bfloat16">
                      bf16 (faster if supported, may fail)
                    </SelectItem>
                  </SelectContent>
                </Select>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between gap-2">
                <label className="text-xs font-medium text-muted-foreground">Silence trim</label>
                <span className={expertClass(expertMode)}>
                  <KeyBadges meta={state?.live_metadata?.SILENCE_TRIM} />
                </span>
              </div>
              <Toggle
                variant="outline"
                pressed={draft.SILENCE_TRIM}
                disabled={state?.live_metadata?.SILENCE_TRIM?.locked}
                onPressedChange={(v) => setDraft({ ...draft, SILENCE_TRIM: v })}
                className="w-fit"
              >
                {draft.SILENCE_TRIM ? 'On' : 'Off'}
              </Toggle>
            </div>

            <div className={`flex flex-col gap-1.5 ${expertClass(expertMode)}`}>
              <div className="flex items-center justify-between gap-2">
                <label className="text-xs font-medium text-muted-foreground">
                  Silence trim threshold (fraction of peak)
                </label>
                <KeyBadges meta={state?.live_metadata?.SILENCE_TRIM_THRESH} />
              </div>
              <Input
                type="number"
                step="0.001"
                min={0}
                max={1}
                value={draft.SILENCE_TRIM_THRESH}
                disabled={state?.live_metadata?.SILENCE_TRIM_THRESH?.locked}
                onChange={(e) =>
                  setDraft({ ...draft, SILENCE_TRIM_THRESH: Number(e.target.value) })
                }
              />
            </div>

            <div className={`flex flex-col gap-1.5 ${expertClass(expertMode)}`}>
              <div className="flex items-center justify-between gap-2">
                <label className="text-xs font-medium text-muted-foreground">
                  Silence trim pad (ms)
                </label>
                <KeyBadges meta={state?.live_metadata?.SILENCE_TRIM_PAD_MS} />
              </div>
              <Input
                type="number"
                min={0}
                value={draft.SILENCE_TRIM_PAD_MS}
                disabled={state?.live_metadata?.SILENCE_TRIM_PAD_MS?.locked}
                onChange={(e) =>
                  setDraft({ ...draft, SILENCE_TRIM_PAD_MS: Number(e.target.value) })
                }
              />
            </div>
          </div>

          {draft.TTS_BACKEND === 'pocket_tts' && (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex flex-col gap-3 rounded-lg border border-border bg-muted/30 p-4"
            >
              <p className="text-sm font-semibold">Pocket TTS generation tuning</p>

              <p className="text-xs text-muted-foreground">
                These settings affect how Pocket TTS generates audio. Changing them will
                briefly reload the model. Use the Speak tab to compare quality after each
                change.
              </p>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Temperature
                  </label>
                  <Input
                    type="number"
                    step="0.1"
                    min={0.1}
                    max={2}
                    value={draft.POCKET_TTS_TEMP ?? 1.2}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        POCKET_TTS_TEMP: Number(e.target.value),
                      })
                    }
                  />
                  <p className="text-[10px] text-muted-foreground">
                    Controls expressiveness vs stability. Lower (0.3–0.5) = more consistent,
                    safer but monotone. Higher (0.9–1.2) = more natural variation but risk of
                    artifacts. Test: generate the same sentence with 0.4 vs 1.0 and compare.
                  </p>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    LSD decode steps
                  </label>
                  <Input
                    type="number"
                    min={1}
                    max={10}
                    value={draft.POCKET_TTS_LSD_DECODE_STEPS ?? 5}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        POCKET_TTS_LSD_DECODE_STEPS: Number(e.target.value),
                      })
                    }
                  />
                  <p className="text-[10px] text-muted-foreground">
                    Number of refinement steps per audio frame. More steps = higher quality,
                    slower. Pocket TTS is fast, so 2–5 is reasonable. Test: compare 1 vs 3 vs
                    5 on a longer sentence for clarity and smoothness.
                  </p>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    EOS threshold
                  </label>
                  <Input
                    type="number"
                    step="0.1"
                    min={-10}
                    max={0}
                    value={draft.POCKET_TTS_EOS_THRESHOLD ?? -4.0}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        POCKET_TTS_EOS_THRESHOLD: Number(e.target.value),
                      })
                    }
                  />
                  <p className="text-[10px] text-muted-foreground">
                    Controls when generation decides it is done. Smaller (more negative) =
                    longer audio, but may include tail noise. Less negative (e.g. -2.5) =
                    earlier stop, risk of cutting off last word. Test: use -3.0 and -5.0;
                    check for early cutoff vs trailing noise.
                  </p>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Noise clamp <span className="text-muted-foreground/60">(optional)</span>
                  </label>
                  <Input
                    type="number"
                    step="0.1"
                    min={0.1}
                    max={10}
                    value={
                      draft.POCKET_TTS_NOISE_CLAMP == null
                        ? ''
                        : draft.POCKET_TTS_NOISE_CLAMP
                    }
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        POCKET_TTS_NOISE_CLAMP:
                          e.target.value === ''
                            ? null
                            : Number(e.target.value),
                      })
                    }
                  />
                  <p className="text-[10px] text-muted-foreground">
                    Caps the magnitude of injected noise. Leaving it empty is recommended.
                    Lower values can reduce harsh artifacts but may make speech flatter. Use
                    only if you hear obvious noise issues. Test: if default sounds noisy, try
                    1.0–2.0 and compare.
                  </p>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Frames after EOS{' '}
                    <span className="text-muted-foreground/60">(optional)</span>
                  </label>
                  <Input
                    type="number"
                    min={0}
                    value={
                      draft.POCKET_TTS_FRAMES_AFTER_EOS == null
                        ? ''
                        : draft.POCKET_TTS_FRAMES_AFTER_EOS
                    }
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        POCKET_TTS_FRAMES_AFTER_EOS:
                          e.target.value === ''
                            ? null
                            : Number(e.target.value),
                      })
                    }
                  />
                  <p className="text-[10px] text-muted-foreground">
                    Number of 80ms frames to keep after end-of-speech. Useful to reduce
                    abrupt cut off. Leave empty to auto-calculate based on text length.
                    Increase only if speech sounds cut too early. Test: if the last word is
                    clipped, try 2–4.
                  </p>
                </div>
              </div>
            </motion.div>
          )}

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
          <p className="text-sm font-semibold">
            {state.live.TTS_BACKEND === 'openvino'
              ? 'Requires re-export'
              : state.live.TTS_BACKEND === 'pytorch'
                ? 'Requires restart'
                : 'Not used by this backend'}
          </p>
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

      {state?.restart_required && Object.keys(state.restart_required).length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className={`flex flex-col gap-3 rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm ${expertClass(expertMode)}`}
        >
          <p className="text-sm font-semibold">Requires container restart</p>
          <p className="text-xs text-muted-foreground">
            Set via env var at container start — this app can't change these live.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(state.restart_required).map(([name, info]) => (
              <Badge key={name} variant="outline" className="font-mono text-[11px]" title={info.reason}>
                {name}: {String(info.value)}
              </Badge>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  )
}

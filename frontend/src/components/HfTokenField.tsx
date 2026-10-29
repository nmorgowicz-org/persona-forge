import { useState } from 'react'
import { ExternalLink, KeyRound, Loader2 } from 'lucide-react'
import { clearHfToken, saveHfToken, type EngineHfGate, type HfTokenStatus } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

const SOURCE_NOTE: Record<NonNullable<HfTokenStatus['source']>, string> = {
  stored: 'Token set (saved on this computer).',
  environment: 'Token set (from the HF_TOKEN environment variable). Saving one here overrides it for engine downloads.',
  login: 'Token set (from your Hugging Face login on this computer).',
}

/**
 * Masked Hugging Face token input for a gated engine. The server answers with only
 * `{ set, source }`; the token is never shown again after it is saved, and the field is cleared
 * as soon as the request ends.
 */
export function HfTokenField({
  engineId,
  gate,
  highlight,
  onChanged,
}: {
  engineId: string
  gate: EngineHfGate
  /** True after an install failed on the token or the gate terms: draws the eye to the field. */
  highlight?: boolean
  onChanged: (status: HfTokenStatus) => void
}) {
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState<'save' | 'clear' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const status = gate.token

  async function save() {
    setBusy('save')
    setError(null)
    try {
      const next = await saveHfToken(value)
      onChanged(next)
    } catch (err) {
      setError(String((err as Error)?.message || err))
    } finally {
      setValue('')
      setBusy(null)
    }
  }

  async function clear() {
    setBusy('clear')
    setError(null)
    try {
      onChanged(await clearHfToken())
    } catch (err) {
      setError(String((err as Error)?.message || err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <form
      className={cn(
        'flex flex-col gap-2 rounded-control border border-border bg-muted/30 px-3 py-2 text-[11px]',
        highlight && 'border-warning/60 bg-warning/10',
      )}
      data-testid={`hf-token-${engineId}`}
      onSubmit={(event) => {
        event.preventDefault()
        if (value.trim()) void save()
      }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <KeyRound className="size-3 text-primary" />
        <span className="font-medium">Hugging Face token</span>
        <span
          className={status.set ? 'text-muted-foreground' : 'text-warning'}
          data-testid={`hf-token-status-${engineId}`}
          data-set={status.set ? 'true' : 'false'}
        >
          {status.set && status.source ? SOURCE_NOTE[status.source] : 'No token set.'}
        </span>
      </div>
      <p className="text-muted-foreground">
        The cloning weights are in the gated <code className="font-mono">{gate.repo}</code> repository.
        Accept its terms yourself on Hugging Face with the account that owns the token; this app never
        accepts them for you.{' '}
        <a
          href={gate.url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline"
        >
          <ExternalLink className="size-3" />
          Open {gate.repo}
        </a>
        . The token is stored in a private file on this computer, used only while an engine downloads,
        and never shown again.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          type="password"
          name={`hf-token-${engineId}`}
          aria-label="Hugging Face access token"
          autoComplete="off"
          spellCheck={false}
          placeholder={status.set ? 'Paste a new token to replace it' : 'Paste a Hugging Face access token'}
          className="h-7 max-w-xs flex-1 text-xs"
          value={value}
          disabled={busy !== null}
          onChange={(event) => setValue(event.target.value)}
        />
        <Button type="submit" size="xs" variant="outline" disabled={busy !== null || !value.trim()}>
          {busy === 'save' && <Loader2 className="animate-spin" />}
          Save token
        </Button>
        {status.can_clear && (
          <Button type="button" size="xs" variant="ghost" disabled={busy !== null} onClick={() => void clear()}>
            {busy === 'clear' && <Loader2 className="animate-spin" />}
            Clear
          </Button>
        )}
      </div>
      {error && (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      )}
    </form>
  )
}

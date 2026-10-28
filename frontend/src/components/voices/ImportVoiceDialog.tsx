import { useState } from 'react'
import { Loader2, Upload } from 'lucide-react'
import { importPreparedVoice, type BuiltInEngineSummary } from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'

const MAX_KB = 1024

/**
 * Built-in voices → "Add imported voice". A prepared voice file is untrusted input, so the dialog
 * says what is accepted and the server checks all of it (schema, size, the engine's own loader)
 * before keeping anything.
 */
export function ImportVoiceDialog({
  engine,
  open,
  onOpenChange,
  onImported,
}: {
  engine: BuiltInEngineSummary
  open: boolean
  onOpenChange: (open: boolean) => void
  onImported: (voiceId: string, displayName: string) => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function close(next: boolean) {
    if (busy) return
    if (!next) {
      setFile(null)
      setName('')
      setError(null)
    }
    onOpenChange(next)
  }

  async function submit() {
    if (!file || !name.trim()) return
    setBusy(true)
    setError(null)
    try {
      const record = await importPreparedVoice(engine.id, file, name.trim())
      onImported(record.voice_id, record.display_name)
      setFile(null)
      setName('')
      onOpenChange(false)
    } catch (err) {
      setError(String((err as Error)?.message || err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-md" data-testid="import-voice-dialog">
        <DialogHeader>
          <DialogTitle>Add imported voice</DialogTitle>
          <DialogDescription>
            Add a prepared voice file to {engine.label}. It is not cloned from audio: it is a file the
            engine already understands, like the built-in voices it ships with.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
            <li>Only <code>.safetensors</code> files, at most {MAX_KB} kB.</li>
            <li>
              The file is untrusted: its structure is checked, then {engine.label} must load it before
              it is kept. Nothing is run from it.
            </li>
            <li>It is stored with its file name, checksum and date, and can be removed here later.</li>
          </ul>
          <label className="flex flex-col gap-1 text-xs font-medium">
            Name
            <Input
              value={name}
              maxLength={40}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Narrator"
              data-testid="import-voice-name"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium">
            Prepared voice file
            <input
              type="file"
              accept=".safetensors"
              data-testid="import-voice-file"
              onChange={(event) => {
                const picked = event.target.files?.[0] ?? null
                setFile(picked)
                if (picked && !name.trim()) {
                  setName(picked.name.replace(/\.safetensors$/i, '').replace(/[^A-Za-z0-9 ._-]+/g, ' ').trim().slice(0, 40))
                }
              }}
              className="text-xs file:mr-2 file:rounded-control file:border file:border-border file:bg-background file:px-2 file:py-1 file:text-xs"
            />
          </label>
          {error && (
            <p role="alert" className="rounded-control border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button type="button" variant="ghost" disabled={busy} onClick={() => close(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={busy || !file || !name.trim()}
            data-testid="import-voice-submit"
            onClick={() => void submit()}
          >
            {busy ? <Loader2 className="animate-spin" /> : <Upload />} {busy ? 'Checking…' : 'Import'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

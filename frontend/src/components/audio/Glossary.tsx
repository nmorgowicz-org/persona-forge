import { useEffect, useRef } from 'react'
import { GLOSSARY, TROUBLESHOOTING } from '@/lib/glossary'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { X } from 'lucide-react'

interface GlossaryProps {
  isOpen: boolean
  onClose: () => void
  focusId?: string | null
}

export function Glossary({ isOpen, onClose, focusId }: GlossaryProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isOpen || !focusId) return
    // Wait a frame so the modal/scroll area has mounted before scrolling.
    const id = requestAnimationFrame(() => {
      containerRef.current
        ?.querySelector(`[data-kb-id="${focusId}"]`)
        ?.scrollIntoView({ block: 'center' })
    })
    return () => cancelAnimationFrame(id)
  }, [isOpen, focusId])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-6 shadow-2xl max-w-lg w-full max-h-[80vh]">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Glossary &amp; Troubleshooting</h2>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">
          Definitions for technical terms, plus fixes for common issues in generated audio.
        </p>
        <ScrollArea className="flex-1">
          <div ref={containerRef} className="flex flex-col gap-6 py-2">
            <div className="grid gap-4">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Terms
              </h3>
              {Object.entries(GLOSSARY).map(([key, entry]) => (
                <div
                  key={key}
                  data-kb-id={key}
                  className={cn(
                    'flex flex-col gap-1 rounded-md border-b border-border/50 px-1.5 py-1 pb-2 transition-colors',
                    focusId === key && 'bg-primary/10 ring-1 ring-primary/40',
                  )}
                >
                  <span className="text-sm font-medium text-foreground">{entry.term}</span>
                  <span className="text-xs text-muted-foreground">{entry.definition}</span>
                </div>
              ))}
            </div>
            <div className="grid gap-4">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Troubleshooting
              </h3>
              {Object.values(TROUBLESHOOTING).map((entry) => (
                <div
                  key={entry.id}
                  data-kb-id={entry.id}
                  className={cn(
                    'flex flex-col gap-1 rounded-md border-b border-border/50 px-1.5 py-1 pb-2 transition-colors',
                    focusId === entry.id && 'bg-primary/10 ring-1 ring-primary/40',
                  )}
                >
                  <span className="text-sm font-medium text-foreground">{entry.title}</span>
                  <span className="text-xs text-muted-foreground">
                    <span className="font-medium text-foreground/80">Symptoms: </span>
                    {entry.symptoms}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    <span className="font-medium text-foreground/80">Fix: </span>
                    {entry.fix}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </ScrollArea>
      </div>
    </div>
  )
}

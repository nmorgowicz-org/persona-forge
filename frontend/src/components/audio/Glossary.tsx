import { GLOSSARY } from '@/lib/glossary'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { X } from 'lucide-react'

interface GlossaryProps {
  isOpen: boolean
  onClose: () => void
}

export function Glossary({ isOpen, onClose }: GlossaryProps) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-6 shadow-2xl max-w-lg w-full max-h-[80vh]">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Audio Glossary</h2>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">
          Definitions for the technical audio terms used throughout the app.
        </p>
        <ScrollArea className="flex-1">
          <div className="grid gap-4 py-2">
            {Object.entries(GLOSSARY).map(([key, entry]) => (
              <div key={key} className="flex flex-col gap-1 border-b border-border/50 pb-2">
                <span className="text-sm font-medium text-foreground">{entry.term}</span>
                <span className="text-xs text-muted-foreground">{entry.definition}</span>
              </div>
            ))}
          </div>
        </ScrollArea>
      </div>
    </div>
  )
}

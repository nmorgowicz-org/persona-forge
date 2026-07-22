import { useState } from 'react'
import { motion } from 'framer-motion'
import { RefreshCw, Zap } from 'lucide-react'
import cudaCopy from '@/content/help/accelerator-cuda.md?raw'
import rocmCopy from '@/content/help/accelerator-rocm.md?raw'
import intelXpuCopy from '@/content/help/accelerator-intel-xpu.md?raw'
import { Button } from '@/components/ui/button'
import type { RuntimeConfigState } from '@/lib/api'

// D8: coach copy lives in markdown, reviewable without touching JSX. This renders just the
// subset of markdown the coach copy actually uses (### headings, ``` fences, plain paragraphs).
const COPY_BY_FAMILY: Record<'cuda' | 'rocm' | 'intel-xpu', string> = {
  cuda: cudaCopy,
  rocm: rocmCopy,
  'intel-xpu': intelXpuCopy,
}

function MarkdownLite({ source }: { source: string }) {
  const blocks: React.ReactNode[] = []
  const lines = source.trim().split('\n')
  let i = 0
  let key = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.startsWith('### ')) {
      blocks.push(
        <h4 key={key++} className="text-sm font-semibold">
          {line.slice(4)}
        </h4>,
      )
      i++
    } else if (line.startsWith('```')) {
      const code: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) {
        code.push(lines[i])
        i++
      }
      i++ // skip closing fence
      blocks.push(
        <pre
          key={key++}
          className="overflow-x-auto rounded-md bg-muted/50 p-3 text-[11px] font-mono"
        >
          {code.join('\n')}
        </pre>,
      )
    } else if (line.trim() === '') {
      i++
    } else {
      const para: string[] = []
      while (i < lines.length && lines[i].trim() !== '' && !lines[i].startsWith('```')) {
        para.push(lines[i])
        i++
      }
      blocks.push(
        <p key={key++} className="text-xs text-muted-foreground">
          {para.join(' ')}
        </p>,
      )
    }
  }
  return <div className="flex flex-col gap-2">{blocks}</div>
}

export function AcceleratorCoachCard({
  accelerator,
  onRedetect,
  redetecting,
}: {
  accelerator: NonNullable<RuntimeConfigState['accelerator']>
  onRedetect: () => void
  redetecting: boolean
}) {
  const [dismissed, setDismissed] = useState(false)
  const family = accelerator.detected_family

  // Only the present∧¬capable gap is coach-worthy; native/already-mapped stays quiet, and
  // there's no snippet for a bare "cpu" detection (nothing to map).
  if (dismissed || !accelerator.present || accelerator.capable || family === 'cpu') {
    return null
  }

  const copy = COPY_BY_FAMILY[family]

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col gap-3 rounded-xl border border-primary/30 bg-primary/5 p-5"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Zap className="size-4 text-primary" />
          <p className="text-sm font-semibold">Accelerator detected, not mapped in yet</p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setDismissed(true)}>
          Dismiss
        </Button>
      </div>

      <MarkdownLite source={copy} />

      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={onRedetect} disabled={redetecting}>
          <RefreshCw className={`size-3.5 ${redetecting ? 'animate-spin' : ''}`} />
          {redetecting ? 'Re-detecting…' : 'Re-detect'}
        </Button>
      </div>
    </motion.div>
  )
}

import { AnimatePresence, motion } from 'framer-motion'
import { Loader2 } from 'lucide-react'
import { useSwapStatus } from '@/hooks/useSwapStatus'

export function SwapBanner() {
  const swapping = useSwapStatus()

  return (
    <AnimatePresence initial={false}>
      {swapping && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          className="overflow-hidden border-b border-border bg-muted/40"
        >
          <div className="flex items-center gap-2 px-4 py-1.5 text-[10px] text-muted-foreground">
            <Loader2 className="size-3 shrink-0 animate-spin" />
            <span>
              Loading Voice Design model — Speak and Integrations will be briefly busy.
            </span>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

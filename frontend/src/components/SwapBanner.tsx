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
          className="overflow-hidden border-b border-primary/30 bg-primary/10"
        >
          <div className="flex items-center gap-2 px-4 py-2 text-xs text-primary">
            <Loader2 className="size-3.5 shrink-0 animate-spin" />
            <span>
              Swapping in the VoiceDesign model — Speak and Integrations will briefly return
              &ldquo;model busy&rdquo; until it finishes. This can take anywhere from a few
              seconds (warm cache) to a few minutes (cold start).
            </span>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

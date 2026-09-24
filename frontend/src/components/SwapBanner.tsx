import { AnimatePresence, motion } from 'motion/react'
import { Loader2 } from 'lucide-react'
import { useSwapStatus } from '@/hooks/useSwapStatus'
import { useAppStore } from '@/store'
import { AppBanner } from '@/components/ui/app-banner'

export function SwapBanner() {
  const swapping = useSwapStatus()
  const page = useAppStore((s) => s.page)

  // Only show this banner on the Voice Design page.
  // During OmniVoice, all status is shown inline + bottom bar.
  if (!swapping || page !== 'voice-design') return null

  return (
    <AnimatePresence initial={false}>
      <motion.div
        initial={{ height: 0, opacity: 0 }}
        animate={{ height: 'auto', opacity: 1 }}
        exit={{ height: 0, opacity: 0 }}
        className="overflow-hidden"
      >
        <AppBanner tone="neutral" icon={<Loader2 className="size-3 shrink-0 animate-spin" />}>
          Loading Voice Design model — Speak and Integrations will be briefly busy.
        </AppBanner>
      </motion.div>
    </AnimatePresence>
  )
}

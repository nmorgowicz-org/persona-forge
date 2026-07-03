import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

export function Tooltip({ tip, children }: { tip: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    const id = setTimeout(() => setOpen(true), 150)
    return () => clearTimeout(id)
  }, [open])

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      {children}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 2, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 2, scale: 0.97 }}
            transition={{ duration: 0.12, ease: 'easeOut' }}
            className="absolute bottom-full left-1/2 z-40 mb-1.5 -translate-x-1/2 whitespace-nowrap rounded-lg border border-border/80 bg-popover px-2 py-1 text-[10px] leading-tight text-popover-foreground shadow-lg"
          >
            {tip}
          </motion.div>
        )}
      </AnimatePresence>
    </span>
  )
}

import { motion } from 'framer-motion'
import { Toggle } from '@/components/ui/toggle'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface ChipButtonProps {
  label: string
  selected: boolean
  onClick: () => void
  experimental?: boolean
}

export function ChipButton({ label, selected, onClick, experimental }: ChipButtonProps) {
  return (
    <Toggle
      pressed={selected}
      onPressedChange={onClick}
      variant="outline"
      className={cn(
        'h-auto rounded-full border px-3 py-1.5 text-xs font-medium data-[state=on]:border-primary data-[state=on]:bg-primary data-[state=on]:text-primary-foreground',
      )}
    >
      <motion.span
        className="inline-flex items-center gap-1.5"
        whileTap={{ scale: 0.94 }}
        animate={{ scale: selected ? 1.03 : 1 }}
        transition={{ type: 'spring', stiffness: 500, damping: 30 }}
      >
        {label}
        {experimental && (
          <Badge variant="outline" className="h-4 px-1 text-[9px] text-amber-500">
            experimental
          </Badge>
        )}
      </motion.span>
    </Toggle>
  )
}

import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { useExperienceLevel } from '@/lib/useExperienceLevel'

interface DiscloseProps {
  // Only 'expert' is supported today: hide this content in 'guided' mode.
  level: 'expert'
  children: ReactNode
  className?: string
}

// Hides power-user controls in guided mode without unmounting them, so component state
// (form values, refs, in-flight requests) survives toggling between guided/expert.
export function Disclose({ level, children, className }: DiscloseProps) {
  const current = useExperienceLevel()
  const hidden = level === 'expert' && current !== 'expert'

  return (
    <div className={cn(hidden && 'hidden', className)} aria-hidden={hidden}>
      {children}
    </div>
  )
}

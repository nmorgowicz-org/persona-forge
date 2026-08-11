import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'

interface AdvancedDrawerProps {
  title: string
  description?: string
  trigger: React.ReactNode
  children: React.ReactNode
}

export function AdvancedDrawer({ title, description, trigger, children }: AdvancedDrawerProps) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        {trigger}
      </SheetTrigger>
      <SheetContent side="right" className="w-full sm:max-w-md overflow-y-auto">
        <SheetHeader className="pb-4 border-b">
          <SheetTitle>{title}</SheetTitle>
          {description && <SheetDescription>{description}</SheetDescription>}
        </SheetHeader>
        <div className="py-4">
          {children}
        </div>
      </SheetContent>
    </Sheet>
  )
}

import type { ReactNode } from 'react'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  AudioLines,
  Check,
  ChevronLeft,
  ChevronRight,
  Mic2,
  Palette,
  Plug,
  Settings2,
  Sparkles,
} from 'lucide-react'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from '@/components/ui/sidebar'
import { Separator } from '@/components/ui/separator'
import { SwapBanner } from '@/components/SwapBanner'
import { type Page, useAppStore } from '@/store'
import { THEMES, type Theme } from '@/lib/theme'
import { cn } from '@/lib/utils'

const SWATCH_COLOR: Record<Theme, string> = {
  violet: 'oklch(0.62 0.19 280)',
  teal: 'oklch(0.6 0.13 175)',
  amber: 'oklch(0.78 0.16 70)',
  rose: 'oklch(0.64 0.2 10)',
}

const SWATCH_LABEL: Record<Theme, string> = {
  violet: 'Violet',
  teal: 'Teal',
  amber: 'Amber',
  rose: 'Rose',
}

const NAV_ITEMS: { page: Page; label: string; icon: typeof Mic2; description: string }[] = [
  { page: 'speak', label: 'Speak', icon: AudioLines, description: 'Text to speech' },
  { page: 'voice-design', label: 'Voice Design', icon: Sparkles, description: 'Craft a new voice' },
  { page: 'voice-library', label: 'Voice Library', icon: Mic2, description: 'Saved voices' },
  { page: 'integrations', label: 'Integrations', icon: Plug, description: 'API & apps' },
  { page: 'runtime', label: 'Runtime', icon: Settings2, description: 'Live server config' },
]

function ThemePaletteBar() {
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)

  return (
    <div className="flex items-center gap-1.5">
      {THEMES.map((t) => {
        const active = theme === t
        return (
          <button
            key={t}
            type="button"
            onClick={() => setTheme(t)}
            className={cn(
              'flex size-4.5 shrink-0 items-center justify-center rounded-full ring-1 ring-white/10 transition-transform hover:scale-110',
              active && 'ring-2 ring-white/80',
            )}
            style={{ background: SWATCH_COLOR[t] }}
            title={SWATCH_LABEL[t]}
          >
            {active && <Check className="size-2.5 text-black/70" strokeWidth={3} />}
          </button>
        )
      })}
    </div>
  )
}

function ThemePaletteButton() {
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const [open, setOpen] = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 })

  useEffect(() => {
    if (!open) return
    const update = () => {
      if (!btnRef.current) return
      const r = btnRef.current.getBoundingClientRect()
      setPos({ x: r.left, y: r.top - 24 })
    }
    update()
    window.addEventListener('resize', update)
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node
      const btn = btnRef.current
      const panel = panelRef.current
      const insideBtn = btn?.contains(target)
      const insidePanel = panel?.contains(target)
      if (!insideBtn && !insidePanel) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('resize', update)
      document.removeEventListener('mousedown', onDown)
    }
  }, [open])

  const panel =
    open &&
    createPortal(
      <div
        ref={panelRef}
        style={{
          position: 'fixed',
          left: pos.x,
          top: pos.y,
          zIndex: 9999,
        }}
        className="flex gap-1.5 rounded-lg border border-border bg-popover px-2.5 py-1.5 shadow-lg"
      >
        {THEMES.map((t) => {
          const active = theme === t
          return (
            <button
              key={t}
              type="button"
              onClick={() => setTheme(t)}
              className={cn(
                'flex size-5 shrink-0 items-center justify-center rounded-full ring-1 ring-white/10 transition-transform hover:scale-110',
                active && 'ring-2 ring-white/80',
              )}
              style={{ background: SWATCH_COLOR[t] }}
              title={SWATCH_LABEL[t]}
            >
              {active && <Check className="size-3 text-black/70" strokeWidth={3} />}
            </button>
          )
        })}
      </div>,
      document.body,
    )

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex size-8 items-center justify-center rounded-md border border-border/90 bg-muted text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        title="Theme"
      >
        <Palette className="size-3.5" />
      </button>
      {panel}
    </>
  )
}

function SidebarCollapseButton() {
  const { open, toggleSidebar } = useSidebar()
  return (
    <button
      type="button"
      onClick={toggleSidebar}
      className="group/collapse flex w-full items-center justify-between rounded-md border border-border/90 px-2.5 py-1.5 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground group-data-[collapsible=icon]:flex"
      title={open ? 'Collapse sidebar' : 'Expand sidebar'}
    >
      <span className="group-data-[collapsible=icon]:hidden">
        {open ? 'Collapse sidebar' : 'Expand sidebar'}
      </span>
      {open ? (
        <ChevronRight className="size-3.5 text-muted-foreground/80 transition-colors group-hover/collapse:text-foreground" />
      ) : (
        <ChevronLeft className="size-3.5 text-muted-foreground/80 transition-colors group-hover/collapse:text-foreground" />
      )}
    </button>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  const page = useAppStore((s) => s.page)
  const setPage = useAppStore((s) => s.setPage)
  const active = NAV_ITEMS.find((item) => item.page === page)

  return (
    <SidebarProvider>
      <Sidebar collapsible="icon">
        <SidebarHeader className="px-3 py-4">
          <div className="flex items-center gap-2 px-1">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <AudioLines className="size-4" />
            </div>
            <div className="flex flex-col group-data-[collapsible=icon]:hidden">
              <span className="text-sm font-semibold leading-none">Persona Forge</span>
              <span className="text-[11px] text-muted-foreground">Voice Studio</span>
            </div>
          </div>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Studio</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {NAV_ITEMS.map((item) => (
                  <SidebarMenuItem key={item.page}>
                    <SidebarMenuButton
                      data-testid={`nav-${item.page}`}
                      isActive={page === item.page}
                      tooltip={item.label}
                      onClick={() => setPage(item.page)}
                    >
                      <item.icon />
                      <span>{item.label}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter className="gap-3 px-3 py-3">
          {/* Expanded: inline color palette bar + short note */}
          <div className="group-data-[collapsible=icon]:hidden flex flex-col gap-1.5">
            <ThemePaletteBar />
            <p className="text-[10px] leading-tight text-muted-foreground">
              Voices designed here are served over the OpenAI-compatible endpoint for Hermes and
              other apps.
            </p>
          </div>
          {/* Collapsed: single palette button */}
          <div className="hidden group-data-[collapsible=icon]:flex justify-center">
            <ThemePaletteButton />
          </div>
          <SidebarCollapseButton />
        </SidebarFooter>
      </Sidebar>
      <SidebarInset>
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border px-4">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-5" />
          <div className="flex flex-col">
            <span className="text-sm font-medium leading-none">{active?.label}</span>
            <span className="text-[11px] text-muted-foreground">{active?.description}</span>
          </div>
        </header>
        <SwapBanner />
        <div className="min-w-0 flex-1 overflow-y-auto">
          <div className="w-full px-6 py-8">{children}</div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}

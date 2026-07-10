import type { ReactNode } from 'react'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  AudioLines,
  ChevronLeft,
  ChevronRight,
  Layers,
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
import { ActivityStatusBar } from '@/components/ui/ActivityStatusBar'
import { Separator } from '@/components/ui/separator'
import { SwapBanner } from '@/components/SwapBanner'
import { HealthStatusBanner } from '@/components/HealthStatusBanner'
import { getRuntimeConfig, getHealth } from '@/lib/api'
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
  { page: 'stitch-studio', label: 'Stitch Studio', icon: Layers, description: 'Arrange clips into a voice' },
  { page: 'integrations', label: 'Integrations', icon: Plug, description: 'API & apps' },
  { page: 'runtime', label: 'Runtime', icon: Settings2, description: 'Live server config' },
]

function PocketTTSWarningBanner() {
  const backend = useAppStore((s) => s.runtimeTtsBackend)
  const cloningAvailable = useAppStore((s) => s.pocketTtsVoiceCloningAvailable)

  const isPocketTTS = backend === 'pocket_tts'
  const cloningOk = cloningAvailable === true
  if (!isPocketTTS || cloningOk) return null

  return (
    <div className="flex flex-col border-b border-amber-400/50 bg-amber-500/10 px-4 py-2 text-amber-600">
      <div className="flex items-center gap-2 text-[11px]">
        <span className="inline-flex size-2 shrink-0 items-center justify-center rounded-full bg-amber-400 animate-pulse" />
        <span className="flex-1">
          Pocket TTS is active, but voice cloning is unavailable until you accept the license on Hugging Face:{' '}
          <a
            href="https://huggingface.co/kyutai/pocket-tts"
            target="_blank"
            rel="noopener noreferrer"
            className="underline"
          >
            huggingface.co/kyutai/pocket-tts
          </a>
        </span>
      </div>
      <div className="mt-1 text-[10px] opacity-70">
        Use the account that matches your HF_TOKEN, then restart the container after accepting.
      </div>
    </div>
  )
}

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
              'h-2 w-6 shrink-0 overflow-hidden rounded-full border border-transparent transition-all hover:scale-110',
              active && 'border-white/80 ring-2 ring-white/80',
            )}
            style={{ background: SWATCH_COLOR[t] }}
            title={SWATCH_LABEL[t]}
          />
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
      setPos({ x: r.right + 6, y: r.top + r.height / 2 - 10 })
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
                'h-2 w-6 shrink-0 rounded-full border border-transparent transition-all hover:scale-110',
                active && 'border-white/80 ring-2 ring-white/80',
              )}
              style={{ background: SWATCH_COLOR[t] }}
              title={SWATCH_LABEL[t]}
            />
          )
        })}
      </div>,
      document.body,
    )

  return (
    <>
      <SidebarMenuButton
        ref={btnRef}
        onClick={() => setOpen((v) => !v)}
        tooltip="Theme"
      >
        <Palette className="size-4" />
      </SidebarMenuButton>
      {panel}
    </>
  )
}

function SidebarVersionDisplay() {
  const [version, setVersion] = useState<string | null>(null)
  const [error, setError] = useState<boolean>(false)

  useEffect(() => {
    getHealth()
      .then((state) => setVersion(state.version as string | null))
      .catch((err) => {
        console.error('Failed to fetch version:', err)
        setError(true)
      })
  }, [])

  if (error) return <div className="text-center text-[11px] text-red-500">vError</div>
  if (!version) return <div className="text-center text-[11px] text-muted-foreground">vLoading...</div>

  return (
    <div className="text-center text-[11px] font-bold text-primary">
      v{version}
    </div>
  )
}

function SidebarCollapseButton() {
  const { open, toggleSidebar } = useSidebar()

  if (!open) {
    return (
      <SidebarMenuButton onClick={toggleSidebar} tooltip="Expand sidebar">
        <ChevronLeft className="size-4" />
      </SidebarMenuButton>
    )
  }

  return (
    <button
      type="button"
      onClick={toggleSidebar}
      className="group/collapse flex w-full items-center justify-between gap-2 rounded-xl border border-border/90 px-3 py-2 text-xs font-medium text-foreground/90 shadow-sm transition-all hover:border-border hover:bg-accent hover:text-foreground hover:shadow"
      title="Collapse sidebar"
    >
      <span>Collapse sidebar</span>
      <ChevronRight className="size-4 shrink-0 text-foreground/90 transition-transform group-hover/collapse:translate-x-0.5 group-hover/collapse:text-foreground" />
    </button>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  const page = useAppStore((s) => s.page)
  const setPage = useAppStore((s) => s.setPage)
  const setRuntimeConfig = useAppStore((s) => s.setRuntimeConfig)
  const active = NAV_ITEMS.find((item) => item.page === page)

  // One-time fetch to initialize Pocket TTS banner state at startup
  useEffect(() => {
    getRuntimeConfig()
      .then((cfg) => {
        setRuntimeConfig({
          runtimeTtsBackend: cfg.live.TTS_BACKEND,
          pocketTtsVoiceCloningAvailable: cfg.live.pocket_tts_voice_cloning_available,
        })
      })
      .catch(() => {
        // Non-critical; banner will stay hidden until RuntimeConfigPage updates the store
      })
  }, [setRuntimeConfig])

  return (
    <SidebarProvider>
      <Sidebar collapsible="icon">
        <SidebarHeader className="px-3 py-4">
          <div className="flex items-center gap-2.5 px-1">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-primary/70 text-primary-foreground shadow-sm ring-1 ring-primary/20">
              <AudioLines className="size-4" />
            </div>
            <div className="flex flex-col group-data-[collapsible=icon]:hidden">
              <span className="text-sm font-semibold leading-none tracking-tight">Persona Forge</span>
              <span className="text-[11px] text-muted-foreground">Voice Studio</span>
            </div>
          </div>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Studio</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {NAV_ITEMS.map((item) => {
                  const isActive = page === item.page
                  return (
                    <SidebarMenuItem key={item.page}>
                      <SidebarMenuButton
                        data-testid={`nav-${item.page}`}
                        isActive={isActive}
                        tooltip={item.label}
                        onClick={() => setPage(item.page)}
                        className={cn(
                          'relative transition-all',
                          isActive &&
                            'before:absolute before:left-0 before:top-1/2 before:h-4 before:w-[3px] before:-translate-y-1/2 before:rounded-full before:bg-primary group-data-[collapsible=icon]:before:hidden',
                        )}
                      >
                        <item.icon />
                        <span className="group-data-[collapsible=icon]:hidden">{item.label}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  )
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter className="flex flex-col gap-2 px-3 py-3">
          {/* Expanded: inline color palette bar + short note */}
          <div className="group-data-[collapsible=icon]:hidden flex flex-col gap-1.5">
            <ThemePaletteBar />
            <p className="text-[10px] leading-tight text-muted-foreground">
              Voices designed here are served over the OpenAI-compatible endpoint for Hermes and
              other apps.
            </p>
          </div>
          {/* Collapsed: theme button (same size as expand button) */}
           <div className="hidden group-data-[collapsible=icon]:flex justify-center">
             <ThemePaletteButton />
           </div>
            <SidebarCollapseButton />
            <div className="text-center text-xs text-white">DEBUG: VERSION COMPONENT HERE</div>
            <SidebarVersionDisplay />
          </SidebarFooter>


      </Sidebar>
      <SidebarInset>
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border/80 bg-background/80 px-4 backdrop-blur-sm">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-5" />
          <div className="flex flex-col">
            <span className="text-sm font-medium leading-none">{active?.label}</span>
            <span className="text-[11px] text-muted-foreground">{active?.description}</span>
          </div>
        </header>
        <HealthStatusBanner />
        <PocketTTSWarningBanner />
        <SwapBanner />
        <div className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto">
          <div className="w-full min-w-0 px-6 py-8">{children}</div>
        </div>
      </SidebarInset>
      <ActivityStatusBar />
    </SidebarProvider>
  )
}

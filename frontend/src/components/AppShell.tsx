import type { ReactNode } from 'react'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  AudioLines,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  GraduationCap,
  Layers,
  Mic2,
  Palette,
  Plug,
  Settings2,
  Sparkles,
  Wand2,
  Wrench,
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
} from '@/components/ui/sidebar'
import { useSidebar } from '@/components/ui/sidebar-context'
import { ActivityStatusBar } from '@/components/ui/ActivityStatusBar'
import { Separator } from '@/components/ui/separator'
import { SwapBanner } from '@/components/SwapBanner'
import { HealthStatusBanner } from '@/components/HealthStatusBanner'
import { UpdateAvailableBanner } from '@/components/UpdateAvailableBanner'
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
  { page: 'wizard', label: 'New Voice (Guided)', icon: Wand2, description: 'Answer a few questions, land in the right editor' },
  { page: 'speak', label: 'Speak', icon: AudioLines, description: 'Text to speech' },
  { page: 'voice-design', label: 'Voice Design', icon: Sparkles, description: 'Craft a new voice' },
  { page: 'voice-library', label: 'Voice Library', icon: Mic2, description: 'Saved voices' },
  { page: 'stitch-studio', label: 'Stitch Studio', icon: Layers, description: 'Arrange clips into a voice' },
  { page: 'integrations', label: 'Integrations', icon: Plug, description: 'API & apps' },
  { page: 'runtime', label: 'Runtime', icon: Settings2, description: 'Live server config' },
]

function StudioNav({ page, setPage }: { page: Page; setPage: (page: Page) => void }) {
  const { isMobile, setOpenMobile } = useSidebar()
  return <SidebarMenu>{NAV_ITEMS.map((item) => {
    const isActive = page === item.page
    return <SidebarMenuItem key={item.page}><SidebarMenuButton
      data-testid={`nav-${item.page}`}
      isActive={isActive}
      tooltip={item.label}
      onClick={() => { setPage(item.page); if (isMobile) setOpenMobile(false) }}
      className={cn('relative transition-all', isActive && 'before:absolute before:left-0 before:top-1/2 before:h-4 before:w-[3px] before:-translate-y-1/2 before:rounded-full before:bg-primary group-data-[collapsible=icon]:before:hidden')}
    ><item.icon /><span className="group-data-[collapsible=icon]:hidden">{item.label}</span></SidebarMenuButton></SidebarMenuItem>
  })}</SidebarMenu>
}

function PocketTTSWarningBanner() {
  const backend = useAppStore((s) => s.runtimeTtsBackend)
  const cloningAvailable = useAppStore((s) => s.pocketTtsVoiceCloningAvailable)

  const isPocketTTS = backend === 'pocket_tts'
  const cloningOk = cloningAvailable === true
  if (!isPocketTTS || cloningOk) return null

  return (
    <div className="flex flex-col border-b border-warning/50 bg-warning/10 px-4 py-2 text-warning">
      <div className="flex items-center gap-2 text-[11px]">
        <span className="inline-flex size-2 shrink-0 items-center justify-center rounded-full bg-warning animate-pulse" />
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

function ExperienceLevelToggle() {
  const level = useAppStore((s) => s.uiExperienceLevel)
  const setLevel = useAppStore((s) => s.setUiExperienceLevel)
  const isExpert = level === 'expert'

  return (
    <button
      type="button"
      data-testid="experience-level-toggle"
      onClick={() => setLevel(isExpert ? 'guided' : 'expert')}
      title={
        isExpert
          ? 'Expert mode: all power-user controls visible. Click for Guided mode.'
          : 'Guided mode: power-user controls hidden. Click for Expert mode.'
      }
      className="flex items-center gap-1.5 rounded-md border border-border/70 px-2 py-1 text-[10px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
    >
      {isExpert ? <Wrench className="size-3" /> : <GraduationCap className="size-3" />}
      {isExpert ? 'Expert' : 'Guided'}
    </button>
  )
}

function ExperienceLevelButton() {
  const level = useAppStore((s) => s.uiExperienceLevel)
  const setLevel = useAppStore((s) => s.setUiExperienceLevel)
  const isExpert = level === 'expert'

  return (
    <SidebarMenuButton
      data-testid="experience-level-toggle-collapsed"
      onClick={() => setLevel(isExpert ? 'guided' : 'expert')}
      tooltip={isExpert ? 'Expert mode (click for Guided)' : 'Guided mode (click for Expert)'}
    >
      {isExpert ? <Wrench className="size-4" /> : <GraduationCap className="size-4" />}
    </SidebarMenuButton>
  )
}

function GlossaryLink() {
  const openGlossaryAt = useAppStore((s) => s.openGlossaryAt)

  return (
    <button
      type="button"
      data-testid="glossary-open-link"
      onClick={() => openGlossaryAt(null)}
      className="flex items-center gap-1.5 self-start text-[10px] text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground"
    >
      <BookOpen className="size-3" />
      Glossary &amp; Troubleshooting
    </button>
  )
}

function GlossaryButton() {
  const openGlossaryAt = useAppStore((s) => s.openGlossaryAt)

  return (
    <SidebarMenuButton
      data-testid="glossary-open-button"
      onClick={() => openGlossaryAt(null)}
      tooltip="Glossary & Troubleshooting"
    >
      <BookOpen className="size-4" />
    </SidebarMenuButton>
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

// Health is re-polled on this interval so the sidebar's version reflects a backend swap
// (see SwapBanner) or redeploy without requiring a full page reload.
const VERSION_POLL_INTERVAL_MS = 30_000

function SidebarVersionDisplay() {
  const [version, setVersion] = useState<string | null>(null)
  const [error, setError] = useState<boolean>(false)

  useEffect(() => {
    let cancelled = false
    const poll = () => {
      getHealth()
        .then((state) => {
          if (cancelled) return
          const s = state as any
          const v = s.version || s.openvino?.version
          setVersion(v as string | null)
          setError(false)
        })
        .catch((err) => {
          if (cancelled) return
          console.error('Failed to fetch version:', err)
          setError(true)
        })
    }
    poll()
    const id = setInterval(poll, VERSION_POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  const label = error ? 'vError' : version ? `v${version}` : 'vLoading...'
  const colorClass = error ? 'text-destructive' : version ? 'text-primary' : 'text-muted-foreground'

  return (
    <>
      {/* Expanded: full "vX.Y.Z" text */}
      <div
        className={cn(
          'group-data-[collapsible=icon]:hidden text-center text-[11px] font-bold',
          colorClass,
        )}
      >
        {label}
      </div>
      {/* Collapsed: compact badge, full version on hover */}
      <div
        title={label}
        className={cn(
          'hidden group-data-[collapsible=icon]:flex justify-center text-[9px] font-bold leading-none',
          colorClass,
        )}
      >
        {error ? '!' : version ? `v${version.split('.')[0]}` : '…'}
      </div>
    </>
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
              <StudioNav page={page} setPage={setPage} />
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter className="flex flex-col gap-2 px-3 py-3">
          {/* Expanded: inline color palette bar + short note */}
          <div className="group-data-[collapsible=icon]:hidden flex flex-col gap-1.5">
            <div className="flex items-center justify-between gap-2">
              <ThemePaletteBar />
              <ExperienceLevelToggle />
            </div>
            <p className="text-[10px] leading-tight text-muted-foreground">
              Voices designed here are served over the OpenAI-compatible endpoint for Hermes and
              other apps.
            </p>
            <GlossaryLink />
          </div>
          {/* Collapsed: theme + experience-level + glossary buttons (same size as expand button) */}
           <div className="hidden group-data-[collapsible=icon]:flex flex-col items-center gap-1">
             <ThemePaletteButton />
             <ExperienceLevelButton />
             <GlossaryButton />
           </div>
             <SidebarCollapseButton />
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
        <UpdateAvailableBanner />
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

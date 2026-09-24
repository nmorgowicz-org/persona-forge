import type { ReactNode } from 'react'
import { useEffect, useMemo, useRef, useState } from 'react'
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
  Search,
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
import { CommandPalette, ShortcutKeymap } from '@/components/CommandPalette'
import { setHelpText } from '@/components/ui/ActivityStatusBar'
import { TransportReadout } from '@/components/audio/TransportReadout'
import {
  isPrimaryModifier,
  openCommandPalette,
  openShortcutKeymap,
  useShortcutScope,
  type ShortcutCommand,
} from '@/hooks/useGlobalShortcuts'
import { Separator } from '@/components/ui/separator'
import { SwapBanner } from '@/components/SwapBanner'
import { HealthStatusBanner } from '@/components/HealthStatusBanner'
import { StartupState } from '@/components/StartupState'
import { Announcer } from '@/components/ui/announcer'
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
  { page: 'voice-edit', label: 'Voice Edit', icon: AudioLines, description: 'Prosody & variants' },
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
      // Active state is light, not paint: an accent rail plus a soft glow, keyed to
      // --glow-accent so it follows the theme (B-P6).
      className={cn(
        'relative transition-all',
        isActive && 'glow-active before:absolute before:left-0 before:top-1/2 before:h-4 before:w-[3px] before:-translate-y-1/2 before:rounded-full before:bg-primary group-data-[collapsible=icon]:before:hidden',
      )}
    ><item.icon /><span className="group-data-[collapsible=icon]:hidden">{item.label}</span></SidebarMenuButton></SidebarMenuItem>
  })}</SidebarMenu>
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
        className="flex gap-1.5 rounded-control border border-border bg-popover px-2.5 py-1.5 shadow-lg"
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
        data-testid="sidebar-version"
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
      className="group/collapse flex w-full items-center justify-between gap-2 rounded-panel border border-border/90 px-3 py-2 text-xs font-medium text-foreground/90 shadow-sm transition-all hover:border-border hover:bg-accent hover:text-foreground hover:shadow"
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
  const serviceStarted = useAppStore((s) => s.serviceStarted)
  const healthStatus = useAppStore((s) => s.healthStatus)
  const healthChecked = useAppStore((s) => s.healthChecked)
  // Info view (D6): one delegated listener for the whole app. Any control can carry a
  // `data-help` string and have it explained in the status bar's info strip on hover or
  // keyboard focus -- no per-control wiring, and nothing renders until there is something to
  // say.
  useEffect(() => {
    const findHelp = (target: EventTarget | null): string | null => {
      if (!(target instanceof Element)) return null
      const owner = target.closest('[data-help]')
      if (!(owner instanceof HTMLElement)) return null
      return owner.dataset.help?.trim() || null
    }
    const onOver = (event: Event) => setHelpText(findHelp(event.target))
    const onOut = () => setHelpText(null)
    const onFocus = (event: Event) => setHelpText(findHelp(event.target))
    const onBlur = () => setHelpText(null)
    document.addEventListener('pointerover', onOver)
    document.addEventListener('pointerout', onOut)
    document.addEventListener('focusin', onFocus)
    document.addEventListener('focusout', onBlur)
    return () => {
      document.removeEventListener('pointerover', onOver)
      document.removeEventListener('pointerout', onOut)
      document.removeEventListener('focusin', onFocus)
      document.removeEventListener('focusout', onBlur)
    }
  }, [])

  const active = NAV_ITEMS.find((item) => item.page === page)

  // The app-wide layer of the shortcut registry: navigation (one command per nav item, so the
  // palette cannot drift from the sidebar), the two global keys, and focus-search. Pages
  // register their own on top -- see hooks/useGlobalShortcuts.ts.
  const appCommands = useMemo<ShortcutCommand[]>(
    () => [
      {
        id: 'palette.open',
        label: 'Open command palette',
        keys: 'Cmd/Ctrl+K',
        allowInEditable: true,
        match: (event) => isPrimaryModifier(event) && (event.key === 'k' || event.key === 'K'),
        run: openCommandPalette,
      },
      {
        id: 'keymap.open',
        // The wording the stitch-only dialog used, preserved: this row is that dialog's
        // replacement, now listing every surface rather than one page's keys.
        label: 'Show this dialog',
        hint: 'Keyboard shortcuts',
        keys: '?',
        match: (event) => event.key === '?' && !event.repeat,
        run: openShortcutKeymap,
      },
      {
        id: 'search.focus',
        label: 'Focus search',
        hint: 'Current page',
        run: () => {
          const field = document.querySelector<HTMLInputElement>('input[type="search"], input[placeholder^="Search"]')
          field?.focus()
          field?.select()
        },
      },
      ...NAV_ITEMS.map((item) => ({
        id: `nav.${item.page}`,
        label: item.label,
        hint: item.description,
        run: () => setPage(item.page),
      })),
    ],
    [setPage],
  )
  useShortcutScope('app', 'Global', appCommands)

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
            {/* The product mark (D7 = Signal Crucible). It carries its own Obsidian ground, so
                it reads at 24 px on any theme without a glow behind it -- verified at 16/24/32/48
                px on light and dark before wiring. */}
            <img
              data-testid="app-brand-mark"
              src="/favicon.svg"
              alt=""
              width={24}
              height={24}
              className="size-6 shrink-0"
            />
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
          <button
            type="button"
            data-testid="command-palette-button"
            onClick={openCommandPalette}
            aria-label="Open command palette"
            title="Search commands (Cmd/Ctrl+K)"
            className="ml-auto inline-flex h-8 shrink-0 items-center gap-2 rounded-md border border-border bg-background px-2.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Search className="size-3.5" />
            <span className="hidden sm:inline">Search</span>
            <kbd className="hidden rounded border border-border bg-muted px-1 font-mono text-[10px] sm:inline">⌘K</kbd>
          </button>
        </header>
        <UpdateAvailableBanner />
        <HealthStatusBanner />
        <SwapBanner />
        <div className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto">
          <div className="w-full min-w-0 px-6 py-8">{children}</div>
        </div>
      </SidebarInset>
      <ActivityStatusBar />
      <TransportReadout />
      <Announcer />
      {/* Cold boot, as a layer rather than a replacement. The backend has answered and said it
          has never started; until it answers at all the shell is what renders, because an
          unasked question is not a cold boot. A startup failure resolves to the error banner
          instead. Kept in the same tree so the palette, keymap and banners stay mounted -- they
          are what the shell is for, and unmounting them mid-boot is a race no test should see. */}
      {healthChecked && !serviceStarted && healthStatus !== 'error' && <StartupState />}
      <CommandPalette />
      <ShortcutKeymap />
    </SidebarProvider>
  )
}

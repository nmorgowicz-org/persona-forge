import type { ReactNode } from 'react'
import {
  AudioLines,
  ChevronLeft,
  ChevronRight,
  Mic2,
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
import { ThemeSwitcher } from '@/components/ThemeSwitcher'
import { SwapBanner } from '@/components/SwapBanner'
import { type Page, useAppStore } from '@/store'

const NAV_ITEMS: { page: Page; label: string; icon: typeof Mic2; description: string }[] = [
  { page: 'speak', label: 'Speak', icon: AudioLines, description: 'Text to speech' },
  { page: 'voice-design', label: 'Voice Design', icon: Sparkles, description: 'Craft a new voice' },
  { page: 'voice-library', label: 'Voice Library', icon: Mic2, description: 'Saved voices' },
  { page: 'integrations', label: 'Integrations', icon: Plug, description: 'API & apps' },
  { page: 'runtime', label: 'Runtime', icon: Settings2, description: 'Live server config' },
]

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
          <ThemeSwitcher />
          <p className="text-[11px] leading-snug text-muted-foreground group-data-[collapsible=icon]:hidden">
            Voices designed here are served over the OpenAI-compatible endpoint for Hermes and
            other apps.
          </p>
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
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-5xl px-6 py-8">{children}</div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}

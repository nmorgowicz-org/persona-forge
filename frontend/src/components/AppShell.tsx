import type { ReactNode } from 'react'
import { AudioLines, Mic2, Plug, Settings2, Sparkles } from 'lucide-react'
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
              <span className="text-sm font-semibold leading-none">Qwen3-TTS</span>
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
        <SidebarFooter className="gap-3 px-3 py-3 group-data-[collapsible=icon]:hidden">
          <ThemeSwitcher />
          <p className="text-[11px] leading-snug text-muted-foreground">
            Voices designed here are served over the OpenAI-compatible endpoint for Hermes and
            other apps.
          </p>
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

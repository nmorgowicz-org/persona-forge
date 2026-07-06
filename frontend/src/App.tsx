import { TooltipProvider } from '@/components/ui/tooltip'
import { AppShell } from '@/components/AppShell'
import { HealthStatusBanner } from '@/components/HealthStatusBanner'
import { useAppStore } from '@/store'
import { SpeakPage } from '@/pages/SpeakPage'
import { VoiceDesignPage } from '@/pages/VoiceDesignPage'
import { VoiceLibraryPage } from '@/pages/VoiceLibraryPage'
import { StitchStudioPage } from '@/pages/StitchStudioPage'
import { IntegrationsPage } from '@/pages/IntegrationsPage'
import { RuntimeConfigPage } from '@/pages/RuntimeConfigPage'

export default function App() {
  const page = useAppStore((s) => s.page)

  return (
    <TooltipProvider>
      <div className="relative flex min-h-screen w-full flex-col">
        <div className="sticky top-0 z-50">
          <HealthStatusBanner />
        </div>
        <AppShell>
          {page === 'speak' && <SpeakPage />}
          {page === 'voice-design' && <VoiceDesignPage />}
          {page === 'voice-library' && <VoiceLibraryPage />}
          {page === 'stitch-studio' && <StitchStudioPage />}
          {page === 'integrations' && <IntegrationsPage />}
          {page === 'runtime' && <RuntimeConfigPage />}
        </AppShell>
      </div>
    </TooltipProvider>
  )
}

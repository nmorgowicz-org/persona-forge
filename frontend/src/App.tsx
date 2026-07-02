import { TooltipProvider } from '@/components/ui/tooltip'
import { AppShell } from '@/components/AppShell'
import { useAppStore } from '@/store'
import { SpeakPage } from '@/pages/SpeakPage'
import { VoiceDesignPage } from '@/pages/VoiceDesignPage'
import { VoiceLibraryPage } from '@/pages/VoiceLibraryPage'
import { IntegrationsPage } from '@/pages/IntegrationsPage'
import { RuntimeConfigPage } from '@/pages/RuntimeConfigPage'

export default function App() {
  const page = useAppStore((s) => s.page)

  return (
    <TooltipProvider>
      <AppShell>
        {page === 'speak' && <SpeakPage />}
        {page === 'voice-design' && <VoiceDesignPage />}
        {page === 'voice-library' && <VoiceLibraryPage />}
        {page === 'integrations' && <IntegrationsPage />}
        {page === 'runtime' && <RuntimeConfigPage />}
      </AppShell>
    </TooltipProvider>
  )
}

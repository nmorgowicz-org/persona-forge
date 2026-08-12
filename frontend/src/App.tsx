import { TitleTooltipBridge, TooltipProvider } from '@/components/ui/tooltip'
import { AppShell } from '@/components/AppShell'
import { useAppStore } from '@/store'
import { PersonaWizardPage } from '@/pages/PersonaWizardPage'
import { SpeakPage } from '@/pages/SpeakPage'
import { VoiceDesignPage } from '@/pages/VoiceDesignPage'
import { VoiceLibraryPage } from '@/pages/VoiceLibraryPage'
import { StitchStudioPage } from '@/pages/StitchStudioPage'
import { IntegrationsPage } from '@/pages/IntegrationsPage'
import { RuntimeConfigPage } from '@/pages/RuntimeConfigPage'
import { Glossary } from '@/components/audio/Glossary'

export default function App() {
  const page = useAppStore((s) => s.page)
  const glossaryOpen = useAppStore((s) => s.glossaryOpen)
  const setGlossaryOpen = useAppStore((s) => s.setGlossaryOpen)
  const glossaryFocusId = useAppStore((s) => s.glossaryFocusId)

  return (
    <TooltipProvider>
      <TitleTooltipBridge />
      <div className="relative flex min-h-screen w-full flex-col">
        <AppShell>
          {page === 'wizard' && <PersonaWizardPage />}
          {page === 'speak' && <SpeakPage />}
          {page === 'voice-design' && <VoiceDesignPage />}
          {page === 'voice-library' && <VoiceLibraryPage />}
          {page === 'stitch-studio' && <StitchStudioPage />}
          {page === 'integrations' && <IntegrationsPage />}
          {page === 'runtime' && <RuntimeConfigPage />}
        </AppShell>
        <Glossary
          isOpen={glossaryOpen}
          onClose={() => setGlossaryOpen(false)}
          focusId={glossaryFocusId}
        />
      </div>
    </TooltipProvider>
  )
}

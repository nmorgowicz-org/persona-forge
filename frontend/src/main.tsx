import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { applyDesktopMarker } from './lib/desktopShell'
import { getPref, subscribePrefs, syncPrefsFromServer } from './lib/uiPreferences'

// Contract D20/§6.10: set data-desktop before the first render so there is no flash, and so all
// desktop-only CSS (in index.css, scoped under html[data-desktop='macos']) is already active
// when the first frame paints.
applyDesktopMarker()

// First paint uses the local copy (instant); the server sync then corrects or migrates it,
// and the subscriber re-applies the theme so a server value wins without a reload. The
// dataset is set directly (not applyTheme) so the sync itself does not trigger a redundant
// preferences POST.
subscribePrefs(() => {
  document.documentElement.dataset.theme = getPref('theme', 'violet')
})
void syncPrefsFromServer()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

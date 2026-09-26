import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { getPref, subscribePrefs, syncPrefsFromServer } from './lib/uiPreferences'

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

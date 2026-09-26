// Persona Forge splash controller (contract §6.1, §6.6, §6.10). Plain JS, no build step, no
// bundler: this file ships verbatim inside the app. It talks to the Rust side only through the
// splash capability's commands/events (get_bootstrap_state, retry_bootstrap, show_logs,
// quit_app, open_settings, bootstrap://progress) — never fetch()/XHR to a remote origin.

// Desktop marker (contract D20/§6.10): the same initialization script the main window's
// desktop_marker_script() injects before this page parses. Setting it here too, before first
// paint, means the splash never flashes an opaque background on macOS even on a slow load.
;(() => {
  var g = window.__PERSONA_FORGE_DESKTOP__
  if (g && g.platform) {
    document.documentElement.dataset.desktop = g.platform
  }
})()

const STEP_ORDER = ['verify', 'venv', 'sync', 'install', 'start', 'wait']
const MAX_LOG_LINES = 200

const stepsEl = document.getElementById('steps')
const logTailEl = document.getElementById('log-tail')
const errorPanelEl = document.getElementById('error-panel')
const errorMessageEl = document.getElementById('error-message')
const errorLogEl = document.getElementById('error-log')
const appEl = document.getElementById('app')

const logLines = []

function setActiveStep(step) {
  const idx = STEP_ORDER.indexOf(step)
  STEP_ORDER.forEach((name, i) => {
    const li = stepsEl.querySelector('[data-step="' + name + '"]')
    if (!li) return
    if (idx === -1) {
      li.removeAttribute('data-status')
      return
    }
    if (i < idx) li.dataset.status = 'done'
    else if (i === idx) li.dataset.status = 'active'
    else li.removeAttribute('data-status')
  })
}

function appendLogLine(line) {
  if (!line) return
  logLines.push(line)
  while (logLines.length > MAX_LOG_LINES) logLines.shift()
  logTailEl.textContent = logLines.join('\n')
  logTailEl.scrollTop = logTailEl.scrollHeight
}

function showError(message, tailLines) {
  appEl.dataset.state = 'error'
  errorMessageEl.textContent = message
  errorLogEl.textContent = (tailLines || logLines.slice(-30)).join('\n')
  errorPanelEl.hidden = false
}

function clearError() {
  appEl.dataset.state = 'booting'
  errorPanelEl.hidden = true
}

async function invoke(cmd, args) {
  // window.__TAURI__.core.invoke — the IPC surface the splash capability allows.
  return window.__TAURI__.core.invoke(cmd, args)
}

async function applyState(state) {
  if (!state) return
  if (state.error) {
    showError(state.error, state.log_tail)
    return
  }
  clearError()
  setActiveStep(state.step)
  if (state.step === 'wait' && state.ready) {
    appEl.dataset.state = 'ready'
  }
}

document.getElementById('retry-button').addEventListener('click', () => {
  clearError()
  invoke('retry_bootstrap').catch((err) => showError(String(err), logLines.slice(-30)))
})

document.getElementById('show-logs-button').addEventListener('click', () => {
  invoke('show_logs').catch(() => {})
})

document.getElementById('quit-button').addEventListener('click', () => {
  invoke('quit_app').catch(() => {})
})

async function main() {
  window.__TAURI__.event.listen('bootstrap://progress', (event) => {
    const payload = event.payload || {}
    if (payload.line) appendLogLine(payload.line)
    if (payload.step) setActiveStep(payload.step)
  })

  try {
    const state = await invoke('get_bootstrap_state')
    await applyState(state)
  } catch (err) {
    showError(String(err), [])
  }
}

main()

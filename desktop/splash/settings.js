const invoke = (command, args) => window.__TAURI__.core.invoke(command, args)

const app = document.getElementById('settings-app')
const form = document.getElementById('settings-form')
const error = document.getElementById('error')
const retryLoad = document.getElementById('retry-load')
const status = document.getElementById('status')
const portMode = document.getElementById('port-mode')
const portInput = document.getElementById('port')
const portField = document.getElementById('port-field')
const addressList = document.getElementById('address-list')
const copyButton = document.getElementById('copy-address')
let addresses = []

function setError(message) {
  error.textContent = message
  error.hidden = !message
  status.textContent = ''
}

function updatePortField() {
  const fixed = portMode.value === 'fixed'
  portInput.disabled = !fixed
  portField.classList.toggle('disabled', !fixed)
}

async function refreshAddresses() {
  addresses = await invoke('list_addresses')
  addressList.replaceChildren()
  if (addresses.length === 0) {
    const item = document.createElement('li')
    item.textContent = 'The local server is not running yet.'
    addressList.append(item)
  } else {
    for (const address of addresses) {
      const item = document.createElement('li')
      item.textContent = address
      addressList.append(item)
    }
  }
  copyButton.disabled = addresses.length === 0
}

function clearAddresses() {
  addresses = []
  copyButton.disabled = true
  const item = document.createElement('li')
  item.textContent = 'Refreshing the local server address…'
  addressList.replaceChildren(item)
}

async function waitForServerReady() {
  for (let attempt = 0; attempt < 360; attempt += 1) {
    const state = await invoke('get_bootstrap_state')
    if (state.ready) return
    if (state.error) throw new Error(state.error)
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error('Timed out waiting for the local server to restart.')
}


async function loadSettings() {
  try {
    const settings = await invoke('get_settings')
    portMode.value = settings.port_mode
    portInput.value = settings.port ?? ''
    document.getElementById('network-access').checked = settings.network_access
    document.getElementById('tray-enabled').checked = settings.tray_enabled
    document.getElementById('ask-where-to-save').checked = settings.ask_where_to_save
    updatePortField()

    await refreshAddresses()
    form.hidden = false
    retryLoad.hidden = true
    app.setAttribute('aria-busy', 'false')
  } catch (reason) {
    app.setAttribute('aria-busy', 'false')
    setError(String(reason))
    retryLoad.hidden = false
  }
}

portMode.addEventListener('change', updatePortField)

form.addEventListener('submit', async (event) => {
  event.preventDefault()
  setError('')
  status.textContent = 'Saving…'
  copyButton.disabled = true
  const port = portInput.value.trim()
  let saveError
  try {
    await invoke('apply_settings', {
      portMode: portMode.value,
      port: port ? Number(port) : null,
      networkAccess: document.getElementById('network-access').checked,
      trayEnabled: document.getElementById('tray-enabled').checked,
      askWhereToSave: document.getElementById('ask-where-to-save').checked,
    })
  } catch (reason) {
    saveError = reason
  }
  clearAddresses()
  try {
    await waitForServerReady()
    await refreshAddresses()
  } catch (reason) {
    if (!saveError) saveError = reason
  }
  if (saveError) {
    setError(String(saveError))
  } else {
    status.textContent = 'Settings saved.'
  }
  copyButton.disabled = addresses.length === 0
})

copyButton.addEventListener('click', async () => {
  if (addresses.length === 0) {
    setError('The local server address is not available yet.')
    return
  }
  try {
    await invoke('copy_text', { text: addresses[0] })
    setError('')
    status.textContent = 'Local address copied.'
  } catch (reason) {
    setError(String(reason))
  }
})

retryLoad.addEventListener('click', async () => {
  retryLoad.disabled = true
  app.setAttribute('aria-busy', 'true')
  setError('')
  await loadSettings()
  retryLoad.disabled = false
})

loadSettings()


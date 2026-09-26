// Desktop marker (contract D20/§6.10). The `main` window's initialization script sets
// `window.__PERSONA_FORGE_DESKTOP__` before any page script runs; this module is how the SPA
// reads it. It is not IPC and grants nothing — adjusting existing behavior for pages rendered
// inside the desktop window, nothing more.

// Runtime-injected by desktop/src/marker.rs (the shell's main-window initialization script).
declare global {
  interface Window {
    __PERSONA_FORGE_DESKTOP__?: { platform?: string } & { readonly platform: string }
  }
}

const PLATFORMS = new Set(['macos', 'windows', 'linux'])

/** 'macos' | 'windows' | 'linux' when inside the desktop window, else null. */
export function desktopPlatform(): 'macos' | 'windows' | 'linux' | null {
  const platform = window.__PERSONA_FORGE_DESKTOP__?.platform
  if (typeof platform === 'string' && PLATFORMS.has(platform)) {
    return platform as 'macos' | 'windows' | 'linux'
  }
  return null
}

/** Apply the `data-desktop` attribute before the first render, so there is no flash. */
export function applyDesktopMarker(): void {
  const platform = desktopPlatform()
  if (platform !== null) {
    document.documentElement.dataset.desktop = platform
  }
}
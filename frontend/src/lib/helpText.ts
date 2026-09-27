let helpText: string | null = null
const helpListeners = new Set<() => void>()

export function setHelpText(next: string | null): void {
  if (helpText === next) return
  helpText = next
  for (const listener of helpListeners) listener()
}

export function subscribeHelpText(listener: () => void): () => void {
  helpListeners.add(listener)
  return () => {
    helpListeners.delete(listener)
  }
}

export function getHelpText(): string | null {
  return helpText
}

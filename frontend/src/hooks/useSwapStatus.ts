import { useAppStore } from '@/store'

// Delegates to the centralized /health poller in store.ts.
// Any consumer of this hook still behaves identically (boolean subscription).
export function useSwapStatus(): boolean {
  return useAppStore((s) => s.swapInProgress)
}

import { useSyncExternalStore } from 'react'
import { FALLBACK_MAIN_APP_ORIGIN, mainAppOrigin } from './api'

const noSubscription = () => () => {}

/**
 * Origin of the main app on this page's own host, safe to use while rendering.
 * The server render uses 127.0.0.1; the browser then switches to its real host
 * (for example localhost) without a hydration mismatch.
 */
export function useMainAppOrigin(): string {
  return useSyncExternalStore(noSubscription, mainAppOrigin, () => FALLBACK_MAIN_APP_ORIGIN)
}

import type { QueryClient } from '@tanstack/vue-query'
import type { WsMessagePayload } from '@/types/ws-events'
import { addDesktopTimeout, parseDesktopTimeout } from '@/lib/desktop-timeout'

export const messageEventHandlers = {
  msg: (_queryClient: QueryClient, payload: string) => {
    const warning = parseDesktopTimeout(JSON.parse(payload) as WsMessagePayload)
    if (warning) addDesktopTimeout(warning)
  }
}

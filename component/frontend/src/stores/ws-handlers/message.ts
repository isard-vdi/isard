import type { QueryClient } from '@tanstack/vue-query'
import type { WsMessagePayload } from '@/types/ws-events'
import { useMessageModalStore } from '@/stores/message-modal'

export const messageEventHandlers = {
  msg: (_queryClient: QueryClient, payload: string) => {
    const data: WsMessagePayload = JSON.parse(payload)
    useMessageModalStore().show(data.type, data.msg_code, data.params ?? {})
  }
}

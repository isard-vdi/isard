import type { QueryClient } from '@tanstack/vue-query'
import type { WsBulkSpawnPayload } from '@/types/ws-events'
import { useBulkSpawnStore } from '@/stores/bulk-spawn'

export const bulkSpawnEventHandlers = {
  creating_desktops: (_queryClient: QueryClient, payload: string) => {
    const data: WsBulkSpawnPayload = JSON.parse(payload)
    useBulkSpawnStore().start(data.deployment_id)
  },

  end_creating_desktops: (_queryClient: QueryClient, payload: string) => {
    const data: WsBulkSpawnPayload = JSON.parse(payload)
    useBulkSpawnStore().end(data.deployment_id)
  }
}

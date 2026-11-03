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
    // Older backends send only deployment_id; record the outcome only when it
    // is present so a missing field never reads as "0 created".
    const outcome =
      typeof data.failed === 'number'
        ? { created: data.created ?? 0, failed: data.failed, failures: data.failures ?? [] }
        : undefined
    useBulkSpawnStore().end(data.deployment_id, outcome)
  }
}

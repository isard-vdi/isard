import type { QueryClient } from '@tanstack/vue-query'
import type { WsUserMigrationPayload } from '@/types/ws-events'
import { useUserMigrationStore } from '@/stores/user-migration'

export const userMigrationEventHandlers = {
  user_migration_data: (_queryClient: QueryClient, payload: string) => {
    const data: WsUserMigrationPayload = JSON.parse(payload)
    useUserMigrationStore().update(data)
  }
}

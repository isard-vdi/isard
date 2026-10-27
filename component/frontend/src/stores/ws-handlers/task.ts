import type { QueryClient } from '@tanstack/vue-query'
import type { WsTaskPayload } from '@/types/ws-events'
import { useStorageTasksStore } from '@/stores/storage-tasks'

export const taskEventHandlers = {
  task: (_queryClient: QueryClient, payload: string) => {
    const task = JSON.parse(payload) as WsTaskPayload
    if (task?.id) useStorageTasksStore().update(task)
  }
}

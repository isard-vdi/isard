import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { WsTaskPayload } from '@/types/ws-events'

export const useStorageTasksStore = defineStore('storage-tasks', () => {
  const tasks = ref<Record<string, WsTaskPayload>>({})

  const update = (task: WsTaskPayload) => {
    tasks.value = { ...tasks.value, [task.id]: { ...tasks.value[task.id], ...task } }
  }

  return { tasks, update }
})

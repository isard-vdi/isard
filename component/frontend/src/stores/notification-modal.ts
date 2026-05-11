import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { NotificationFlatItem } from '@/gen/oas/apiv4'

export const useNotificationModalStore = defineStore('notification-modal', () => {
  const open = ref(false)
  const notifications = ref<NotificationFlatItem[]>([])

  const show = (items: NotificationFlatItem[]) => {
    notifications.value = items
    open.value = true
  }

  const close = () => {
    open.value = false
    notifications.value = []
  }

  return { open, notifications, show, close }
})

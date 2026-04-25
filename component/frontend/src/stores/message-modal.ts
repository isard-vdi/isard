import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { WsMessageParams } from '@/types/ws-events'

export type MessageModalLevel = 'info' | 'warning' | 'danger' | 'success'

const TYPE_TO_LEVEL: Record<string, MessageModalLevel> = {
  warning: 'warning',
  danger: 'danger',
  info: 'info',
  success: 'success'
}

export const useMessageModalStore = defineStore('message-modal', () => {
  const open = ref(false)
  const msgCode = ref<string>('')
  const level = ref<MessageModalLevel>('warning')
  const params = ref<WsMessageParams>({})

  const desktopId = computed(() => params.value.desktop_id ?? null)
  const extendEnabled = computed(() => params.value.extend_enabled === true)
  const extendTime = computed(() => params.value.extend_time ?? 0)

  const canExtend = computed(
    () => msgCode.value === 'desktop-time-limit' && extendEnabled.value && !!desktopId.value
  )

  const show = (type: string | null, code: string, rawParams: WsMessageParams) => {
    const next: WsMessageParams = { ...rawParams }
    if (typeof next.date === 'string' && next.date.length > 0) {
      const parsed = new Date(next.date)
      if (!Number.isNaN(parsed.getTime())) {
        next.date = parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
    }
    msgCode.value = code
    level.value = (type && TYPE_TO_LEVEL[type]) || 'warning'
    params.value = next
    open.value = true
  }

  const hide = () => {
    open.value = false
  }

  const $reset = () => {
    open.value = false
    msgCode.value = ''
    level.value = 'warning'
    params.value = {}
  }

  return {
    open,
    msgCode,
    level,
    params,
    desktopId,
    extendEnabled,
    extendTime,
    canExtend,
    show,
    hide,
    $reset
  }
})

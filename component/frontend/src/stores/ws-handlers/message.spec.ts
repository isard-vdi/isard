import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { QueryClient } from '@tanstack/vue-query'

import { messageEventHandlers } from './message'
import { useMessageModalStore } from '@/stores/message-modal'

const queryClient = {} as QueryClient

describe('ws-handlers / message', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('parses JSON payload and shows the modal via the store', () => {
    const payload = JSON.stringify({
      type: 'warning',
      msg_code: 'desktop-time-limit',
      params: { desktop_id: 'abc', extend_enabled: true, extend_time: 30 }
    })

    messageEventHandlers.msg(queryClient, payload)

    const store = useMessageModalStore()
    expect(store.open).toBe(true)
    expect(store.msgCode).toBe('desktop-time-limit')
    expect(store.level).toBe('warning')
    expect(store.desktopId).toBe('abc')
    expect(store.canExtend).toBe(true)
  })

  it('treats missing params as empty object', () => {
    const payload = JSON.stringify({ type: 'info', msg_code: 'searching-resources' })

    messageEventHandlers.msg(queryClient, payload)

    const store = useMessageModalStore()
    expect(store.open).toBe(true)
    expect(store.msgCode).toBe('searching-resources')
    expect(store.params).toEqual({})
  })
})

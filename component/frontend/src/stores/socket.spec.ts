import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

interface FakeSocket {
  on: ReturnType<typeof vi.fn>
  connect: ReturnType<typeof vi.fn>
  disconnect: ReturnType<typeof vi.fn>
}

const sockets: FakeSocket[] = []

vi.mock('@/services/socket', () => ({
  createSocket: () => {
    const socket = { on: vi.fn(), connect: vi.fn(), disconnect: vi.fn() }
    sockets.push(socket)
    return socket
  }
}))
vi.mock('@tanstack/vue-query', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/vue-query')>()),
  useQueryClient: () => ({})
}))
vi.mock('./ws-handlers', () => ({ registerSocketHandlers: vi.fn() }))

import { useSocketStore } from './socket'

describe('socket store', () => {
  beforeEach(() => {
    sockets.length = 0
    setActivePinia(createPinia())
  })

  it('reuses the pending client when navigations race the handshake', async () => {
    const store = useSocketStore()
    await store.connectWithToken()
    await store.connectWithToken()
    await store.connectWithToken()

    expect(store.isConnected).toBe(false)
    expect(sockets).toHaveLength(1)
    expect(sockets[0].connect).toHaveBeenCalledTimes(1)
  })

  it('keeps a single client across a drop that socket.io retries on its own', async () => {
    const store = useSocketStore()
    await store.connectWithToken()

    const onDisconnect = sockets[0].on.mock.calls.find(([event]) => event === 'disconnect')?.[1]
    onDisconnect?.('transport close')
    await store.connectWithToken()

    expect(sockets).toHaveLength(1)
  })

  it('builds a fresh client after an explicit disconnect', async () => {
    const store = useSocketStore()
    await store.connectWithToken()
    store.disconnect()
    await store.connectWithToken()

    expect(sockets[0].disconnect).toHaveBeenCalledTimes(1)
    expect(sockets).toHaveLength(2)
  })
})

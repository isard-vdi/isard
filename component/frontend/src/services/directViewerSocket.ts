import { ref, onUnmounted, type Ref } from 'vue'
import type { QueryClient } from '@tanstack/vue-query'
import { createSocket } from './socket'

/**
 * Creates and manages a dedicated socket connection for the direct viewer.
 * This is separate from the main user socket so that logged-in users
 * keep their existing connection while also receiving directviewer_update events.
 */
export function useDirectViewerSocket(
  token: Ref<string>,
  queryClient: QueryClient,
  queryKey: any,
  onViewersChanged: () => void
) {
  const isConnected = ref(false)
  let socket: ReturnType<typeof createSocket> | null = null

  const connect = (getJwt: () => string | undefined) => {
    if (socket) return

    socket = createSocket(getJwt)

    socket.on('connect', () => {
      isConnected.value = true
    })

    socket.on('disconnect', () => {
      isConnected.value = false
    })

    socket.on('directviewer_update', (payload: string) => {
      const { viewers_changed, ...data } = JSON.parse(payload)

      queryClient.setQueryData(queryKey, (old: any) => {
        if (!old) return data
        return { ...old, ...data }
      })
      if (viewers_changed) onViewersChanged()
    })

    socket.connect()
  }

  const disconnect = () => {
    if (socket) {
      socket.removeAllListeners()
      socket.disconnect()
      socket = null
      isConnected.value = false
    }
  }

  onUnmounted(() => {
    disconnect()
  })

  return {
    isConnected,
    connect,
    disconnect
  }
}

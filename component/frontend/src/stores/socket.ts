import { defineStore } from 'pinia'
import { createSocket } from '@/services/socket'
import { useQueryClient } from '@tanstack/vue-query'
import { registerSocketHandlers } from './ws-handlers'
import { ref } from 'vue'
import type { Socket } from 'socket.io-client'

// Using setup stores
export const useSocketStore = defineStore('socket', () => {
  // Resolve the QueryClient once, in the pinia setup-factory context where
  // Vue's inject() works. Calling useQueryClient() inside connectWithToken
  // (a pinia action invoked from the router guard) throws because actions
  // run outside any component/setup injection scope.
  const queryClient = useQueryClient()
  const isConnected = ref(false)
  let socket: Socket | null = null

  const connectWithToken = async () => {
    // Guard on the instance: `isConnected` is false while socket.io is still
    // (re)connecting, and every navigation in that window built another client.
    if (socket) return

    socket = createSocket()
    registerSocketHandlers(socket, queryClient)

    socket.on('connect', () => {
      isConnected.value = true
    })

    socket.on('disconnect', (reason) => {
      isConnected.value = false
      console.warn('[socket] disconnected:', reason)
    })

    socket.on('connect_error', (error) => {
      console.error('[socket] connection error:', error.message)
    })

    socket.connect()
  }

  const disconnect = () => {
    if (socket) {
      socket.disconnect()
      socket = null
    }
    isConnected.value = false
  }

  const $reset = () => {
    disconnect()
  }

  return {
    isConnected,
    $reset,
    connectWithToken,
    disconnect
  }
})

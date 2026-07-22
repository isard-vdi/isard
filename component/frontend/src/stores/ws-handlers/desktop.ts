import { patchEntityList } from '@/lib/utils'
import type { WsDeletePayload, WsDesktopPayload, WsDesktopsQueuePayload } from '@/types/ws-events'
import type { UserDesktop } from '@/gen/oas/apiv4'
import { QueryClient } from '@tanstack/vue-query'
import { getUserDesktopsOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

const key = getUserDesktopsOptions().queryKey

type DesktopWithQueue = UserDesktop & { queue?: number }

export const desktopEventHandlers = {
  desktop_add: (queryClient: QueryClient, payload: string) => {
    const data: WsDesktopPayload = JSON.parse(payload)
    queryClient.setQueryData(key, (old) => {
      if (!old) {
        queryClient.setQueryDefaults(key, { staleTime: 0 })
      }
      return {
        ...old,
        desktops: patchEntityList(old?.desktops || [], 'add', data)
      }
    })
  },

  desktop_update: (queryClient: QueryClient, payload: string) => {
    const data: WsDesktopPayload = JSON.parse(payload)
    queryClient.setQueryData(key, (old) => {
      if (!old) {
        queryClient.setQueryDefaults(key, { staleTime: 0 })
      }
      return {
        ...old,
        desktops: patchEntityList(old?.desktops || [], 'update', data)
      }
    })
  },

  desktop_delete: (queryClient: QueryClient, payload: string) => {
    const data: WsDeletePayload = JSON.parse(payload)
    queryClient.setQueryData(key, (old) => {
      if (!old) {
        queryClient.setQueryDefaults(key, { staleTime: 0 })
      }
      return {
        ...old,
        desktops: patchEntityList(old?.desktops || [], 'delete', data)
      }
    })
  },

  desktops_queue: (queryClient: QueryClient, payload: string) => {
    const data: WsDesktopsQueuePayload = JSON.parse(payload)
    queryClient.setQueryData(key, (old) => {
      if (!old?.desktops) return old
      return {
        ...old,
        desktops: old.desktops.map((d: DesktopWithQueue) =>
          d.id in data ? { ...d, queue: data[d.id].position } : d
        )
      }
    })
  }
}

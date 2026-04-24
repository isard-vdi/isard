import { patchEntityList } from '@/lib/utils'
import type { WsDeletePayload, WsMediaPayload } from '@/types/ws-events'
import { QueryClient } from '@tanstack/vue-query'
import {
  getUserMediaApiV4ItemsMediaGetOptions,
  getUserSharedMediaApiV4ItemsMediaGetSharedGetOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

const key = getUserMediaApiV4ItemsMediaGetOptions().queryKey
const sharedKey = getUserSharedMediaApiV4ItemsMediaGetSharedGetOptions().queryKey

export const mediaEventHandlers = {
  media_add: (queryClient: QueryClient, payload: string) => {
    const data: WsMediaPayload = JSON.parse(payload)
    queryClient.setQueryData(key, (old) => {
      if (!old) {
        queryClient.setQueryDefaults(key, { staleTime: 0 })
      }
      return {
        ...old,
        media: patchEntityList(old?.media || [], 'add', data)
      }
    })
  },

  media_update: (queryClient: QueryClient, payload: string) => {
    const data: WsMediaPayload = JSON.parse(payload)
    queryClient.setQueryData(key, (old) => {
      if (!old) {
        queryClient.setQueryDefaults(key, { staleTime: 0 })
      }
      return {
        ...old,
        media: patchEntityList(old?.media || [], 'update', data)
      }
    })
    // change-handler emits user-scope media events to the owner's
    // /userspace room. When the recipient is a category admin/manager
    // (subscribed to /administrators), they get the same event and may
    // hold the shared-media query in cache — invalidate it so status
    // transitions reflect on the Shared tab.
    queryClient.invalidateQueries({ queryKey: sharedKey })
  },

  media_delete: (queryClient: QueryClient, payload: string) => {
    const data: WsDeletePayload = JSON.parse(payload)
    queryClient.setQueryData(key, (old) => {
      if (!old) {
        queryClient.setQueryDefaults(key, { staleTime: 0 })
      }
      return {
        ...old,
        media: patchEntityList(old?.media || [], 'delete', data)
      }
    })
    queryClient.setQueryData(sharedKey, (old) => {
      if (!old) return old
      return {
        ...old,
        media: patchEntityList(old?.media || [], 'delete', data)
      }
    })
  }
}

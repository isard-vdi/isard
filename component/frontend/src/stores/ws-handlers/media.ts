import { patchEntityList } from '@/lib/utils'
import type {
  WsDeletePayload,
  WsMediaPayload,
  WsMediaProgress,
  WsProgressPayload
} from '@/types/ws-events'
import { QueryClient } from '@tanstack/vue-query'
import {
  getUserMediaOptions,
  getUserSharedMediaOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

const key = getUserMediaOptions().queryKey
const sharedKey = getUserSharedMediaOptions().queryKey

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

  // The tick never reaches the row, so it arrives on its own event with
  // nothing but the counters: merge it into both cached lists, and never
  // invalidate — it lands once a second.
  media_progress: (queryClient: QueryClient, payload: string) => {
    const data: WsProgressPayload<WsMediaProgress> = JSON.parse(payload)
    for (const queryKey of [key, sharedKey]) {
      queryClient.setQueryData(queryKey, (old) => {
        if (!old) return old
        return {
          ...old,
          media: patchEntityList(old?.media || [], 'update', data)
        }
      })
    }
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

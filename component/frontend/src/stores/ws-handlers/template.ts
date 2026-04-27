import { patchEntityList } from '@/lib/utils'
import type { WsDeletePayload, WsTemplatePayload } from '@/types/ws-events'
import { QueryClient } from '@tanstack/vue-query'
import { getUserTemplatesOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

const key = getUserTemplatesOptions().queryKey

export const templateEventHandlers = {
  template_add: (queryClient: QueryClient, payload: string) => {
    const data: WsTemplatePayload = JSON.parse(payload)
    queryClient.setQueryData(key, (old) => {
      if (!old) {
        queryClient.setQueryDefaults(key, { staleTime: 0 })
      }
      return {
        ...old,
        templates: patchEntityList(old?.templates || [], 'add', data)
      }
    })
  },

  template_update: (queryClient: QueryClient, payload: string) => {
    const data: WsTemplatePayload = JSON.parse(payload)
    queryClient.setQueryData(key, (old) => {
      if (!old) {
        queryClient.setQueryDefaults(key, { staleTime: 0 })
      }
      return {
        ...old,
        templates: patchEntityList(old?.templates || [], 'update', data)
      }
    })
  },

  template_delete: (queryClient: QueryClient, payload: string) => {
    const data: WsDeletePayload = JSON.parse(payload)
    queryClient.setQueryData(key, (old) => {
      if (!old) {
        queryClient.setQueryDefaults(key, { staleTime: 0 })
      }
      return {
        ...old,
        templates: patchEntityList(old?.templates || [], 'delete', data)
      }
    })
  }
}

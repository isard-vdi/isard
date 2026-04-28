import { patchEntityList } from '@/lib/utils'
import type { WsDeletePayload, WsDeploymentPayload } from '@/types/ws-events'
import { QueryClient } from '@tanstack/vue-query'
import { getAllDeploymentsOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

const key = getAllDeploymentsOptions().queryKey

export const deploymentEventHandlers = {
  deployment_add: (queryClient: QueryClient, payload: string) => {
    const data: WsDeploymentPayload = JSON.parse(payload)
    queryClient.setQueryData(key, (old) => {
      if (!old) {
        queryClient.setQueryDefaults(key, { staleTime: 0 })
      }
      return {
        ...old,
        deployments: patchEntityList(old?.deployments || [], 'add', data)
      }
    })
  },

  deployment_update: (queryClient: QueryClient, payload: string) => {
    const data: WsDeploymentPayload = JSON.parse(payload)
    queryClient.setQueryData(key, (old) => {
      if (!old) {
        queryClient.setQueryDefaults(key, { staleTime: 0 })
      }
      return {
        ...old,
        deployments: patchEntityList(old?.deployments || [], 'update', data)
      }
    })
  },

  deployment_delete: (queryClient: QueryClient, payload: string) => {
    const data: WsDeletePayload = JSON.parse(payload)
    queryClient.setQueryData(key, (old) => {
      if (!old) {
        queryClient.setQueryDefaults(key, { staleTime: 0 })
      }
      return {
        ...old,
        deployments: patchEntityList(old?.deployments || [], 'delete', data)
      }
    })
  }
}

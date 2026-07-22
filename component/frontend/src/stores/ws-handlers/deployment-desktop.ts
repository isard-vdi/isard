import { QueryClient, type QueryKey } from '@tanstack/vue-query'
import type {
  WsDeletePayload,
  WsDeploymentDesktopPayload,
  WsDeploymentPayload
} from '@/types/ws-events'

/**
 * Match any TanStack Query whose first key element is a generated-client
 * descriptor referring to a deployment-scoped endpoint. The generated keys
 * take the shape `[{ _id: 'getLabApiV4Item...', path: {...} }]`, so we
 * check the `_id` prefix string for "Deployment" or "Lab".
 */
function isDeploymentScopedQuery(queryKey: QueryKey): boolean {
  const first = queryKey[0]
  if (!first || typeof first !== 'object') return false
  const id = (first as { _id?: unknown })._id
  if (typeof id !== 'string') return false
  return id.includes('Deployment') || id.includes('Lab')
}

function invalidateDeploymentScoped(queryClient: QueryClient) {
  queryClient.invalidateQueries({
    predicate: (query) => isDeploymentScopedQuery(query.queryKey)
  })
}

export const deploymentDesktopEventHandlers = {
  deploymentdesktop_add: (queryClient: QueryClient, payload: string) => {
    const _data: WsDeploymentDesktopPayload = JSON.parse(payload)
    invalidateDeploymentScoped(queryClient)
  },

  deploymentdesktop_update: (queryClient: QueryClient, payload: string) => {
    const _data: WsDeploymentDesktopPayload = JSON.parse(payload)
    invalidateDeploymentScoped(queryClient)
  },

  deploymentdesktop_delete: (queryClient: QueryClient, payload: string) => {
    const _data: WsDeletePayload = JSON.parse(payload)
    invalidateDeploymentScoped(queryClient)
  },

  deployments_update: (queryClient: QueryClient, payload: string) => {
    const _data: WsDeploymentPayload = JSON.parse(payload)
    invalidateDeploymentScoped(queryClient)
  }
}

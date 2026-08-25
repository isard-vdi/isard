import { QueryClient, type QueryKey } from '@tanstack/vue-query'
import type {
  WsDeletePayload,
  WsDeploymentDesktopPayload,
  WsDeploymentPayload
} from '@/types/ws-events'
import { DEPLOYMENT_VISIBILITY_MUTATION_KEY } from '@/composables/useDeploymentVisibility'

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

/**
 * Coalescing window for the invalidation below.
 *
 * The change handler emits one `deploymentdesktop_update` per domain, so a
 * bulk write — hiding one deployment desktop across 100 users — arrives as 100
 * events. Without this, each one invalidates every deployment-scoped query
 * and triggers its own refetch.
 *
 * A module-level timer rather than `useDebounceFn`: these handlers are a
 * plain object with no component instance to own a composable.
 */
const INVALIDATE_DEBOUNCE_MS = 300
let invalidateTimer: ReturnType<typeof setTimeout> | null = null

function invalidateDeploymentScoped(queryClient: QueryClient) {
  if (invalidateTimer !== null) clearTimeout(invalidateTimer)
  invalidateTimer = setTimeout(() => {
    invalidateTimer = null
    // Our own visibility write is in flight: its optimistic patch is
    // authoritative until the mutation's `onSettled` invalidates. Refetching
    // here would clobber it with state the server may not have applied yet.
    if (queryClient.isMutating({ mutationKey: DEPLOYMENT_VISIBILITY_MUTATION_KEY }) > 0) return
    queryClient.invalidateQueries({
      predicate: (query) => isDeploymentScopedQuery(query.queryKey)
    })
  }, INVALIDATE_DEBOUNCE_MS)
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

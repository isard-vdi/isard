import { QueryClient, hashKey, type QueryKey } from '@tanstack/vue-query'
import type {
  WsDeletePayload,
  WsDeploymentDesktopPayload,
  WsDeploymentPayload
} from '@/types/ws-events'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'
import type { GetAllDeploymentsResponse, GetDeploymentResponse } from '@/gen/oas/apiv4/types.gen'
import {
  getAllDeploymentsQueryKey,
  getDeploymentQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { recomputeDeployment } from '@/lib/deployment-visibility'
import { patchEntityList } from '@/lib/utils'
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
 * The change handler emits one event per domain, so a bulk write — adding a
 * desktop to a deployment with 100 users — arrives as 100 events. Without
 * this, each one invalidates every deployment-scoped query and triggers its
 * own refetch.
 *
 * A module-level timer rather than `useDebounceFn`: these handlers are a
 * plain object with no component instance to own a composable.
 */
const INVALIDATE_DEBOUNCE_MS = 300
let invalidateTimer: ReturnType<typeof setTimeout> | null = null
// Hashes of queries already patched in place; null once any call in the
// window needs everything refetched.
let invalidateSkip: Set<string> | null = null

function invalidateDeploymentScoped(queryClient: QueryClient, patched?: QueryKey) {
  const pending = invalidateTimer !== null
  if (!patched) invalidateSkip = null
  else if (!pending) invalidateSkip = new Set([hashKey(patched)])
  else invalidateSkip?.add(hashKey(patched))

  if (invalidateTimer !== null) clearTimeout(invalidateTimer)
  invalidateTimer = setTimeout(() => {
    invalidateTimer = null
    const skip = invalidateSkip
    invalidateSkip = null
    // Our own visibility write is in flight: its optimistic patch is
    // authoritative until the mutation settles. Refetching here would clobber
    // it with state the server may not have applied yet.
    if (queryClient.isMutating({ mutationKey: DEPLOYMENT_VISIBILITY_MUTATION_KEY }) > 0) return
    queryClient.invalidateQueries({
      predicate: (query) => isDeploymentScopedQuery(query.queryKey) && !skip?.has(query.queryHash)
    })
  }, INVALIDATE_DEBOUNCE_MS)
}

// `WaitingIP` is display-only for a started wireguard desktop whose guest IP
// has not landed; the row says `Started`, which is what a refetch would write.
const rowStatus = (status?: string) =>
  status === DesktopStatusEnum.WAITING_IP ? DesktopStatusEnum.STARTED : status

/**
 * Fold a desktop event into the cached deployment instead of refetching it.
 *
 * The payload carries everything the matrix cell holds — visibility, status
 * and name — so the deployment itself costs zero requests however many
 * events a bulk change emits. The other deployment-scoped queries (a
 * participant's own desktops, the shared list) are still refetched, since
 * only the owner's view has a deployment to patch. The deployment is
 * refetched too when the cell is not in cache: the event is then about a
 * desktop created or reassigned while the page was open, and only a read can
 * tell us which column it belongs to.
 */
function patchDeploymentDesktop(queryClient: QueryClient, data: WsDeploymentDesktopPayload) {
  if (!data.tag) return
  const queryKey = getDeploymentQueryKey({ path: { deployment_id: data.tag } })
  const cached = queryClient.getQueryData<GetDeploymentResponse>(queryKey)
  if (!cached) {
    invalidateDeploymentScoped(queryClient)
    return
  }

  // While our own visibility write is in flight the optimistic patch owns
  // `visible`: an event emitted just before the write would otherwise revert
  // it for a frame. The rest of the row is still news worth keeping.
  const keepVisible =
    queryClient.isMutating({ mutationKey: DEPLOYMENT_VISIBILITY_MUTATION_KEY }) > 0

  let found = false
  const users = cached.users.map((user) => {
    if (user.id !== data.user) return user
    return {
      ...user,
      desktops: (user.desktops ?? []).map((desktop) => {
        if (desktop.desktop_id !== data.id) return desktop
        found = true
        return {
          ...desktop,
          name: data.name,
          status: rowStatus(data.status),
          visible: keepVisible ? desktop.visible : !!data.visible
        }
      }),
      last_access: Math.max(user.last_access ?? 0, data.accessed ?? 0) || null
    }
  })

  if (!found) {
    invalidateDeploymentScoped(queryClient)
    return
  }
  queryClient.setQueryData<GetDeploymentResponse>(
    queryKey,
    recomputeDeployment({ ...cached, users })
  )
  invalidateDeploymentScoped(queryClient, queryKey)
}

export const deploymentDesktopEventHandlers = {
  deploymentdesktop_add: (queryClient: QueryClient, payload: string) => {
    const _data: WsDeploymentDesktopPayload = JSON.parse(payload)
    invalidateDeploymentScoped(queryClient)
  },

  deploymentdesktop_update: (queryClient: QueryClient, payload: string) => {
    const data: WsDeploymentDesktopPayload = JSON.parse(payload)
    patchDeploymentDesktop(queryClient, data)
  },

  deploymentdesktop_delete: (queryClient: QueryClient, payload: string) => {
    const _data: WsDeletePayload = JSON.parse(payload)
    invalidateDeploymentScoped(queryClient)
  },

  // The desktop rows are already kept in step by `deploymentdesktop_update`,
  // and `deployment_update` refreshes the list for the owner. What is left is
  // the deployment's own columns for a co-owner, who is in this room only.
  deployments_update: (queryClient: QueryClient, payload: string) => {
    const data: WsDeploymentPayload = JSON.parse(payload)
    const queryKey = getDeploymentQueryKey({ path: { deployment_id: data.id } })
    queryClient.setQueryData<GetDeploymentResponse>(queryKey, (cached) =>
      cached
        ? { ...cached, info: { ...cached.info, name: data.name, description: data.description } }
        : cached
    )
    queryClient.setQueryData<GetAllDeploymentsResponse>(getAllDeploymentsQueryKey(), (cached) =>
      cached
        ? {
            ...cached,
            deployments: patchEntityList(cached.deployments, 'update', {
              id: data.id,
              name: data.name,
              // DeploymentsHandler is the only emitter of this event and it
              // aliases the aggregates to snake_case, but a payload without
              // them must leave the cached counters alone rather than blank
              // them.
              ...(typeof data.visible_desktops === 'number'
                ? {
                    tag_visible: !!data.tag_visible,
                    visible_desktops: data.visible_desktops,
                    started_desktops: data.started_desktops,
                    total_desktops: data.total_desktops
                  }
                : {})
            })
          }
        : cached
    )
  }
}

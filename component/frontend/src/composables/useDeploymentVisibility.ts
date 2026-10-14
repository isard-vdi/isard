import { useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  setDeploymentVisibilityMutation,
  getDeploymentQueryKey,
  getAllDeploymentsQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type {
  DeploymentVisibilityResponse,
  GetAllDeploymentsResponse,
  GetDeploymentResponse,
  SetDeploymentVisibilityRequest
} from '@/gen/oas/apiv4/types.gen'
import { recomputeDeployment } from '@/lib/deployment-visibility'
import { patchEntityList } from '@/lib/utils'

/**
 * Stable key so the WebSocket handler can tell "our own visibility write is
 * in flight" and hold off patching over the optimistic state.
 */
export const DEPLOYMENT_VISIBILITY_MUTATION_KEY = ['deploymentVisibility'] as const

/** Does this desktop fall inside the scope the request selects? */
function isSelected(
  desktop: { desktop_id: string; tag_desktop_id?: string | null },
  userId: string,
  body: SetDeploymentVisibilityRequest
): boolean {
  // `desktop_ids` is the most specific selector and ignores the others.
  if (body.desktop_ids?.length) return body.desktop_ids.includes(desktop.desktop_id)
  if (body.users?.length && !body.users.includes(userId)) return false
  if (body.tag_desktop_ids?.length) {
    return !!desktop.tag_desktop_id && body.tag_desktop_ids.includes(desktop.tag_desktop_id)
  }
  return true
}

/**
 * Apply a visibility SET to a cached deployment, mirroring the server's
 * derivation so the optimistic state and the eventual truth agree.
 */
export function patchVisibility(
  cached: GetDeploymentResponse | undefined,
  body: SetDeploymentVisibilityRequest
): GetDeploymentResponse | undefined {
  if (!cached) return cached

  return recomputeDeployment({
    ...cached,
    users: cached.users.map((user) => ({
      ...user,
      desktops: (user.desktops ?? []).map((desktop) =>
        isSelected(desktop, user.id, body) ? { ...desktop, visible: body.visible } : desktop
      )
    }))
  })
}

/** What `onMutate` hands to `onError` so a failed write can be rolled back. */
interface RollbackContext {
  previous: GetDeploymentResponse | undefined
}

export function useDeploymentVisibility(deploymentId: () => string) {
  const queryClient = useQueryClient()
  const queryKey = () => getDeploymentQueryKey({ path: { deployment_id: deploymentId() } })

  return useMutation({
    ...setDeploymentVisibilityMutation(),
    mutationKey: DEPLOYMENT_VISIBILITY_MUTATION_KEY,

    onMutate: async (variables) => {
      // Stop in-flight refetches so a response computed before the write
      // cannot land on top of the optimistic patch.
      await queryClient.cancelQueries({ queryKey: queryKey() })
      const previous = queryClient.getQueryData<GetDeploymentResponse>(queryKey())
      queryClient.setQueryData<GetDeploymentResponse>(queryKey(), (cached) =>
        patchVisibility(cached, variables.body as SetDeploymentVisibilityRequest)
      )
      return { previous }
    },

    // The response is the recomputed aggregate, so reconciling from it costs
    // no GET. A refetch here would be one request per click, and the change
    // handler emits one event per affected desktop on top of that.
    onSuccess: (data) => {
      const result = data as DeploymentVisibilityResponse

      queryClient.setQueryData<GetDeploymentResponse>(queryKey(), (cached) => {
        if (!cached) return cached
        return {
          ...cached,
          info: {
            ...cached.info,
            tag_visible: result.tag_visible,
            visible_desktops: result.visible_desktops,
            existing_desktops: result.existing_desktops
          }
        }
      })

      // Only the counters the write moved: the list row is otherwise the
      // same deployment it already holds.
      queryClient.setQueryData<GetAllDeploymentsResponse>(getAllDeploymentsQueryKey(), (cached) =>
        cached
          ? {
              ...cached,
              deployments: patchEntityList(cached.deployments, 'update', {
                id: result.id,
                tag_visible: result.tag_visible,
                visible_desktops: result.visible_desktops
              })
            }
          : cached
      )

      // The optimistic patch flipped the cells the selectors matched; the
      // server counted the rows that actually exist. A disagreement means the
      // cache is missing or holding a stale row, and only a read can fix it.
      const patched = queryClient.getQueryData<GetDeploymentResponse>(queryKey())
      const cells = (patched?.users ?? []).flatMap((user) => user.desktops ?? [])
      if (cells.length && cells.filter((cell) => cell.visible).length !== result.visible_desktops) {
        queryClient.invalidateQueries({ queryKey: queryKey() })
      }
    },

    // This vue-query version passes the onMutate result as the third argument
    // and types it `unknown`, so narrow it here to keep the rollback typed.
    onError: (_error, _variables, onMutateResult) => {
      const context = onMutateResult as RollbackContext | undefined
      if (context?.previous) queryClient.setQueryData(queryKey(), context.previous)
    }
  })
}

import { useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  setDeploymentVisibilityMutation,
  getDeploymentQueryKey,
  getAllDeploymentsQueryKey
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type {
  GetDeploymentResponse,
  SetDeploymentVisibilityRequest
} from '@/gen/oas/apiv4/types.gen'

/**
 * Stable key so the WebSocket handler can tell "our own visibility write is
 * in flight" and hold off invalidating over the optimistic patch.
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
 * derivation so the optimistic state and the eventual truth agree:
 * a user is visible when *any* of their desktops is, and so is the
 * deployment.
 */
export function patchVisibility(
  cached: GetDeploymentResponse | undefined,
  body: SetDeploymentVisibilityRequest
): GetDeploymentResponse | undefined {
  if (!cached) return cached

  let visibleDesktops = 0
  const users = (cached.users ?? []).map((user) => {
    const desktops = (user.desktops ?? []).map((desktop) =>
      isSelected(desktop, user.id, body) ? { ...desktop, visible: body.visible } : desktop
    )
    visibleDesktops += desktops.filter((desktop) => desktop.visible).length
    return { ...user, desktops, visible: desktops.some((desktop) => desktop.visible) }
  })

  return {
    ...cached,
    users,
    info: {
      ...cached.info,
      visible_desktops: visibleDesktops,
      tag_visible: visibleDesktops > 0
    }
  }
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

    // This vue-query version passes the onMutate result as the third argument
    // and types it `unknown`, so narrow it here to keep the rollback typed.
    onError: (_error, _variables, onMutateResult) => {
      const context = onMutateResult as RollbackContext | undefined
      if (context?.previous) queryClient.setQueryData(queryKey(), context.previous)
    },

    onSettled: () => {
      // Must be the generated key helper: generated keys are
      // `[{ _id, baseUrl, path }]`, so a bare string never matches.
      queryClient.invalidateQueries({ queryKey: queryKey() })
      queryClient.invalidateQueries({ queryKey: getAllDeploymentsQueryKey() })
    }
  })
}

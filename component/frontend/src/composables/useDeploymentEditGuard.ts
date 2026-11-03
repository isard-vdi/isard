import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'

import { getDeploymentOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { startedDesktopCount } from '@/lib/deployment-edit'

/** The API rejects editing a deployment with started desktops, so those get flagged first. */
export function useDeploymentEditGuard() {
  const router = useRouter()
  const route = useRoute()
  const queryClient = useQueryClient()

  const guarded = ref<{ deploymentId: string; startedCount: number } | null>(null)
  const pending = ref(false)

  const editRoute = (deploymentId: string) => ({
    name: 'edit-deployment',
    params: { deploymentId }
  })

  const requestEdit = async (deploymentId: string) => {
    if (pending.value) return
    pending.value = true
    const fromPath = route.path
    // Fresh: a cached entry from a while ago can miss a desktop started since.
    const deployment = await queryClient
      .fetchQuery({
        ...getDeploymentOptions({ path: { deployment_id: deploymentId } }),
        staleTime: 0
      })
      .catch(() => undefined)
      .finally(() => (pending.value = false))
    // The user left while the check ran: don't pull them back.
    if (route.path !== fromPath) return
    // On a failed check the form opens anyway: saving still runs the API's own.
    const startedCount = startedDesktopCount(deployment)
    if (startedCount > 0) {
      guarded.value = { deploymentId, startedCount }
      return
    }
    router.push(editRoute(deploymentId))
  }

  /**
   * Bound on the edit RouterLink's capture phase, so it runs before the link navigates:
   * a plain click goes through the check, a modified one (new tab...) is left to the link.
   */
  const onEditClick = (event: MouseEvent, deploymentId: string) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) {
      return
    }
    event.preventDefault()
    requestEdit(deploymentId)
  }

  const closeGuard = () => (guarded.value = null)

  return { guarded, pending, editRoute, requestEdit, onEditClick, closeGuard }
}

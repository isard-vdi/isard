import { QueryClient } from '@tanstack/vue-query'
import { getAllSharedDeploymentsOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

const key = getAllSharedDeploymentsOptions().queryKey

function updateStartedDesktops(queryClient: QueryClient, payload: any, delta: number) {
  const { id } = JSON.parse(payload)
  queryClient.setQueryData(key, (old) => {
    if (!old) return old
    return {
      ...old,
      deployments: old.deployments.map((d) =>
        d.id === id ? { ...d, started_desktops: Math.max(0, d.started_desktops + delta) } : d
      )
    }
  })
}

export const sharedDeploymentEventHandlers = {
  shared_deployment_desktop_start: (queryClient: QueryClient, payload: any) => {
    updateStartedDesktops(queryClient, payload, 1)
  },
  shared_deployment_desktop_stop: (queryClient: QueryClient, payload: any) => {
    updateStartedDesktops(queryClient, payload, -1)
  }
}

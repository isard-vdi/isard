import { QueryClient } from '@tanstack/vue-query'

// Invalidate-only pattern: payload is ignored — we refetch to match Vue 2 behavior.
const invalidatePlanningQueries = (queryClient: QueryClient) => {
  queryClient.invalidateQueries({
    queryKey: ['getItemPlans']
  })
}

export const planningEventHandlers = {
  plan_add: (queryClient: QueryClient, _payload: string) => invalidatePlanningQueries(queryClient),
  plan_update: (queryClient: QueryClient, _payload: string) =>
    invalidatePlanningQueries(queryClient),
  plan_delete: (queryClient: QueryClient, _payload: string) =>
    invalidatePlanningQueries(queryClient)
}

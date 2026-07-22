import { useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  createPlanMutation,
  updatePlanMutation,
  deletePlanMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

export function usePlanningMutations() {
  const queryClient = useQueryClient()

  const invalidatePlanningQueries = () => {
    queryClient.invalidateQueries({
      queryKey: ['getItemPlans']
    })
  }

  const createPlan = useMutation({
    ...createPlanMutation(),
    onSuccess: invalidatePlanningQueries
  })

  const updatePlan = useMutation({
    ...updatePlanMutation(),
    onSuccess: invalidatePlanningQueries
  })

  const deletePlan = useMutation({
    ...deletePlanMutation(),
    onSuccess: invalidatePlanningQueries
  })

  return { createPlan, updatePlan, deletePlan, invalidatePlanningQueries }
}

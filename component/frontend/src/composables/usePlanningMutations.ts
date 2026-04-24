import { useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  createPlanApiV4ItemReservablesPlannerPostMutation,
  updatePlanApiV4ItemReservablesPlannerPlanIdStartEndPutMutation,
  deletePlanApiV4ItemReservablesPlannerPlanIdDeleteMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

export function usePlanningMutations() {
  const queryClient = useQueryClient()

  const invalidatePlanningQueries = () => {
    queryClient.invalidateQueries({
      queryKey: ['getItemPlansApiV4ItemReservablesPlannerByItemItemIdGet']
    })
  }

  const createPlan = useMutation({
    ...createPlanApiV4ItemReservablesPlannerPostMutation(),
    onSuccess: invalidatePlanningQueries
  })

  const updatePlan = useMutation({
    ...updatePlanApiV4ItemReservablesPlannerPlanIdStartEndPutMutation(),
    onSuccess: invalidatePlanningQueries
  })

  const deletePlan = useMutation({
    ...deletePlanApiV4ItemReservablesPlannerPlanIdDeleteMutation(),
    onSuccess: invalidatePlanningQueries
  })

  return { createPlan, updatePlan, deletePlan, invalidatePlanningQueries }
}

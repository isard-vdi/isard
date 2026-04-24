import { useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  createBookingEventApiV4ItemBookingEventPostMutation,
  updateBookingEventApiV4ItemBookingEventBookingIdEditPutMutation,
  deleteBookingEventApiV4ItemBookingEventBookingIdDeleteMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

export function useBookingMutations() {
  const queryClient = useQueryClient()

  const invalidateBookingQueries = () => {
    queryClient.invalidateQueries({ queryKey: ['getUserBookingsApiV4ItemsBookingsGet'] })
    queryClient.invalidateQueries({
      queryKey: ['getBookingDesktopApiV4ItemBookingGetDesktopItemIdGet']
    })
    queryClient.invalidateQueries({
      queryKey: ['getBookingDesktopApiV4ItemBookingGetDeploymentItemIdGet']
    })
  }

  const createEvent = useMutation({
    ...createBookingEventApiV4ItemBookingEventPostMutation(),
    onSuccess: invalidateBookingQueries
  })

  const editEvent = useMutation({
    ...updateBookingEventApiV4ItemBookingEventBookingIdEditPutMutation(),
    onSuccess: invalidateBookingQueries
  })

  const deleteEvent = useMutation({
    ...deleteBookingEventApiV4ItemBookingEventBookingIdDeleteMutation(),
    onSuccess: invalidateBookingQueries
  })

  return { createEvent, editEvent, deleteEvent, invalidateBookingQueries }
}

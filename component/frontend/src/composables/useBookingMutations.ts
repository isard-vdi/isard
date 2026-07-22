import { useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  createBookingEventMutation,
  updateBookingEventMutation,
  deleteBookingEventMutation
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

export function useBookingMutations() {
  const queryClient = useQueryClient()

  const invalidateBookingQueries = () => {
    queryClient.invalidateQueries({ queryKey: ['getUserBookings'] })
    queryClient.invalidateQueries({
      queryKey: ['getBookingDesktop']
    })
    queryClient.invalidateQueries({
      queryKey: ['getBookingDeployment']
    })
  }

  const createEvent = useMutation({
    ...createBookingEventMutation(),
    onSuccess: invalidateBookingQueries
  })

  const editEvent = useMutation({
    ...updateBookingEventMutation(),
    onSuccess: invalidateBookingQueries
  })

  const deleteEvent = useMutation({
    ...deleteBookingEventMutation(),
    onSuccess: invalidateBookingQueries
  })

  return { createEvent, editEvent, deleteEvent, invalidateBookingQueries }
}

import { QueryClient } from '@tanstack/vue-query'

// Invalidate-only pattern: payload is ignored — we refetch to match Vue 2 behavior.
const invalidateBookingQueries = (queryClient: QueryClient) => {
  queryClient.invalidateQueries({ queryKey: ['getUserBookings'] })
  queryClient.invalidateQueries({
    queryKey: ['getBookingDesktop']
  })
  queryClient.invalidateQueries({
    queryKey: ['getBookingDeployment']
  })
}

export const bookingEventHandlers = {
  booking_add: (queryClient: QueryClient, _payload: string) =>
    invalidateBookingQueries(queryClient),
  booking_update: (queryClient: QueryClient, _payload: string) =>
    invalidateBookingQueries(queryClient),
  booking_delete: (queryClient: QueryClient, _payload: string) =>
    invalidateBookingQueries(queryClient)
}

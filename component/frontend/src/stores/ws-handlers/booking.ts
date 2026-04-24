import { QueryClient } from '@tanstack/vue-query'

// Invalidate-only pattern: payload is ignored — we refetch to match Vue 2 behavior.
const invalidateBookingQueries = (queryClient: QueryClient) => {
  queryClient.invalidateQueries({ queryKey: ['getUserBookingsApiV4ItemsBookingsGet'] })
  queryClient.invalidateQueries({
    queryKey: ['getBookingDesktopApiV4ItemBookingGetDesktopItemIdGet']
  })
  queryClient.invalidateQueries({
    queryKey: ['getBookingDesktopApiV4ItemBookingGetDeploymentItemIdGet']
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

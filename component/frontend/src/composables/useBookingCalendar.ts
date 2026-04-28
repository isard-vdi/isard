import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import {
  getUserBookingsOptions,
  getBookingDesktopOptions,
  getBookingDeploymentOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { toCalendarEvents } from '@/lib/booking/adapter'
import type { BookingItemType, BookingReturnType } from '@/lib/booking/constants'

export interface DateRange {
  start: string
  end: string
}

export function useBookingsSummary(range: MaybeRefOrGetter<DateRange>) {
  const query = useQuery(
    computed(() =>
      getUserBookingsOptions({
        query: {
          startDate: toValue(range).start,
          endDate: toValue(range).end
        }
      })
    )
  )
  const events = computed(() => toCalendarEvents(query.data.value ?? []))
  return { ...query, events }
}

export function useItemBookings(
  itemType: MaybeRefOrGetter<Exclude<BookingItemType, 'all'>>,
  itemId: MaybeRefOrGetter<string>,
  range: MaybeRefOrGetter<DateRange>,
  returnType: MaybeRefOrGetter<BookingReturnType> = () => 'all'
) {
  const query = useQuery(
    computed(() => {
      const id = toValue(itemId)
      const r = toValue(range)
      const ret = toValue(returnType)
      const opts = {
        path: { item_id: id },
        query: { startDate: r.start, endDate: r.end, returnType: ret }
      }
      return toValue(itemType) === 'desktop'
        ? getBookingDesktopOptions(opts)
        : getBookingDeploymentOptions(opts)
    })
  )
  const events = computed(() => toCalendarEvents(query.data.value ?? []))
  return { ...query, events }
}

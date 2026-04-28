import { computed, type Ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'

import {
  getReservablesOptions,
  getReservableItemsOptions,
  listEnabledSubitemsOptions,
  getItemPlansOptions
} from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { ApiReservableItem, ApiSubitem, ApiPlan } from '@/lib/planning/adapter'
import { toPlanCalendarEvents } from '@/lib/planning/adapter'
import type { CalendarEvent } from '@/lib/booking/adapter'

export function useReservableTypes() {
  const query = useQuery(getReservablesOptions())
  const types = computed<string[]>(() => query.data.value?.reservables ?? [])
  return { types, isLoading: query.isLoading, isError: query.isError }
}

export function useReservableItems(reservableType: Ref<string>) {
  const query = useQuery(
    computed(() => ({
      ...getReservableItemsOptions({
        path: { reservable_type: reservableType.value }
      }),
      enabled: !!reservableType.value
    }))
  )
  const items = computed<ApiReservableItem[]>(
    () => (query.data.value?.items as ApiReservableItem[] | undefined) ?? []
  )
  return { items, isLoading: query.isLoading, isError: query.isError }
}

export function useReservableSubitems(reservableType: Ref<string>, itemId: Ref<string>) {
  const query = useQuery(
    computed(() => ({
      ...listEnabledSubitemsOptions({
        path: { reservable_type: reservableType.value, item_id: itemId.value }
      }),
      enabled: !!reservableType.value && !!itemId.value
    }))
  )
  const subitems = computed<ApiSubitem[]>(
    () => (query.data.value as ApiSubitem[] | undefined) ?? []
  )
  return { subitems, isLoading: query.isLoading, isError: query.isError }
}

export function useItemPlans(itemId: Ref<string>, range: Ref<{ start: string; end: string }>) {
  const query = useQuery(
    computed(() => ({
      ...getItemPlansOptions({
        path: { item_id: itemId.value }
      }),
      enabled: !!itemId.value
    }))
  )
  const plans = computed<ApiPlan[]>(() => (query.data.value as ApiPlan[] | undefined) ?? [])
  const events = computed<CalendarEvent[]>(() => {
    const filtered = plans.value.filter((plan) => {
      const planStart = new Date(plan.start)
      const planEnd = new Date(plan.end)
      const rangeStart = new Date(range.value.start)
      const rangeEnd = new Date(range.value.end)
      return planStart < rangeEnd && planEnd > rangeStart
    })
    return toPlanCalendarEvents(filtered)
  })
  return { plans, events, isLoading: query.isLoading, isError: query.isError }
}

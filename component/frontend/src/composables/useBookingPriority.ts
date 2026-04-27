import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { getBookingPriorityDesktopOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { parsePriority } from '@/lib/booking/adapter'

export function useBookingPriority(itemId: MaybeRefOrGetter<string | null>) {
  const query = useQuery(
    computed(() => ({
      ...getBookingPriorityDesktopOptions({
        path: { item_id: toValue(itemId) ?? '' }
      }),
      enabled: Boolean(toValue(itemId))
    }))
  )

  const priority = computed(() => {
    const raw = query.data.value
    return raw
      ? parsePriority(raw as { forbid_time?: number; max_time?: number; max_items?: number })
      : { forbidTime: 0, maxTime: 0, maxItems: 0 }
  })

  const itemName = computed(() => (query.data.value as { name?: string } | undefined)?.name ?? '')

  return { ...query, priority, itemName }
}

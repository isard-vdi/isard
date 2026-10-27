import { computed, onScopeDispose, reactive, toValue, watchEffect } from 'vue'
import type { MaybeRefOrGetter } from 'vue'

const lifts = reactive(new Map<symbol, number>())

export const floatingCornerLift = computed(() => Math.max(0, ...lifts.values()))

export function useFloatingCornerLift(lift: MaybeRefOrGetter<number>) {
  const key = Symbol('floating-corner-lift')

  watchEffect(() => {
    const value = toValue(lift)
    if (value > 0) lifts.set(key, value)
    else lifts.delete(key)
  })

  onScopeDispose(() => lifts.delete(key))
}

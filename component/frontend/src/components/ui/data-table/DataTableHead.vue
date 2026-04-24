<script setup lang="ts">
import { computed } from 'vue'
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

import { Button } from '@/components/ui/button'

interface Props {
  sortable?: boolean
  sorted?: 'asc' | 'desc' | false
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  sortable: false,
  sorted: false
})

const emit = defineEmits<{
  togleSorting: []
}>()

const sortButtonIcon = computed(() => {
  switch (props.sorted) {
    case 'asc':
      return 'chevron-up'
    case 'desc':
      return 'chevron-down'
    default:
      return 'chevron-selector-vertical'
  }
})
</script>

<template>
  <div
    :class="
      cn(
        'h-10 px-2',
        'flex items-center justify-start overflow-hidden',
        'font-semibold text-gray-warm-600 text-xs',
        '[&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-0.5',
        props.class
      )
    "
  >
    <slot />
    <Button
      v-if="props.sortable"
      size="sm"
      hierarchy="link-gray"
      class="mx-1 size-4 p-0 text-current/70"
      :icon="sortButtonIcon"
      @click="emit('togleSorting')"
    />
  </div>
</template>

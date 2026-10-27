<script setup lang="ts">
import { useTemplateRef } from 'vue'
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()

const scroller = useTemplateRef<HTMLElement>('scroller')
const header = useTemplateRef<HTMLElement>('header')

const syncScrollLeft = (from: HTMLElement | null, to: HTMLElement | null) => {
  if (from && to && to.scrollLeft !== from.scrollLeft) to.scrollLeft = from.scrollLeft
}

const forwardHorizontalWheel = (event: WheelEvent) => {
  if (scroller.value && event.deltaX) scroller.value.scrollLeft += event.deltaX
}
</script>

<template>
  <div
    :class="
      cn(
        'bg-base-white border border-gray-warm-300 rounded-lg',
        'py-4 px-8 w-full',
        'flex flex-col gap-4',
        props.class
      )
    "
  >
    <div>
      <!-- Defaults to the height of the top bar in Sidebar.vue; a page with its own sticky
           toolbar sets --data-table-sticky-top to where that toolbar ends. -->
      <div
        v-if="$slots.header"
        ref="header"
        class="sticky top-[var(--data-table-sticky-top,var(--spacing-16))] z-20 overflow-hidden bg-base-white"
        @scroll="syncScrollLeft(header, scroller)"
        @wheel.passive="forwardHorizontalWheel"
      >
        <slot name="header" />
      </div>

      <div ref="scroller" class="overflow-x-auto" @scroll="syncScrollLeft(scroller, header)">
        <slot />
      </div>
    </div>

    <slot name="pagination" />
  </div>
</template>

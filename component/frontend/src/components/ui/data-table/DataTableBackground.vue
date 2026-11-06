<script setup lang="ts">
import { ref, useTemplateRef } from 'vue'
import type { HTMLAttributes } from 'vue'
import { useElementSize, useIntersectionObserver } from '@vueuse/core'
import { cn } from '@/lib/utils'
import { useFloatingCornerLift } from '@/composables/useFloatingCornerLift'

const props = defineProps<{
  class?: HTMLAttributes['class']
  stickyFooter?: boolean
}>()

const scroller = useTemplateRef<HTMLElement>('scroller')
const header = useTemplateRef<HTMLElement>('header')
const footer = useTemplateRef<HTMLElement>('footer')

const syncScrollLeft = (from: HTMLElement | null, to: HTMLElement | null) => {
  if (from && to && to.scrollLeft !== from.scrollLeft) to.scrollLeft = from.scrollLeft
}

const forwardHorizontalWheel = (event: WheelEvent) => {
  if (scroller.value && event.deltaX) scroller.value.scrollLeft += event.deltaX
}

const footerStuck = ref(false)
const { height: footerHeight } = useElementSize(footer, undefined, { box: 'border-box' })

// With the root a pixel short at the bottom, a footer stuck to the viewport's edge is never
// fully in view, while one back in its place in the page is.
useIntersectionObserver(
  () => (props.stickyFooter ? footer.value : undefined),
  ([entry]) => {
    footerStuck.value =
      !!entry &&
      entry.isIntersecting &&
      entry.intersectionRatio < 1 &&
      entry.boundingClientRect.bottom > (entry.rootBounds?.bottom ?? window.innerHeight)
  },
  { rootMargin: '0px 0px -1px 0px', threshold: [0, 1] }
)

useFloatingCornerLift(() => (props.stickyFooter && footerStuck.value ? footerHeight.value : 0))
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

    <!-- The negative margins must stay within the gap above and the padding below in both
         densities, so the footer keeps its place in the page and is only padded once stuck. -->
    <div
      v-if="$slots.pagination"
      ref="footer"
      :class="
        cn(
          props.stickyFooter && 'sticky bottom-0 z-20 -mt-2 -mb-3 bg-base-white pt-2 pb-3',
          footerStuck && 'shadow-[0_-1px_0_var(--gray-warm-200)]'
        )
      "
    >
      <slot name="pagination" />
    </div>
  </div>
</template>

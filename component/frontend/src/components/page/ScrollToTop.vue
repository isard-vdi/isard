<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useEventListener, usePreferredReducedMotion } from '@vueuse/core'
import { useI18n } from 'vue-i18n'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

const props = withDefaults(
  defineProps<{
    // Distance, in pixels, the page has to travel before the button shows up. It defaults to
    // zero so that short pages, which only scroll a hundred pixels or so, still offer the way back.
    threshold?: number
    // The button does not place itself: the caller owns the floating corner it lives in.
    class?: HTMLAttributes['class']
  }>(),
  { threshold: 0, class: undefined }
)

const { t } = useI18n()
const route = useRoute()

const reducedMotion = usePreferredReducedMotion()
const behavior = computed<ScrollBehavior>(() =>
  reducedMotion.value === 'reduce' ? 'auto' : 'smooth'
)

const visible = ref(false)

function refresh() {
  visible.value = window.scrollY > props.threshold
}

useEventListener('scroll', refresh, { passive: true })

// A shorter page clamps the scroll position on its own, and browsers do not always report that
// as a scroll event, so the new view is measured once it has rendered.
watch(
  () => route.fullPath,
  () => nextTick(refresh)
)

onMounted(refresh)

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: behavior.value })
}
</script>

<template>
  <TooltipProvider>
    <Tooltip>
      <TooltipTrigger as-child>
        <!-- Fading in place, rather than mounting on demand, keeps the tooltip anchored to a
             trigger that is always there. -->
        <Button
          hierarchy="secondary-color"
          icon="arrow-up"
          icon-size="lg"
          :class="
            cn(
              'pointer-events-auto size-12 rounded-full p-0 shadow-xl transition duration-200 print:hidden',
              !visible && 'pointer-events-none translate-y-2 opacity-0',
              props.class
            )
          "
          :aria-label="t('components.scroll-to-top.label')"
          :aria-hidden="!visible"
          :tabindex="visible ? undefined : -1"
          @click="scrollToTop"
        />
      </TooltipTrigger>
      <TooltipContent side="left" :title="t('components.scroll-to-top.label')" />
    </Tooltip>
  </TooltipProvider>
</template>

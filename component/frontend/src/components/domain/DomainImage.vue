<script setup lang="ts">
import { computed, ref, watch, type HTMLAttributes } from 'vue'

import thingsUrl from '@/assets/img/things.svg'
import { cn } from '@/lib/utils'

interface Props {
  imageUrl?: string | null
  // `card` fills a card's image area; `compact` fits a list or table thumbnail.
  variant?: 'card' | 'compact'
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  imageUrl: undefined,
  variant: 'card',
  class: undefined
})

// A domain whose image 404s (a card id that lost its extension, a url that
// does not match its id, a user card whose file is gone) painted nothing, so
// the box read as broken wherever it appeared. This is an <img> rather than
// the background-image the call sites used before because only an element
// load reports the failure.
const failed = ref(false)

watch(
  () => props.imageUrl,
  () => (failed.value = false)
)

const showFallback = computed(() => !props.imageUrl || failed.value)

const markClass = computed(() =>
  props.variant === 'card' ? 'min-w-30 max-w-40' : 'w-1/2 max-w-16'
)
</script>

<template>
  <div :class="cn('relative overflow-hidden', props.class)">
    <img
      v-if="!showFallback"
      :src="props.imageUrl!"
      alt=""
      aria-hidden="true"
      draggable="false"
      class="absolute inset-0 h-full w-full object-cover object-center"
      @error="failed = true"
    />
    <div v-else class="absolute inset-0 flex items-center justify-center bg-brand-700">
      <img :src="thingsUrl" alt="" aria-hidden="true" draggable="false" :class="markClass" />
    </div>
    <slot />
  </div>
</template>

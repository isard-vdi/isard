<script setup lang="ts">
import { type HTMLAttributes } from 'vue'
import thingsUrl from '@/assets/img/things.svg'
import { cn } from '@/lib/utils'

interface Props {
  title: string
  subtitle?: string
  class?: HTMLAttributes['class']
  img?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  //   as: 'button'
  img: true
})
</script>

<template>
  <!-- TODO: Use figma variables -->
  <div :class="cn('flex gap-4 items-center', props.class)">
    <div class="flex gap-4 items-center min-w-0">
      <h1 class="text-gray-warm-700 text-xl sm:text-[24px] font-bold leading-8">
        {{ props.title }}
      </h1>
      <img v-if="props.img" :src="thingsUrl" alt="things" class="h-4 sm:h-6 shrink-0" />
    </div>
    <p
      v-if="props.subtitle"
      class="flex-1 min-w-40 max-md:hidden line-clamp-2 text-gray-warm-500 font-medium pt-0.5"
    >
      {{ props.subtitle }}
    </p>
  </div>
</template>

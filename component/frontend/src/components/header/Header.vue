<script setup lang="ts">
import { type HTMLAttributes } from 'vue'
import thingsUrl from '@/assets/img/things.svg'

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
  <div class="flex flex-col gap-[10px]">
    <div class="flex flex-row gap-4">
      <h1 class="text-gray-warm-700 text-xl sm:text-[24px] font-bold leading-8">
        {{ props.title }}
      </h1>
      <img v-if="props.img" :src="thingsUrl" alt="things" class="h-4 mt-2 sm:mt-0 sm:h-8" />
    </div>
    <p v-if="props.subtitle" class="hidden md:block text-gray-warm-500 font-medium">
      {{ props.subtitle }}
    </p>
  </div>
</template>

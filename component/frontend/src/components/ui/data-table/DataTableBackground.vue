<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
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
    <div class="overflow-x-scroll">
      <slot />
    </div>

    <slot name="pagination" />
  </div>
</template>

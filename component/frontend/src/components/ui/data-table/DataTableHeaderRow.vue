<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div
    :class="cn('col-span-full grid grid-cols-subgrid', 'border-b border-[#e7e5e4]', props.class)"
  >
    <slot />
  </div>
</template>

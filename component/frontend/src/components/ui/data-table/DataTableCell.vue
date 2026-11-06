<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div :class="cn('p-2', 'flex items-center justify-start overflow-hidden', props.class)">
    <slot />
  </div>
</template>

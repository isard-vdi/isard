<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div data-sidebar="footer" :class="cn('flex flex-col gap-2 m-2 overflow-hidden', props.class)">
    <slot />
  </div>
</template>

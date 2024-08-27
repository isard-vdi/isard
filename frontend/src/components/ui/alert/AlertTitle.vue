<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <h5 :class="cn('mb-[4px] text-sm font-semibold', props.class)">
    <slot />
  </h5>
</template>

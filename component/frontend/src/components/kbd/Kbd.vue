<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{ class?: HTMLAttributes['class'] }>()
</script>

<template>
  <kbd
    :class="
      cn(
        'rounded border border-gray-warm-300 px-1.5 py-0.5 text-xs font-medium text-gray-warm-500',
        props.class
      )
    "
  >
    <slot />
  </kbd>
</template>

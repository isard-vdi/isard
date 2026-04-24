<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div
    data-sidebar="content"
    :class="
      cn(
        'flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overflow-x-hidden group-data-[collapsible=icon]:overflow-x-hidden',
        props.class
      )
    "
  >
    <slot />
  </div>
</template>

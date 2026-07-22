<script setup lang="ts">
import { Icon } from '@/components/icon'
import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'vue'

const props = defineProps<{
  icon: string
  content?: string | number
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <div
    :class="
      cn(
        `
        gap-1 px-3.75 py-0.5
        inline-flex items-center
        border border-gray-warm-300 rounded-lg
        bg-base-white 
        text-lg text-gray-warm-700 font-medium
        transition-colors focus:outline-hidden focus:ring-2 focus:ring-ring focus:ring-offset-2
        `,
        props.class
      )
    "
  >
    <Icon :name="props.icon" size="sm" />
    <span v-if="props.content != undefined">{{ props.content }}</span>
  </div>
</template>

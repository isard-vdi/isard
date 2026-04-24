<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
  destructive?: boolean
  disabled?: boolean
}>()
</script>

<template>
  <div
    data-slot="input-group"
    role="group"
    :class="
      cn(
        'w-full rounded-md border border-gray-warm-300 px-3 py-2',
        'bg-background text-4 leading-6 ring-offset-background',
        'shadow-[0px_1px_2px_0px_rgba(16,24,40,0.05)]',
        'placeholder:text-muted-foreground',
        'group/input-group dark:bg-input/30 relative flex items-center transition-[color,box-shadow]',
        'h-10 min-w-0 has-[>textarea]:h-auto',

        // Variants based on alignment.
        'has-[>[data-align=inline-start]]:[&>input]:pl-2',
        'has-[>[data-align=inline-end]]:[&>input]:pr-2',
        'has-[>[data-align=block-start]]:h-auto has-[>[data-align=block-start]]:flex-col has-[>[data-align=block-start]]:[&>input]:pb-3',
        'has-[>[data-align=block-end]]:h-auto has-[>[data-align=block-end]]:flex-col has-[>[data-align=block-end]]:[&>input]:pt-3',

        // Focus state with focus-within
        'focus-within:outline-hidden focus-within:ring-sm focus-within:ring-offset-0 focus-within:ring-4',
        'focus-within:border-secondary-3-400 focus-within:ring-brand',

        // Destructive state
        props.destructive && 'focus-within:border-error-300 focus-within:ring-error-200',
        props.destructive && 'border-error-300',

        // Disabled state
        props.disabled && ' bg-gray-warm-100',

        props.class
      )
    "
  >
    <slot />
  </div>
</template>

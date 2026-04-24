<script lang="ts" setup>
import type { CalendarCellTriggerProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { CalendarCellTrigger, useForwardProps } from 'reka-ui'
import { cn } from '@/lib/utils'

const props = withDefaults(
  defineProps<CalendarCellTriggerProps & { class?: HTMLAttributes['class'] }>(),
  {
    as: 'button'
  }
)

const delegatedProps = reactiveOmit(props, 'class')

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <CalendarCellTrigger
    data-slot="calendar-cell-trigger"
    :class="
      cn(
        // Base styles
        'w-10 h-10 p-0 font-normal cursor-default rounded-[20px] transition-all relative',

        // Default state (current month, not selected, not today)
        'text-gray-warm-700',
        'hover:bg-gray-warm-200',
        'focus-visible:ring-2 focus-visible:ring-gray-warm-100 focus-visible:ring-offset-0 focus-visible:outline-none',

        // Selected state
        'data-[selected]:bg-brand-700',
        'data-[selected]:text-base-white',
        'data-[selected]:font-medium',
        'data-[selected]:hover:bg-brand-800',
        'data-[selected]:focus-visible:ring-2',
        'data-[selected]:focus-visible:ring-gray-warm-100',

        // Today state (not selected) - styled like selected but with different background
        '[&[data-today]:not([data-selected])]:bg-brand-100',
        '[&[data-today]:not([data-selected])]:text-gray-warm-700',
        '[&[data-today]:not([data-selected])]:font-medium',
        '[&[data-today]:not([data-selected])]:hover:bg-brand-200',
        '[&[data-today]:not([data-selected])]:focus-visible:ring-2',
        '[&[data-today]:not([data-selected])]:focus-visible:ring-gray-warm-100',

        // Outside view (other months)
        'data-[outside-view]:text-gray-warm-400',

        // Disabled state
        'data-[disabled]:text-gray-warm-500',
        'data-[disabled]:cursor-not-allowed',

        // Unavailable state
        'data-[unavailable]:text-gray-warm-500',
        'data-[unavailable]:line-through',

        props.class
      )
    "
    v-bind="forwardedProps"
  >
    <slot />
  </CalendarCellTrigger>
</template>

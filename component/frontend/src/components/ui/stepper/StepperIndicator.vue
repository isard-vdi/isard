<script lang="ts" setup>
import type { StepperIndicatorProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { StepperIndicator, useForwardProps } from 'reka-ui'
import { cn } from '@/lib/utils'

const props = defineProps<StepperIndicatorProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')

const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <StepperIndicator
    v-slot="slotProps"
    v-bind="forwarded"
    :class="
      cn(
        // Default
        'inline-flex items-center justify-center rounded-full text-xl w-12 h-12 transition-colors duration-500 ease-in-out',
        'bg-gray-warm-200 text-gray-warm-500 font-normal',
        // Disabled
        'group-data-[disabled]:text-muted-foreground group-data-[disabled]:text-gray-warm-400',
        // Active
        'group-data-[state=active]:bg-secondary-2-500 group-data-[state=active]:text-base-white group-data-[state=active]:font-bold',
        // Completed
        'group-data-[state=completed]:bg-success-500 group-data-[state=completed]:text-base-white group-data-[state=completed]:font-bold',
        props.class
      )
    "
  >
    <slot v-bind="slotProps" />
  </StepperIndicator>
</template>

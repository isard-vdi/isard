<script lang="ts" setup>
import type { StepperTitleProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { StepperTitle, useForwardProps } from 'reka-ui'
import { cn } from '@/lib/utils'

const props = defineProps<StepperTitleProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')

const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <StepperTitle
    v-bind="forwarded"
    :class="
      cn(
        'font-bold text-sm whitespace-nowrap mt-1 text-center',
        // Completed
        'group-data-[state=completed]:text-success-800 ',
        // Active
        'group-data-[state=active]:text-gray-warm-800',
        // Disabled
        'group-data-disabled:text-gray-warm-500',
        props.class
      )
    "
  >
    <slot />
  </StepperTitle>
</template>

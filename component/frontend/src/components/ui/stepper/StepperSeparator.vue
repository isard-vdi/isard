<script lang="ts" setup>
import type { StepperSeparatorProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { StepperSeparator, useForwardProps } from 'reka-ui'
import { cn } from '@/lib/utils'

const props = defineProps<StepperSeparatorProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')

const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <StepperSeparator
    v-bind="forwarded"
    :class="
      cn(
        'flex-1 h-1 rounded-3xl bg-gray-warm-200 transition-colors duration-500 ease-in-out mx-2',
        // Active
        'group-data-[state=active]:bg-[linear-gradient(to_right,theme(colors.secondary-2.500)_0%,theme(colors.secondary-2.500)_50%,theme(colors.gray-warm.200)_50%,theme(colors.gray-warm.200)_100%)]',
        // Completed
        'group-data-[state=completed]:bg-success-500',
        props.class
      )
    "
  />
</template>

<script setup lang="ts">
import type { SelectTriggerProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { ChevronDown } from 'lucide-vue-next'
import { SelectIcon, SelectTrigger, useForwardProps } from 'reka-ui'
import { selectTriggerVariants, type SelectTriggerVariants } from '.'
import { cn } from '@/lib/utils'

const props = defineProps<
  SelectTriggerProps & {
    hierarchy?: SelectTriggerVariants
    class?: HTMLAttributes['class']
    size?: 'default'
  }
>()

const delegatedProps = reactiveOmit(props, 'class', 'size')
const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <SelectTrigger
    data-slot="select-trigger"
    :data-size="size"
    v-bind="forwardedProps"
    :class="cn(selectTriggerVariants({ hierarchy: props.hierarchy }), props.class)"
  >
    <slot />
    <SelectIcon as-child>
      <ChevronDown class="w-4 h-4 text-gray-warm-500" />
    </SelectIcon>
  </SelectTrigger>
</template>

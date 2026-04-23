<script setup lang="ts">
import type { DropdownMenuSubTriggerProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { ChevronRight } from 'lucide-vue-next'
import { DropdownMenuSubTrigger, useForwardProps } from 'reka-ui'
import { cn } from '@/lib/utils'
import { Icon } from '@/components/icon'

const props = defineProps<DropdownMenuSubTriggerProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <DropdownMenuSubTrigger
    v-bind="forwardedProps"
    :class="
      cn(
        'flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none focus:bg-accent data-[state=open]:bg-accent',
        props.class
      )
    "
  >
    <slot />
    <Icon name="chevron-right" class="ml-auto size-4 shrink-0" />
  </DropdownMenuSubTrigger>
</template>

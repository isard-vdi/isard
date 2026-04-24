<script setup lang="ts">
import type { ContextMenuItemEmits, ContextMenuItemProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { ContextMenuItem, useForwardPropsEmits } from 'reka-ui'
import { cn } from '@/lib/utils'

const props = withDefaults(
  defineProps<
    ContextMenuItemProps & {
      class?: HTMLAttributes['class']
      inset?: boolean
      variant?: 'default' | 'destructive'
    }
  >(),
  {
    variant: 'default'
  }
)
const emits = defineEmits<ContextMenuItemEmits>()

const delegatedProps = reactiveOmit(props, 'class')

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <ContextMenuItem
    data-slot="context-menu-item"
    :data-inset="inset ? '' : undefined"
    :data-variant="variant"
    v-bind="forwarded"
    :class="
      cn(
        `focus:bg-accent focus:underline
        data-[variant=destructive]:text-error-600 data-[variant=destructive]:focus:bg-error-400/20 dark:data-[variant=destructive]:focus:bg-error-400/40 data-[variant=destructive]:focus:text-error-700 data-[variant=destructive]:*:[svg]:!text-error-700
        [&_svg:not([class*=\'text-\'])]:text-gray-warm-700 relative flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-hidden select-none font-medium text-gray-warm-600
        data-[disabled]:pointer-events-none data-[disabled]:opacity-50
        data-[inset]:pl-8
        [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*=\'size-\'])]:size-4`,
        props.class
      )
    "
  >
    <slot />
  </ContextMenuItem>
</template>

<script setup lang="ts">
import type { DropdownMenuSubContentEmits, DropdownMenuSubContentProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { DropdownMenuSubContent, useForwardPropsEmits } from 'reka-ui'
import { cn } from '@/lib/utils'

// Both offsets undo the 5px (p-1 plus border) that insets a menu's items from
// its box: the sub trigger this anchors on, and this menu's own first item.
// Without them the submenu opens over the menu that spawned it, with its first
// option sitting below the row that opened it. The extra 4 is the gap a
// top-level menu leaves.
const props = withDefaults(
  defineProps<DropdownMenuSubContentProps & { class?: HTMLAttributes['class'] }>(),
  { sideOffset: 9, alignOffset: -5 }
)
const emits = defineEmits<DropdownMenuSubContentEmits>()

const delegatedProps = reactiveOmit(props, 'class')

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <DropdownMenuSubContent
    v-bind="forwarded"
    :class="
      cn(
        'z-50 min-w-32 overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2',
        props.class
      )
    "
  >
    <slot />
  </DropdownMenuSubContent>
</template>

<script setup lang="ts">
import { type HTMLAttributes, computed } from 'vue'
import {
  SelectItem,
  SelectItemIndicator,
  type SelectItemProps,
  SelectItemText,
  useForwardProps
} from 'radix-vue'
import { Check } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

const props = defineProps<SelectItemProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props

  return delegated
})

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <SelectItem
    v-bind="forwardedProps"
    :class="
      cn(
        `relative flex w-full cursor-default select-none items-center
	rounded-sm py-1.5 p-[10px]
	text-md text-gray-warm-900 font-medium outline-none
	hover:cursor-pointer hover:bg-brand-100
	focus:bg-brand-100
	data-[disabled]:pointer-events-none data-[disabled]:opacity-50`,
        props.class
      )
    "
  >
    <SelectItemText>
      <slot />
    </SelectItemText>

    <span class="absolute right-2 flex h-3.5 w-3.5 items-center justify-center">
      <SelectItemIndicator>
        <Check class="h-4 w-4 text-brand-700" />
      </SelectItemIndicator>
    </span>
  </SelectItem>
</template>

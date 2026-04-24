<script setup lang="ts">
import type { VariantProps } from 'class-variance-authority'
import type { ToggleGroupRootProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import type { toggleVariants } from '@/components/ui/toggle'
import { reactiveOmit } from '@vueuse/core'
import { ToggleGroupRoot, useForwardProps } from 'reka-ui'
import { provide } from 'vue'
import { cn } from '@/lib/utils'

type ToggleGroupVariants = VariantProps<typeof toggleVariants>

const props = withDefaults(
  defineProps<
    ToggleGroupRootProps & {
      class?: HTMLAttributes['class']
      variant?: ToggleGroupVariants['variant']
      size?: ToggleGroupVariants['size']
      spacing?: number
    }
  >(),
  {
    type: 'single',
    spacing: 0
  }
)

const modelValue = defineModel<string | string[]>()

provide('toggleGroup', {
  variant: props.variant,
  size: props.size,
  spacing: props.spacing
})

const delegatedProps = reactiveOmit(props, 'class', 'size', 'variant', 'modelValue')
const forwardedProps = useForwardProps(delegatedProps)

function onUpdateModelValue(value: string | string[]) {
  if (props.type === 'single') {
    if (value !== undefined && value !== '') {
      modelValue.value = value
    }
  } else {
    if (Array.isArray(value) && value.length > 0) {
      modelValue.value = value
    }
  }
}
</script>

<template>
  <ToggleGroupRoot
    v-slot="slotProps"
    data-slot="toggle-group"
    :data-size="size"
    :data-variant="variant"
    :data-spacing="spacing"
    :style="{
      '--gap': spacing
    }"
    v-bind="forwardedProps"
    :model-value="modelValue"
    :class="
      cn(
        'group/toggle-group flex w-fit items-center gap-[--spacing(var(--gap))] rounded-md data-[spacing=default]:data-[variant=outline]:shadow-xs',
        props.class
      )
    "
    @update:model-value="onUpdateModelValue"
  >
    <slot v-bind="slotProps" />
  </ToggleGroupRoot>
</template>

<script setup lang="ts">
import type { SeparatorProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { Separator } from 'reka-ui'
import { cn } from '@/lib/utils'

interface Props extends SeparatorProps {
  class?: HTMLAttributes['class']
  label?: string
  color?: string
}
const props = withDefaults(defineProps<Props & { class?: HTMLAttributes['class'] }>(), {
  orientation: 'horizontal',
  decorative: true,
  color: 'gray-warm-200'
})

const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <Separator
    data-slot="separator-root"
    v-bind="delegatedProps"
    :class="
      cn(
        'relative flex items-center',
        props.orientation === 'horizontal' ? 'h-px w-full' : 'w-px h-full',
        props.class
      )
    "
  >
    <div
      :class="
        cn(
          `grow bg-${props.color}`,
          props.orientation === 'vertical' ? 'w-px h-full' : 'h-px w-full'
        )
      "
      :style="{
        backgroundColor: `var(--${props.color})`
      }"
    ></div>
    <span
      v-if="props.label || $slots.default"
      :class="
        cn(
          'text-xs text-muted-foreground z-10 whitespace-nowrap',
          props.orientation === 'vertical' ? 'py-1' : 'px-2',
          !$slots.default && 'bg-background'
        )
      "
    >
      <slot>{{ props.label }}</slot>
    </span>
    <div
      :class="
        cn(
          `grow bg-${props.color}`,
          props.orientation === 'vertical' ? 'w-px h-full' : 'h-px w-full'
        )
      "
      :style="{
        backgroundColor: `var(--${props.color})`
      }"
    ></div>
  </Separator>
</template>

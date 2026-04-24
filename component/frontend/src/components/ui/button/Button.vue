<script setup lang="ts">
import type { PrimitiveProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import type { ButtonVariants } from '.'
import { Primitive } from 'reka-ui'
import { cn } from '@/lib/utils'
import { buttonVariants } from '.'
import { Icon, type IconVariants } from '@/components/icon'

interface Props extends PrimitiveProps {
  hierarchy?: ButtonVariants['hierarchy']
  size?: ButtonVariants['size']
  icon?: string
  class?: HTMLAttributes['class']
  iconSize?: IconVariants['size']
  iconFillColor?: string
  iconStrokeColor?: string
  iconClass?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  as: 'button',
  iconStrokeColor: 'currentColor'
})
</script>

<template>
  <Primitive
    data-slot="button"
    :as="as"
    :as-child="asChild"
    :class="cn(buttonVariants({ hierarchy, size }), props.class)"
  >
    <Icon
      v-if="props.icon"
      :key="props.icon"
      :name="props.icon"
      :size="props.iconSize"
      :fill-color="props.iconFillColor"
      :stroke-color="props.iconStrokeColor"
      :class="props.iconClass"
    />
    <slot />
  </Primitive>
</template>
